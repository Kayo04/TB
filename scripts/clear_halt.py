"""
Manual CLI to clear a durable halt. This is deliberately the ONLY place
bot.risk.kill_switch.clear_halt() is called anywhere in the codebase -- no
automated code path can un-halt the bot on its own.

    py scripts/clear_halt.py "tiago" "investigated the drawdown alert, resuming"
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from bot.persistence.db import get_connection
from bot.risk import kill_switch

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('Usage: py scripts/clear_halt.py "<cleared_by>" "<note>"')
        sys.exit(1)

    cleared_by, note = sys.argv[1], sys.argv[2]
    conn = get_connection(autocommit=True)

    if not kill_switch.is_halted(conn):
        print("Bot is not currently halted -- nothing to clear.")
    else:
        kill_switch.clear_halt(conn, cleared_by=cleared_by, note=note)
        print(f"Halt cleared by {cleared_by!r}: {note!r}")

    conn.close()
