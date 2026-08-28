import pytest

from app.core import reconciliation


async def _setup(conn):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'live')"
    )
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order, runtime_state) "
        "VALUES ('p1', 's1', 'expert', 'n', 'p', 't', 's', '#111', '🤖', 1, 'preparing')"
    )
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order, runtime_state) "
        "VALUES ('h1', 's1', 'host', 'n', 'p', 't', 's', '#222', '🎙️', 0, 'speaking')"
    )
    await conn.execute(
        "INSERT INTO turns (id, session_id, sequence, status) VALUES ('t1', 's1', 1, 'generating')"
    )
    await conn.execute(
        "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal, insight_status) "
        "VALUES ('u1', 's1', 't1', 'p1', 'expert', 'x', 1, 'processing')"
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_reconcile_resets_states(conn):
    await _setup(conn)
    await reconciliation.reconcile(conn)
    assert (await (await conn.execute("SELECT runtime_state FROM participants WHERE id='p1'")).fetchone())[0] == "waiting"
    assert (await (await conn.execute("SELECT runtime_state FROM participants WHERE id='h1'")).fetchone())[0] == "idle"
    assert (await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone())[0] == "paused"
    assert (await (await conn.execute("SELECT status, generation_epoch FROM turns WHERE id='t1'")).fetchone()) == ("cancelled", 2)
    assert (await (await conn.execute("SELECT insight_status FROM utterances WHERE id='u1'")).fetchone())[0] == "pending"


@pytest.mark.asyncio
async def test_reconcile_idempotent(conn):
    await _setup(conn)
    await reconciliation.reconcile(conn)
    await reconciliation.reconcile(conn)  # 二次执行不抛异常、不产生额外变化
    assert (await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone())[0] == "paused"
