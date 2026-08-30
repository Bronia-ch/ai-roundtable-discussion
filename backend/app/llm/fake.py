"""LLM_FAKE=1 的离线替身：确定性输出满足各 call_type 的 schema 契约，绝不出网。

供 E2E 与本地演示使用；输出与真实 LLM 同构（可被各消费方校验接受），
内容固定保证 E2E 断言稳定。intent 返回空意愿 → 引擎走确定性 RuleScheduler
（真实调度路径，非降级路径）。

ScriptedLLMProvider 为测试脚本替身（不访问网络、不读取密钥）。
"""

import asyncio
import re
from typing import Any

from app.config import Settings


class ScriptedLLMProvider:
    """按 call_type 返回预设脚本响应。不访问网络、不读取密钥。"""

    def __init__(self, script: dict[str, Any]):
        self.script = script

    async def generate(self, call_type: str, system: str, user: str) -> dict[str, Any]:
        if call_type not in self.script:
            raise KeyError(call_type)
        return self.script[call_type]

PANEL_HOST = {
    "name": "周明远",
    "profession": "科技评论员",
    "title": "资深主编",
    "stance": "中立理性",
    "avatar_color": "#5B8DEF",
    "avatar_emoji": "🎙️",
}
PANEL_EXPERTS = [
    {"name": "林晓", "profession": "经济学家", "title": "教授", "stance": "担忧：AI 红利集中", "avatar_color": "#E4572E", "avatar_emoji": "📉"},
    {"name": "陈曦", "profession": "AI 实验室主任", "title": "研究员", "stance": "乐观：AI 可普惠化", "avatar_color": "#2EA66E", "avatar_emoji": "🤖"},
    {"name": "王芳", "profession": "社会学者", "title": "副教授", "stance": "警惕：数字鸿沟", "avatar_color": "#8E44AD", "avatar_emoji": "🧭"},
    {"name": "赵磊", "profession": "政策研究员", "title": "研究员", "stance": "务实：分层监管", "avatar_color": "#D9822B", "avatar_emoji": "⚖️"},
    {"name": "孙悦", "profession": "数据科学家", "title": "工程师", "stance": "审慎：算法透明", "avatar_color": "#2A9D8F", "avatar_emoji": "🔬"},
]

# 前端创建表单允许的全部专家人数；fake 输出必须恰好返回请求人数
SUPPORTED_EXPERT_COUNTS = (3, 4, 5)
_EXPERT_COUNT_RE = re.compile(r"专家人数[：:](\d+)")


def _expert_count(user: str) -> int:
    m = _EXPERT_COUNT_RE.search(user)
    if not m:
        return 4
    count = int(m.group(1))
    if count not in SUPPORTED_EXPERT_COUNTS:
        raise ValueError(f"FakeLLM 不支持的专家人数: {count}（允许 {SUPPORTED_EXPERT_COUNTS}）")
    return count


# schema.sql insights 表的 CHECK 允许值（fake 输出必须落在此值域内）
INSIGHT_KINDS = ("focus", "consensus", "divergence", "open_question")


class FakeLLMProvider:
    """LLM_FAKE=1 离线替身：按 call_type 返回确定性合法结构。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    async def generate(self, call_type: str, system: str, user: str) -> dict[str, Any]:
        # 人为节奏：拉长讨论轮次，给 E2E 暂停/继续断言留窗口（真实 LLM 天然有网络延迟）
        await asyncio.sleep(0.25)
        if call_type == "panel":
            return {
                "host": dict(PANEL_HOST),
                "experts": [dict(e) for e in PANEL_EXPERTS[:_expert_count(user)]],
            }
        if call_type == "host":
            return {"text": "欢迎来到今天的圆桌讨论，我们聚焦人工智能与社会公平。"}
        if call_type == "intent":
            return {"items": []}  # 空意愿 → RuleScheduler 确定性调度
        if call_type == "utterance":
            return {"text": "我认为技术发展必须兼顾社会公平，这是底线。"}
        if call_type == "insight":
            return {"create": {"kind": "focus", "text": "AI 公平是核心关注点"}}
        if call_type == "report":
            return {
                "summary": "专家们一致认为 AI 应兼顾效率与公平。",
                "key_consensus": ["AI 需要公平治理"],
                "main_divergence": ["AI 红利分配方式存在分歧"],
                "unresolved_questions": ["再培训体系如何落地"],
                "suggested_actions": ["建立 AI 公平评估机制"],
            }
        raise ValueError(f"FakeLLM 未支持 call_type: {call_type}")
