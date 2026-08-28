from app.core.scheduler import RuleScheduler, pick_speaker


def _mk(cands, wills, intents, stances, history, seed=1):
    return pick_speaker(cands, wills, intents, stances, history, seed=seed)


def test_last_speaker_excluded():
    out = _mk(
        ["a", "b"],
        {"a": 0.9, "b": 0.1},
        {"a": "rebut", "b": "answer"},
        {"a": "X", "b": "Y"},
        {"last": "a", "counts": {"a": 1, "b": 0}, "gaps": {"a": 0, "b": 5}},
    )
    assert out == "b"


def test_deterministic_same_seed():
    args = (
        ["a", "b"],
        {"a": 0.5, "b": 0.5},
        {"a": "answer", "b": "answer"},
        {"a": "X", "b": "Y"},
        {"last": None, "counts": {"a": 0, "b": 0}, "gaps": {"a": 0, "b": 0}},
    )
    assert _mk(*args, seed=7) == _mk(*args, seed=7)


def test_starved_expert_gets_boost():
    out = _mk(
        ["a", "b"],
        {"a": 0.9, "b": 0.05},
        {"a": "answer", "b": "answer"},
        {"a": "X", "b": "Y"},
        {"last": None, "counts": {"a": 3, "b": 0}, "gaps": {"a": 1, "b": 20}},
    )
    assert out == "b"


def test_rule_scheduler_fallback():
    out = RuleScheduler().pick(
        ["a", "b"],
        {"last": None, "counts": {"a": 0, "b": 0}, "gaps": {"a": 0, "b": 0}},
        seed=1,
    )
    assert out in ("a", "b")


def test_named_followup_exception_allows_repeat():
    out = _mk(
        ["a", "b"],
        {"a": 0.9, "b": 0.1},
        {"a": "answer", "b": "answer"},
        {"a": "X", "b": "Y"},
        {
            "last": "a",
            "counts": {"a": 1, "b": 0},
            "gaps": {"a": 0, "b": 5},
            "named_followup": "a",
        },
    )
    assert out == "a"


def test_single_candidate_lifts_exclusion():
    out = _mk(
        ["a"],
        {"a": 0.5},
        {"a": "answer"},
        {"a": "X"},
        {"last": "a", "counts": {"a": 1}, "gaps": {"a": 0}},
    )
    assert out == "a"


def test_host_interjection_does_not_clear_history():
    out = _mk(
        ["a", "b"],
        {"a": 0.9, "b": 0.1},
        {"a": "answer", "b": "answer"},
        {"a": "X", "b": "Y"},
        {
            "last": "a",
            "counts": {"a": 2, "b": 0},
            "gaps": {"a": 0, "b": 3},
            "host_interjected": True,
        },
    )
    assert out == "b"


def test_diversity_rewards_different_stance():
    out = _mk(
        ["a", "b"],
        {"a": 0.5, "b": 0.5},
        {"a": "answer", "b": "answer"},
        {"a": "X", "b": "Y"},
        {
            "last": None,
            "counts": {"a": 0, "b": 0},
            "gaps": {"a": 0, "b": 0},
            "recent_stances": ["X", "X", "X"],
        },
        seed=1,
    )
    assert out == "b"


def test_diversity_same_stance_deterministic():
    args = (
        ["a", "b"],
        {"a": 0.5, "b": 0.5},
        {"a": "answer", "b": "answer"},
        {"a": "X", "b": "X"},
        {
            "last": None,
            "counts": {"a": 0, "b": 0},
            "gaps": {"a": 0, "b": 0},
            "recent_stances": ["X", "X", "X"],
        },
    )
    assert _mk(*args, seed=7) == _mk(*args, seed=7)
