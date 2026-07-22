"""
Backtester mínimo e honesto — Milestone 0.

Objetivo: provar se uma estratégia tem (ou NÃO tem) edge ANTES de a automatizar.
- Sem look-ahead bias: a posição decidida no fecho da barra t só entra em vigor em t+1.
- Com custos realistas: fees + slippage aplicados sobre o turnover.
- Corre em qualquer lado com dados sintéticos; troca-se por dados reais via ccxt.

Este ficheiro é deliberadamente simples e legível. É a fundação, não o produto final.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Camada de dados
# --------------------------------------------------------------------------- #

def fetch_ohlcv_ccxt(symbol="BTC/USDT", timeframe="1h", limit=1500, exchange="binance"):
    """
    Busca dados REAIS de uma exchange. Requer `pip install ccxt`.
    Corre isto LOCALMENTE (a exchange não está acessível a partir deste ambiente).
    Não precisa de API key para dados históricos públicos.
    """
    import ccxt  # import local para o resto do módulo correr sem ccxt instalado
    ex = getattr(ccxt, exchange)()
    raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("ts")


def synthetic_ohlcv(n=1500, seed=42, start=30000.0):
    """
    Série de preços sintética (random walk com leve drift).
    IMPORTANTE: isto é ruído puro. Serve só para validar que o MOTOR funciona,
    nunca para tirar conclusões sobre a estratégia.
    """
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0001, 0.01, n)
    close = start * np.exp(np.cumsum(rets))
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({"close": close}, index=idx)


# --------------------------------------------------------------------------- #
# Estratégia (determinística — é aqui que o edge vive ou morre)
# --------------------------------------------------------------------------- #

def ma_crossover_signal(df, fast=20, slow=50):
    """
    Sinal de posição: 1 = long, 0 = flat.
    Calculado no FECHO da barra t (só é usado a partir de t+1 no backtest).
    """
    f = df["close"].rolling(fast).mean()
    s = df["close"].rolling(slow).mean()
    return (f > s).astype(int)


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #

def backtest(df, signal, fee_bps=10.0, slippage_bps=5.0, bars_per_year=8760):
    """
    fee_bps + slippage_bps: custo por unidade de turnover, em basis points (1 bp = 0.01%).
    A posição entra em vigor na barra SEGUINTE ao sinal -> elimina look-ahead.
    bars_per_year: 8760 para barras de 1h em crypto 24/7; ajusta ao timeframe.
    """
    px = df["close"]
    ret = px.pct_change().fillna(0.0)

    pos = signal.shift(1).fillna(0)            # posição em vigor nesta barra
    turnover = pos.diff().abs().fillna(0)      # quanto a posição mudou (entradas/saídas)
    cost = turnover * (fee_bps + slippage_bps) / 1e4

    strat_ret = pos * ret - cost
    equity = (1 + strat_ret).cumprod()
    bh_equity = (1 + ret).cumprod()            # buy & hold, o benchmark que raramente se bate

    return _metrics(strat_ret, equity, bh_equity, pos, bars_per_year)


def _metrics(strat_ret, equity, bh_equity, pos, bars_per_year):
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


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    df = fetch_ohlcv_ccxt("BTC/USDT", "1h", 1500)

    sig = ma_crossover_signal(df, fast=20, slow=50)
    res = backtest(df, sig, fee_bps=10.0, slippage_bps=5.0)

    print("MA crossover (20/50) — DADOS REAIS (BTC/USDT, 1h, binance):")
    for k, v in res.items():
        print(f"  {k:>18}: {v}")
