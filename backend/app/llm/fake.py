from typing import Any


class ScriptedLLMProvider:
    """按 call_type 返回预设脚本响应。不访问网络、不读取密钥。"""

    def __init__(self, script: dict[str, Any]):
        self.script = script

    async def generate(self, call_type: str, system: str, user: str) -> dict[str, Any]:
        if call_type not in self.script:
            raise KeyError(call_type)
        return self.script[call_type]


class FakeLLMProvider:
    """返回占位响应。从不访问网络、从不读取密钥。"""

    async def generate(self, call_type: str, system: str, user: str) -> dict[str, Any]:
        return {"_fake": True, "call_type": call_type}
