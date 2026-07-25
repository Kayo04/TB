"""
Runs against the real trading_bot Postgres container, same as the other
Postgres-backed test files. Test doubles for Strategy/MarketDataSource are
used deliberately -- orchestration only depends on the Strategy Protocol
(not any concrete strategy) and the MarketDataSource Protocol, so testing
against conformant doubles is the more honest test of the decoupling than
importing MACrossoverStrategy/CcxtDataSource would be.
"""

from __future__ import annotations
import asyncio
import time

import pandas as pd
import pytest

from bot.data.base import Bar
from bot.execution.base import Transition
from bot.execution.paper_broker import PaperBroker
from bot.execution.transitions import order_from_transition
from bot.persistence.reconciliation import LedgerPositionSource
from bot.risk.base import RiskLimits
from bot.risk.gate import RiskGate, StaticMarkPriceSource
from bot.orchestration.alerts import LogAlertSink
from bot.orchestration.runner import LiveRunner, RunnerConfig

SYMBOL = "BTC/USDT"


class ScriptedStrategy:
    """compute_signal returns a caller-controlled signal per bar timestamp."""
    name = "scripted"

    def __init__(self, warmup: int, signals: dict[pd.Timestamp, int]):
        self._warmup = warmup
        self._signals = signals

    def warmup_bars(self) -> int:
        return self._warmup

    def compute_signal(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series([self._signals.get(ts, 0) for ts in df.index], index=df.index)


class BrokenStrategy:
    name = "broken"

    def warmup_bars(self) -> int:
        return 1

    def compute_signal(self, df: pd.DataFrame) -> pd.Series:
        raise RuntimeError("simulated strategy failure")


class HangingStrategy:
    """compute_signal blocks the calling (background) thread for hang_seconds."""
    name = "hanging"

    def __init__(self, warmup: int, hang_seconds: float):
        self._warmup = warmup
        self._hang_seconds = hang_seconds

    def warmup_bars(self) -> int:
        return self._warmup

    def compute_signal(self, df: pd.DataFrame) -> pd.Series:
        time.sleep(self._hang_seconds)
        return pd.Series([0] * len(df), index=df.index)


class FakeDataSource:
    def __init__(self, bars: list[Bar]):
        self._bars = bars

    def fetch_history(self, symbol, timeframe, since, until=None):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    async def stream(self, symbol, timeframe):
        for bar in self._bars:
            yield bar


class HangingDataSource:
    """stream() never yields and never raises on its first open -- simulating a
    websocket connection that silently dies (no exception, no data), exactly
    what a naive await could block on forever. Every open after the first
    behaves normally, so a test can prove reconnection actually recovers."""

    def __init__(self, bars_after_hang: list[Bar]):
        self._bars_after_hang = bars_after_hang
        self.open_count = 0

    def fetch_history(self, symbol, timeframe, since, until=None):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    async def stream(self, symbol, timeframe):
        self.open_count += 1
        if self.open_count == 1:
            await asyncio.sleep(3600)  # never resolves within any real test window
            return
        for bar in self._bars_after_hang:
            yield bar


def _bar(ts: str, close: float = 100.0) -> Bar:
    return Bar(ts=pd.Timestamp(ts), open=close, high=close + 1, low=close - 1, close=close, volume=1.0)


def _make_runner(strategy, db_conn, data_source=None, limits=None, config=None) -> LiveRunner:
    mark_prices = StaticMarkPriceSource()
    limits = limits or RiskLimits()
    broker = RiskGate(PaperBroker(db_conn), db_conn, limits, mark_prices)
    return LiveRunner(
        data_source=data_source,
        strategy=strategy,
        symbol=SYMBOL,
        timeframe="1h",
        broker=broker,
        conn=db_conn,
        mark_prices=mark_prices,
        limits=limits,
        external=LedgerPositionSource(db_conn),
        alert_sink=LogAlertSink(),
        config=config,
    ), broker


# --------------------------------------------------------------------------- #
# Fail-closed: a cycle-level failure skips the bar, submits nothing, still logs
# --------------------------------------------------------------------------- #

def test_cycle_failure_skips_bar_no_order_submitted_but_still_logged(db_conn):
    bar = _bar("2024-01-01T00:00:00Z")
    runner, broker = _make_runner(BrokenStrategy(), db_conn)

    with pytest.raises(RuntimeError, match="simulated strategy failure"):
        asyncio.run(runner.run_cycle(bar))

    fill_count = db_conn.execute("SELECT COUNT(*) AS c FROM fills").fetchone()["c"]
    order_count = db_conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
    assert fill_count == 0, "a cycle that raises must never submit an order"
    assert order_count == 0

    row = db_conn.execute(
        "SELECT * FROM run_log WHERE bar_ts = %s", (bar.ts.to_pydatetime(),)
    ).fetchone()
    assert row is not None, "run_log must be written even when the cycle raises"
    assert row["decision"] == "cycle_failed"
    assert "simulated strategy failure" in row["reason"]
    assert row["signal"] is None
    assert row["halted_after"] is False


# --------------------------------------------------------------------------- #
# Restart resumes from durable state, no duplicate order
# --------------------------------------------------------------------------- #

def test_restart_resumes_from_durable_state_no_duplicate_order(db_conn):
    bar = _bar("2024-01-01T00:00:00Z")
    strategy1 = ScriptedStrategy(warmup=1, signals={bar.ts: 1})
    limits = RiskLimits(max_position_size=10.0)

    runner1, broker1 = _make_runner(strategy1, db_conn, limits=limits)
    asyncio.run(runner1.run_cycle(bar))
    assert broker1.position(SYMBOL) == pytest.approx(1.0)

    row1 = db_conn.execute(
        "SELECT * FROM run_log WHERE bar_ts = %s", (bar.ts.to_pydatetime(),)
    ).fetchone()
    assert row1["decision"] == "order_submitted"
    assert row1["order_status"] == "filled"

    # --- simulate a process restart: brand new broker + runner, no shared in-memory state ---
    strategy2 = ScriptedStrategy(warmup=1, signals={bar.ts: 1})
    runner2, broker2 = _make_runner(strategy2, db_conn, limits=limits)
    assert broker2.position(SYMBOL) == pytest.approx(1.0), "position must be rebuilt from the ledger on restart"

    # Worst case: the exact same bar gets reprocessed after restart. Because
    # position was correctly rebuilt, signal(1) == prior(1) -- no transition
    # is even attempted, let alone a duplicate order.
    asyncio.run(runner2.run_cycle(bar))
    assert broker2.position(SYMBOL) == pytest.approx(1.0)
    fill_count = db_conn.execute(
        "SELECT COUNT(*) AS c FROM fills WHERE symbol = %s", (SYMBOL,)
    ).fetchone()["c"]
    assert fill_count == 1, "reprocessing the same bar after 'restart' must not double the fill"

    row2 = db_conn.execute(
        "SELECT * FROM run_log WHERE bar_ts = %s ORDER BY run_log_id DESC LIMIT 1", (bar.ts.to_pydatetime(),)
    ).fetchone()
    assert row2["decision"] == "no_transition"

    # Belt-and-braces: even if a bug caused the identical transition to be
    # resubmitted directly, milestone 2/3's deterministic client_order_id
    # dedup (not new orchestration logic) makes it a safe no-op.
    replay_order = order_from_transition(
        Transition(SYMBOL, bar.ts + pd.Timedelta("1h"), 0, 1), strategy1.name, reference_price=bar.close
    )
    replay_fill = broker2.submit_order(replay_order)
    assert replay_fill.status == "duplicate_ignored"
    assert broker2.position(SYMBOL) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Hung cycle hits its timeout, loop moves on to the next bar
# --------------------------------------------------------------------------- #

def test_hung_cycle_hits_timeout_and_loop_moves_on(db_conn):
    bar1 = _bar("2024-01-01T00:00:00Z")
    bar2 = _bar("2024-01-01T01:00:00Z")
    data_source = FakeDataSource([bar1, bar2])
    config = RunnerConfig(
        cycle_timeout_seconds=0.2, stream_reconnect_base_delay=0.05, stream_reconnect_max_delay=0.1
    )
    strategy = HangingStrategy(warmup=1, hang_seconds=1.0)
    runner, _broker = _make_runner(strategy, db_conn, data_source=data_source, config=config)

    try:
        asyncio.run(asyncio.wait_for(runner.run_forever(), timeout=1.5))
    except asyncio.TimeoutError:
        pass  # expected -- run_forever() never returns on its own; we just bounded the test

    # Earliest-recorded row per bar_ts reflects the immediate timeout outcome.
    # A timed-out cycle's worker thread keeps running in the background
    # (documented in runner.py) and eventually finishes on its own, writing
    # its OWN later run_log row -- that's real, expected behaviour, not
    # something to assert against here; we only care what happened first.
    rows = db_conn.execute("SELECT bar_ts, decision FROM run_log ORDER BY created_at ASC").fetchall()
    first_decision: dict[pd.Timestamp, str] = {}
    for r in rows:
        ts = pd.Timestamp(r["bar_ts"])
        first_decision.setdefault(ts, r["decision"])

    assert bar1.ts in first_decision, "the hung cycle for bar1 must still produce a run_log row"
    assert bar2.ts in first_decision, "the loop must move on to bar2 instead of getting stuck on bar1's timeout"
    assert first_decision[bar1.ts] == "cycle_failed"
    assert first_decision[bar2.ts] == "cycle_failed"


# --------------------------------------------------------------------------- #
# A stream that silently never yields (no exception, no data) times out and
# reconnects -- instead of hanging forever, which is what happened for real
# for 2+ hours before this fix (a hung watch_ohlcv() call with no timeout
# around waiting for the next bar, only around processing one already received).
# --------------------------------------------------------------------------- #

def test_stream_hang_times_out_and_triggers_reconnect(db_conn):
    bar = _bar("2024-01-01T00:00:00Z")
    data_source = HangingDataSource(bars_after_hang=[bar])
    config = RunnerConfig(
        cycle_timeout_seconds=0.2,
        stream_reconnect_base_delay=0.05,
        stream_reconnect_max_delay=0.1,
        stream_wait_timeout_seconds=0.2,  # override: a real timeframe-scaled wait is untestable
    )
    strategy = ScriptedStrategy(warmup=1, signals={bar.ts: 0})
    runner, _broker = _make_runner(strategy, db_conn, data_source=data_source, config=config)

    try:
        asyncio.run(asyncio.wait_for(runner.run_forever(), timeout=1.0))
    except asyncio.TimeoutError:
        pass  # run_forever() never returns on its own; we just bounded the test

    assert data_source.open_count >= 2, (
        "a stream that never yields must trigger a reconnect (a second stream() open) "
        "instead of blocking run_forever() forever on the first"
    )
    row = db_conn.execute(
        "SELECT * FROM run_log WHERE bar_ts = %s", (bar.ts.to_pydatetime(),)
    ).fetchone()
    assert row is not None, "after reconnecting, the loop must actually resume processing real bars"
    assert row["decision"] == "no_transition"
