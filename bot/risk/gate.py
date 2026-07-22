"""
RiskGate wraps a Broker and IS a Broker (same protocol: submit_order,
position) -- a caller holds "a Broker" without knowing or caring whether
it's raw or risk-wrapped, the same seam PaperBroker/LiveBroker already
share and ExternalPositionSource already uses for reconciliation.

submit_order() runs, in order: the kill-switch check, then per-order checks
(max position size, max orders per period), then the daily-drawdown check.
Drawdown is portfolio-level, not really "about" this particular order --
it's evaluated here only because there's no periodic orchestration loop yet
to call it independently. Milestone 5's loop should also call
checks.check_daily_drawdown on its own cadence, not only piggybacked on
order submission.

The whole evaluation is wrapped in one try/except: ANY exception raised by
ANY check is caught here and converted into a blocked decision -- never
re-raised, never treated as an implicit allow. This is the enforcement
point for "when in doubt, stop" on the order-submission path;
kill_switch.is_halted() enforces the same principle for reading halt state
itself.

mark_prices is supplied by a MarkPriceSource, not fetched by this module --
same decoupling as ExternalPositionSource: the risk layer never imports
bot.data. A future orchestration loop that already has the current bar's
price on hand supplies it; StaticMarkPriceSource is the trivial
implementation for that and for tests.
"""

from __future__ import annotations
from typing import Optional, Protocol
import psycopg

from bot.execution.base import Broker, Fill, Order
from bot.risk import checks, kill_switch
from bot.risk.base import RiskDecision, RiskLimits


class MarkPriceSource(Protocol):
    def prices(self) -> dict[str, float]: ...


class StaticMarkPriceSource:
    def __init__(self, prices: Optional[dict[str, float]] = None):
        self._prices = dict(prices) if prices else {}

    def prices(self) -> dict[str, float]:
        return dict(self._prices)

    def set(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price


class RiskGate:
    def __init__(
        self,
        broker: Broker,
        conn: psycopg.Connection,
        limits: Optional[RiskLimits] = None,
        mark_prices: Optional[MarkPriceSource] = None,
    ):
        self._broker = broker
        self._conn = conn
        self._limits = limits or RiskLimits()
        self._mark_prices = mark_prices or StaticMarkPriceSource()

    def position(self, symbol: str) -> float:
        return self._broker.position(symbol)

    def submit_order(self, order: Order) -> Fill:
        try:
            decision = self._evaluate(order)
        except Exception as exc:
            decision = RiskDecision.block(f"risk check raised: {exc!r}")

        if decision.blocked:
            return _rejected_fill(order, decision.reason)
        return self._broker.submit_order(order)

    def _evaluate(self, order: Order) -> RiskDecision:
        if kill_switch.is_halted(self._conn):
            return RiskDecision.block("kill switch is engaged")

        decision = checks.check_max_position_size(self._conn, self._broker, order, self._limits)
        if decision.blocked:
            return decision

        decision = checks.check_max_orders_per_period(self._conn, order, self._limits)
        if decision.blocked:
            return decision

        decision = checks.check_daily_drawdown(
            self._conn, self._broker, self._limits, self._mark_prices.prices()
        )
        if decision.blocked:
            return decision

        return RiskDecision.allow()


def _rejected_fill(order: Order, reason: str) -> Fill:
    return Fill(
        client_order_id=order.client_order_id,
        symbol=order.symbol,
        side=order.side,
        qty=order.qty,
        status="rejected",
        filled_price=None,
        fee=None,
        effective_ts=order.effective_ts,
        filled_ts=None,
        reason=reason,
    )
