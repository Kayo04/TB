"""
Durable halt state. Postgres (risk_events, append-only) is the only source
of truth -- nothing about halt state lives in memory, so a process restart
can never un-halt anything by accident.

is_halted() fails CLOSED: if the read itself raises (connection down,
whatever), that is treated as halted, not as "unknown, so allow". This is
one of the two places in the whole risk layer that "when in doubt, stop" is
enforced (the other is RiskGate's outer try/except in gate.py).

clear_halt() is intentionally never called from anywhere in this package or
by any automated code path -- its only caller in this codebase is
scripts/clear_halt.py, a manual CLI. A halted bot restarting just re-reads
the same latest risk_events row and stays halted.
"""

from __future__ import annotations
import psycopg


def is_halted(conn: psycopg.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT event_type FROM risk_events ORDER BY created_at DESC, event_id DESC LIMIT 1"
        ).fetchone()
    except Exception:
        return True  # can't read state -> assume the worst, never assume "fine"
    if row is None:
        return False  # no event ever recorded -> never halted (explicit, not a NULL accident)
    return row["event_type"] == "halt"


def trip_halt(conn: psycopg.Connection, reason: str, triggered_by: str) -> None:
    conn.execute(
        "INSERT INTO risk_events (event_type, reason, triggered_by) VALUES ('halt', %s, %s)",
        (reason, triggered_by),
    )


def clear_halt(conn: psycopg.Connection, cleared_by: str, note: str) -> None:
    """Only ever called from scripts/clear_halt.py -- never from automated code."""
    if not cleared_by.strip() or not note.strip():
        raise ValueError("clear_halt requires a non-empty cleared_by and note")
    conn.execute(
        "INSERT INTO risk_events (event_type, reason, triggered_by) VALUES ('clear', %s, %s)",
        (note, cleared_by),
    )
