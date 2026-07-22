"""
Postgres connection + schema for the execution layer's order store.

Minimal orders table, not the full milestone-3 ledger/positions/reconciliation
schema -- just enough for atomic dedupe (client_order_id UNIQUE) and position
reconstruction after a restart (symbol/side/qty). "pending" status is reserved
for a future LiveBroker; PaperBroker never writes it (see base.py).
"""

from __future__ import annotations
import os
import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    client_order_id TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty             DOUBLE PRECISION NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('pending', 'filled', 'rejected')),
    filled_price    DOUBLE PRECISION,
    fee             DOUBLE PRECISION,
    effective_ts    TIMESTAMPTZ NOT NULL,
    filled_ts       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def get_connection(autocommit: bool = True) -> psycopg.Connection:
    dsn = os.environ["DATABASE_URL"]
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=autocommit)


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_SQL)
