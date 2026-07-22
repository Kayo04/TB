"""
    py scripts/migrate.py
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from bot.persistence.db import get_connection
from bot.persistence.migrate import run_migrations

if __name__ == "__main__":
    conn = get_connection(autocommit=True)
    applied = run_migrations(conn)
    if applied:
        print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("Already up to date.")
    conn.close()
