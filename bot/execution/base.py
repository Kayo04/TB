"""
Execution interface — Milestone 2.

Strategy never imports anything here, and the backtest engine doesn't either:
this layer answers "does the system run reliably," a different question from
"does this strategy have edge after costs" (the backtest engine's job).

qty is a fixed placeholder unit for now -- position sizing is the risk layer's
job (milestone 4), not decided here.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional, Protocol
import pandas as pd

Side = Literal["buy", "sell"]

# "pending" is unused by PaperBroker today -- reserved so a future LiveBroker
# (whose fill is NOT known before the venue call) can use it without a schema
# change. See PROGRESS.md for why PaperBroker doesn't need it: its fill is
# synthetic and fully computable before any I/O, so submit+record collapse
# into a single atomic write with no in-between state.
OrderStatus = Literal["pending", "filled", "rejected", "duplicate_ignored"]


@dataclass(frozen=True)
class Transition:
    symbol: str
    effective_ts: pd.Timestamp   # the bar this position takes effect on (mirrors the backtest engine's t+1 shift)
    from_position: int
    to_position: int


@dataclass(frozen=True)
class Order:
    client_order_id: str
    symbol: str
    side: Side
    qty: float
    effective_ts: pd.Timestamp
    reference_price: float       # price the paper fill is simulated against (open of effective_ts bar)


@dataclass(frozen=True)
class Fill:
    client_order_id: str
    symbol: str
    side: Side
    qty: float
    status: OrderStatus
    filled_price: Optional[float]
    fee: Optional[float]
    effective_ts: pd.Timestamp
    filled_ts: Optional[pd.Timestamp]


class Broker(Protocol):
    def submit_order(self, order: Order) -> Fill:
        """
        Idempotent: resubmitting an Order with a client_order_id already
        recorded must return the SAME fill again (status="duplicate_ignored")
        without mutating position a second time.
        """
        ...

    def position(self, symbol: str) -> float:
        """Current position, reconstructed from persisted fills -- never trusted from memory alone."""
        ...
