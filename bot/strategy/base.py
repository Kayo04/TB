"""
Strategy interface — Milestone 1.

A Strategy is a pure function of OHLCV history to a position signal. It never
touches the exchange, never has execution knowledge, and never decides when
its own signal takes effect (that's the caller's job — see backtest/engine.py
and, later, the live runner — both apply the same "decided at close of bar t,
in effect at t+1" rule so the shift-by-1 logic lives in exactly one place).
"""

from __future__ import annotations
from typing import Protocol, runtime_checkable
import pandas as pd


@runtime_checkable
class Strategy(Protocol):
    """
    Contract:
    - compute_signal(df) is pure: same input -> same output, no I/O, no mutation
      of df, no side effects.
    - Output is a pd.Series aligned to df.index, values in {0, 1} (1 = long,
      0 = flat). Short/leverage/weights are out of scope until a strategy
      actually needs them.

    warmup_bars is a HARD UPPER BOUND on memory, not a "meaningful after N bars"
    hint: the signal at bar t must be a function of at most the last
    warmup_bars closed bars ending at t (bounded/FIR window — e.g. a rolling
    mean over a fixed window). This is what makes backtest/live parity provable:
    the live runner only ever hands compute_signal a rolling buffer of the last
    warmup_bars-or-so closed bars, never the full history. A strategy whose
    latest signal depends on unbounded/expanding history — e.g. an EMA seeded
    from bar 0, or any recursive indicator carrying state from the start of the
    series — will silently disagree between the vectorized (full-history) and
    incremental (truncated-buffer) code paths, because the truncated buffer
    initializes differently than the full run. Such strategies must be
    reformulated to a bounded window (e.g. seed the EMA from a fixed lookback
    instead of bar 0) or are excluded from this interface — do not implement
    them against compute_signal as-is.

    See tests/test_strategy.py for the parity test that enforces this in
    practice: it asserts the vectorized and incremental paths agree at every
    bar, for every strategy. That test is the actual guarantee behind the
    CLAUDE.md success metric ("comportamento ao vivo bate certo com o
    backtest") — this interface only makes the guarantee possible, the test
    is what checks it holds for a given strategy.
    """

    name: str

    def warmup_bars(self) -> int:
        """Hard upper bound on how many trailing closed bars compute_signal needs."""
        ...

    def compute_signal(self, df: pd.DataFrame) -> pd.Series:
        """OHLCV DataFrame (indexed by ts, has at least a 'close' column) -> position series."""
        ...
