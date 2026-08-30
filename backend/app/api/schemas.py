"""T0.1 会话契约的请求/响应 schema（最小契约，不扩字段）。"""

from pydantic import BaseModel, field_validator


class CreateSessionRequest(BaseModel):
    """topic 去首尾空白后非空；expert_count 默认 4，范围 2–6（规格 §line75）。

    session_id / status / created_at 未声明字段：客户端传入被忽略，以服务端生成值为准。
    """

    topic: str
    expert_count: int = 4

    @field_validator("topic")
    @classmethod
    def _topic_non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("topic 必须非空")
        return v

    @field_validator("expert_count")
    @classmethod
    def _expert_count_range(cls, v: int) -> int:
        if not 2 <= v <= 6:
            raise ValueError("expert_count 必须在 2–6 之间")
        return v


class CommandRequest(BaseModel):
    """命令请求体：command_id strip 后必须非空（" " / "   " 拒绝 422）。"""

    command_id: str

    @field_validator("command_id")
    @classmethod
    def _command_id_non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("command_id 必须非空")
        return v


class SessionItem(BaseModel):
    """列表/创建响应的会话条目：严格五字段，不泄露内部数据库字段。"""

    session_id: str
    topic: str
    expert_count: int
    status: str
    created_at: str


class SessionCreated(SessionItem):
    """POST /sessions 201 响应。"""


class SessionListOut(BaseModel):
    sessions: list[SessionItem]
