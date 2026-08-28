def check_limits(
    count: int,
    soft_limit: int = 40,
    absolute_limit: int = 100,
    granted_extra: int = 0,
) -> tuple[str, int]:
    """发言数上限：软上限默认 40（每次"继续" granted_extra+10），绝对上限 100 只能结束。"""
    if count >= absolute_limit:
        return ("must_end", 0)
    effective_soft = soft_limit + granted_extra
    if count >= effective_soft:
        return ("paused", 0)
    return ("continue", effective_soft - count)
