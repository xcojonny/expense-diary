"""Unit tests for the vision-LLM adapter and provider resolution.

These cover the observability/robustness fixes: the adapter must surface the
provider's own error text (so a misconfigured key/model is diagnosable), tolerate
odd response shapes, and the resolver must not silently degrade to the no-op when
a provider *was* configured."""

import httpx
import pytest

from app.core.config import Settings
from app.integrations.llm import get_vision_llm
from app.integrations.llm.null import NullVisionLLM
from app.integrations.llm.openai_compatible import LLMError, OpenAICompatibleVisionLLM

PROMPT = "extract"
IMG = b"\xff\xd8\xff\x00fake-jpeg-bytes"


def _adapter() -> OpenAICompatibleVisionLLM:
    return OpenAICompatibleVisionLLM(
        base_url="https://example.test/v1", model="test-model", api_key="k", timeout=5.0
    )


def _mock_client(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Route the adapter's internal httpx client through a MockTransport."""
    real = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("timeout", None)
        return real(transport=httpx.MockTransport(handler), timeout=5.0)

    monkeypatch.setattr("app.integrations.llm.openai_compatible.httpx.AsyncClient", factory)


async def test_extract_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok": true}'}}]}
        )

    _mock_client(monkeypatch, handler)
    out = await _adapter().extract(image_bytes=IMG, media_type="image/jpeg", prompt=PROMPT)
    assert out == '{"ok": true}'


async def test_http_error_includes_provider_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    _mock_client(monkeypatch, handler)
    with pytest.raises(LLMError) as exc:
        await _adapter().extract(image_bytes=IMG, media_type="image/jpeg", prompt=PROMPT)
    # The provider's own message must reach the error (→ receipt.error + logs).
    assert "401" in str(exc.value)
    assert "invalid api key" in str(exc.value)


async def test_empty_choices_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    _mock_client(monkeypatch, handler)
    with pytest.raises(LLMError):
        await _adapter().extract(image_bytes=IMG, media_type="image/jpeg", prompt=PROMPT)


async def test_timeout_raises_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=req)

    _mock_client(monkeypatch, handler)
    with pytest.raises(LLMError) as exc:
        await _adapter().extract(image_bytes=IMG, media_type="image/jpeg", prompt=PROMPT)
    assert "Zeit" in str(exc.value)  # "Zeitüberschreitung"


def test_content_of_tolerates_bad_shapes() -> None:
    of = OpenAICompatibleVisionLLM._content_of
    assert of({"choices": [{"message": {"content": "x"}}]}) == "x"
    assert of({}) is None
    assert of({"choices": []}) is None
    assert of({"choices": [{"message": {"content": None}}]}) is None
    assert of("not-a-dict") is None


def test_resolver_uses_openai_compatible_when_configured() -> None:
    settings = Settings(llm_provider="openai", llm_model="gpt-4o-mini")
    assert isinstance(get_vision_llm(settings), OpenAICompatibleVisionLLM)


def test_resolver_none_is_null() -> None:
    settings = Settings(llm_provider="none")
    assert isinstance(get_vision_llm(settings), NullVisionLLM)


def test_resolver_unknown_provider_falls_back_to_null() -> None:
    # e.g. someone sets LLM_PROVIDER=openrouter — not one of the supported names.
    settings = Settings(llm_provider="openrouter", llm_model="openai/gpt-4o-mini")
    assert isinstance(get_vision_llm(settings), NullVisionLLM)
