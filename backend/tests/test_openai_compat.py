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
async def test_401_raises_auth_error():
    def handler(request):
        return httpx.Response(401, json={"error": "unauthorized"})

    p = _provider(handler)
    with pytest.raises(AuthError):
        await p.generate("roster", "sys", "user")
