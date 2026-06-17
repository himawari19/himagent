import os
import sqlite3
import json
import base64
import threading
from datetime import datetime

_GENERATION_LOCK = threading.Lock()
_GENERATION_JOBS = {}
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
                payload_json TEXT,
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
        conn.commit()


def _db_row_to_dict(row):
    if not row:
        return None
    return {
        'job_id': row[0],
        'status': row[1],
        'message': row[2],
        'progress': row[3] or 0,
        'cache_key': row[4],
        'cached': bool(row[5]),
        'payload_json': row[6],
        'result_json': row[7],
        'error': row[8],
        'created_at': row[9],
        'updated_at': row[10],
    }


def _db_fetch_job(job_id):
    if not os.path.exists(_GENERATION_DB_PATH):
        return None
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        row = conn.execute(
            "SELECT job_id, status, message, progress, cache_key, cached, payload_json, result_json, error, created_at, updated_at FROM generation_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return _db_row_to_dict(row)


def _db_upsert_job(job_id, state):
    now = datetime.utcnow().isoformat()
    existing = _db_fetch_job(job_id) or {}
    merged = {**existing, **state}
    merged.setdefault('created_at', now)
    merged['updated_at'] = now
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO generation_jobs (
                job_id, status, message, progress, cache_key, cached, payload_json, result_json, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status,
                message=excluded.message,
                progress=excluded.progress,
                cache_key=excluded.cache_key,
                cached=excluded.cached,
                payload_json=excluded.payload_json,
                result_json=excluded.result_json,
                error=excluded.error,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            """,
            (
                job_id,
                merged.get('status', 'queued'),
                merged.get('message', ''),
                int(merged.get('progress', 0) or 0),
                merged.get('cache_key'),
                1 if merged.get('cached') else 0,
                merged.get('payload_json'),
                merged.get('result_json'),
                merged.get('error'),
                merged.get('created_at'),
                merged['updated_at'],
            ),
        )
        conn.commit()
    return merged


def _db_get_cache(cache_key):
    if not os.path.exists(_GENERATION_DB_PATH):
        return None
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        row = conn.execute(
            "SELECT result_json FROM generation_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _serialize_payload(payload):
    serializable = dict(payload)
    serializable['files'] = [
        {
            'filename': item.get('filename', ''),
            'content_b64': base64.b64encode(item.get('bytes', b'')).decode('ascii'),
        }
        for item in payload.get('files', [])
    ]
    return json.dumps(serializable, ensure_ascii=False)


def _deserialize_payload(payload_json):
    raw = json.loads(payload_json)
    raw['files'] = [
        {
            'filename': item.get('filename', ''),
            'bytes': base64.b64decode(item.get('content_b64', '')),
        }
        for item in raw.get('files', [])
    ]
    return raw


def _store_job_state(job_id, state):
    state_to_store = dict(state)
    if 'payload' in state_to_store and state_to_store['payload'] is not None:
        state_to_store['payload_json'] = _serialize_payload(state_to_store.pop('payload'))
    if 'result' in state_to_store and state_to_store['result'] is not None:
        state_to_store['result_json'] = json.dumps(state_to_store.pop('result'), ensure_ascii=False)
    return _db_upsert_job(job_id, state_to_store)


def _set_job_state(job_id, **updates):
    with _GENERATION_LOCK:
        job = _GENERATION_JOBS.setdefault(job_id, {})
        job.update(updates)
        job["updated_at"] = datetime.utcnow().isoformat()
        persisted = _store_job_state(job_id, job)
        return persisted


def _get_job_state(job_id):
    with _GENERATION_LOCK:
        job = _GENERATION_JOBS.get(job_id)
    if job:
        return dict(job)
    persisted = _db_fetch_job(job_id)
    if not persisted:
        return {}
    try:
        if persisted.get('payload_json'):
            persisted['payload'] = _deserialize_payload(persisted['payload_json'])
    except Exception:
        pass
    try:
        if persisted.get('result_json'):
            persisted['result'] = json.loads(persisted['result_json'])
    except Exception:
        pass
    with _GENERATION_LOCK:
        _GENERATION_JOBS[job_id] = dict(persisted)
    return dict(persisted)


_init_generation_store()
