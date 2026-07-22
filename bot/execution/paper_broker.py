"""
PaperBroker -- see PROGRESS.md for the full design rationale. Summary:

The fill is synthetic and fully computable in memory before any I/O (price
from order.reference_price + slippage, fee from fee_bps). That means
"record the ID" and "record the fill" are the same write, not two: a single
atomic statement (bot.persistence.ledger.record_fill) is the entire
transaction. There is no "pending" row ever written by this broker -- no
crash window leaves an ambiguous half-done order, because there's no gap
between deciding the fill and persisting it.

A future LiveBroker does NOT get this for free: a real venue's fill is not
known before the call, so it needs the classic two-phase
record-pending-then-confirm pattern instead. That's why "pending" exists in
the schema even though this broker never writes it.

This broker computes WHAT the fill is; bot.persistence.ledger owns HOW it's
durably recorded and read back. position() is never trusted from in-memory
state across a restart -- self._positions is a cache, rebuilt from Postgres
(the source of truth) every time this class is constructed, and updated only
in lockstep with a successful durable write using the identical values just
recorded.
"""

from __future__ import annotations
import pandas as pd
import psycopg

from bot.execution.base import Fill, Order
from bot.persistence import ledger


class PaperBroker:
    def __init__(self, conn: psycopg.Connection, fee_bps: float = 10.0, slippage_bps: float = 5.0):
        self._conn = conn
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self._positions: dict[str, float] = {}
        self._rebuild_positions()

    def _rebuild_positions(self) -> None:
        self._positions = ledger.all_positions(self._conn)

    def position(self, symbol: str) -> float:
        return self._positions.get(symbol, 0.0)

    def submit_order(self, order: Order) -> Fill:
        slip_mult = 1 + (self.slippage_bps / 1e4) * (1 if order.side == "buy" else -1)
        filled_price = order.reference_price * slip_mult
        fee = order.qty * filled_price * (self.fee_bps / 1e4)
        filled_ts = order.effective_ts

        row = ledger.record_fill(self._conn, order, filled_price, fee, filled_ts)

        if row is not None:
            self._positions[order.symbol] = self.position(order.symbol) + (
                order.qty if order.side == "buy" else -order.qty
            )
            return self._fill_from_row(order, row, status="filled")

        # Conflict -- either this exact order was already filled in a prior
        # run, or a concurrent submit_order() call won the race just now.
        # Either way: someone already recorded it, don't touch position again.
        existing = ledger.existing_fill(self._conn, order.client_order_id)
        return self._fill_from_row(order, existing, status="duplicate_ignored")

    @staticmethod
    def _fill_from_row(order: Order, row: dict, status: str) -> Fill:
        return Fill(
            client_order_id=row["client_order_id"],
            symbol=row["symbol"],
            side=row["side"],
            qty=row["qty"],
            status=status,
            filled_price=row["price"],
            fee=row["fee"],
            effective_ts=order.effective_ts,  # not stored on fills -- orders owns intent, order is already in scope
            filled_ts=pd.Timestamp(row["filled_ts"]),
        )
