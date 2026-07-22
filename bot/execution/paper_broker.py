"""
PaperBroker -- see PROGRESS.md for the full design rationale. Summary:

The fill is synthetic and fully computable in memory before any I/O (price
from order.reference_price + slippage, fee from fee_bps). That means
"record the ID" and "record the fill" are the same write, not two: a single
INSERT ... ON CONFLICT DO NOTHING ... RETURNING is the entire transaction.
There is no "pending" row ever written by this broker -- no crash window
leaves an ambiguous half-done order, because there's no gap between deciding
the fill and persisting it.

A future LiveBroker does NOT get this for free: a real venue's fill is not
known before the call, so it needs the classic two-phase
record-pending-then-confirm pattern instead. That's why "pending" exists in
the schema even though this broker never writes it.

position() is never trusted from in-memory state across a restart -- it's
rebuilt from Postgres (the source of truth) every time this class is
constructed.
"""

from __future__ import annotations
import pandas as pd
import psycopg

from bot.execution.base import Fill, Order


class PaperBroker:
    def __init__(self, conn: psycopg.Connection, fee_bps: float = 10.0, slippage_bps: float = 5.0):
        self._conn = conn
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self._positions: dict[str, float] = {}
        self._rebuild_positions()

    def _rebuild_positions(self) -> None:
        rows = self._conn.execute(
            "SELECT symbol, side, qty FROM orders WHERE status = 'filled' ORDER BY filled_ts"
        ).fetchall()
        positions: dict[str, float] = {}
        for row in rows:
            delta = row["qty"] if row["side"] == "buy" else -row["qty"]
            positions[row["symbol"]] = positions.get(row["symbol"], 0.0) + delta
        self._positions = positions

    def position(self, symbol: str) -> float:
        return self._positions.get(symbol, 0.0)

    def submit_order(self, order: Order) -> Fill:
        slip_mult = 1 + (self.slippage_bps / 1e4) * (1 if order.side == "buy" else -1)
        filled_price = order.reference_price * slip_mult
        fee = order.qty * filled_price * (self.fee_bps / 1e4)
        filled_ts = order.effective_ts

        row = self._conn.execute(
            """
            INSERT INTO orders
                (client_order_id, symbol, side, qty, status, filled_price, fee, effective_ts, filled_ts)
            VALUES (%s, %s, %s, %s, 'filled', %s, %s, %s, %s)
            ON CONFLICT (client_order_id) DO NOTHING
            RETURNING *
            """,
            (
                order.client_order_id, order.symbol, order.side, order.qty,
                filled_price, fee, order.effective_ts.to_pydatetime(), filled_ts.to_pydatetime(),
            ),
        ).fetchone()

        if row is not None:
            self._positions[order.symbol] = self.position(order.symbol) + (
                order.qty if order.side == "buy" else -order.qty
            )
            return self._fill_from_row(row, status="filled")

        # Conflict -- either this exact order was already filled in a prior
        # run, or a concurrent submit_order() call won the race just now.
        # Either way: someone already recorded it, don't touch position again.
        existing = self._conn.execute(
            "SELECT * FROM orders WHERE client_order_id = %s", (order.client_order_id,)
        ).fetchone()
        return self._fill_from_row(existing, status="duplicate_ignored")

    @staticmethod
    def _fill_from_row(row: dict, status: str) -> Fill:
        return Fill(
            client_order_id=row["client_order_id"],
            symbol=row["symbol"],
            side=row["side"],
            qty=row["qty"],
            status=status,
            filled_price=row["filled_price"],
            fee=row["fee"],
            effective_ts=pd.Timestamp(row["effective_ts"]),
            filled_ts=pd.Timestamp(row["filled_ts"]) if row["filled_ts"] else None,
        )
