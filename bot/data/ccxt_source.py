"""
CcxtDataSource — concrete MarketDataSource backed by ccxt.

Historical: REST, since-paginated (loops fetch_ohlcv, advancing `since` past
the last returned bar each round) so callers aren't capped at one request's
limit (~1000 bars on binance).

Live: verified at build time (2026-07-22) that ccxt.pro's watch_ohlcv works
for binance public OHLCV with no API key and no license gate — see
PROGRESS.md. Used as the primary path. If an exchange/timeframe combination
doesn't support watchOHLCV (has["watchOHLCV"] is False), falls back to REST
short-polling at each bar-close boundary, behind the exact same stream()
interface — callers can't tell which path is active.
"""

from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import ccxt
import pandas as pd

from bot.data.base import Bar

try:
    import ccxt.pro as ccxtpro
    _HAS_CCXT_PRO = True
except ImportError:
    _HAS_CCXT_PRO = False

logger = logging.getLogger(__name__)


def _to_utc_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


class CcxtDataSource:
    def __init__(self, exchange: str = "binance"):
        self.exchange_id = exchange
        self._sync_exchange = getattr(ccxt, exchange)()

    # ---------------------------------------------------------------- #
    # Historical
    # ---------------------------------------------------------------- #

    def fetch_history(
        self,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: Optional[datetime] = None,
    ) -> pd.DataFrame:
        until = until or datetime.now(timezone.utc)
        since_ms = _to_utc_ms(since)
        until_ms = _to_utc_ms(until)
        tf_ms = self._sync_exchange.parse_timeframe(timeframe) * 1000

        rows: list[list] = []
        seen_ts: set[int] = set()
        cursor = since_ms

        while cursor < until_ms:
            batch = self._sync_exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=1000)
            if not batch:
                break
            for row in batch:
                if row[0] not in seen_ts and row[0] <= until_ms:
                    seen_ts.add(row[0])
                    rows.append(row)

            last_ts = batch[-1][0]
            if last_ts <= cursor:
                break  # exchange isn't advancing -> stop instead of looping forever
            cursor = last_ts + tf_ms

            if len(batch) < 1000:
                break  # short batch -> caught up to the exchange's latest data

            time.sleep(self._sync_exchange.rateLimit / 1000)

        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.drop_duplicates(subset="ts").sort_values("ts").set_index("ts")

        since_tz = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        until_tz = until if until.tzinfo else until.replace(tzinfo=timezone.utc)
        return df[(df.index >= since_tz) & (df.index <= until_tz)]

    # ---------------------------------------------------------------- #
    # Live
    # ---------------------------------------------------------------- #

    def _supports_watch_ohlcv(self) -> bool:
        if not _HAS_CCXT_PRO:
            return False
        if not hasattr(ccxtpro, self.exchange_id):
            return False
        probe = getattr(ccxtpro, self.exchange_id)()
        supported = bool(probe.has.get("watchOHLCV"))
        return supported

    async def stream(self, symbol: str, timeframe: str) -> AsyncIterator[Bar]:
        use_ws = self._supports_watch_ohlcv()
        logger.info("stream(%s, %s): using %s", symbol, timeframe, "websocket" if use_ws else "REST polling")
        if use_ws:
            async for bar in self._stream_ws(symbol, timeframe):
                yield bar
        else:
            async for bar in self._stream_poll(symbol, timeframe):
                yield bar

    async def _stream_ws(self, symbol: str, timeframe: str) -> AsyncIterator[Bar]:
        ex = getattr(ccxtpro, self.exchange_id)()
        last_emitted_ts: Optional[int] = None
        first_call = True
        try:
            while True:
                if first_call:
                    logger.info("_stream_ws: awaiting first watch_ohlcv(%s, %s)", symbol, timeframe)
                candles = await ex.watch_ohlcv(symbol, timeframe)
                if first_call:
                    logger.info("_stream_ws: first watch_ohlcv() resolved with %d candles", len(candles))
                    first_call = False
                if len(candles) < 2:
                    continue
                closed = candles[:-1]  # last element is the still-forming bar
                for row in closed:
                    ts_ms = row[0]
                    if last_emitted_ts is not None and ts_ms <= last_emitted_ts:
                        continue
                    last_emitted_ts = ts_ms
                    yield Bar(
                        ts=pd.Timestamp(ts_ms, unit="ms", tz="UTC"),
                        open=row[1], high=row[2], low=row[3], close=row[4], volume=row[5],
                    )
        finally:
            await ex.close()

    async def _stream_poll(self, symbol: str, timeframe: str) -> AsyncIterator[Bar]:
        tf_seconds = self._sync_exchange.parse_timeframe(timeframe)
        last_emitted_ts: Optional[int] = None
        logger.info("_stream_poll: polling %s %s every %.0fs", symbol, timeframe, min(tf_seconds / 4, 30))
        while True:
            batch = self._sync_exchange.fetch_ohlcv(symbol, timeframe, limit=2)
            if len(batch) >= 2:
                row = batch[-2]  # last element may still be forming; -2 is the last closed bar
                ts_ms = row[0]
                if last_emitted_ts is None or ts_ms > last_emitted_ts:
                    last_emitted_ts = ts_ms
                    yield Bar(
                        ts=pd.Timestamp(ts_ms, unit="ms", tz="UTC"),
                        open=row[1], high=row[2], low=row[3], close=row[4], volume=row[5],
                    )
            await asyncio.sleep(min(tf_seconds / 4, 30))
