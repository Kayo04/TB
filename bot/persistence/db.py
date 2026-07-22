"""Connection helper. Schema is owned entirely by migrations/ -- see migrate.py."""

from __future__ import annotations
import os
import psycopg
from psycopg.rows import dict_row


def get_connection(autocommit: bool = True) -> psycopg.Connection:
    dsn = os.environ["DATABASE_URL"]
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=autocommit)
