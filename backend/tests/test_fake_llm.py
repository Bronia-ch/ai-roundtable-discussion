import inspect

import pytest

from app.llm.fake import FakeLLMProvider, ScriptedLLMProvider


@pytest.mark.asyncio
async def test_scripted_returns_preset():
    llm = ScriptedLLMProvider({"roster": {"host": "H", "experts": []}})
    out = await llm.generate("roster", "sys", "user")
    assert out == {"host": "H", "experts": []}


@pytest.mark.asyncio
async def test_scripted_missing_key_raises():
    llm = ScriptedLLMProvider({})
    with pytest.raises(KeyError):
        await llm.generate("roster", "sys", "user")


@pytest.mark.asyncio
async def test_fake_returns_dict_without_network():
    out = await FakeLLMProvider().generate("intent", "s", "u")
    assert isinstance(out, dict)


def test_fake_module_has_no_network_dependency():
    import app.llm.fake as fake_mod

    src = inspect.getsource(fake_mod)
    for forbidden in ("httpx", "requests", "urllib", "socket", "http"):
        assert forbidden not in src, f"fake module references {forbidden}"
