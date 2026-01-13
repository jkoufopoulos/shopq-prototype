"""Storage - database, models, caching, repositories"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from shopq.infrastructure.database import db_transaction, get_db_connection


class BaseRepository:
    """Base class for database repositories with common CRUD operations."""

    def __init__(self, table_name: str) -> None:
        if not isinstance(table_name, str) or not table_name.replace("_", "").isalnum():
            raise ValueError(f"Invalid table name: {table_name}")
        self.table_name = table_name

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        with get_db_connection() as conn:
            yield conn

    def query_one(self, query: str, params: tuple[Any, ...] | None = None) -> sqlite3.Row | None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.fetchone()

    def query_all(self, query: str, params: tuple[Any, ...] | None = None) -> list[sqlite3.Row]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.fetchall()

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> int | None:
        """
        Execute a write query (INSERT, UPDATE, DELETE)

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            Last inserted row ID

        Side Effects:
            - Writes to database table specified in query
            - Commits transaction automatically (via db_transaction)
            - Rolls back on error
        """
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.lastrowid


__all__ = ["BaseRepository"]
