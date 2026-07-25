"""
Pagination tests for CcxtDataSource.fetch_history, against a fake exchange
client so these run offline/deterministically -- no real network calls.
Also covers the live _stream_ws newUpdates-truncation regression (see
test_watch_ohlcv_newUpdates_truncation_no_longer_stalls_bar_close below).
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd

from bot.data import ccxt_source as ccxt_source_module
from bot.data.ccxt_source import CcxtDataSource


class _FakeExchange:
    """Mimics the subset of a ccxt exchange client fetch_history relies on."""

    rateLimit = 0  # no sleep in tests

    def __init__(self, rows, timeframe_seconds=3600):
        self.rows = rows
        self.timeframe_seconds = timeframe_seconds
        self.calls = 0

    def parse_timeframe(self, timeframe):
        return self.timeframe_seconds

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        self.calls += 1
        return [r for r in self.rows if r[0] >= since][:limit]


def _make_rows(n, start_ms, step_ms):
    return [[start_ms + i * step_ms, 1.0, 1.0, 1.0, float(i), 1.0] for i in range(n)]


def _source_with_fake(rows, timeframe_seconds=3600):
    source = CcxtDataSource(exchange="binance")
    source._sync_exchange = _FakeExchange(rows, timeframe_seconds=timeframe_seconds)
    return source


def test_fetch_history_paginates_past_single_request_cap():
    step_ms = 3600 * 1000
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    start_ms = int(start.timestamp() * 1000)
    rows = _make_rows(2500, start_ms, step_ms)  # 2.5x a single 1000-row page

    source = _source_with_fake(rows)
    until = start + timedelta(milliseconds=step_ms * 2499)

    df = source.fetch_history("BTC/USDT", "1h", since=start, until=until)

    assert len(df) == 2500
    assert df.index.is_monotonic_increasing
    assert not df.index.duplicated().any()
    assert source._sync_exchange.calls >= 3  # had to actually paginate


def test_fetch_history_dedupes_and_sorts():
    step_ms = 3600 * 1000
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    start_ms = int(start.timestamp() * 1000)
    rows = _make_rows(1500, start_ms, step_ms)

    source = _source_with_fake(rows)
    until = start + timedelta(milliseconds=step_ms * 1499)

    df = source.fetch_history("BTC/USDT", "1h", since=start, until=until)

    assert len(df) == 1500
    assert df.index[0] == pd.Timestamp(start)
    assert df.index[-1] == pd.Timestamp(until)


def test_fetch_history_stops_when_exchange_has_no_more_data():
    step_ms = 3600 * 1000
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    start_ms = int(start.timestamp() * 1000)
    rows = _make_rows(50, start_ms, step_ms)  # far less than requested

    source = _source_with_fake(rows)
    until = start + timedelta(days=365)  # ask for way more than exists

    df = source.fetch_history("BTC/USDT", "1h", since=start, until=until)

    assert len(df) == 50


# --------------------------------------------------------------------------- #
# Regression: ccxt.pro's newUpdates=True default truncated watch_ohlcv() to a
# single candle per call, so len(candles) < 2 was true forever and no bar
# close was ever detected in a real long-running bot. Confirmed by reading
# the installed ccxt==4.5.67 source (ArrayCache.getLimit /
# watch_ohlcv_for_symbols): with newUpdates truthy, the returned window is
# capped to the count of *new* updates since the previous call -- normally 1
# per websocket push -- regardless of any limit passed in. The fix in
# CcxtDataSource._stream_ws sets ex.newUpdates = False and passes an
# explicit limit, restoring the full cached window. This fake reproduces
# that exact truncation semantics so the test fails again (times out) if
# the fix is ever reverted.
# --------------------------------------------------------------------------- #

class _FakeCcxtProWatchOhlcvTruncating:
    """
    Mimics ccxt.pro's real watch_ohlcv cache: overwrites the last entry
    in-place while a candle's timestamp is unchanged (still forming),
    appends a new entry once the timestamp advances (previous candle just
    closed). When newUpdates is true (ccxt.pro's real default) only the
    single most-recently-touched entry is returned, no matter what limit is
    requested -- the actual cause of the bug. When newUpdates is false, the
    last `limit` entries of the accumulated cache are returned instead.
    """

    has = {"watchOHLCV": True}

    def __init__(self, updates: list[list]):
        self._updates = updates
        self._next_index = 0
        self._cache: list[list] = []
        self.newUpdates = True  # ccxt.pro's real default -- the dangerous one
        self.closed = False

    async def watch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        if self._next_index < len(self._updates):
            row = self._updates[self._next_index]
            self._next_index += 1
            if self._cache and self._cache[-1][0] == row[0]:
                self._cache[-1] = row  # tick update to the still-forming candle
            else:
                self._cache.append(row)  # timestamp advanced -> previous candle closed
        await asyncio.sleep(0)  # behave like a real await point
        if self.newUpdates:
            return self._cache[-1:] if self._cache else []
        if limit is not None:
            return self._cache[-limit:]
        return list(self._cache)

    async def close(self):
        self.closed = True


def test_watch_ohlcv_newUpdates_truncation_no_longer_stalls_bar_close(monkeypatch):
    step_ms = 3600 * 1000
    base_ms = 1_700_000_000_000
    # Two ticks updating the still-forming candle at `base_ms`, then the
    # timestamp advances -- the moment the real bug meant would NEVER be
    # detected, because every call kept returning exactly one candle.
    updates = [
        [base_ms, 100.0, 100.0, 100.0, 100.0, 1.0],
        [base_ms, 100.0, 101.0, 99.0, 101.0, 1.5],
        [base_ms + step_ms, 101.0, 102.0, 101.0, 102.0, 2.0],
    ]
    fake = _FakeCcxtProWatchOhlcvTruncating(updates)
    monkeypatch.setattr(ccxt_source_module.ccxtpro, "binance", lambda: fake)

    source = CcxtDataSource(exchange="binance")

    async def _first_bar():
        async for bar in source.stream("BTC/USDT", "1h"):
            return bar

    bar = asyncio.run(asyncio.wait_for(_first_bar(), timeout=2.0))

    assert bar is not None, "a bar close must be detected despite newUpdates-style truncation"
    assert bar.ts == pd.Timestamp(base_ms, unit="ms", tz="UTC")
    assert bar.close == 101.0  # last tick to the candle before it closed
    assert fake.newUpdates is False, "the fix must disable newUpdates before watching, not just pass a limit"
