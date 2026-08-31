import httpx
import pytest

from app.config import Settings
from app.core.errors import AuthError
from app.llm.openai_compat import OpenAICompatProvider


def _provider(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://api.example.com/v1")
    settings = Settings(base_url="https://api.example.com/v1", api_key="sk-test-not-real", model="test-model")
    return OpenAICompatProvider(settings, client=client)


@pytest.mark.asyncio
async def test_generate_returns_parsed_json():
    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"host": "H"}'}}]})

    p = _provider(handler)
    out = await p.generate("roster", "sys", "user")
    assert out == {"host": "H"}


@pytest.mark.asyncio
async def test_natural_language_utterance_preserves_real_model_text():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "这是一个有证据支撑的真实观点。"}}]})

    p = _provider(handler)
    assert await p.generate("utterance", "sys", "user") == {
        "text": "这是一个有证据支撑的真实观点。"
    }


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_parsed():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "```json\n{\"text\":\"你好\"}\n```"}}]})

    p = _provider(handler)
    assert await p.generate("host", "sys", "user") == {"text": "你好"}


@pytest.mark.asyncio
async def test_401_raises_auth_error():
    def handler(request):
        return httpx.Response(401, json={"error": "unauthorized"})

    p = _provider(handler)
    with pytest.raises(AuthError):
        await p.generate("roster", "sys", "user")
