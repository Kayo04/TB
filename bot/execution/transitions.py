"""
Turns a position series into Transitions, and a Transition into an Order.
Pure, no I/O, no exchange/broker knowledge -- the strategy/backtest layers
don't import this, and this doesn't import them.
"""

from __future__ import annotations
import pandas as pd

from bot.execution.base import Order, Transition
from bot.execution.order_ids import make_client_order_id


def diff_transitions(effective_position: pd.Series, symbol: str, prior_position: int = 0) -> list[Transition]:
    """
    prior_position is the position in effect BEFORE the first row of this
    series -- default 0 (cold start, flat). A resumed live runner must pass
    the actual rebuilt position (see Broker.position()) instead of assuming
    flat, or a restart mid-position would emit a spurious transition.
    """
    transitions: list[Transition] = []
    prev = prior_position
    for ts, pos in effective_position.items():
        pos = int(pos)
        if pos != prev:
            transitions.append(
                Transition(symbol=symbol, effective_ts=pd.Timestamp(ts), from_position=prev, to_position=pos)
            )
        prev = pos
    return transitions


def order_from_transition(
    transition: Transition,
    strategy_name: str,
    reference_price: float,
    qty: float = 1.0,
) -> Order:
    """qty defaults to a fixed placeholder unit -- sizing is milestone 4's job."""
    client_order_id = make_client_order_id(
        strategy_name, transition.symbol, transition.effective_ts,
        transition.from_position, transition.to_position,
    )
    side = "buy" if transition.to_position > transition.from_position else "sell"
    return Order(
        client_order_id=client_order_id,
        symbol=transition.symbol,
        side=side,
        qty=qty,
        effective_ts=transition.effective_ts,
        reference_price=reference_price,
    )
