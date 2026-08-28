import pytest
from pydantic import ValidationError

from app import models


def test_event_envelope_requires_sequence():
    with pytest.raises(ValidationError):
        models.SSEEventEnvelope(event="x", session_id="s", data={})


def test_intent_willingness_clamped():
    assert (
        models.IntentItem(
            participant_id="p1", intent_type="rebut", willingness=5.0
        ).willingness
        == 1.0
    )
    assert (
        models.IntentItem(
            participant_id="p1", intent_type="rebut", willingness=-1.0
        ).willingness
        == 0.0
    )


def test_intent_bad_enum_rejected():
    with pytest.raises(ValidationError):
        models.IntentItem(participant_id="p1", intent_type="sing", willingness=0.5)


def test_insight_delta_relation_enum():
    with pytest.raises(ValidationError):
        models.InsightEvidenceDelta(insight_id="i1", relation="likes")
