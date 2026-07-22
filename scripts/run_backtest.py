"""
CLI entrypoint — replaces the old backtester.py __main__ block.

    py scripts/run_backtest.py
"""

from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.data.ccxt_source import CcxtDataSource
from bot.strategy.ma_crossover import MACrossoverStrategy
from bot.backtest.engine import backtest


if __name__ == "__main__":
    source = CcxtDataSource(exchange="binance")
    since = datetime.now(timezone.utc) - timedelta(hours=1500)
    df = source.fetch_history("BTC/USDT", "1h", since=since)

    strategy = MACrossoverStrategy(fast=20, slow=50)
    res = backtest(df, strategy, fee_bps=10.0, slippage_bps=5.0)

    print(f"MA crossover (20/50) — DADOS REAIS (BTC/USDT, 1h, {source.exchange_id}):")
    for k, v in res.items():
        print(f"  {k:>18}: {v}")
