"""
Backtest engine — same math as the original backtester.py, now parameterized
by a Strategy instead of a bare signal function.

No look-ahead: the engine, not the strategy, shifts the signal by one bar
before it takes effect. Costs (fees + slippage) applied on turnover. Buy &
hold always computed as the benchmark.

NOTE (see PROGRESS.md "Pré-requisitos do gate de estratégia"): this engine
still reports a single in-sample number over the whole series. It does not
yet support an out-of-sample / walk-forward split — that's a prerequisite for
the strategy gate, not yet built.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from bot.strategy.base import Strategy


def backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    bars_per_year: int = 8760,
) -> dict:
    """
    fee_bps + slippage_bps: cost per unit of turnover, in basis points.
    bars_per_year: 8760 for 1h bars in 24/7 crypto; adjust for other timeframes.
    """
    px = df["close"]
    ret = px.pct_change().fillna(0.0)

    raw_signal = strategy.compute_signal(df)
    pos = raw_signal.shift(1).fillna(0)         # position in effect this bar
    turnover = pos.diff().abs().fillna(0)
    cost = turnover * (fee_bps + slippage_bps) / 1e4

    strat_ret = pos * ret - cost
    equity = (1 + strat_ret).cumprod()
    bh_equity = (1 + ret).cumprod()

    return _metrics(strat_ret, equity, bh_equity, pos, bars_per_year)


def _metrics(strat_ret, equity, bh_equity, pos, bars_per_year) -> dict:
    total = equity.iloc[-1] - 1
    bh_total = bh_equity.iloc[-1] - 1
    n = len(strat_ret)
    ann = equity.iloc[-1] ** (bars_per_year / n) - 1
    vol = strat_ret.std() * np.sqrt(bars_per_year)
    sharpe = (strat_ret.mean() * bars_per_year) / vol if vol > 0 else float("nan")
    max_dd = (equity / equity.cummax() - 1).min()
    n_trades = int(((pos == 1) & (pos.shift(1) == 0)).sum())

    return {
        "retorno_total_%": round(total * 100, 2),
        "buy_and_hold_%": round(bh_total * 100, 2),
        "retorno_anual_%": round(ann * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_%": round(max_dd * 100, 2),
        "n_trades": n_trades,
        "barras": n,
    }
