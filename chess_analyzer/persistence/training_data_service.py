# chess_analyzer/persistence/training_data_service.py
"""
Data Access Layer for the application's main statistics database.

This service provides a high-level, transactional interface for all interactions
with the training/statistics SQLite database. It encapsulates all SQL queries
and abstracts away the database connection management, providing a clean API for
the rest of the application. It is designed to be stateless, creating connections
on a per-transaction basis to ensure safety in a concurrent environment.
"""
import asyncio
import chess
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

import aiosqlite
import structlog

from chess_analyzer.exceptions import PersistenceError
from chess_analyzer.types import (
    GameReportRow, PositionStats, QueuePayload, QueuedAnnotatedGame,
    QueuedPosition, QueuedStatUpdate, QueuedMove, QueuedGameStat
)
from chess_analyzer.persistence.queries import (
    AccuracyTrendQuery, BlunderReelQuery,
    CognitiveDissonanceQuery, KpiQuery, OpeningPerformanceQuery
)
from chess_analyzer.utils.retry import retry_with_backoff

RETRYABLE_DB_EXCEPTIONS: Tuple[Type[Exception], ...] = (aiosqlite.OperationalError,)
logger = structlog.get_logger(__name__)

class TrainingDataService:
    """An async, STATELESS Data Access Layer (DAL) for the training database."""
    
    _SCHEMA: str = """
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS positions (
            fen TEXT PRIMARY KEY, player_to_move TEXT NOT NULL, material_balance INTEGER NOT NULL,
            game_phase TEXT, total_occurrences INTEGER NOT NULL DEFAULT 1, first_seen_game_id TEXT,
            last_seen_game_id TEXT, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS position_stats (
            fen TEXT PRIMARY KEY, total_occurrences INTEGER NOT NULL DEFAULT 0,
            average_cpl REAL NOT NULL DEFAULT 0.0, brilliant_count INTEGER NOT NULL DEFAULT 0,
            great_move_count INTEGER NOT NULL DEFAULT 0, good_move_count INTEGER NOT NULL DEFAULT 0,
            dubious_move_count INTEGER NOT NULL DEFAULT 0, inaccuracy_count INTEGER NOT NULL DEFAULT 0,
            mistake_count INTEGER NOT NULL DEFAULT 0, blunder_count INTEGER NOT NULL DEFAULT 0,
            is_critical_tactic BOOLEAN NOT NULL DEFAULT 0, tactic_type TEXT,
            total_time_spent_seconds REAL NOT NULL DEFAULT 0.0,
            move_count_in_time_trouble INTEGER NOT NULL DEFAULT 0, eval_std_dev REAL,
            FOREIGN KEY (fen) REFERENCES positions(fen) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS moves (
            move_id INTEGER PRIMARY KEY AUTOINCREMENT, game_id TEXT NOT NULL, fen TEXT NOT NULL,
            ply INTEGER NOT NULL, move_uci TEXT NOT NULL, best_move_san TEXT, cpl REAL, classification TEXT NOT NULL,
            time_spent_seconds REAL, post_move_eval REAL, is_reciprocal_blunder BOOLEAN DEFAULT 0,
            game_phase TEXT DEFAULT 'Unknown',
            FOREIGN KEY (fen) REFERENCES positions(fen) ON DELETE CASCADE, UNIQUE(game_id, ply)
        );
        CREATE TABLE IF NOT EXISTS openings (opening_id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS game_stats (
            game_id TEXT NOT NULL,
            player_name TEXT NOT NULL,
            player_color TEXT NOT NULL,
            is_user_game INTEGER NOT NULL DEFAULT 0,
            -- This new column directly links a game to its single opening.
            opening_id INTEGER,
            game_date DATE,
            game_time TEXT,
            time_control_category TEXT,
            opponent_rating INTEGER,
            eval_volatility REAL,
            accuracy_percent REAL,
            result TEXT,
            termination TEXT,
            PRIMARY KEY (game_id, player_name),
            FOREIGN KEY (opening_id) REFERENCES openings(opening_id)
        );
        CREATE TABLE IF NOT EXISTS annotated_games (
            game_id TEXT PRIMARY KEY,
            pgn_text TEXT NOT NULL
        );
    """
    
    _initialized = False
    _init_lock = asyncio.Lock()

    def __init__(self, db_path: str):
        self._db_path = Path(db_path)
    
    async def initialize_db(self) -> None:
        """A one-time setup method to create the database and schema if they don't exist."""
        async with self._init_lock:
            if self._initialized:
                return
            logger.debug("Initializing database schema.", db_path=str(self._db_path))
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                async with aiosqlite.connect(self._db_path) as conn:
                    await conn.executescript(self._SCHEMA)
                    await conn.commit()
                self._initialized = True
                logger.info("Database schema initialized successfully.", db_path=str(self._db_path))
            except aiosqlite.Error as e:
                raise PersistenceError(f"Failed to initialize training database at '{self._db_path}'") from e
    
    @retry_with_backoff(exceptions_to_catch=RETRYABLE_DB_EXCEPTIONS, db_type="training_write")
    async def persist_complete_game_buffer(self, game_buffer: List[QueuePayload]) -> None:
        """Persists all data for a single game within one atomic database transaction."""
        game_data: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in game_buffer:
            if isinstance(item, QueuedPosition):
                game_data['positions'].append(item.position_payload)
            elif isinstance(item, QueuedStatUpdate):
                game_data['stats'].append(item.stats_payload)
            elif isinstance(item, QueuedMove):
                game_data['moves'].append(item.move_payload)
            elif isinstance(item, QueuedGameStat):
                game_data['game_stats'].append(item.game_stat_payload)
            elif isinstance(item, QueuedAnnotatedGame):
                game_data['annotated_games'].append(asdict(item))
                
        try:
            async with aiosqlite.connect(self._db_path, timeout=10) as conn:
                conn.row_factory = aiosqlite.Row
                
                if positions_data := game_data.get('positions'):
                    sql = """INSERT INTO positions (fen, player_to_move, material_balance, game_phase, first_seen_game_id, last_seen_game_id)
                             VALUES (:fen, :player_to_move, :material_balance, :game_phase, :game_id, :game_id)
                             ON CONFLICT(fen) DO UPDATE SET total_occurrences = total_occurrences + 1, last_seen_game_id = excluded.last_seen_game_id, last_updated = CURRENT_TIMESTAMP;"""
                    await conn.executemany(sql, positions_data)

                if stats_data := game_data.get('stats'):
                    sql = """INSERT OR REPLACE INTO position_stats 
                             (fen, total_occurrences, average_cpl, brilliant_count, great_move_count, good_move_count, dubious_move_count, inaccuracy_count, mistake_count, blunder_count, is_critical_tactic, tactic_type, total_time_spent_seconds, move_count_in_time_trouble, eval_std_dev) 
                             VALUES (:fen, :total_occurrences, :average_cpl, :brilliant_count, :great_move_count, :good_move_count, :dubious_move_count, :inaccuracy_count, :mistake_count, :blunder_count, :is_critical_tactic, :tactic_type, :total_time_spent_seconds, :move_count_in_time_trouble, :eval_std_dev)"""
                    await conn.executemany(sql, stats_data)
                
                if moves_data := game_data.get('moves'):
                    sql = """INSERT OR IGNORE INTO moves 
                             (game_id, fen, ply, move_uci, best_move_san, cpl, classification, time_spent_seconds, post_move_eval, is_reciprocal_blunder, game_phase) 
                             VALUES (:game_id, :fen, :ply, :move_uci, :best_move_san, :cpl, :classification, :time_spent_seconds, :post_move_eval, :is_reciprocal_blunder, :game_phase)"""
                    await conn.executemany(sql, moves_data)

                if game_stats_data := game_data.get('game_stats'):
                    # --- FIX: The INSERT query now includes the opening_id column ---
                    sql = """INSERT OR IGNORE INTO game_stats 
                             (game_id, player_name, player_color, is_user_game, opening_id, game_date, game_time, time_control_category, opponent_rating, eval_volatility, accuracy_percent, result, termination) 
                             VALUES (:game_id, :player_name, :player_color, :is_user_game, :opening_id, :date, :game_time, :time_control_category, :opponent_rating, :eval_volatility, :accuracy_percent, :result, :termination)"""
                    # --- FIX: Loop through each stat payload to resolve the opening_id ---
                    for payload in game_stats_data:
                        opening_id = None
                        if opening_name := payload.get('opening_name'):
                            cursor = await conn.execute("SELECT opening_id FROM openings WHERE name = ?", (opening_name,))
                            row = await cursor.fetchone()
                            if row:
                                opening_id = row['opening_id']
                            else:
                                cursor = await conn.execute("INSERT INTO openings (name) VALUES (?)", (opening_name,))
                                opening_id = cursor.lastrowid
                        payload['opening_id'] = opening_id
                        await conn.execute(sql, payload)

                if annotated_games_data := game_data.get('annotated_games'):
                    sql = """INSERT OR IGNORE INTO annotated_games (game_id, pgn_text) 
                             VALUES (:game_id, :pgn_text)"""
                    await conn.executemany(sql, annotated_games_data)

                await conn.commit()
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to persist game buffer: {e}") from e

    async def get_position_stats_batch(self, fens: List[str]) -> Dict[str, "PositionStats"]:
        """Retrieves long-term statistics for a batch of FENs for the analysis pipeline."""
        if not fens:
            return {}
        
        placeholders = ','.join('?' for _ in fens)
        sql = f"SELECT * FROM position_stats WHERE fen IN ({placeholders})"
        
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(sql, tuple(fens)) as cursor:
                    rows = await cursor.fetchall()

                results = {}
                for row in rows:
                    results[row['fen']] = PositionStats(**dict(row))
                return results
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get stats batch: {e}") from e
        
    # --- NEW: Methods for Paginated Game Report ---

    async def get_game_report_count(self, filters: Dict) -> int:
        """
        Gets the total number of unique games that match the given filters.
        This is used to set up the UI for lazy loading (e.g., scrollbar size).
        """
        # Use parameterized query to prevent SQL injection
        where_clause = "WHERE gs.player_name = ?"
        params = (filters['player_name'],)
        query = f"SELECT COUNT(DISTINCT game_id) FROM game_stats gs {where_clause};"
        
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                cursor = await conn.execute(query, tuple(params))
                row = await cursor.fetchone()
                return row[0] if row else 0
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get game report count: {e}") from e

    async def get_paginated_game_report(self, filters: Dict, limit: int, offset: int) -> List[GameReportRow]:
        """
        Fetches a 'page' of aggregated game data for the main report view.
        
        This query is optimized to gather all necessary data for the report in a single pass,

        """
        where_clause = "WHERE gs_filter.player_name = ?"
        params = (filters['player_name'],)

        query = f"""
            WITH GameBlunders AS (
                SELECT
                    m.game_id,
                    SUM(CASE WHEN p.player_to_move = 'w' AND m.classification = 'Blunder' THEN 1 ELSE 0 END) as white_blunders,
                    SUM(CASE WHEN p.player_to_move = 'b' AND m.classification = 'Blunder' THEN 1 ELSE 0 END) as black_blunders
                FROM moves m
                JOIN positions p ON m.fen = p.fen
                WHERE m.classification = 'Blunder'
                GROUP BY m.game_id
            )
            SELECT
                gs.game_id, gs.game_date, gs.result,
                MAX(CASE WHEN gs.player_color = 'White' THEN gs.player_name END) as white_player,
                MAX(CASE WHEN gs.player_color = 'Black' THEN gs.player_name END) as black_player,
                MAX(CASE WHEN gs.player_color = 'White' THEN gs.accuracy_percent END) as white_accuracy,
                MAX(CASE WHEN gs.player_color = 'Black' THEN gs.accuracy_percent END) as black_accuracy,
                COALESCE(gb.white_blunders, 0) as white_blunders,
                COALESCE(gb.black_blunders, 0) as black_blunders,
                -- The opening_id is the same for both players in a game, so MAX() is safe.
                MAX(o.name) as opening_name
            FROM game_stats gs
            LEFT JOIN GameBlunders gb ON gs.game_id = gb.game_id
            -- Directly join with openings table using the new foreign key in game_stats.
            LEFT JOIN openings o ON gs.opening_id = o.opening_id
            WHERE gs.game_id IN (SELECT DISTINCT game_id FROM game_stats gs_filter {where_clause})
            GROUP BY gs.game_id
            ORDER BY gs.game_date DESC, gs.game_time DESC
            LIMIT ? OFFSET ?;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                logger.info(
                    "TDS: EXECUTING PAGINATED GAME REPORT QUERY",
                    sql=query.replace('\n', ' ').strip(),
                    params=params + (limit, offset)
                )
                cursor = await conn.execute(query, params + (limit, offset))
                rows = await cursor.fetchall()
                return [GameReportRow(**dict(row)) for row in rows]
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get paginated game report: {e}") from e
        
    async def get_annotated_pgn(self, game_id: str) -> Optional[str]:
        """
        Retrieves the full annotated PGN text for a single game by its ID.
        """
        query = "SELECT pgn_text FROM annotated_games WHERE game_id = ?;"
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                # No need for a row factory, we just want the first column.
                cursor = await conn.execute(query, (game_id,))
                row = await cursor.fetchone()
                return row[0] if row else None
        except aiosqlite.Error as e:
            logger.error("Failed to retrieve annotated PGN", game_id=game_id, exc_info=True)
            raise PersistenceError(f"Failed to get annotated PGN for game_id {game_id}: {e}") from e

    def _classify_evaluation(self, evaluation: float, player_color: str) -> str:
        """
        Classifies a centipawn evaluation into a discrete state from the player's perspective.
        """
        # Flip the evaluation sign if the player is Black
        if player_color.lower() == 'black':
            evaluation *= -1

        if evaluation > 350:
            return "Winning"
        elif 100 < evaluation <= 350:
            return "Better"
        elif -100 <= evaluation <= 100:
            return "Equal"
        elif -350 <= evaluation < -100:
            return "Worse"
        else:  # evaluation < -350
            return "Losing"

    def _get_terminal_state(self, result: str, player_color: str) -> str:
        """Determines the terminal game state based on result and player color."""
        if result == '1/2-1/2':
            return 'Game Drawn'
        if (result == '1-0' and player_color == 'White') or (result == '0-1' and player_color == 'Black'):
            return 'Game Won'
        return 'Game Lost'

        # --- Dashboard Query Methods (Fully Implemented) ---

    async def get_kpis(self, query_obj: KpiQuery) -> Dict:
        # The query object now encapsulates the logic of which filters to apply.
        where_clause, params = query_obj.build_clause("gs")
        query = f"""
            SELECT
                COUNT(gs.game_id) as total_games,
                AVG(gs.accuracy_percent) as overall_avg_accuracy,
                SUM(CASE WHEN (gs.result = '1-0' AND gs.player_color = 'White') OR (gs.result = '0-1' AND gs.player_color = 'Black') THEN 1 ELSE 0 END) as overall_wins,
                SUM(CASE WHEN (gs.result = '0-1' AND gs.player_color = 'White') OR (gs.result = '1-0' AND gs.player_color = 'Black') THEN 1 ELSE 0 END) as overall_losses,
                SUM(CASE WHEN gs.result = '1/2-1/2' THEN 1 ELSE 0 END) as overall_draws,
                (SELECT AVG(accuracy_percent) FROM (
                    SELECT accuracy_percent FROM game_stats gs {where_clause} ORDER BY gs.game_date DESC LIMIT 20
                )) as recent_avg_accuracy
            FROM game_stats gs {where_clause};
        """
        final_data = {}
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                
                logger.info(
                    "TDS: EXECUTING KPI QUERY",
                    sql=query.replace('\n', ' ').strip(),
                    params=tuple(params) * 2
                )
                # The WHERE clause is used twice, so the params list must be duplicated.
                cursor = await conn.execute(query, tuple(params) * 2)
                
                row = await cursor.fetchone()
                final_data = dict(row) if row and row['total_games'] > 0 else {}
                logger.debug("TDS KPI query complete.", data=final_data)
                return final_data
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get KPIs: {e}") from e
        finally:
            logger.debug("TDS: get_kpis returning data.", data=final_data)

    async def get_accuracy_trend(self, query_obj: AccuracyTrendQuery) -> List[Dict]:
        """
        Fetches trend data aggregated by a specified time period and for a
        specified metric, for use in the performance calendar.
        """
        where_clause, params = query_obj.build_clause("gs")
        
        # --- NEW: Add date range filtering ---
        if query_obj.date_range:
            months = 0
            if query_obj.date_range == "Last 3 Months":
                months = 3
            elif query_obj.date_range == "Last 6 Months":
                months = 6
            
            if months > 0:
                # SQLite's date functions work with 'YYYY-MM-DD'.
                where_clause += f" AND REPLACE(gs.game_date, '.', '-') >= date('now', '-{months} months')"

        # --- 1. Dynamic Granularity Expression ---
        granularity = query_obj.granularity
        if granularity == "Weekly":
            date_key_expression = "strftime('%Y-%W', REPLACE(gs.game_date, '.', '-'))"
        elif granularity == "Monthly":
            date_key_expression = "strftime('%Y-%m', REPLACE(gs.game_date, '.', '-'))"
        elif granularity == "Daily":
            date_key_expression = "strftime('%Y-%m-%d', REPLACE(gs.game_date, '.', '-'))"
        else:
            logger.warning("Invalid granularity received, defaulting to Weekly.", received=granularity)
            date_key_expression = "strftime('%Y-%W', REPLACE(gs.game_date, '.', '-'))"

        # --- 2. Dynamic Metric Expression ---
        metric = query_obj.metric
        if metric == "Accuracy":
            metric_expression = "AVG(gs.accuracy_percent)"
        elif metric == "Win Rate":
            metric_expression = "SUM(CASE WHEN (gs.result = '1-0' AND gs.player_color = 'White') OR (gs.result = '0-1' AND gs.player_color = 'Black') THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(gs.game_id)"
        else:
            logger.warning("Invalid metric received, defaulting to Accuracy.", received=metric)
            metric_expression = "AVG(gs.accuracy_percent)"

        # --- 3. Construct Final Query ---
        query = f"""
            SELECT
                {date_key_expression} as date_key,
                {metric_expression} as metric_value,
                COUNT(gs.game_id) as game_count,
                json_group_array(
                    json_object(
                        'game_id', gs.game_id,
                        'opponent_rating', gs.opponent_rating,
                        'result', gs.result,
                        'player_color', gs.player_color
                    )
                ) as games_json
            FROM game_stats gs
            {where_clause} 
            AND gs.accuracy_percent IS NOT NULL 
            AND gs.game_date IS NOT NULL 

            GROUP BY date_key
            ORDER BY date_key;
        """
        result_list = []
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                logger.info(
                    "TDS: EXECUTING DYNAMIC TREND QUERY",
                    sql=query.replace('\n', ' ').strip(),
                    params=tuple(params)
                )
                cursor = await conn.execute(query, tuple(params))
                result_list = [dict(row) for row in await cursor.fetchall()]
                logger.debug("TDS Dynamic Trend query complete.", item_count=len(result_list))
                return result_list
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get dynamic trend data: {e}") from e
        finally:
            logger.debug("TDS: get_accuracy_trend returning dynamic data.", count=len(result_list))

    async def get_opening_performance_table(self, query_obj: OpeningPerformanceQuery) -> List[Dict]:
        """
        Fetches aggregated performance data for each opening played by the user.
        This version uses a corrected and more efficient JOIN strategy.
        """
        where_clause, params = query_obj.build_clause("gs")
        
        query = f"""
            SELECT
                o.name AS opening_name,
                gs.opening_id,
                COUNT(gs.game_id) AS games_played,
                SUM(CASE WHEN (gs.result = '1-0' AND gs.player_color = 'White') OR (gs.result = '0-1' AND gs.player_color = 'Black') THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN gs.result = '1/2-1/2' THEN 1 ELSE 0 END) AS draws,
                AVG(gs.accuracy_percent) AS avg_accuracy
            FROM game_stats AS gs
            JOIN openings AS o ON gs.opening_id = o.opening_id
            {where_clause} AND gs.opening_id IS NOT NULL
            GROUP BY gs.opening_id, o.name
            HAVING games_played > 0
            ORDER BY games_played DESC, avg_accuracy DESC;
        """
        
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                logger.info(
                    "TDS: EXECUTING OPENING PERFORMANCE QUERY",
                    sql=query.replace('\n', ' ').strip(),
                    params=tuple(params)
                )
                cursor = await conn.execute(query, tuple(params))
                results = [dict(row) for row in await cursor.fetchall()]
                logger.info("TDS: Found opening performance data.", count=len(results))
                return results
        except aiosqlite.Error as e:
            logger.error("TDS: Failed to get opening performance", exc_info=e)
            raise PersistenceError(f"Failed to get opening performance: {e}") from e
        
    async def get_cognitive_dissonance_positions(self, query_obj: CognitiveDissonanceQuery) -> List[Dict]:
        where_clause, params = query_obj.build_clause("gs")
        query = f"""
            SELECT
                m.game_id, m.ply, m.fen, m.time_spent_seconds, m.cpl, m.post_move_eval,
                m.move_uci as played_move_uci, m.best_move_san,
                (m.time_spent_seconds * m.cpl) as dissonance_score
            FROM moves m
            JOIN game_stats gs ON m.game_id = gs.game_id
            {where_clause} AND gs.opening_id = ? AND m.cpl > 100
            ORDER BY dissonance_score DESC LIMIT ?;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                
                final_params = tuple(params + [query_obj.opening_id, query_obj.limit])

                logger.info(
                    "TDS: EXECUTING DISSONANCE QUERY",
                    sql=query.replace('\n', ' ').strip(), params=final_params
                )
                
                cursor = await conn.execute(query, final_params)
                results = await cursor.fetchall()
                logger.debug("TDS: Raw dissonance data from DB.", data=[dict(r) for r in results])
                logger.info("TDS: Dissonance query returned rows.", count=len(results))
                
                return [dict(row) for row in results]
                
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get dissonance positions: {e}") from e
        
    async def get_blunder_reel_data(self, query_obj: BlunderReelQuery) -> List[Dict]:
        where_clause, params = query_obj.build_clause("gs")
        query = f"""
            SELECT m.game_id, m.ply, m.fen as fen_before_blunder, m.move_uci as played_move_uci, m.cpl
            FROM moves m
            JOIN game_stats gs ON m.game_id = gs.game_id
            JOIN positions p ON m.fen = p.fen
            {where_clause}
            AND (
                (gs.player_color = 'White' AND p.player_to_move = 'w') OR
                (gs.player_color = 'Black' AND p.player_to_move = 'b')
            )
            AND m.classification = 'Blunder' ORDER BY m.cpl DESC LIMIT ?;
        """

        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params + [query_obj.limit]))
                rows = await cursor.fetchall()
                enriched_data = []
                for row in rows:
                    data = dict(row)
                    board = chess.Board(data['fen_before_blunder'])
                    try:
                        played_move = chess.Move.from_uci(data['played_move_uci'])
                        data['played_move_san'] = board.san(played_move)
                    except (ValueError, chess.InvalidMoveError):
                        data['played_move_san'] = data['played_move_uci']
                    data['correct_move_san'] = "N/A"
                    data['correct_eval_str'] = ""
                    enriched_data.append(data)
                return enriched_data
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get blunder reel data: {e}") from e