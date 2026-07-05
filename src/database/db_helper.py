"""
DatabaseHelper — lightweight SQLite connection and query manager.

Design decisions:
- One persistent connection per instance (lazy-opened, closed explicitly or via context manager).
- Foreign keys are always enabled (PRAGMA foreign_keys = ON).
- Rows are returned as plain dicts so callers never depend on sqlite3.Row internals.
- All write operations roll back automatically on error, then re-raise so callers can handle failures.
"""
import sqlite3
from pathlib import Path
from typing import Any, Optional, Union

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseHelper:
    """Manage a single SQLite connection with helpers for common query patterns."""

    def __init__(self, db_path: Union[str, Path]) -> None:
        """
        Args:
            db_path: Filesystem path to the SQLite database file.
                     The file (and its parent directories) will be created
                     automatically by SQLite the first time a connection is opened.
        """
        self.db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def open(self) -> sqlite3.Connection:
        """Open and return the database connection (idempotent)."""
        if self._connection is None:
            logger.debug("Opening SQLite connection to %s", self.db_path)
            self._connection = sqlite3.connect(str(self.db_path))
            # Enforce referential integrity — SQLite disables it by default
            self._connection.execute("PRAGMA foreign_keys = ON;")
            # Make rows behave like dicts
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Close the database connection if one is open."""
        if self._connection is not None:
            logger.debug("Closing SQLite connection to %s", self.db_path)
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "DatabaseHelper":
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def initialize_database(self, schema_path: Union[str, Path]) -> None:
        """
        Read *schema_path* and execute it against the database.

        Uses ``executescript`` so the file may contain multiple statements
        separated by semicolons and comments.

        Args:
            schema_path: Path to a ``.sql`` file containing ``CREATE TABLE``
                         and ``CREATE TRIGGER`` statements.

        Raises:
            FileNotFoundError: When *schema_path* does not exist.
            sqlite3.Error: On any SQL execution error (connection is rolled back).
        """
        schema_path = Path(schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        logger.info("Initialising database schema from %s", schema_path)
        schema_sql = schema_path.read_text(encoding="utf-8")

        conn = self.open()
        try:
            conn.executescript(schema_sql)
            conn.commit()
            logger.info("Database schema initialised successfully.")
        except sqlite3.Error:
            conn.rollback()
            logger.exception("Schema initialisation failed; changes rolled back.")
            raise

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def execute(self, query: str, params: Union[tuple, dict] = ()) -> int:
        """
        Execute a write query (``INSERT``, ``UPDATE``, ``DELETE``).

        Args:
            query:  Parameterised SQL statement.
            params: Positional tuple or named dict of bind parameters.

        Returns:
            ``lastrowid`` for INSERT statements, ``rowcount`` for UPDATE/DELETE.

        Raises:
            sqlite3.Error: On any SQL error (connection is rolled back).
        """
        conn = self.open()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
            result = cursor.lastrowid if cursor.lastrowid else cursor.rowcount
            logger.debug("execute() → %s  params=%s  result=%s", query[:80], params, result)
            return result
        except sqlite3.Error:
            conn.rollback()
            logger.exception("execute() failed; rolled back.  query=%s", query[:80])
            raise

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def fetch_all(self, query: str, params: Union[tuple, dict] = ()) -> list[dict[str, Any]]:
        """
        Execute a ``SELECT`` query and return **all** matching rows as dicts.

        Args:
            query:  Parameterised SQL statement.
            params: Positional tuple or named dict of bind parameters.

        Returns:
            A (possibly empty) list of row dictionaries.
        """
        conn = self.open()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        logger.debug("fetch_all() → %d rows  query=%s", len(rows), query[:80])
        return [dict(row) for row in rows]

    def fetch_one(self, query: str, params: Union[tuple, dict] = ()) -> Optional[dict[str, Any]]:
        """
        Execute a ``SELECT`` query and return the **first** row as a dict, or ``None``.

        Args:
            query:  Parameterised SQL statement.
            params: Positional tuple or named dict of bind parameters.

        Returns:
            A single row dictionary, or ``None`` if no rows matched.
        """
        conn = self.open()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        logger.debug("fetch_one() → %s  query=%s", "hit" if row else "miss", query[:80])
        return dict(row) if row else None
