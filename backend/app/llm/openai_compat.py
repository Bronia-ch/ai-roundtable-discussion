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
        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            raise SchemaError("模型输出不是合法 JSON")
