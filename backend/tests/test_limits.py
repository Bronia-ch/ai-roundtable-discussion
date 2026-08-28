from app.core.limits import check_limits


def test_below_soft_limit_continues():
    action, remaining = check_limits(39)
    assert action == "continue"
    assert remaining == 1


def test_at_soft_limit_pauses():
    action, _ = check_limits(40)
    assert action == "paused"


def test_granted_extra_extends():
    action, remaining = check_limits(45, granted_extra=10)
    assert action == "continue"
    assert remaining == 5


def test_absolute_limit_cannot_bypass():
    assert check_limits(100)[0] == "must_end"
    assert check_limits(100, granted_extra=100)[0] == "must_end"
