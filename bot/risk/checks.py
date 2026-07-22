"""
Individual risk checks. Each returns a RiskDecision and must never swallow
its own uncertainty into an allow: if a check can't determine an answer it
should raise, and let RiskGate's outer catch (gate.py) turn that into a
block.

Per-order checks (max position size, max orders per period) only ever
reject the single order in question -- the bot keeps running, and the next
proposed order is evaluated fresh. That's the correct, expected response to
a strategy proposing something outside its limits, not a system failure.

check_daily_drawdown is different, and order-agnostic on purpose: a breach
represents something systemically wrong (losses beyond tolerance), not a
single order's problem, so it calls kill_switch.trip_halt() itself in
addition to returning a blocked decision. handle_reconciliation is the same
shape, wired to milestone 3's reconcile() output -- reconciliation.py
itself has no idea this module exists.
"""

from __future__ import annotations
import psycopg

from bot.execution.base import Broker, Order
from bot.persistence.reconciliation import Divergence
from bot.risk import kill_switch
from bot.risk.base import RiskDecision, RiskLimits


def check_max_position_size(
    conn: psycopg.Connection, broker: Broker, order: Order, limits: RiskLimits
) -> RiskDecision:
    current = broker.position(order.symbol)
    signed_qty = order.qty if order.side == "buy" else -order.qty
    resulting = current + signed_qty
    if abs(resulting) > limits.max_position_size:
        return RiskDecision.block(
            f"order would move {order.symbol} position to {resulting}, "
            f"exceeding max_position_size={limits.max_position_size}"
        )
    return RiskDecision.allow()


def check_max_orders_per_period(
    conn: psycopg.Connection, order: Order, limits: RiskLimits
) -> RiskDecision:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM orders
        WHERE strategy_name = %s
          AND created_at > now() - (%s * interval '1 second')
        """,
        (order.strategy_name, limits.order_period_seconds),
    ).fetchone()
    if row["c"] >= limits.max_orders_per_period:
        return RiskDecision.block(
            f"{row['c']} orders already placed by {order.strategy_name} in the last "
            f"{limits.order_period_seconds}s, at max_orders_per_period={limits.max_orders_per_period}"
        )
    return RiskDecision.allow()


def _cash_flow_today(conn: psycopg.Connection) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(
            CASE WHEN side = 'buy' THEN -(qty * price + fee) ELSE (qty * price - fee) END
        ), 0) AS cash_flow
        FROM fills
        WHERE filled_ts >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
        """
    ).fetchone()
    return float(row["cash_flow"])


def record_equity_snapshot(
    conn: psycopg.Connection, broker: Broker, mark_prices: dict[str, float]
) -> float:
    """
    total_equity = realized cash flow so far today (from fills, fee-inclusive)
    + mark-to-market value of whatever's currently open (position * mark
    price, per symbol). No cost-basis/lot-matching needed: this is a running
    account-value figure, not a per-trade P&L.
    """
    cash_flow = _cash_flow_today(conn)
    mark_to_market = sum(broker.position(symbol) * price for symbol, price in mark_prices.items())
    total_equity = cash_flow + mark_to_market
    conn.execute(
        "INSERT INTO equity_snapshots (total_equity, cash_flow, mark_to_market) VALUES (%s, %s, %s)",
        (total_equity, cash_flow, mark_to_market),
    )
    return total_equity


def check_daily_drawdown(
    conn: psycopg.Connection, broker: Broker, limits: RiskLimits, mark_prices: dict[str, float]
) -> RiskDecision:
    current_equity = record_equity_snapshot(conn, broker, mark_prices)

    peak_row = conn.execute(
        """
        SELECT MAX(total_equity) AS peak FROM equity_snapshots
        WHERE recorded_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
        """
    ).fetchone()
    peak = float(peak_row["peak"])  # includes the snapshot just inserted

    if peak <= 0:
        return RiskDecision.allow()  # no meaningful positive equity base yet to measure a drawdown against

    drawdown = (peak - current_equity) / peak
    if drawdown > limits.max_daily_drawdown_pct:
        reason = (
            f"daily drawdown {drawdown:.2%} exceeds max_daily_drawdown_pct="
            f"{limits.max_daily_drawdown_pct:.2%} (peak={peak}, current={current_equity})"
        )
        kill_switch.trip_halt(conn, reason=reason, triggered_by="max_daily_drawdown")
        return RiskDecision.block(reason)
    return RiskDecision.allow()


def handle_reconciliation(conn: psycopg.Connection, divergences: list[Divergence]) -> None:
    """
    Called by whoever calls reconcile() (the orchestration loop, milestone
    5) with its result. reconcile() itself never imports this module and
    never calls trip_halt -- the dependency points from risk toward
    reconciliation's output type, never the other way.
    """
    if not divergences:
        return
    reason = "; ".join(
        f"{d.symbol}: internal={d.internal_position} external={d.external_position} diff={d.difference}"
        for d in divergences
    )
    kill_switch.trip_halt(conn, reason=reason, triggered_by="reconciliation_divergence")
