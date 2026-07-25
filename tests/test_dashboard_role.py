"""
dashboard_ro is defined in migration 0004 -- this proves the enforcement is
real: a role that literally cannot write, not "we just didn't write any
INSERT statements in the dashboard code." Same standard as everywhere else
in this project (fail-closed, DB-level enforcement over convention) --
proving it means connecting as dashboard_ro and watching a write attempt
get rejected by Postgres itself, not grepping the dashboard's source.

The role's password is never committed (see the migration's docstring) --
this test sets a test-only password directly via the superuser connection,
scoped to this ephemeral test database, not any real secret.
"""

from __future__ import annotations
import os
from urllib.parse import urlparse

import psycopg
import pytest
from psycopg.rows import dict_row

_TEST_PASSWORD = "dashboard_ro_test_only"


@pytest.fixture
def dashboard_ro_conn(db_conn):
    db_conn.execute(f"ALTER ROLE dashboard_ro WITH PASSWORD '{_TEST_PASSWORD}'")

    parsed = urlparse(os.environ["DATABASE_URL"])
    ro_dsn = parsed._replace(
        netloc=f"dashboard_ro:{_TEST_PASSWORD}@{parsed.hostname}:{parsed.port}"
    ).geturl()

    conn = psycopg.connect(ro_dsn, row_factory=dict_row, autocommit=True)
    yield conn
    conn.close()


def test_dashboard_ro_can_select(dashboard_ro_conn):
    row = dashboard_ro_conn.execute("SELECT COUNT(*) AS c FROM run_log").fetchone()
    assert row["c"] >= 0


def test_dashboard_ro_cannot_insert(dashboard_ro_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        dashboard_ro_conn.execute(
            "INSERT INTO risk_events (event_type, reason, triggered_by) VALUES ('halt', 'x', 'x')"
        )


def test_dashboard_ro_cannot_update(dashboard_ro_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        dashboard_ro_conn.execute("UPDATE run_log SET signal = 0")


def test_dashboard_ro_cannot_delete(dashboard_ro_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        dashboard_ro_conn.execute("DELETE FROM run_log")


def test_dashboard_ro_covers_a_future_table_via_default_privileges(dashboard_ro_conn, db_conn):
    """
    ALTER DEFAULT PRIVILEGES should mean a brand-new table created after
    dashboard_ro already exists is still readable without a follow-up
    GRANT -- this is the whole point of using it instead of one-off grants.
    """
    db_conn.execute("CREATE TABLE IF NOT EXISTS _dashboard_role_test_table (id INT)")
    try:
        row = dashboard_ro_conn.execute(
            "SELECT COUNT(*) AS c FROM _dashboard_role_test_table"
        ).fetchone()
        assert row["c"] == 0
    finally:
        db_conn.execute("DROP TABLE IF EXISTS _dashboard_role_test_table")
