from typing import Any, Literal

from pydantic import BaseModel, Field


class ImagePart(BaseModel):
    """Multimodal image payload for vision model extraction."""

    data: bytes
    mime_type: Literal["image/png", "image/jpeg"] = "image/png"


class StructuredResult(BaseModel):
    """Result of a structured LLM call with metadata and accounting."""

    data: Any  # Parsed and validated Pydantic model instance
    raw_text: str = ""
    model_used: str = ""
    provider_used: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    image_count: int = 0
    cost_usd: float | None = None
    cached: bool = False
    latency_ms: float = 0.0
    attempts: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)
