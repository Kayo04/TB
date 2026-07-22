"""
Append-only run_log -- one row per cycle attempt, success or failure. The
durable, queryable history of what the loop actually did, and the intended
data source for the future dashboard. Written from a `finally` block in
LiveRunner so a failed cycle still logs.
"""

from __future__ import annotations
from typing import Optional
import pandas as pd
import psycopg


def record_cycle(
    conn: psycopg.Connection,
    bar_ts: pd.Timestamp,
    symbol: str,
    signal: Optional[int],
    decision: str,
    order_status: Optional[str],
    reason: Optional[str],
    reconciliation_divergent: Optional[bool],
    halted_after: bool,
    cycle_duration_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO run_log
            (bar_ts, symbol, signal, decision, order_status, reason,
             reconciliation_divergent, halted_after, cycle_duration_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            bar_ts.to_pydatetime(),
            symbol,
            signal,
            decision,
            order_status,
            reason,
            reconciliation_divergent,
            halted_after,
            cycle_duration_ms,
        ),
    )
