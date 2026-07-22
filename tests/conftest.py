from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from dotenv import load_dotenv

load_dotenv()

from bot.persistence.db import get_connection
from bot.persistence.migrate import run_migrations


@pytest.fixture
def db_conn():
    conn = get_connection(autocommit=True)
    run_migrations(conn)
    conn.execute(
        "TRUNCATE TABLE fills, orders, reconciliation_checks, risk_events, equity_snapshots "
        "RESTART IDENTITY CASCADE"
    )
    yield conn
    conn.close()
