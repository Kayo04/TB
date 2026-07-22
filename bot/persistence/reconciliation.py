"""
Reconciliation compares two INDEPENDENT views of position and records the
result, always, divergent or not. It detects and reports -- it does not
decide what to do about a divergence. Deciding whether to halt is the risk
layer's job (milestone 4, not built yet); this stays decoupled from that on
purpose, same principle as everywhere else in this project.

In paper mode there's no real exchange, so the "external" view is a fresh,
independent fold of the ledger (LedgerPositionSource) -- bypassing whatever
broker is being checked entirely. This still catches a real bug class: a
broker's in-memory position cache silently drifting from what's actually
durably recorded. A future LiveBroker's external truth is the venue's own
account state; VenuePositionSource (via ccxt) would implement the same
ExternalPositionSource protocol so reconcile() doesn't change when live
execution exists -- only which concrete source gets passed in. Note for that
day: spot crypto has wallet balances, not a "position" field the way futures
do, so that translation lives inside VenuePositionSource, not here.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import pandas as pd
import psycopg

from bot.execution.base import Broker
from bot.persistence.ledger import position_from_ledger


class ExternalPositionSource(Protocol):
    def position(self, symbol: str) -> float: ...


class LedgerPositionSource:
    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def position(self, symbol: str) -> float:
        return position_from_ledger(self._conn, symbol)


@dataclass(frozen=True)
class Divergence:
    symbol: str
    internal_position: float
    external_position: float
    difference: float
    checked_at: pd.Timestamp


def reconcile(
    conn: psycopg.Connection,
    broker: Broker,
    external: ExternalPositionSource,
    symbols: list[str],
    tolerance: float = 1e-9,
) -> list[Divergence]:
    divergences: list[Divergence] = []
    checked_at = pd.Timestamp.now(tz="UTC")

    for symbol in symbols:
        internal = broker.position(symbol)
        ext = external.position(symbol)
        diff = internal - ext
        is_divergent = abs(diff) > tolerance

        conn.execute(
            """
            INSERT INTO reconciliation_checks
                (symbol, internal_position, external_position, difference, is_divergent, checked_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (symbol, internal, ext, diff, is_divergent, checked_at.to_pydatetime()),
        )

        if is_divergent:
            divergences.append(Divergence(symbol, internal, ext, diff, checked_at))

    return divergences
