import os
import sqlite3
import json
import threading
from datetime import datetime

_GENERATION_LOCK = threading.Lock()
_GENERATION_CACHE = {}
_GENERATION_ACTIVE_BY_CACHE = {}

_GENERATION_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'generation_jobs.sqlite3'
)


def _init_generation_store():
    os.makedirs(os.path.dirname(_GENERATION_DB_PATH), exist_ok=True)
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generation_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                message TEXT,
                progress INTEGER DEFAULT 0,
                cache_key TEXT,
                cached INTEGER DEFAULT 0,
                result_json TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generation_cache (
                cache_key TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_cache_key ON generation_jobs(cache_key)"
        )
        # Drop legacy payload_json column if it exists (added before this refactor)
        try:
            conn.execute("ALTER TABLE generation_jobs DROP COLUMN payload_json")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def _db_row_to_dict(row):
    if not row:
        return None
    return {
        'job_id':      row[0],
        'status':      row[1],
        'message':     row[2],
        'progress':    row[3] or 0,
        'cache_key':   row[4],
        'cached':      bool(row[5]),
        'result_json': row[6],
        'error':       row[7],
        'created_at':  row[8],
        'updated_at':  row[9],
    }


def _db_fetch_job(job_id):
    if not os.path.exists(_GENERATION_DB_PATH):
        return None
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        row = conn.execute(
            "SELECT job_id, status, message, progress, cache_key, cached, result_json, error, created_at, updated_at "
            "FROM generation_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return _db_row_to_dict(row)


def _db_upsert_job(job_id, state):
    now = datetime.utcnow().isoformat()
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        if state.get('status') is None:
            # Progress/message-only update — never creates a row, avoids NOT NULL on status
            conn.execute(
                "UPDATE generation_jobs SET message=?, progress=?, updated_at=? WHERE job_id=?",
                (state.get('message'), state.get('progress'), now, job_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO generation_jobs
                    (job_id, status, message, progress, cache_key, cached, result_json, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status      = COALESCE(excluded.status,      generation_jobs.status),
                    message     = COALESCE(excluded.message,     generation_jobs.message),
                    progress    = COALESCE(excluded.progress,    generation_jobs.progress),
                    cache_key   = COALESCE(excluded.cache_key,   generation_jobs.cache_key),
                    cached      = COALESCE(excluded.cached,      generation_jobs.cached),
                    result_json = COALESCE(excluded.result_json, generation_jobs.result_json),
                    error       = excluded.error,
                    updated_at  = excluded.updated_at
                """,
                (
                    job_id,
                    state.get('status'),
                    state.get('message'),
                    state.get('progress'),
                    state.get('cache_key'),
                    1 if state.get('cached') else 0,
                    state.get('result_json'),
                    state.get('error'),
                    now,
                    now,
                ),
            )
        conn.commit()


def _set_job_state(job_id, **updates):
    state = {k: v for k, v in updates.items() if k != 'payload'}
    if 'result' in state and state['result'] is not None:
        state['result_json'] = json.dumps(state.pop('result'), ensure_ascii=False)
    else:
        state.pop('result', None)
    _db_upsert_job(job_id, state)


def _get_job_state(job_id):
    persisted = _db_fetch_job(job_id)
    if not persisted:
        return {}
    try:
        if persisted.get('result_json'):
            persisted['result'] = json.loads(persisted['result_json'])
    except Exception:
        pass
    return persisted


_init_generation_store()
