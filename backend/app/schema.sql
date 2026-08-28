PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  topic TEXT NOT NULL,
  expert_count INTEGER NOT NULL DEFAULT 4,
  status TEXT NOT NULL DEFAULT 'draft',
  last_stable_state TEXT,
  error_code TEXT,
  retry_operation TEXT,
  last_event_sequence INTEGER NOT NULL DEFAULT 0,
  is_sample INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS participants (
  id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('host', 'expert')),
  name TEXT NOT NULL,
  profession TEXT NOT NULL,
  title TEXT NOT NULL,
  stance TEXT NOT NULL,
  avatar_color TEXT NOT NULL,
  avatar_emoji TEXT NOT NULL,
  sort_order INTEGER NOT NULL,
  runtime_state TEXT NOT NULL DEFAULT 'waiting',
  public_focus TEXT NOT NULL DEFAULT '',
  speech_count INTEGER NOT NULL DEFAULT 0,
  last_spoke_turn INTEGER,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(session_id, id),
  UNIQUE(session_id, sort_order),
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS turns (
  id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  generation_epoch INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'planning'
    CHECK(status IN ('planning', 'preparing', 'generating', 'completed', 'cancelled', 'failed')),
  selected_participant_id TEXT,
  intent_snapshot TEXT,
  started_at TEXT,
  completed_at TEXT,
  cancelled_at TEXT,
  UNIQUE(session_id, sequence),
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS utterances (
  id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  speaker_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('host', 'expert')),
  text TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  insight_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(insight_status IN ('pending', 'processing', 'succeeded', 'retry_wait', 'permanently_failed')),
  insight_retry_count INTEGER NOT NULL DEFAULT 0,
  insight_last_error TEXT,
  insight_next_retry_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY(id),
  UNIQUE(session_id, id),
  UNIQUE(session_id, ordinal),
  FOREIGN KEY(session_id, speaker_id) REFERENCES participants(session_id, id),
  FOREIGN KEY(turn_id) REFERENCES turns(id)
);

CREATE TABLE IF NOT EXISTS insights (
  id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('focus', 'consensus', 'divergence', 'open_question')),
  text TEXT NOT NULL,
  support_count INTEGER NOT NULL DEFAULT 0,
  oppose_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'resolved')),
  version INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY(id),
  UNIQUE(session_id, id),
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS insight_evidence (
  session_id TEXT NOT NULL,
  insight_id TEXT NOT NULL,
  utterance_id TEXT NOT NULL,
  participant_id TEXT NOT NULL,
  relation TEXT NOT NULL CHECK(relation IN ('supports', 'opposes', 'mentions', 'resolves')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(insight_id, utterance_id, relation),
  FOREIGN KEY(session_id, insight_id) REFERENCES insights(session_id, id),
  FOREIGN KEY(session_id, utterance_id) REFERENCES utterances(session_id, id),
  FOREIGN KEY(session_id, participant_id) REFERENCES participants(session_id, id)
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(session_id, sequence)
);

CREATE TABLE IF NOT EXISTS command_receipts (
  session_id TEXT NOT NULL,
  command_id TEXT NOT NULL,
  command_type TEXT NOT NULL,
  accepted_at TEXT NOT NULL DEFAULT (datetime('now')),
  status TEXT NOT NULL DEFAULT 'accepted',
  result TEXT,
  error TEXT,
  PRIMARY KEY(session_id, command_id)
);

CREATE TABLE IF NOT EXISTS discussion_reports (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL UNIQUE,
  summary TEXT NOT NULL,
  key_consensus TEXT,
  main_divergence TEXT,
  unresolved_questions TEXT,
  suggested_actions TEXT,
  raw_json TEXT NOT NULL,
  degraded_components TEXT,
  permanently_failed_insight_count INTEGER NOT NULL DEFAULT 0,
  used_rule_scheduler_count INTEGER NOT NULL DEFAULT 0,
  failed_turn_count INTEGER NOT NULL DEFAULT 0,
  report_generated_with_degraded_context INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);
