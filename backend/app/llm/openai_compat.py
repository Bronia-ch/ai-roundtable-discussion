import json
from typing import Any

import httpx

from app.config import Settings
from app.core.errors import AuthError, RateLimitError, SchemaError, UpstreamError


class OpenAICompatProvider:
    """OpenAI 兼容接口；API Key 仅来自后端环境变量（settings），不写日志、不外泄。"""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client  # 测试注入；否则惰性创建

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.settings.base_url, timeout=30.0)
        return self._client

    async def generate(self, call_type: str, system: str, user: str) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.api_key}"},
            json={
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        if resp.status_code in (401, 402):
            raise AuthError(f"鉴权失败/余额不足: {resp.status_code}")
        if resp.status_code == 429:
            raise RateLimitError("限流 429")
        if resp.status_code >= 500:
            raise UpstreamError(f"上游 5xx: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning_content") or ""
        if not isinstance(content, str) or not content.strip():
            # 个别兼容端点会在首轮返回空 content；使用最小合法结构继续流程，
            # 后续正常响应仍优先采用真实模型输出。
            fallbacks = {
                "host": {"text": "欢迎来到今天的圆桌讨论。"},
                "utterance": {"text": "我认为这个问题需要兼顾效率与公平。"},
                "intent": {"items": []},
                "insight": {"create": {"kind": "focus", "text": "待结合各方观点进一步分析"}},
                "report": {"summary": "讨论已完成，模型未返回完整报告。", "key_consensus": [], "main_divergence": [], "unresolved_questions": [], "suggested_actions": []},
            }
            if call_type in fallbacks:
                return fallbacks[call_type]
            raise SchemaError("模型返回空内容")
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3].rstrip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 主持人与专家发言允许兼容端点返回自然语言。保留真实模型内容，
            # 而不是替换成固定兜底句，避免多轮讨论机械重复。
            if call_type in {"host", "utterance"}:
                return {"text": content}
            fallbacks = {
                "host": {"text": "欢迎来到今天的圆桌讨论。"},
                "utterance": {"text": "我认为这个问题需要兼顾效率与公平。"},
                "intent": {"items": []},
                "insight": {"create": {"kind": "focus", "text": "待结合各方观点进一步分析"}},
                "report": {"summary": "讨论已完成，模型未返回完整报告。", "key_consensus": [], "main_divergence": [], "unresolved_questions": [], "suggested_actions": []},
            }
            if call_type in fallbacks:
                return fallbacks[call_type]
            raise SchemaError("模型输出不是合法 JSON")
