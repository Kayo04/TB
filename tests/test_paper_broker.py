"""
Runs against the real trading_bot Postgres container (DATABASE_URL in .env) --
not mocked. The whole point of choosing Postgres now instead of SQLite was to
validate concurrency/transaction semantics against the storage tech that
actually ships, so these tests connect for real.
"""

from __future__ import annotations
import os
import threading

import pandas as pd
import psycopg
import pytest

from bot.execution.base import Order
from bot.execution.paper_broker import PaperBroker
from bot.persistence.db import get_connection


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


def _order_count(conn, client_order_id) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE client_order_id = %s", (client_order_id,)
    ).fetchone()["c"]


def _fill_count(conn, client_order_id) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS c FROM fills WHERE client_order_id = %s", (client_order_id,)
    ).fetchone()["c"]


# --------------------------------------------------------------------------- #
# 1. Clean replay after a "restart" (fresh broker instance)
# --------------------------------------------------------------------------- #

def test_clean_replay_returns_same_fill_no_duplicate(db_conn):
    order = _make_order()
    broker = PaperBroker(db_conn)
    fill1 = broker.submit_order(order)
    assert fill1.status == "filled"

    # simulate restart: brand new broker instance, no shared in-memory state
    restarted_broker = PaperBroker(db_conn)
    fill2 = restarted_broker.submit_order(order)  # replay of the identical transition

    assert fill2.status == "duplicate_ignored"
    assert fill2.filled_price == fill1.filled_price
    assert fill2.filled_ts == fill1.filled_ts
    assert _order_count(db_conn, order.client_order_id) == 1
    assert _fill_count(db_conn, order.client_order_id) == 1
    assert restarted_broker.position(order.symbol) == order.qty  # not double counted


# --------------------------------------------------------------------------- #
# 2. Aborted attempt (crash before commit) leaves no trace in EITHER table
# --------------------------------------------------------------------------- #

def test_aborted_insert_leaves_no_trace_then_real_attempt_succeeds(db_conn):
    order = _make_order(client_order_id="order-aborted")

    # simulate a crash mid-write: separate connection, run the same shape of
    # write record_fill() would (order + fill together), then roll back --
    # as if the process died before the transaction committed.
    conn2 = psycopg.connect(os.environ["DATABASE_URL"])  # autocommit False by default
    conn2.execute(
        """
        INSERT INTO orders (client_order_id, strategy_name, symbol, side, qty, status, effective_ts)
        VALUES (%s, %s, %s, %s, %s, 'filled', %s)
        """,
        (order.client_order_id, order.strategy_name, order.symbol, order.side, order.qty,
         order.effective_ts.to_pydatetime()),
    )
    conn2.execute(
        """
        INSERT INTO fills (client_order_id, symbol, side, qty, price, fee, filled_ts)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (order.client_order_id, order.symbol, order.side, order.qty, 30000.0, 3.0,
         order.effective_ts.to_pydatetime()),
    )
    conn2.rollback()
    conn2.close()

    assert _order_count(db_conn, order.client_order_id) == 0, "rolled-back attempt must leave no order row"
    assert _fill_count(db_conn, order.client_order_id) == 0, "rolled-back attempt must leave no fill row"

    broker = PaperBroker(db_conn)
    fill = broker.submit_order(order)  # the "real" attempt, after the simulated crash
    assert fill.status == "filled"
    assert _order_count(db_conn, order.client_order_id) == 1
    assert _fill_count(db_conn, order.client_order_id) == 1


# --------------------------------------------------------------------------- #
# 3. Crash after commit, before the caller sees the result
# --------------------------------------------------------------------------- #

def test_crash_after_commit_before_caller_sees_result(db_conn):
    order = _make_order(client_order_id="order-crash-after-commit")
    broker = PaperBroker(db_conn)

    first_fill = broker.submit_order(order)
    # simulate: process died right after Postgres ack'd the insert, caller
    # never got first_fill -- on restart, the runner replays the same
    # transition not knowing whether the first attempt succeeded.
    second_fill = broker.submit_order(order)

    assert second_fill.status == "duplicate_ignored"
    assert second_fill.filled_price == first_fill.filled_price
    assert second_fill.fee == first_fill.fee
    assert second_fill.filled_ts == first_fill.filled_ts
    assert _order_count(db_conn, order.client_order_id) == 1
    assert _fill_count(db_conn, order.client_order_id) == 1
    assert broker.position(order.symbol) == order.qty  # only counted once despite two calls


# --------------------------------------------------------------------------- #
# 4. Concurrent duplicate submission -- validates real Postgres atomicity
# --------------------------------------------------------------------------- #

def test_concurrent_duplicate_submission_only_one_fill(db_conn):
    order = _make_order(client_order_id="order-concurrent")
    results: list = []
    errors: list = []
    lock = threading.Lock()

    def worker():
        conn = get_connection(autocommit=True)
        try:
            broker = PaperBroker(conn)
            fill = broker.submit_order(order)
            with lock:
                results.append(fill)
        except Exception as e:  # pragma: no cover - surfaced via assertion below
            with lock:
                errors.append(e)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"unexpected errors during concurrent submission: {errors}"
    statuses = [r.status for r in results]
    assert statuses.count("filled") == 1, "exactly one concurrent submission should win the insert"
    assert statuses.count("duplicate_ignored") == len(threads) - 1
    assert _order_count(db_conn, order.client_order_id) == 1
    assert _fill_count(db_conn, order.client_order_id) == 1


# --------------------------------------------------------------------------- #
# 5. Position rebuilt from Postgres on startup, not trusted from memory
# --------------------------------------------------------------------------- #

def test_position_rebuilt_from_postgres_on_startup(db_conn):
    buy = _make_order(client_order_id="order-buy", side="buy", qty=1.0,
                       effective_ts="2024-01-01T00:00:00Z")
    sell = _make_order(client_order_id="order-sell", side="sell", qty=0.4,
                        effective_ts="2024-01-01T01:00:00Z")

    prior_run_broker = PaperBroker(db_conn)
    prior_run_broker.submit_order(buy)
    prior_run_broker.submit_order(sell)

    # simulate restart: fresh instance, no shared in-memory state
    fresh_broker = PaperBroker(db_conn)
    assert fresh_broker.position("BTC/USDT") == pytest.approx(0.6)
