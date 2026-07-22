"""
Synthetic OHLCV generator — pure noise, for proving the engine only.
Never use this to draw conclusions about a strategy (see CLAUDE.md).
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def synthetic_ohlcv(n: int = 1500, seed: int = 42, start: float = 30000.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0001, 0.01, n)
    close = start * np.exp(np.cumsum(rets))
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"close": close}, index=idx)
