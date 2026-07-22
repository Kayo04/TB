"""
Market data interface — Milestone 1.

One abstraction for historical (backtest) and live (paper/future-live) OHLCV,
so the rest of the system (strategy, backtest engine, eventually the live
runner) never talks to an exchange library directly. Swapping market
(crypto -> stocks/ETFs) or venue is a new module implementing this Protocol,
nothing else changes.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Optional, Protocol
import pandas as pd


@dataclass(frozen=True)
class Bar:
    ts: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataSource(Protocol):
    def fetch_history(
        self,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Historical OHLCV from `since` to `until` (default: now), paginated
        internally so callers aren't limited by a single request's cap.
        Returns a DataFrame indexed by ts (UTC), sorted ascending, deduped,
        columns: open, high, low, close, volume.
        """
        ...

    async def stream(self, symbol: str, timeframe: str) -> AsyncIterator[Bar]:
        """
        Yields bars in real time as they close. Never yields the currently
        forming (incomplete) bar — that would be the live-data equivalent of
        look-ahead bias, letting a strategy see a bar before it's actually
        finished.
        """
        ...
