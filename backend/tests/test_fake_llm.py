"""FakeLLMProvider 契约：输出必须通过真实消费方校验（防 E2E 玄学失败）。"""

import pytest

from app.core.engine import _validate_report
from app.core.panel import PERSON_FIELDS, _validate_panel
from app.llm.fake import INSIGHT_KINDS, SUPPORTED_EXPERT_COUNTS, FakeLLMProvider, _expert_count


@pytest.mark.asyncio
async def test_panel_output_passes_validate_panel():
    provider = FakeLLMProvider()
    resp = await provider.generate("panel", "", "专家人数：4")
    host, experts = _validate_panel(resp, 4)
    assert len(experts) == 4
    for p in [host, *experts]:
        assert all(isinstance(p[f], str) and p[f].strip() for f in PERSON_FIELDS)


@pytest.mark.asyncio
async def test_panel_supports_all_frontend_counts():
    """前端允许 3/4/5：fake 必须恰好返回请求人数，且成员不重复。"""
    provider = FakeLLMProvider()
    for n in SUPPORTED_EXPERT_COUNTS:
        resp = await provider.generate("panel", "", f"专家人数：{n}")
        host, experts = _validate_panel(resp, n)
        assert len(experts) == n
        names = {p["name"] for p in [host, *experts]}
        assert len(names) == n + 1


def test_expert_count_parsing():
    assert _expert_count("讨论主题：AI；专家人数：3") == 3
    assert _expert_count("无数字") == 4  # 兜底默认
    with pytest.raises(ValueError):
        _expert_count("专家人数：9")


@pytest.mark.asyncio
async def test_report_output_passes_validate_report():
    provider = FakeLLMProvider()
    resp = await provider.generate("report", "", "讨论主题：AI")
    cleaned = _validate_report(resp)  # 真实校验器
    assert isinstance(cleaned["summary"], str) and cleaned["summary"].strip()


@pytest.mark.asyncio
async def test_insight_kind_within_schema_check():
    """insight.kind 必须落在 schema.sql CHECK 允许值域内（引擎直接写库）。"""
    provider = FakeLLMProvider()
    resp = await provider.generate("insight", "", "")
    create = resp["create"]
    assert isinstance(create, dict)
    assert create["kind"] in INSIGHT_KINDS
    assert isinstance(create["text"], str) and create["text"].strip()


@pytest.mark.asyncio
async def test_host_utterance_intent_shape():
    provider = FakeLLMProvider()
    host = await provider.generate("host", "", "")
    assert isinstance(host["text"], str) and host["text"].strip()
    utt = await provider.generate("utterance", "", "")
    assert isinstance(utt["text"], str) and utt["text"].strip()
    intent = await provider.generate("intent", "", "")
    assert isinstance(intent["items"], list)  # 空意愿 → RuleScheduler 真实调度
