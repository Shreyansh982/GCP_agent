"""SQLite connection and explicit migration support."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with required integrity protections enabled."""
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def apply_migrations(database_path: str | Path) -> None:
    """Apply checked-in SQL migrations once, in lexical version order."""
    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row["version"] for row in connection.execute("SELECT version FROM schema_migrations")
        }
        for migration in sorted(MIGRATIONS_DIRECTORY.glob("*.sql")):
            if migration.name in applied:
                continue
            script = migration.read_text(encoding="utf-8")
            try:
                connection.executescript(script)
                connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (migration.name,))
            except sqlite3.DatabaseError:
                connection.rollback()
                raise


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run repository writes atomically and roll them back on every failure."""
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()

