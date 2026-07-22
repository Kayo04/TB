from __future__ import annotations
import pandas as pd

from bot.execution.transitions import diff_transitions, order_from_transition


def test_diff_transitions_cold_start():
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    pos = pd.Series([0, 0, 1, 1, 0], index=idx)

    transitions = diff_transitions(pos, "BTC/USDT")

    assert len(transitions) == 2
    assert transitions[0].from_position == 0 and transitions[0].to_position == 1
    assert transitions[0].effective_ts == idx[2]
    assert transitions[1].from_position == 1 and transitions[1].to_position == 0
    assert transitions[1].effective_ts == idx[4]


def test_diff_transitions_no_change_no_transitions():
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    pos = pd.Series([1, 1, 1], index=idx)
    assert diff_transitions(pos, "BTC/USDT", prior_position=1) == []


def test_diff_transitions_resumed_mid_position_no_spurious_transition():
    """
    Simulates a restart while already long: the resumed buffer starts at
    position 1 with no prior bar to diff against in the series itself. Passing
    the real rebuilt position (1) as prior_position must NOT emit a spurious
    0->1 transition just because the buffer's first row happens to be 1.
    """
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    pos = pd.Series([1, 1, 0], index=idx)

    transitions = diff_transitions(pos, "BTC/USDT", prior_position=1)

    assert len(transitions) == 1
    assert transitions[0].from_position == 1 and transitions[0].to_position == 0


def test_order_from_transition_buy_and_sell_sides():
    idx = pd.date_range("2024-01-01", periods=1, freq="h", tz="UTC")
    pos = pd.Series([1], index=idx)
    enter = diff_transitions(pos, "BTC/USDT")[0]
    order = order_from_transition(enter, "ma_crossover", reference_price=100.0)

    assert order.side == "buy"
    assert order.symbol == "BTC/USDT"
    assert order.reference_price == 100.0
    assert order.qty == 1.0

    exit_transition = diff_transitions(pd.Series([0], index=idx), "BTC/USDT", prior_position=1)[0]
    exit_order = order_from_transition(exit_transition, "ma_crossover", reference_price=100.0)
    assert exit_order.side == "sell"
