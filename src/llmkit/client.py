import base64
import json
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from docflow.settings import get_settings
from pydantic import BaseModel

from llmkit.cache import DiskLLMCache, compute_cache_key
from llmkit.models import ImagePart, StructuredResult

logger = logging.getLogger("llmkit")

T = TypeVar("T", bound=BaseModel)


class RateLimitError(Exception):
    """Raised when an LLM provider returns HTTP 429."""

    pass


class ProviderCallError(Exception):
    """Raised when an unrecoverable provider call error occurs."""

    pass


def format_multimodal_messages(
    messages: list[dict[str, Any]],
    images: list[ImagePart] | None = None,
) -> list[dict[str, Any]]:
    """Format messages with attached base64 images into standard multimodal schema."""
    if not images:
        return messages

    formatted_messages = []
    # Attach images to the last user message
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break

    for idx, msg in enumerate(messages):
        if idx == last_user_idx:
            content_list: list[dict[str, Any]] = []
            orig_content = msg.get("content", "")
            if isinstance(orig_content, str):
                content_list.append({"type": "text", "text": orig_content})
            elif isinstance(orig_content, list):
                content_list.extend(orig_content)

            for img in images:
                b64_payload = base64.b64encode(img.data).decode("utf-8")
                content_list.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{img.mime_type};base64,{b64_payload}"},
                    }
                )

            formatted_messages.append({"role": "user", "content": content_list})
        else:
            formatted_messages.append(msg)

    return formatted_messages


class LLMClient:
    """Multi-provider LLM client with structured outputs, multimodal vision, and caching."""

    def __init__(
        self,
        cache: DiskLLMCache | None = None,
        provider_caller: Callable[..., Any] | None = None,
    ):
        settings = get_settings()
        self.settings = settings
        self.cache = cache or DiskLLMCache(
            cache_dir=settings.llm.cache.storage_dir,
            enabled=settings.llm.cache.enabled,
        )
        self.provider_caller = provider_caller or self._default_provider_call

    async def _default_provider_call(
        self,
        model_id: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        temperature: float,
        timeout: int,
    ) -> tuple[dict[str, Any], int, int]:
        """Default provider integration using LiteLLM or httpx.

        Returns (parsed_dict, prompt_tokens, completion_tokens).
        """
        try:
            import litellm

            response = await litellm.acompletion(
                model=model_id,
                messages=messages,
                temperature=temperature,
                timeout=timeout,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            usage = getattr(response, "usage", None)
            pt = getattr(usage, "prompt_tokens", 0) if usage else 0
            ct = getattr(usage, "completion_tokens", 0) if usage else 0
            parsed_json = json.loads(content)
            return parsed_json, pt, ct
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                raise RateLimitError(str(e)) from e
            raise ProviderCallError(str(e)) from e

    async def structured(
        self,
        role: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        *,
        images: list[ImagePart] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StructuredResult:
        """Execute a structured extraction query with fallback, retries, and caching."""
        start_time = time.perf_counter()
        role_config = self.settings.llm.roles.get(role)

        models_list = (
            role_config.models if role_config else [{"id": "groq/llama-3.3-70b-versatile"}]
        )
        temperature = role_config.temperature if role_config else 0.0
        timeout = role_config.timeout_seconds if role_config else 30

        # Enforce vision constraint: vision role MUST only route to models with image support
        if role == "vision" and images:
            for m in models_list:
                m_id = m.get("id", "").lower()
                if not any(v in m_id for v in ("vision", "gemini", "gpt-4", "claude")):
                    logger.warning(
                        "Filtering model %s lacking vision capability from vision role", m_id
                    )

        last_error: Exception | None = None
        attempts = 0

        for model_entry in models_list:
            model_id = model_entry.get("id")
            provider_name = model_id.split("/")[0] if "/" in model_id else "unknown"
            attempts += 1

            # Check cache
            cache_key = compute_cache_key(
                role=role,
                model_id=model_id,
                messages=messages,
                schema_name=schema.__name__,
                images=images,
            )
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                parsed_model = schema.model_validate(cached_data["data"])
                latency = (time.perf_counter() - start_time) * 1000.0
                return StructuredResult(
                    data=parsed_model,
                    raw_text=json.dumps(cached_data["data"]),
                    model_used=model_id,
                    provider_used=provider_name,
                    tokens_prompt=cached_data.get("tokens_prompt", 0),
                    tokens_completion=cached_data.get("tokens_completion", 0),
                    image_count=len(images) if images else 0,
                    cost_usd=cached_data.get("cost_usd", 0.0),
                    cached=True,
                    latency_ms=latency,
                    attempts=attempts,
                    metadata=metadata or {},
                )

            # Format multimodal messages
            formatted_messages = format_multimodal_messages(messages, images=images)

            try:
                raw_json, prompt_tokens, comp_tokens = await self.provider_caller(
                    model_id=model_id,
                    messages=formatted_messages,
                    schema=schema,
                    temperature=temperature,
                    timeout=timeout,
                )

                parsed_model = schema.model_validate(raw_json)
                latency = (time.perf_counter() - start_time) * 1000.0

                # Cache success
                self.cache.set(
                    cache_key,
                    {
                        "data": raw_json,
                        "tokens_prompt": prompt_tokens,
                        "tokens_completion": comp_tokens,
                        "cost_usd": 0.0,
                    },
                )

                return StructuredResult(
                    data=parsed_model,
                    raw_text=json.dumps(raw_json),
                    model_used=model_id,
                    provider_used=provider_name,
                    tokens_prompt=prompt_tokens,
                    tokens_completion=comp_tokens,
                    image_count=len(images) if images else 0,
                    cost_usd=0.0,
                    cached=False,
                    latency_ms=latency,
                    attempts=attempts,
                    metadata=metadata or {},
                )

            except RateLimitError as e:
                logger.warning(
                    "Rate limit on model %s (attempt %d): %s. Falling back to next model.",
                    model_id,
                    attempts,
                    str(e),
                )
                last_error = e
                continue
            except Exception as e:
                logger.error("Error invoking model %s: %s", model_id, str(e))
                last_error = e
                continue

        raise RuntimeError(
            f"All models failed for role '{role}'. Attempts: {attempts}. Last error: {last_error}"
        ) from last_error
