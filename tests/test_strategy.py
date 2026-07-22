"""
Parity test: vectorized compute_signal (full history) vs. incremental
compute_signal (rolling buffer capped at warmup_bars, mirroring what a live
runner does) must agree at every bar.

This is the actual guarantee behind CLAUDE.md's success metric
("comportamento ao vivo bate certo com o backtest") -- the Strategy interface
only makes the guarantee possible for bounded-memory (FIR) strategies; this
test is what checks it holds. Any new Strategy implementation should be added
to STRATEGIES below.
"""

from __future__ import annotations
import numpy as np
import pytest

from bot.data.synthetic import synthetic_ohlcv
from bot.strategy.base import Strategy
from bot.strategy.ma_crossover import MACrossoverStrategy


STRATEGIES = [
    MACrossoverStrategy(fast=20, slow=50),
    MACrossoverStrategy(fast=5, slow=10),
]


@pytest.mark.parametrize(
    "strategy", STRATEGIES, ids=lambda s: f"{s.name}_f{s.fast}_s{s.slow}"
)
def test_strategy_satisfies_protocol(strategy):
    assert isinstance(strategy, Strategy)


@pytest.mark.parametrize(
    "strategy", STRATEGIES, ids=lambda s: f"{s.name}_f{s.fast}_s{s.slow}"
)
def test_vectorized_incremental_parity(strategy):
    df = synthetic_ohlcv(n=300, seed=7)
    warmup = strategy.warmup_bars()

    vectorized = strategy.compute_signal(df)
    assert len(vectorized) == len(df)

    mismatches = []
    for t in range(len(df)):
        start = max(0, t - warmup + 1)
        buffer = df.iloc[start : t + 1]
        assert len(buffer) <= warmup  # the live runner never hands over more than this

        incremental_value = strategy.compute_signal(buffer).iloc[-1]
        vectorized_value = vectorized.iloc[t]

        if not np.isclose(incremental_value, vectorized_value, equal_nan=True):
            mismatches.append((t, df.index[t], incremental_value, vectorized_value))

    assert not mismatches, (
        f"parity broken for {strategy.name} (fast={strategy.fast}, slow={strategy.slow}) "
        f"at {len(mismatches)} bar(s), first: bar={mismatches[0][0]} ts={mismatches[0][1]} "
        f"incremental={mismatches[0][2]} vectorized={mismatches[0][3]}"
    )
