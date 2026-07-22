from __future__ import annotations
import pandas as pd

from bot.execution.order_ids import make_client_order_id


def test_deterministic_same_inputs_same_id():
    ts = pd.Timestamp("2024-01-01T00:00:00", tz="UTC")
    a = make_client_order_id("ma_crossover", "BTC/USDT", ts, 0, 1)
    b = make_client_order_id("ma_crossover", "BTC/USDT", ts, 0, 1)
    assert a == b


def test_naive_and_utc_aware_timestamp_produce_same_id():
    naive = pd.Timestamp("2024-01-01T00:00:00")
    aware = pd.Timestamp("2024-01-01T00:00:00", tz="UTC")
    a = make_client_order_id("ma_crossover", "BTC/USDT", naive, 0, 1)
    b = make_client_order_id("ma_crossover", "BTC/USDT", aware, 0, 1)
    assert a == b


def test_different_timestamp_different_id():
    a = make_client_order_id("ma_crossover", "BTC/USDT", pd.Timestamp("2024-01-01", tz="UTC"), 0, 1)
    b = make_client_order_id("ma_crossover", "BTC/USDT", pd.Timestamp("2024-01-02", tz="UTC"), 0, 1)
    assert a != b


def test_different_strategy_different_id_same_bar():
    ts = pd.Timestamp("2024-01-01T00:00:00", tz="UTC")
    a = make_client_order_id("ma_crossover", "BTC/USDT", ts, 0, 1)
    b = make_client_order_id("other_strategy", "BTC/USDT", ts, 0, 1)
    assert a != b, "two strategies deciding on the same symbol/bar must not collide"


def test_different_transition_direction_different_id():
    ts = pd.Timestamp("2024-01-01T00:00:00", tz="UTC")
    enter = make_client_order_id("ma_crossover", "BTC/USDT", ts, 0, 1)
    exit_ = make_client_order_id("ma_crossover", "BTC/USDT", ts, 1, 0)
    assert enter != exit_
