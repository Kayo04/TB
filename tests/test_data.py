"""
Pagination tests for CcxtDataSource.fetch_history, against a fake exchange
client so these run offline/deterministically -- no real network calls.
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone

import pandas as pd

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
