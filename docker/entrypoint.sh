#!/bin/sh
set -e
python scripts/migrate.py
exec python scripts/run_live.py
