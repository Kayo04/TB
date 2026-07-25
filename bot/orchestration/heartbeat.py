"""
Durable liveness signal -- see migrations/0005_heartbeat.sql for why this is
separate from run_log. One row per component, upserted in place.
"""

from __future__ import annotations
from typing import Optional
import psycopg


def record_heartbeat(conn: psycopg.Connection, component: str, detail: Optional[str] = None) -> None:
    conn.execute(
        """
        INSERT INTO heartbeat (component, detail, last_seen_at)
        VALUES (%s, %s, now())
        ON CONFLICT (component) DO UPDATE
        SET detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at
        """,
        (component, detail),
    )
