# chess_analyzer/services/sqlite_cache_service.py
"""
Provides a concrete implementation of the `CacheService` protocol using SQLite.

This service is responsible for persistent, on-disk caching of engine analysis
results. By storing the outcome of expensive engine computations, it prevents
redundant work on subsequent runs, dramatically speeding up the analysis of
positions that have been seen before. The cache key is a composite of the FEN,
engine settings, and engine version to ensure cache integrity.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type, TYPE_CHECKING

import aiosqlite
import structlog

from chess_analyzer.exceptions import CacheConnectionError, CacheReadError, CacheWriteError
from chess_analyzer.types import AnalysisResult, CacheKey, RawEngineLine
from chess_analyzer.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from chess_analyzer.config.settings import CacheSettings

logger = structlog.get_logger(__name__)

# A tuple of exceptions that are considered transient and can be retried.
# This primarily targets "database is locked" errors in SQLite under WAL mode.
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    aiosqlite.OperationalError,
)

# The SQL statement to create the cache table if it doesn't exist.
# The primary key ensures that each unique combination of position (FEN) and
# analysis settings is stored only once.
CREATE_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS engine_analysis_cache (
    fen TEXT NOT NULL,
    depth INTEGER NOT NULL,
    multipv_count INTEGER NOT NULL,
    engine_identifier TEXT NOT NULL,
    analysis_result_json TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (fen, depth, multipv_count, engine_identifier)
)
"""

class SqliteCacheService:
    """
    A `CacheService` implementation using a local SQLite database for persistence.
    
    This class is an async context manager, managing its own database connection
    lifecycle.
    """

    def __init__(self, settings: "CacheSettings"):
        """
        Initializes the cache service.
        
        Args:
            settings: The cache configuration containing the database file path.
        """
        self._db_path = Path(settings.db_filepath)
        self._connection: Optional[aiosqlite.Connection] = None

    async def __aenter__(self) -> "SqliteCacheService":
        """Initializes the database connection and creates the schema on entering the context."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = await aiosqlite.connect(self._db_path, timeout=10.0)
            # Use WAL (Write-Ahead Logging) mode for better concurrency performance.
            await self._connection.execute("PRAGMA journal_mode=WAL;")
            await self._connection.execute(CREATE_CACHE_TABLE_SQL)
            await self._connection.commit()
        except aiosqlite.Error as e:
            raise CacheConnectionError(f"Failed to initialize SQLite cache: {e}") from e
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Closes the database connection on exiting the context."""
        if self._connection:
            await self._connection.close()
    
    def _ensure_connected(self) -> aiosqlite.Connection:
        """Internal helper to ensure the database connection is active."""
        if self._connection is None:
            raise CacheConnectionError("Cache service is not connected.")
        return self._connection

    @retry_with_backoff(exceptions_to_catch=RETRYABLE_EXCEPTIONS, db_type="cache")
    async def get_cached_analyses_batch(
        self, cache_keys: List[CacheKey]
    ) -> Dict[CacheKey, AnalysisResult]:
        """
        Retrieves a batch of analysis results from the SQLite cache.

        Args:
            cache_keys: A list of `CacheKey` objects to look up.

        Returns:
            A dictionary mapping the found `CacheKey` objects to their
            corresponding `AnalysisResult`. Keys not found in the cache
            will be omitted from the result.
        
        Raises:
            CacheReadError: If a non-retriable database error occurs.
        """
        conn = self._ensure_connected()
        if not cache_keys:
            return {}

        # Build a query with parameter placeholders for a safe, efficient batch lookup.
        placeholders = ", ".join(["(?, ?, ?, ?)"] * len(cache_keys))
        query = f"SELECT * FROM engine_analysis_cache WHERE (fen, depth, multipv_count, engine_identifier) IN ({placeholders})"
        
        # Flatten the list of keys into a single list of parameters for the query.
        flat_params = [
            param for key in cache_keys
            for param in (key.fen, key.depth, key.multipv, key.engine_id)
        ]

        try:
            async with conn.execute(query, flat_params) as cursor:
                rows = await cursor.fetchall()
        except aiosqlite.Error as e:
            raise CacheReadError(f"Failed to fetch from cache: {e}") from e

        results: Dict[CacheKey, AnalysisResult] = {}
        for row_data in rows:
            # Reconstruct the key and result objects from the database row.
            key = CacheKey(fen=row_data[0], depth=row_data[1], multipv=row_data[2], engine_id=row_data[3])
            json_str = row_data[4]
            try:
                # The analysis result is stored as a JSON string.
                lines_data = json.loads(json_str)
                engine_lines = [RawEngineLine(**data) for data in lines_data]
                results[key] = AnalysisResult(top_engine_lines=engine_lines)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Corrupt data in cache for key, skipping.", cache_key=key, error=e)
                continue
        
        return results

    @retry_with_backoff(exceptions_to_catch=RETRYABLE_EXCEPTIONS, db_type="cache")
    async def store_analyses_batch(
        self, results: Dict[CacheKey, AnalysisResult]
    ) -> None:
        """
        Stores a batch of analysis results in the SQLite cache.

        Uses `INSERT OR IGNORE` to prevent errors if a key already exists,
        making the operation idempotent.

        Args:
            results: A dictionary mapping `CacheKey` objects to the `AnalysisResult`
                     to be stored.
                     
        Raises:
            CacheWriteError: If a non-retriable database error occurs.
        """
        conn = self._ensure_connected()
        if not results:
            return

        query = "INSERT OR IGNORE INTO engine_analysis_cache (fen, depth, multipv_count, engine_identifier, analysis_result_json) VALUES (?, ?, ?, ?, ?)"
        
        try:
            # Prepare data for insertion, serializing the result to a JSON string.
            data_to_insert = [
                (
                    key.fen, key.depth, key.multipv, key.engine_id,
                    json.dumps([asdict(line) for line in result.top_engine_lines])
                ) for key, result in results.items()
            ]
            await conn.executemany(query, data_to_insert)
            await conn.commit()
        except aiosqlite.Error as e:
            await conn.rollback()
            raise CacheWriteError(f"Failed to store into cache: {e}") from e