from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from .config import DB_PATH, ensure_dirs

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS run_narratives (
    run_id TEXT PRIMARY KEY,
    text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    input_hash TEXT NOT NULL,
    input_json TEXT NOT NULL,
    plan_json TEXT,
    trace_json TEXT,
    audit_json TEXT,
    gaps_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_cache (
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    tool TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(case_id,tool,input_hash)
);
CREATE TABLE IF NOT EXISTS run_jobs (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    recoveries INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_until REAL,
    heartbeat_at TEXT,
    error_code TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS case_workflows (
    case_id TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    case_version INTEGER NOT NULL DEFAULT 0,
    waiting_for TEXT,
    checkpointed INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_outbox (
    event_id INTEGER PRIMARY KEY REFERENCES case_events(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    state TEXT NOT NULL DEFAULT 'pending',
    error TEXT
);
CREATE TABLE IF NOT EXISTS access_tokens (
    token_hash TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    role TEXT NOT NULL,
    projects_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS access_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    principal TEXT NOT NULL,
    role TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status INTEGER NOT NULL,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    byte_size INTEGER NOT NULL DEFAULT 0,
    element_count INTEGER NOT NULL DEFAULT 0,
    storey_count INTEGER NOT NULL DEFAULT 0,
    units TEXT NOT NULL DEFAULT 'm'
);

CREATE TABLE IF NOT EXISTS storeys (
    model_id TEXT NOT NULL,
    guid TEXT NOT NULL,
    name TEXT NOT NULL,
    elevation_m REAL,
    placement_z_m REAL,
    element_count INTEGER NOT NULL DEFAULT 0,
    slab_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (model_id, guid),
    FOREIGN KEY (model_id) REFERENCES models(model_id)
);

CREATE TABLE IF NOT EXISTS elements (
    model_id TEXT NOT NULL,
    guid TEXT NOT NULL,
    ifc_class TEXT NOT NULL,
    name TEXT NOT NULL,
    storey_guid TEXT NOT NULL,
    storey_name TEXT NOT NULL,
    PRIMARY KEY (model_id, guid),
    FOREIGN KEY (model_id) REFERENCES models(model_id)
);
CREATE INDEX IF NOT EXISTS idx_elements_storey ON elements(model_id, storey_guid);
CREATE INDEX IF NOT EXISTS idx_elements_class ON elements(model_id, ifc_class);

CREATE TABLE IF NOT EXISTS zones (
    zone_id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    storey_guid TEXT NOT NULL,
    storey_name TEXT NOT NULL,
    target_guid TEXT NOT NULL,
    data_json TEXT NOT NULL,
    FOREIGN KEY (model_id) REFERENCES models(model_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    activity TEXT NOT NULL,
    planned_start TEXT NOT NULL,
    planned_end TEXT NOT NULL,
    owner TEXT NOT NULL,
    provenance TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    bim_guids_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (zone_id) REFERENCES zones(zone_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    bim_guids_json TEXT NOT NULL DEFAULT '[]',
    file_path TEXT,
    kind TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    stage TEXT NOT NULL,
    provenance TEXT NOT NULL,
    observation_json TEXT NOT NULL,
    label TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'seed',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    rule_id TEXT PRIMARY KEY,
    standard TEXT NOT NULL,
    clause TEXT NOT NULL,
    text TEXT NOT NULL,
    text_kind TEXT NOT NULL,
    source_path TEXT NOT NULL,
    pdf_page INTEGER,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL,
    effective_from TEXT,
    checked_on TEXT,
    jurisdiction TEXT,
    applicability TEXT,
    version TEXT,
    human_page_checked INTEGER NOT NULL DEFAULT 1
);

CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts USING fts5(
    rule_id UNINDEXED,
    tokens,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    project_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    task_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    bim_guids_json TEXT NOT NULL DEFAULT '[]',
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    rule_ids_json TEXT NOT NULL DEFAULT '[]',
    findings_json TEXT NOT NULL DEFAULT '[]',
    controls_json TEXT NOT NULL DEFAULT '[]',
    review_json TEXT,
    implementation_json TEXT,
    verification_json TEXT,
    assumptions_json TEXT NOT NULL DEFAULT '[]',
    provenance TEXT NOT NULL DEFAULT 'mixed_real_bim_simulated_site_state',
    mode TEXT NOT NULL DEFAULT 'demo',
    last_run_id TEXT,
    analysis_incomplete INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id),
    FOREIGN KEY (zone_id) REFERENCES zones(zone_id)
);

CREATE TABLE IF NOT EXISTS case_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    at TEXT NOT NULL,
    status TEXT NOT NULL,
    event TEXT NOT NULL,
    actor TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    provenance TEXT NOT NULL DEFAULT 'system',
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_case_events_case ON case_events(case_id, id);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    trace_json TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    mode TEXT NOT NULL DEFAULT 'demo',
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_runs_case ON runs(case_id, created_at);

CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    node TEXT NOT NULL,
    role TEXT NOT NULL,
    tool TEXT,
    input_summary TEXT NOT NULL DEFAULT '',
    output_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    error TEXT,
    rationale TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id, seq);

CREATE TABLE IF NOT EXISTS acceptance_results (
    test_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    expected TEXT NOT NULL,
    actual TEXT NOT NULL,
    passed INTEGER NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    case_id TEXT,
    run_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_plans (
    case_id TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    activities_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_plan_revisions (
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    activities_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY(case_id,revision)
);
CREATE TABLE IF NOT EXISTS site_notes (
    note_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    bim_guids_json TEXT NOT NULL,
    body TEXT NOT NULL,
    paragraphs_json TEXT NOT NULL,
    analysis_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(document_id,version)
);
CREATE INDEX IF NOT EXISTS idx_notes_case ON site_notes(case_id,created_at);
CREATE TABLE IF NOT EXISTS text_resolutions (
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    conflict_id TEXT NOT NULL,
    observation_hash TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY(case_id,conflict_id,observation_hash)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    actor_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_messages_scope ON case_messages(case_id,actor_id,id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_case_message_run ON case_messages(case_id,run_id,role);

CREATE TABLE IF NOT EXISTS model_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT,
    run_id TEXT,
    evidence_id TEXT,
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    usage_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_model_calls_case ON model_calls(case_id,id);
"""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    target = path or DB_PATH
    conn = sqlite3.connect(str(target), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def connect() -> sqlite3.Connection:
    return _connect()


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    ensure_dirs()
    with transaction() as conn:
        conn.executescript(SCHEMA)
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(cases)').fetchall()}
        for name, declaration in {
            'request_text': "TEXT NOT NULL DEFAULT ''",
            'task_actor_id': "TEXT NOT NULL DEFAULT 'demo-user'",
            'task_spec_json': 'TEXT', 'safety_state_json': 'TEXT', 'decision_package_json': 'TEXT',
            'scope_json': 'TEXT',
        }.items():
            if name not in columns:
                conn.execute(f'ALTER TABLE cases ADD COLUMN {name} {declaration}')
        evidence_columns = {row['name'] for row in conn.execute('PRAGMA table_info(evidence)')}
        if 'perception_json' not in evidence_columns:
            conn.execute("ALTER TABLE evidence ADD COLUMN perception_json TEXT NOT NULL DEFAULT '{}'")
        row = conn.execute("SELECT COUNT(*) AS n FROM models").fetchone()
        if not row or row["n"] == 0:
            from .seed import seed_all

            seed_all(conn)


def reset_db() -> None:
    ensure_dirs()
    if DB_PATH.exists():
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(DB_PATH) + suffix)
            if candidate.exists():
                candidate.unlink()
    init_db()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
