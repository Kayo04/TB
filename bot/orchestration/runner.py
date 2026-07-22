"""
LiveRunner ties every existing piece into one process: bar-aligned loop
consuming MarketDataSource.stream() as its clock, one cycle per closed bar,
wired straight through Strategy -> transitions -> RiskGate -> reconciliation
-> risk checks -> run_log. No new decision logic -- see PROGRESS.md for the
full design rationale.

The rolling OHLCV buffer is deliberately NOT persisted -- it's cheap to
rebuild from public history on every start (cold or restart) via
seed_from_history(), unlike positions/orders/halt state, which live in
Postgres because they can't be safely re-derived from a public feed.

The actual cycle body (_run_cycle_sync) is synchronous -- Strategy.compute_signal
and every persistence/risk call are sync, so there's nothing to `await`
inside it. It's run via asyncio.to_thread() so that asyncio.wait_for()'s
per-cycle timeout is actually enforceable: a plain sync call inside an
`async def` with no internal await points can't be preempted by wait_for --
it would just block the event loop until it returns, making the timeout a
no-op. A cycle that genuinely hangs past the timeout leaves its worker thread
running in the background (Python threads can't be force-killed) --
run_forever records that cycle as failed itself the moment the timeout
fires (see the TimeoutError branch below), since the abandoned thread's own
finally block hasn't run yet and may not for a while. The abandoned thread
still eventually completes on its own and writes ITS OWN run_log row when
it does (a second, later row for the same bar) -- reflecting whatever it
actually did, success or failure, not the fact that the loop had already
given up on it. In the pathological worst case that includes a real
submit_order() call landing "out of band" after the loop moved on. Given
cycles are bar-aligned roughly an hour apart and the timeout default is
30s, the odds of that abandoned thread still being alive -- and racing the
next cycle's use of the shared connection -- when the next bar arrives are
negligible in practice, but it's a real, undefended race in the
pathological case. Documented, not hidden; not fixed here.

Cycle-level failures (including a timeout) are caught inside run_forever's
inner loop and never escape to the outer stream-reconnect logic -- a bad
cycle just means skip this bar, not reconnect. Only a genuine failure of
stream() itself (connection drop, etc.) triggers the outer backoff/
reconnect loop. Both `except` clauses catch Exception, not BaseException --
asyncio.CancelledError must propagate untouched for the loop to be
cancellable at all.
"""

from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import psycopg

from bot.data.base import Bar, MarketDataSource
from bot.execution.base import Broker, Transition
from bot.execution.transitions import order_from_transition
from bot.persistence.reconciliation import ExternalPositionSource, reconcile
from bot.risk import checks, kill_switch
from bot.risk.base import RiskLimits
from bot.risk.gate import MarkPriceSource
from bot.strategy.base import Strategy
from bot.orchestration.alerts import AlertSink
from bot.orchestration.run_log import record_cycle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunnerConfig:
    cycle_timeout_seconds: float = 30.0
    stream_reconnect_base_delay: float = 5.0
    stream_reconnect_max_delay: float = 300.0


class LiveRunner:
    def __init__(
        self,
        data_source: MarketDataSource,
        strategy: Strategy,
        symbol: str,
        timeframe: str,
        broker: Broker,
        conn: psycopg.Connection,
        mark_prices: MarkPriceSource,
        limits: RiskLimits,
        external: ExternalPositionSource,
        alert_sink: AlertSink,
        config: Optional[RunnerConfig] = None,
    ):
        self.data_source = data_source
        self.strategy = strategy
        self.symbol = symbol
        self.timeframe = timeframe
        self.broker = broker
        self.conn = conn
        self.mark_prices = mark_prices
        self.limits = limits
        self.external = external
        self.alert_sink = alert_sink
        self.config = config or RunnerConfig()
        self._timeframe_delta = pd.Timedelta(timeframe)
        self._buffer_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        self._buffer_df.index.name = "ts"

    # ------------------------------------------------------------------ #
    # Startup
    # ------------------------------------------------------------------ #

    def seed_from_history(self) -> None:
        warmup = self.strategy.warmup_bars()
        since = datetime.now(timezone.utc) - warmup * self._timeframe_delta
        df = self.data_source.fetch_history(self.symbol, self.timeframe, since=since)
        self._buffer_df = df.iloc[-warmup:] if len(df) > warmup else df

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #

    async def run_forever(self) -> None:
        delay = self.config.stream_reconnect_base_delay
        while True:
            try:
                async for bar in self.data_source.stream(self.symbol, self.timeframe):
                    try:
                        await asyncio.wait_for(
                            self.run_cycle(bar), timeout=self.config.cycle_timeout_seconds
                        )
                    except asyncio.TimeoutError:
                        # The awaited to_thread() call gave up -- the worker
                        # thread is still running _run_cycle_sync and hasn't
                        # reached its own finally block yet (and may not for
                        # a while). Nothing else will record this cycle as
                        # failed, so do it here, immediately and durably,
                        # rather than leaving the outcome to depend on
                        # whatever that abandoned thread eventually does.
                        logger.error(
                            "cycle TIMED OUT for bar %s after %.1fs", bar.ts, self.config.cycle_timeout_seconds
                        )
                        record_cycle(
                            self.conn,
                            bar_ts=bar.ts,
                            symbol=self.symbol,
                            signal=None,
                            decision="cycle_failed",
                            order_status=None,
                            reason=f"cycle timed out after {self.config.cycle_timeout_seconds}s",
                            reconciliation_divergent=None,
                            halted_after=kill_switch.is_halted(self.conn),
                            cycle_duration_ms=int(self.config.cycle_timeout_seconds * 1000),
                        )
                    except Exception as exc:
                        # _run_cycle_sync ran synchronously to completion (in
                        # its worker thread) and its own finally block
                        # already wrote a run_log row before re-raising --
                        # logging again here would just duplicate it.
                        logger.error("cycle failed for bar %s: %r", bar.ts, exc)
                    delay = self.config.stream_reconnect_base_delay
            except Exception as exc:
                logger.error("stream failed: %r -- reconnecting in %.0fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.config.stream_reconnect_max_delay)

    # ------------------------------------------------------------------ #
    # One cycle
    # ------------------------------------------------------------------ #

    async def run_cycle(self, bar: Bar) -> None:
        await asyncio.to_thread(self._run_cycle_sync, bar)

    def _append_bar(self, bar: Bar) -> None:
        row = pd.DataFrame(
            [[bar.open, bar.high, bar.low, bar.close, bar.volume]],
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([bar.ts], name="ts"),
        )
        self._buffer_df = pd.concat([self._buffer_df, row])
        self._buffer_df = self._buffer_df[~self._buffer_df.index.duplicated(keep="last")].sort_index()
        warmup = self.strategy.warmup_bars()
        if len(self._buffer_df) > warmup:
            self._buffer_df = self._buffer_df.iloc[-warmup:]

    def _run_cycle_sync(self, bar: Bar) -> None:
        start = time.monotonic()
        was_halted = kill_switch.is_halted(self.conn)
        signal: Optional[int] = None
        decision = "cycle_failed"
        order_status: Optional[str] = None
        reason: Optional[str] = None
        divergent: Optional[bool] = None
        try:
            self._append_bar(bar)
            signal_series = self.strategy.compute_signal(self._buffer_df)
            signal = int(signal_series.iloc[-1])
            self.mark_prices.set(self.symbol, bar.close)

            prior = int(self.broker.position(self.symbol))
            if signal != prior:
                effective_ts = bar.ts + self._timeframe_delta
                transition = Transition(self.symbol, effective_ts, prior, signal)
                order = order_from_transition(transition, self.strategy.name, reference_price=bar.close)
                fill = self.broker.submit_order(order)
                decision = "order_submitted"
                order_status = fill.status
                reason = fill.reason
            else:
                decision = "no_transition"

            divergences = reconcile(self.conn, self.broker, self.external, [self.symbol])
            checks.handle_reconciliation(self.conn, divergences)
            divergent = bool(divergences)

            checks.check_daily_drawdown(self.conn, self.broker, self.limits, self.mark_prices.prices())
        except Exception as exc:
            reason = f"{reason + ' | ' if reason else ''}cycle error: {exc!r}"
            raise
        finally:
            is_halted_now = kill_switch.is_halted(self.conn)
            duration_ms = int((time.monotonic() - start) * 1000)
            record_cycle(
                self.conn,
                bar_ts=bar.ts,
                symbol=self.symbol,
                signal=signal,
                decision=decision,
                order_status=order_status,
                reason=reason,
                reconciliation_divergent=divergent,
                halted_after=is_halted_now,
                cycle_duration_ms=duration_ms,
            )
            if is_halted_now and not was_halted:
                self.alert_sink.send(
                    f"KILL SWITCH TRIPPED for {self.symbol}: halted after cycle at bar {bar.ts}"
                )
            logger.info(
                "cycle bar=%s signal=%s decision=%s order_status=%s divergent=%s halted=%s duration_ms=%d",
                bar.ts, signal, decision, order_status, divergent, is_halted_now, duration_ms,
            )
