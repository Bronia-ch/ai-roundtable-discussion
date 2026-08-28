from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, field_validator


class IntentType(str, Enum):
    answer = "answer"
    supplement = "supplement"
    rebut = "rebut"
    clarify = "clarify"


class Relation(str, Enum):
    supports = "supports"
    opposes = "opposes"
    mentions = "mentions"
    resolves = "resolves"


class IntentItem(BaseModel):
    participant_id: str
    intent_type: IntentType
    willingness: float = 0.0
    target_participant_id: Optional[str] = None
    target_claim_id: Optional[str] = None
    public_focus: str = ""

    @field_validator("willingness")
    @classmethod
    def _clamp_willingness(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class IntentBatch(BaseModel):
    items: list[IntentItem]


class InsightEvidenceDelta(BaseModel):
    insight_id: str
    relation: Relation


class InsightDelta(BaseModel):
    create: Optional[dict[str, Any]] = None  # {kind, text}
    update: Optional[dict[str, Any]] = None  # {insight_id, kind?, text?, status?}
    evidence: Optional[InsightEvidenceDelta] = None


class SSEEventEnvelope(BaseModel):
    event: str
    sequence: int
    schema_version: int = 1
    session_id: str
    timestamp: str = ""
    data: dict[str, Any] = {}


class SessionOut(BaseModel):
    id: str
    topic: str
    expert_count: int
    status: str
    last_stable_state: Optional[str] = None
    error_code: Optional[str] = None
    retry_operation: Optional[str] = None
    last_event_sequence: int
    is_sample: int = 0


class ParticipantOut(BaseModel):
    id: str
    session_id: str
    role: str
    name: str
    profession: str
    title: str
    stance: str
    avatar_color: str
    avatar_emoji: str
    sort_order: int
    runtime_state: str
    public_focus: str


class UtteranceOut(BaseModel):
    id: str
    turn_id: str
    speaker_id: str
    role: str
    text: str
    ordinal: int


class InsightOut(BaseModel):
    id: str
    kind: str
    text: str
    support_count: int
    oppose_count: int
    status: str
    version: int
