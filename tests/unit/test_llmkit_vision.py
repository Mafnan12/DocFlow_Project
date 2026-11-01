from typing import Any

import pytest
from llmkit.cache import DiskLLMCache
from llmkit.client import LLMClient, RateLimitError
from llmkit.models import ImagePart
from pydantic import BaseModel


class DummyExtraction(BaseModel):
    vendor: str
    total: str


@pytest.mark.asyncio
async def test_image_message_built_correctly(tmp_path):
    received_payload: list[dict[str, Any]] = []

    async def mock_provider(model_id, messages, schema, temperature, timeout):
        nonlocal received_payload
        received_payload = messages
        return {"vendor": "Kopi Corner", "total": "45.00"}, 100, 20

    cache = DiskLLMCache(cache_dir=tmp_path / "cache")
    client = LLMClient(cache=cache, provider_caller=mock_provider)

    sample_img = ImagePart(data=b"fake_png_binary_bytes_12345", mime_type="image/png")
    messages = [{"role": "user", "content": "Extract total"}]

    result = await client.structured(
        role="vision",
        messages=messages,
        schema=DummyExtraction,
        images=[sample_img],
    )

    assert result.data.vendor == "Kopi Corner"
    assert result.data.total == "45.00"
    assert result.image_count == 1
    assert result.cached is False

    # Check that mocked provider received standard multimodal parts
    assert len(received_payload) == 1
    content_list = received_payload[0]["content"]
    assert isinstance(content_list, list)
    text_parts = [c for c in content_list if c.get("type") == "text"]
    img_parts = [c for c in content_list if c.get("type") == "image_url"]

    assert len(text_parts) == 1
    assert text_parts[0]["text"] == "Extract total"
    assert len(img_parts) == 1
    assert img_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_cache_hit_and_miss_with_images(tmp_path):
    call_count = 0

    async def mock_provider(model_id, messages, schema, temperature, timeout):
        nonlocal call_count
        call_count += 1
        return {"vendor": f"Vendor {call_count}", "total": "10.00"}, 50, 10

    cache = DiskLLMCache(cache_dir=tmp_path / "cache")
    client = LLMClient(cache=cache, provider_caller=mock_provider)

    img_a = ImagePart(data=b"receipt_image_A_content", mime_type="image/jpeg")
    img_b = ImagePart(data=b"receipt_image_B_different", mime_type="image/jpeg")
    messages = [{"role": "user", "content": "Extract invoice"}]

    # Call 1: Image A -> Cache miss, live provider call
    res1 = await client.structured(
        role="vision",
        messages=messages,
        schema=DummyExtraction,
        images=[img_a],
    )
    assert call_count == 1
    assert res1.cached is False
    assert res1.data.vendor == "Vendor 1"

    # Call 2: Exact same Image A + prompt -> Cache hit, call_count remains 1
    res2 = await client.structured(
        role="vision",
        messages=messages,
        schema=DummyExtraction,
        images=[img_a],
    )
    assert call_count == 1
    assert res2.cached is True
    assert res2.data.vendor == "Vendor 1"

    # Call 3: Different Image B -> Cache miss, call_count becomes 2
    res3 = await client.structured(
        role="vision",
        messages=messages,
        schema=DummyExtraction,
        images=[img_b],
    )
    assert call_count == 2
    assert res3.cached is False
    assert res3.data.vendor == "Vendor 2"


@pytest.mark.asyncio
async def test_fallback_within_vision_role_on_429(tmp_path):
    models_attempted: list[str] = []

    async def mock_provider_with_ratelimit(model_id, messages, schema, temperature, timeout):
        models_attempted.append(model_id)
        if len(models_attempted) == 1:
            # First model hits rate limit 429
            raise RateLimitError("HTTP 429: TPM quota exceeded on primary vision model")
        # Second model succeeds
        return {"vendor": "Backup Vendor", "total": "99.00"}, 120, 25

    cache = DiskLLMCache(cache_dir=tmp_path / "cache")
    client = LLMClient(cache=cache, provider_caller=mock_provider_with_ratelimit)

    # Force two models in vision role
    client.settings.llm.roles["vision"].models = [
        {"id": "gemini/gemini-1.5-flash"},
        {"id": "groq/llama-3.2-11b-vision-preview"},
    ]

    sample_img = ImagePart(data=b"image_data_for_fallback", mime_type="image/png")
    messages = [{"role": "user", "content": "Extract receipt"}]

    result = await client.structured(
        role="vision",
        messages=messages,
        schema=DummyExtraction,
        images=[sample_img],
    )

    # Assert fallback succeeded
    assert len(models_attempted) == 2
    assert models_attempted[0] == "gemini/gemini-1.5-flash"
    assert models_attempted[1] == "groq/llama-3.2-11b-vision-preview"
    assert result.model_used == "groq/llama-3.2-11b-vision-preview"
    assert result.provider_used == "groq"
    assert result.attempts == 2
    assert result.data.vendor == "Backup Vendor"
