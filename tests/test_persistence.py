from __future__ import annotations
import pandas as pd
import pytest

from bot.execution.base import Order
from bot.execution.paper_broker import PaperBroker
from bot.persistence import ledger
from bot.persistence.reconciliation import LedgerPositionSource, reconcile


def _make_order(client_order_id="order-1", strategy_name="ma_crossover", symbol="BTC/USDT",
                 side="buy", qty=1.0, effective_ts="2024-01-01T00:00:00Z", reference_price=30000.0) -> Order:
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
# The atomic order+fill CTE
# --------------------------------------------------------------------------- #

def test_record_fill_writes_order_and_fill_together(db_conn):
    order = _make_order(client_order_id="order-ctei")

    row = ledger.record_fill(db_conn, order, price=30015.0, fee=3.0, filled_ts=order.effective_ts)

    assert row is not None
    assert row["client_order_id"] == "order-ctei"
    assert row["price"] == 30015.0

    order_row = db_conn.execute(
        "SELECT * FROM orders WHERE client_order_id = %s", (order.client_order_id,)
    ).fetchone()
    fill_row = db_conn.execute(
        "SELECT * FROM fills WHERE client_order_id = %s", (order.client_order_id,)
    ).fetchone()
    assert order_row is not None and order_row["status"] == "filled"
    assert order_row["strategy_name"] == "ma_crossover"
    assert fill_row is not None and fill_row["price"] == 30015.0


def test_record_fill_conflict_inserts_nothing_in_either_table(db_conn):
    order = _make_order(client_order_id="order-conflict")

    first = ledger.record_fill(db_conn, order, price=30015.0, fee=3.0, filled_ts=order.effective_ts)
    assert first is not None

    second = ledger.record_fill(db_conn, order, price=99999.0, fee=999.0, filled_ts=order.effective_ts)
    assert second is None, "conflicting client_order_id must insert nothing -- not even a second fills row"

    order_count = db_conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE client_order_id = %s", (order.client_order_id,)
    ).fetchone()["c"]
    fill_count = db_conn.execute(
        "SELECT COUNT(*) AS c FROM fills WHERE client_order_id = %s", (order.client_order_id,)
    ).fetchone()["c"]
    assert order_count == 1
    assert fill_count == 1  # still just the first fill -- the 99999.0 price never landed


# --------------------------------------------------------------------------- #
# Position as a fold over fills
# --------------------------------------------------------------------------- #

def test_position_from_ledger_matches_manual_fold(db_conn):
    ledger.record_fill(db_conn, _make_order("o1", side="buy", qty=1.0), 30000.0, 3.0, pd.Timestamp("2024-01-01T00:00:00Z"))
    ledger.record_fill(db_conn, _make_order("o2", side="buy", qty=0.5), 30100.0, 1.5, pd.Timestamp("2024-01-01T01:00:00Z"))
    ledger.record_fill(db_conn, _make_order("o3", side="sell", qty=0.3), 30200.0, 0.9, pd.Timestamp("2024-01-01T02:00:00Z"))

    assert ledger.position_from_ledger(db_conn, "BTC/USDT") == pytest.approx(1.2)


def test_position_always_equals_fold_of_fills(db_conn):
    """
    The invariant PaperBroker.position() must never violate: after any
    sequence of submit_order calls, the broker's served (cached) position
    equals a fresh, independent fold of the ledger. This is the same
    comparison reconciliation performs in production -- here it's a direct
    test instead of a periodic check.
    """
    broker = PaperBroker(db_conn)
    orders = [
        _make_order("inv-1", symbol="BTC/USDT", side="buy", qty=1.0, effective_ts="2024-01-01T00:00:00Z"),
        _make_order("inv-2", symbol="BTC/USDT", side="buy", qty=0.4, effective_ts="2024-01-01T01:00:00Z"),
        _make_order("inv-3", symbol="ETH/USDT", side="buy", qty=2.0, effective_ts="2024-01-01T02:00:00Z"),
        _make_order("inv-4", symbol="BTC/USDT", side="sell", qty=0.6, effective_ts="2024-01-01T03:00:00Z"),
    ]
    for order in orders:
        broker.submit_order(order)

    for symbol in ("BTC/USDT", "ETH/USDT"):
        assert broker.position(symbol) == pytest.approx(ledger.position_from_ledger(db_conn, symbol))


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #

def test_reconciliation_no_divergence_when_consistent(db_conn):
    broker = PaperBroker(db_conn)
    broker.submit_order(_make_order("recon-ok", symbol="BTC/USDT", side="buy", qty=1.0))

    divergences = reconcile(db_conn, broker, LedgerPositionSource(db_conn), ["BTC/USDT"])

    assert divergences == []
    row = db_conn.execute(
        "SELECT * FROM reconciliation_checks WHERE symbol = 'BTC/USDT' ORDER BY checked_at DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["is_divergent"] is False
    assert row["internal_position"] == pytest.approx(1.0)
    assert row["external_position"] == pytest.approx(1.0)


def test_reconciliation_detects_injected_cache_vs_ledger_divergence(db_conn):
    """
    Simulates the exact bug class reconciliation exists to catch: the
    broker's in-memory cache silently drifting from the ledger (a future
    bad code path, a race, manual tampering -- doesn't matter which). We
    inject the drift directly rather than trying to cause a real one.
    """
    broker = PaperBroker(db_conn)
    broker.submit_order(_make_order("recon-divergent", symbol="BTC/USDT", side="buy", qty=1.0))
    assert broker.position("BTC/USDT") == pytest.approx(1.0)

    broker._positions["BTC/USDT"] = 1.0 + 0.5  # injected corruption -- ledger still says 1.0

    divergences = reconcile(db_conn, broker, LedgerPositionSource(db_conn), ["BTC/USDT"])

    assert len(divergences) == 1
    d = divergences[0]
    assert d.symbol == "BTC/USDT"
    assert d.internal_position == pytest.approx(1.5)
    assert d.external_position == pytest.approx(1.0)
    assert d.difference == pytest.approx(0.5)

    row = db_conn.execute(
        "SELECT * FROM reconciliation_checks WHERE symbol = 'BTC/USDT' ORDER BY checked_at DESC LIMIT 1"
    ).fetchone()
    assert row["is_divergent"] is True
    assert row["difference"] == pytest.approx(0.5)
