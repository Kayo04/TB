"""
MA crossover — bounded-window (FIR) strategy, moved from the old backtester.py.

Proof-of-engine only (see CLAUDE.md non-goals): a copied popular strategy is
not a source of edge. It's useful here specifically because it's a clean
example of a bounded-memory strategy that satisfies the Strategy.warmup_bars
contract exactly: the signal at bar t depends only on the last `slow` closed
bars (a fixed rolling window), nothing further back.
"""

from __future__ import annotations
import pandas as pd


class MACrossoverStrategy:
    name = "ma_crossover"

    def __init__(self, fast: int = 20, slow: int = 50):
        if fast >= slow:
            raise ValueError(f"fast ({fast}) must be < slow ({slow})")
        self.fast = fast
        self.slow = slow

    def warmup_bars(self) -> int:
        return self.slow

    def compute_signal(self, df: pd.DataFrame) -> pd.Series:
        f = df["close"].rolling(self.fast).mean()
        s = df["close"].rolling(self.slow).mean()
        return (f > s).astype(int)
