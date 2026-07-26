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

# RiskLimits.max_daily_drawdown_pct defaults to a conservative 5% (see
# bot/risk/base.py) -- appropriate once real position sizing exists. Today
# qty is still a fixed 1.0-unit placeholder (see bot/execution/transitions.py),
# so daily equity is just one position's raw P&L against a tiny cash-flow
# base that resets to ~0 every UTC day -- ordinary BTC noise routinely swings
# that base by 30-100%+ in percentage terms, tripping the kill-switch on
# noise rather than a real problem (see PROGRESS.md for the live incident
# that prompted this). Overridable via env so recalibrating doesn't need a
# code change; MUST be revisited once real sizing exists, since a wide
# threshold against a *real* capital base is not the same risk decision.
MAX_DAILY_DRAWDOWN_PCT = float(os.environ.get("MAX_DAILY_DRAWDOWN_PCT", "0.05"))

if __name__ == "__main__":
    logger.info("run_live starting: symbol=%s timeframe=%s exchange=%s", SYMBOL, TIMEFRAME, EXCHANGE)
    conn = get_connection(autocommit=True)
    # Separate connection for the heartbeat background task -- see
    # LiveRunner's docstring/constructor. Must be a distinct Connection
    # object, not just a distinct reference to the same one.
    heartbeat_conn = get_connection(autocommit=True)
    run_migrations(conn)
    logger.info("migrations applied, constructing runner")

    strategy = MACrossoverStrategy(fast=20, slow=50)
    data_source = CcxtDataSource(exchange=EXCHANGE)
    mark_prices = StaticMarkPriceSource()
    limits = RiskLimits(max_daily_drawdown_pct=MAX_DAILY_DRAWDOWN_PCT)
    logger.info("risk limits: max_daily_drawdown_pct=%.2f (env MAX_DAILY_DRAWDOWN_PCT)", MAX_DAILY_DRAWDOWN_PCT)
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
        heartbeat_conn=heartbeat_conn,
    )
    runner.seed_from_history()
    asyncio.run(runner.run_forever())
