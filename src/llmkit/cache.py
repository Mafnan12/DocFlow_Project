import hashlib
import json
from pathlib import Path
from typing import Any

from llmkit.models import ImagePart


def compute_cache_key(
    role: str,
    model_id: str,
    messages: list[dict[str, Any]],
    schema_name: str,
    images: list[ImagePart] | None = None,
) -> str:
    """Compute a deterministic SHA-256 cache key.

    Crucially, image raw bytes are NEVER stored directly in the key;
    instead, a SHA-256 digest of each image's content is computed.
    """
    hasher = hashlib.sha256()
    hasher.update(role.encode("utf-8"))
    hasher.update(model_id.encode("utf-8"))
    hasher.update(schema_name.encode("utf-8"))

    # Hash message history
    serialized_messages = json.dumps(messages, sort_keys=True)
    hasher.update(serialized_messages.encode("utf-8"))

    # Hash image contents if present
    if images:
        for idx, img in enumerate(images):
            img_hash = hashlib.sha256(img.data).hexdigest()
            hasher.update(f"img_{idx}_{img.mime_type}_{img_hash}".encode())

    return hasher.hexdigest()


class DiskLLMCache:
    """Persistent filesystem cache for LLM structured extraction results."""

    def __init__(self, cache_dir: str | Path = ".cache/llm", enabled: bool = True):
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, cache_key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        file_path = self.cache_dir / f"{cache_key}.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def set(self, cache_key: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        file_path = self.cache_dir / f"{cache_key}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
        except Exception:
            pass
