"""
Owns all reads/writes to orders + fills. PaperBroker (and, later, LiveBroker)
computes WHAT a fill is; this module owns HOW it's durably recorded and read
back -- the split that keeps reconciliation's "independent view" genuinely
independent of the broker's own cache, not just a different name for the
same code path.

record_fill's single statement is what preserves milestone 2's idempotency
guarantee across the orders/fills split: if client_order_id already exists in
orders, the CTE short-circuits and the fills insert writes nothing, in the
same atomic round trip -- no gap between "decided" and "durably recorded".
"""

from __future__ import annotations
import pandas as pd
import psycopg

from bot.execution.base import Order

_RECORD_FILL_SQL = """
WITH new_order AS (
    INSERT INTO orders (client_order_id, strategy_name, symbol, side, qty, status, effective_ts)
    VALUES (%(client_order_id)s, %(strategy_name)s, %(symbol)s, %(side)s, %(qty)s, 'filled', %(effective_ts)s)
    ON CONFLICT (client_order_id) DO NOTHING
    RETURNING client_order_id, symbol, side, qty
)
INSERT INTO fills (client_order_id, symbol, side, qty, price, fee, filled_ts)
SELECT client_order_id, symbol, side, qty, %(price)s, %(fee)s, %(filled_ts)s
FROM new_order
RETURNING *;
"""


def record_fill(
    conn: psycopg.Connection,
    order: Order,
    price: float,
    fee: float,
    filled_ts: pd.Timestamp,
) -> dict | None:
    """
    Returns the new fills row, or None if client_order_id was already
    recorded (by this call or a concurrent one) -- caller falls back to
    existing_fill().
    """
    return conn.execute(
        _RECORD_FILL_SQL,
        {
            "client_order_id": order.client_order_id,
            "strategy_name": order.strategy_name,
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
            "effective_ts": order.effective_ts.to_pydatetime(),
            "price": price,
            "fee": fee,
            "filled_ts": filled_ts.to_pydatetime(),
        },
    ).fetchone()


def existing_fill(conn: psycopg.Connection, client_order_id: str) -> dict | None:
    return conn.execute(
        "SELECT * FROM fills WHERE client_order_id = %s", (client_order_id,)
    ).fetchone()


def position_from_ledger(conn: psycopg.Connection, symbol: str) -> float:
    """Fresh fold over fills, from scratch -- no cache. This IS the source of truth."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN side = 'buy' THEN qty ELSE -qty END), 0) AS position
        FROM fills WHERE symbol = %s
        """,
        (symbol,),
    ).fetchone()
    return float(row["position"])


def all_positions(conn: psycopg.Connection) -> dict[str, float]:
    """Same fold as position_from_ledger, grouped across all symbols -- used to rebuild a broker's cache on startup."""
    rows = conn.execute(
        """
        SELECT symbol, COALESCE(SUM(CASE WHEN side = 'buy' THEN qty ELSE -qty END), 0) AS position
        FROM fills GROUP BY symbol
        """
    ).fetchall()
    return {row["symbol"]: float(row["position"]) for row in rows}


def fills_for(conn: psycopg.Connection, symbol: str) -> list[dict]:
    return conn.execute(
        "SELECT * FROM fills WHERE symbol = %s ORDER BY filled_ts", (symbol,)
    ).fetchall()
