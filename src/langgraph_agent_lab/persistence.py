"""Checkpointer adapter.

Supports multiple persistence backends:
- memory: In-memory (default, no infrastructure needed)
- sqlite: SQLite with WAL mode for concurrent reads
- postgres: PostgreSQL for production deployments
"""

from __future__ import annotations

import sqlite3
from typing import Any


def build_checkpointer(
    kind: str = "memory", database_url: str | None = None,
) -> Any | None:  # noqa: ANN401
    """Return a LangGraph checkpointer.

    Args:
        kind: One of 'none', 'memory', 'sqlite', 'postgres'.
        database_url: Connection string for sqlite/postgres backends.

    Returns:
        A LangGraph-compatible checkpointer, or None if kind='none'.
    """
    if kind == "none":
        return None

    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()

    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError(
                "SQLite checkpointer requires: pip install langgraph-checkpoint-sqlite",
            ) from exc
        # Use check_same_thread=False to support Streamlit's multi-threaded execution
        conn = sqlite3.connect(database_url or "checkpoints.db", check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        return SqliteSaver(conn=conn)

    if kind == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:
            raise RuntimeError(
                "Postgres checkpointer requires: pip install langgraph-checkpoint-postgres",
            ) from exc
        return PostgresSaver.from_conn_string(database_url or "")

    raise ValueError(f"Unknown checkpointer kind: {kind}")
