from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from dotenv import load_dotenv

load_dotenv()

from bot.execution.db import ensure_schema, get_connection


@pytest.fixture
def db_conn():
    conn = get_connection(autocommit=True)
    ensure_schema(conn)
    conn.execute("TRUNCATE orders")
    yield conn
    conn.close()
