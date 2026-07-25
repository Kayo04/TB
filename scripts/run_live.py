"""
Autonomous paper-trading loop. Bar-aligned: wakes on every closed 1h bar via
CcxtDataSource.stream(), runs one full cycle (signal -> transition ->
RiskGate.submit_order -> reconcile -> risk checks -> run_log), forever.
Still paper-only, still MA crossover 20/50 -- same engine-proving strategy
as scripts/run_backtest.py, not a claim of edge.

    py scripts/run_live.py
"""

from __future__ import annotations
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from bot.data.ccxt_source import CcxtDataSource
from bot.strategy.ma_crossover import MACrossoverStrategy
from bot.execution.paper_broker import PaperBroker
from bot.persistence.db import get_connection
from bot.persistence.migrate import run_migrations
from bot.persistence.reconciliation import LedgerPositionSource
from bot.risk.base import RiskLimits
from bot.risk.gate import RiskGate, StaticMarkPriceSource
from bot.orchestration.alerts import LogAlertSink
from bot.orchestration.runner import LiveRunner

_LOG_LEVEL = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
# Root stays at INFO regardless -- ccxt/urllib3/websockets are extremely
# chatty at DEBUG (full market-listing dumps per call) and would drown out
# anything of ours. LOG_LEVEL=DEBUG only elevates our own "bot.*" loggers.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("bot").setLevel(_LOG_LEVEL)
logger = logging.getLogger(__name__)

SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"
EXCHANGE = "binance"

if __name__ == "__main__":
    logger.info("run_live starting: symbol=%s timeframe=%s exchange=%s", SYMBOL, TIMEFRAME, EXCHANGE)
    conn = get_connection(autocommit=True)
    run_migrations(conn)
    logger.info("migrations applied, constructing runner")

    strategy = MACrossoverStrategy(fast=20, slow=50)
    data_source = CcxtDataSource(exchange=EXCHANGE)
    mark_prices = StaticMarkPriceSource()
    limits = RiskLimits()
    broker = RiskGate(PaperBroker(conn), conn, limits, mark_prices)

    runner = LiveRunner(
        data_source=data_source,
        strategy=strategy,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        broker=broker,
        conn=conn,
        mark_prices=mark_prices,
        limits=limits,
        external=LedgerPositionSource(conn),
        alert_sink=LogAlertSink(),
    )
    runner.seed_from_history()
    asyncio.run(runner.run_forever())
