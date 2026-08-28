from typing import Any, Protocol


class LLMProvider(Protocol):
    async def generate(self, call_type: str, system: str, user: str) -> dict[str, Any]: ...
