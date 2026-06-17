"""SQLite-backed generation result cache."""
import json
import sqlite3
from datetime import datetime, timezone


def get_generation_cache(db_path: str, cache_key: str):
    if not cache_key:
        return None
    with sqlite3.connect(db_path) as conn:
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


def set_generation_cache(db_path: str, cache_key: str, result: dict) -> None:
    if not cache_key or not result:
        return
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO generation_cache (cache_key, result_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                result_json=excluded.result_json,
                updated_at=excluded.updated_at
            """,
            (cache_key, json.dumps(result, ensure_ascii=False), now, now),
        )
        conn.commit()

