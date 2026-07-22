"""
Runs against the real trading_bot Postgres container, same as
test_paper_broker.py / test_persistence.py -- the fail-closed and durability
guarantees are exactly the kind of thing that must be proven against real
Postgres semantics, not a mock.
"""

from __future__ import annotations
import pandas as pd
import pytest

from bot.execution.base import Order
from bot.execution.paper_broker import PaperBroker
from bot.persistence.db import get_connection
from bot.risk import checks, kill_switch
from bot.risk.base import RiskLimits
from bot.risk.gate import RiskGate


def _make_order(client_order_id="order-1", strategy_name="ma_crossover", symbol="BTC/USDT",
                 side="buy", qty=1.0, effective_ts="2024-01-01T00:00:00Z", reference_price=100.0) -> Order:
    return Order(
        client_order_id=client_order_id,
        strategy_name=strategy_name,
        symbol=symbol,
        side=side,
        qty=qty,
        effective_ts=pd.Timestamp(effective_ts),
        reference_price=reference_price,
    )


# --------------------------------------------------------------------------- #
# Fail-closed enforcement
# --------------------------------------------------------------------------- #

def test_risk_check_exception_defaults_to_block(db_conn, monkeypatch):
    """
    If a check raises for any reason (bad data, a bug, a timeout), RiskGate
    must reject the order rather than let the exception propagate into an
    implicit allow. The underlying broker must never be called.
    """
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated check failure")

    monkeypatch.setattr(checks, "check_max_position_size", _boom)

    broker = PaperBroker(db_conn)
    gate = RiskGate(broker, db_conn)
    order = _make_order(client_order_id="order-boom")

    fill = gate.submit_order(order)

    assert fill.status == "rejected"
    assert "simulated check failure" in fill.reason
    # the broker never ran -- no order/fill row exists anywhere
    order_row = db_conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE client_order_id = %s", (order.client_order_id,)
    ).fetchone()
    assert order_row["c"] == 0


def test_is_halted_returns_true_when_read_fails():
    """
    If the halt-state read itself fails (e.g. connection is unusable), that
    must be treated as halted, not as "unknown, so allow".
    """
    conn = get_connection(autocommit=True)
    conn.close()  # force any subsequent conn.execute to raise

    assert kill_switch.is_halted(conn) is True


# --------------------------------------------------------------------------- #
# Durable halt survives a restart, only the manual CLI path clears it
# --------------------------------------------------------------------------- #

def test_durable_halt_survives_restart_and_only_clears_via_clear_halt(db_conn):
    assert kill_switch.is_halted(db_conn) is False

    kill_switch.trip_halt(db_conn, reason="manual test halt", triggered_by="manual")
    assert kill_switch.is_halted(db_conn) is True

    # simulate a restart: brand new connection, no shared in-memory state
    restarted_conn = get_connection(autocommit=True)
    assert kill_switch.is_halted(restarted_conn) is True, "halt must survive a process restart"

    # a fresh RiskGate on the new connection must also refuse to trade
    broker = PaperBroker(restarted_conn)
    gate = RiskGate(broker, restarted_conn)
    fill = gate.submit_order(_make_order(client_order_id="order-while-halted"))
    assert fill.status == "rejected"
    assert "kill switch" in fill.reason

    # only the explicit clear path un-halts it
    kill_switch.clear_halt(restarted_conn, cleared_by="tiago", note="test clear")
    assert kill_switch.is_halted(restarted_conn) is False
    assert kill_switch.is_halted(db_conn) is False  # same durable state, any connection sees it

    restarted_conn.close()


def test_clear_halt_requires_non_empty_reason(db_conn):
    kill_switch.trip_halt(db_conn, reason="halt", triggered_by="manual")
    with pytest.raises(ValueError):
        kill_switch.clear_halt(db_conn, cleared_by="", note="")
    assert kill_switch.is_halted(db_conn) is True  # rejected clear attempt changed nothing


# --------------------------------------------------------------------------- #
# Max position size: rejects one order, bot keeps running
# --------------------------------------------------------------------------- #

def test_max_position_size_rejects_order_but_bot_keeps_running(db_conn):
    limits = RiskLimits(max_position_size=1.0)
    broker = PaperBroker(db_conn, fee_bps=0, slippage_bps=0)
    gate = RiskGate(broker, db_conn, limits)

    within_limit = gate.submit_order(_make_order(client_order_id="pos-1", side="buy", qty=1.0))
    assert within_limit.status == "filled"
    assert broker.position("BTC/USDT") == pytest.approx(1.0)

    over_limit = gate.submit_order(_make_order(client_order_id="pos-2", side="buy", qty=1.0))
    assert over_limit.status == "rejected"
    assert "max_position_size" in over_limit.reason
    assert broker.position("BTC/USDT") == pytest.approx(1.0), "rejected order must not move position"

    # the bot is NOT halted -- a later order back within limits still succeeds
    assert kill_switch.is_halted(db_conn) is False
    recovers = gate.submit_order(_make_order(client_order_id="pos-3", side="sell", qty=0.5))
    assert recovers.status == "filled"
    assert broker.position("BTC/USDT") == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# Daily drawdown breach trips the durable halt
# --------------------------------------------------------------------------- #

def test_drawdown_breach_trips_durable_halt(db_conn):
    limits = RiskLimits(max_daily_drawdown_pct=0.05)
    broker = PaperBroker(db_conn, fee_bps=0, slippage_bps=0)
    gate = RiskGate(broker, db_conn, limits)

    buy = gate.submit_order(_make_order(client_order_id="dd-buy", side="buy", qty=1.0, reference_price=100.0))
    assert buy.status == "filled"

    # peak: mark price rallies to 200 -> equity = cash_flow(-100) + mtm(200) = 100
    peak_decision = checks.check_daily_drawdown(db_conn, broker, limits, {"BTC/USDT": 200.0})
    assert peak_decision.blocked is False
    assert kill_switch.is_halted(db_conn) is False

    # trough: mark price craters to 90 -> equity = -100 + 90 = -10, drawdown from peak 100 is 110%
    trough_decision = checks.check_daily_drawdown(db_conn, broker, limits, {"BTC/USDT": 90.0})
    assert trough_decision.blocked is True
    assert "daily drawdown" in trough_decision.reason

    assert kill_switch.is_halted(db_conn) is True
    event = db_conn.execute("SELECT * FROM risk_events ORDER BY event_id DESC LIMIT 1").fetchone()
    assert event["event_type"] == "halt"
    assert event["triggered_by"] == "max_daily_drawdown"

    # halt propagates through the gate to ANY subsequent order, even one
    # that's otherwise well within every other limit
    after_halt = gate.submit_order(_make_order(client_order_id="dd-after-halt", side="sell", qty=0.1, reference_price=90.0))
    assert after_halt.status == "rejected"
    assert "kill switch" in after_halt.reason


def test_drawdown_within_tolerance_does_not_halt(db_conn):
    limits = RiskLimits(max_daily_drawdown_pct=0.05)
    broker = PaperBroker(db_conn, fee_bps=0, slippage_bps=0)
    gate = RiskGate(broker, db_conn, limits)

    gate.submit_order(_make_order(client_order_id="dd-ok-buy", side="buy", qty=1.0, reference_price=100.0))

    checks.check_daily_drawdown(db_conn, broker, limits, {"BTC/USDT": 200.0})  # peak: equity=100
    small_dip = checks.check_daily_drawdown(db_conn, broker, limits, {"BTC/USDT": 197.0})  # equity=97, dd=3%

    assert small_dip.blocked is False
    assert kill_switch.is_halted(db_conn) is False


# --------------------------------------------------------------------------- #
# Max orders per period (runaway-order guard, built per explicit request)
# --------------------------------------------------------------------------- #

def test_max_orders_per_period_rejects_after_limit(db_conn):
    limits = RiskLimits(max_orders_per_period=3, order_period_seconds=3600, max_position_size=1000.0)
    broker = PaperBroker(db_conn, fee_bps=0, slippage_bps=0)
    gate = RiskGate(broker, db_conn, limits)

    for i in range(3):
        fill = gate.submit_order(_make_order(client_order_id=f"rate-{i}", side="buy", qty=1.0))
        assert fill.status == "filled"

    fourth = gate.submit_order(_make_order(client_order_id="rate-4", side="buy", qty=1.0))
    assert fourth.status == "rejected"
    assert "max_orders_per_period" in fourth.reason
    assert kill_switch.is_halted(db_conn) is False, "rate limit is a per-order reject, not a halt"
