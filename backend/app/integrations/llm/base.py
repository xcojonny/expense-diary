from typing import Protocol, runtime_checkable


@runtime_checkable
class VisionLLM(Protocol):
    """Adapter interface for the receipt-extraction vision model.

    Implementations return the model's raw response text (expected to be the
    JSON described by the extraction prompt) so the pure domain parser owns all
    interpretation. Returning ``None`` means "no model available" — the caller
    then routes the receipt to ``needs_review`` instead of failing. Any real
    error (network/timeout/HTTP) is raised and handled as ``failed`` upstream.
    """

    async def extract(self, *, image_bytes: bytes, media_type: str, prompt: str) -> str | None:
        ...
