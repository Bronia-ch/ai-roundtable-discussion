import pytest

from app.core.errors import AuthError, SchemaError, classify_error
from app.llm.reliability import call_with_retry


@pytest.mark.asyncio
async def test_retry_on_recoverable():
    attempts = []

    async def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError()
        return "ok"

    result = await call_with_retry(fn, classify=classify_error, max_retries=3, base_delay=0.001)
    assert result == "ok"
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_no_retry_on_auth():
    attempts = []

    async def fn():
        attempts.append(1)
        raise AuthError()

    with pytest.raises(AuthError):
        await call_with_retry(fn, classify=classify_error, max_retries=3, base_delay=0.001)
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_no_retry_on_schema():
    attempts = []

    async def fn():
        attempts.append(1)
        raise SchemaError()

    with pytest.raises(SchemaError):
        await call_with_retry(fn, classify=classify_error, max_retries=3, base_delay=0.001)
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_exhausted_raises():
    async def fn():
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        await call_with_retry(fn, classify=classify_error, max_retries=2, base_delay=0.001)
