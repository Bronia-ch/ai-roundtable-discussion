import random
from typing import Any

WEIGHTS = {"alpha": 0.4, "beta": 0.3, "gamma": 0.2, "delta": 0.1}
STARVATION_THRESHOLD = 10

_INTENT_RELEVANCE = {
    "rebut": 1.0,
    "clarify": 0.9,
    "supplement": 0.7,
    "answer": 0.6,
}


def _relevance(intent_type: str) -> float:
    return _INTENT_RELEVANCE.get(intent_type, 0.5)


def _fairness(gap: int) -> float:
    return min(gap, 10) / 10.0


def _diversity(candidate: str, stances: dict[str, str], history: dict[str, Any]) -> float:
    """近期立场单一时，异质立场获得多样性加分（确定性、无 LLM）。"""
    recent = history.get("recent_stances", [])
    if not recent:
        return 0.0
    cand_stance = stances.get(candidate, "")
    if len(set(recent)) == 1 and cand_stance != recent[0]:
        return 1.0
    return 0.0


def _eligible(candidates: list[str], history: dict[str, Any]) -> list[str]:
    last = history.get("last")
    named = history.get("named_followup")
    if last and last != named and last in candidates and len(candidates) > 1:
        eligible = [c for c in candidates if c != last]
    else:
        eligible = list(candidates)
    return eligible or list(candidates)


def _starved(eligible: list[str], gaps: dict[str, int]) -> str | None:
    starved = [c for c in eligible if gaps.get(c, 0) >= STARVATION_THRESHOLD]
    if not starved:
        return None
    return max(starved, key=lambda c: gaps.get(c, 0))


def pick_speaker(
    candidates: list[str],
    willingness: dict[str, float],
    intents: dict[str, str],
    stances: dict[str, str],
    history: dict[str, Any],
    *,
    seed: int,
) -> str:
    """确定性纯函数：选出下一位发言者。模型不得指定最终发言者——本函数只消费已校验的意图/意愿信号。"""
    if not candidates:
        raise ValueError("no candidates")

    gaps = history.get("gaps", {})
    eligible = _eligible(candidates, history)

    starved = _starved(eligible, gaps)
    if starved is not None:
        return starved

    def score(c: str) -> float:
        w = willingness.get(c, 0.0)
        return (
            WEIGHTS["alpha"] * w
            + WEIGHTS["beta"] * _relevance(intents.get(c, "answer"))
            + WEIGHTS["gamma"] * _fairness(gaps.get(c, 0))
            + WEIGHTS["delta"] * _diversity(c, stances, history)
        )

    best = max(score(c) for c in eligible)
    tied = [c for c in eligible if score(c) == best]
    if len(tied) == 1:
        return tied[0]

    # gap 更久者优先，再平按 seed 伪随机（同种子同结果）
    tied = sorted(tied, key=lambda c: gaps.get(c, 0), reverse=True)
    top_gap = gaps.get(tied[0], 0)
    tied = [c for c in tied if gaps.get(c, 0) == top_gap]
    return random.Random(seed).choice(sorted(tied))


class RuleScheduler:
    """意图评估失败时的规则降级：以公平性（gap）替代意愿。"""

    def pick(self, candidates: list[str], history: dict[str, Any], *, seed: int) -> str:
        if not candidates:
            raise ValueError("no candidates")
        gaps = history.get("gaps", {})
        eligible = _eligible(candidates, history)
        starved = _starved(eligible, gaps)
        if starved is not None:
            return starved
        return max(eligible, key=lambda c: gaps.get(c, 0))
