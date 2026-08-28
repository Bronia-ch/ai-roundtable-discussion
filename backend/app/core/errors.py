import sqlite3
from dataclasses import dataclass, field
from enum import Enum


class ErrorClass(str, Enum):
    RECOVERABLE = "recoverable"
    AUTH = "auth"
    SCHEMA = "schema"
    FATAL = "fatal"


class AuthError(Exception):
    """鉴权失败 / 余额不足——不重试。"""


class SchemaError(Exception):
    """LLM 输出结构持续非法——降级处理。"""


class FatalPersistenceError(Exception):
    """会话级不可恢复的持久化/一致性错误——仅此类进入 failed。"""


def classify_error(exc: Exception) -> ErrorClass:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ErrorClass.RECOVERABLE
    if isinstance(exc, AuthError):
        return ErrorClass.AUTH
    if isinstance(exc, SchemaError):
        return ErrorClass.SCHEMA
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        if "locked" in msg or "busy" in msg:
            return ErrorClass.RECOVERABLE
        return ErrorClass.FATAL
    if isinstance(exc, (FatalPersistenceError, sqlite3.DatabaseError)):
        return ErrorClass.FATAL
    return ErrorClass.FATAL


@dataclass
class Degradation:
    degraded_components: list[str] = field(default_factory=list)
    permanently_failed_insight_count: int = 0
    used_rule_scheduler_count: int = 0
    failed_turn_count: int = 0
    report_generated_with_degraded_context: bool = False
