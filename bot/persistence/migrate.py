"""
Minimal versioned migration runner. Explicit and reproducible, not a manual
one-off DROP/CREATE: schema_migrations tracks which numbered .sql files in
migrations/ have already been applied, so run_migrations() is safe to call
on every startup and in every test -- already-applied files are skipped.
"""

from __future__ import annotations
from pathlib import Path
import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_migrations_table(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _applied_versions(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def run_migrations(conn: psycopg.Connection) -> list[str]:
    """Applies any not-yet-applied migration files, in filename order. Returns newly applied versions."""
    _ensure_migrations_table(conn)
    applied = _applied_versions(conn)
    newly_applied: list[str] = []

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.stem
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        with conn.transaction():
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        newly_applied.append(version)

    return newly_applied
