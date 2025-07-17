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
    PositionStats, QueuePayload, QueuedPosition, QueuedStatUpdate, QueuedMove,
    QueuedGameStat, QueuedOpeningLink
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
            ply INTEGER NOT NULL, move_uci TEXT NOT NULL, cpl REAL, classification TEXT NOT NULL,
            time_spent_seconds REAL, post_move_eval REAL, is_reciprocal_blunder BOOLEAN DEFAULT 0,
            FOREIGN KEY (fen) REFERENCES positions(fen) ON DELETE CASCADE, UNIQUE(game_id, ply)
        );
        CREATE TABLE IF NOT EXISTS openings (opening_id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS position_to_opening (
            fen TEXT, opening_id INTEGER, occurrence_count INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (fen, opening_id),
            FOREIGN KEY (fen) REFERENCES positions(fen) ON DELETE CASCADE,
            FOREIGN KEY (opening_id) REFERENCES openings(opening_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS game_stats (
            game_id TEXT PRIMARY KEY,
            player_name TEXT NOT NULL,
            player_color TEXT NOT NULL,
            is_user_game INTEGER NOT NULL DEFAULT 0,
            game_date DATE,
            time_control_category TEXT,
            opponent_rating INTEGER,
            eval_volatility REAL,
            accuracy_percent REAL,
            result TEXT
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
            elif isinstance(item, QueuedOpeningLink):
                game_data['opening_links'].append(asdict(item))
                
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
                             (game_id, fen, ply, move_uci, cpl, classification, time_spent_seconds, is_reciprocal_blunder, post_move_eval) 
                             VALUES (:game_id, :fen, :ply, :move_uci, :cpl, :classification, :time_spent_seconds, :is_reciprocal_blunder, :post_move_eval)"""
                    await conn.executemany(sql, moves_data)

                if game_stats_data := game_data.get('game_stats'):
                    sql = """INSERT OR IGNORE INTO game_stats 
                             (game_id, player_name, player_color, is_user_game, game_date, time_control_category, opponent_rating, eval_volatility, accuracy_percent, result) 
                             VALUES (:game_id, :player_name, :player_color, :is_user_game, :game_date, :time_control_category, :opponent_rating, :eval_volatility, :accuracy_percent, :result)"""
                    await conn.executemany(sql, game_stats_data)
                
                if opening_links_data := game_data.get('opening_links'):
                    for link in opening_links_data:
                        cursor = await conn.execute("SELECT opening_id FROM openings WHERE name = ?", (link['opening_name'],))
                        row = await cursor.fetchone()
                        if row: opening_id = row['opening_id']
                        else:
                            cursor = await conn.execute("INSERT INTO openings (name) VALUES (?)", (link['opening_name'],))
                            opening_id = cursor.lastrowid
                        await conn.execute("INSERT INTO position_to_opening (fen, opening_id) VALUES (?, ?) ON CONFLICT(fen, opening_id) DO UPDATE SET occurrence_count = occurrence_count + 1;", (link['fen'], opening_id))
                
                await conn.commit()
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to persist game buffer: {e}") from e

    async def get_position_stats_batch(self, fens: List[str]) -> Dict[str, "PositionStats"]:
        """Retrieves long-term statistics for a batch of FENs for the analysis pipeline."""
        if not fens: return {}
        
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
        
    def _build_filter_clause(self, filters: Dict, table_alias: str = "gs") -> Tuple[str, List[Any]]:
        """Builds a SQL WHERE clause and parameters from a filter dictionary."""
        params = []
        where_clauses = [f"{table_alias}.is_user_game = 1"]
        
        if tc := filters.get('time_control'):
            where_clauses.append(f"{table_alias}.time_control_category = ?")
            params.append(tc)
        if color := filters.get('color'):
            where_clauses.append(f"{table_alias}.player_color = ?")
            params.append(color)
            
        return f"WHERE {' AND '.join(where_clauses)}", params

        
    # --- Dashboard Query Methods (Fully Implemented) ---

    async def get_kpis(self, filters: Dict) -> Dict:
        where_clause, params = self._build_filter_clause(filters, "gs")
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
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params))
                row = await cursor.fetchone()
                return dict(row) if row and row['total_games'] > 0 else {}
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get KPIs: {e}") from e
        

    async def get_accuracy_trend(self, filters: Dict) -> List[Dict]:
        """Fetches accuracy over time, respecting filters."""
        where_clause, params = self._build_filter_clause(filters, "gs")
        
        # Select all necessary columns for the "Opponent Cloud" plot
        query = f"""
            SELECT 
                gs.game_id, 
                gs.game_date, 
                gs.accuracy_percent,
                gs.result,
                gs.player_color,
                gs.opponent_rating
            FROM game_stats gs
            {where_clause} AND gs.accuracy_percent IS NOT NULL
            ORDER BY gs.game_date;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params))
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get accuracy trend: {e}") from e

    async def get_performance_by_phase(self, filters: Dict) -> List[Dict]:
        where_clause, params = self._build_filter_clause(filters)
        query = f"""
            SELECT p.game_phase, AVG(m.cpl) as average_cpl,
                   SUM(CASE WHEN m.classification = 'Blunder' THEN 1 ELSE 0 END) as blunder_count
            FROM moves m JOIN positions p ON m.fen = p.fen JOIN game_stats gs ON m.game_id = gs.game_id
            {where_clause} GROUP BY p.game_phase;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params))
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get phase performance: {e}") from e

    async def get_decision_making_matrix_data(self, filters: Dict) -> List[Dict]:
        where_clause, params = self._build_filter_clause(filters)
        query = f"""
            SELECT m.time_spent_seconds, ps.eval_std_dev, m.cpl, m.classification, m.game_id, m.ply
            FROM moves m JOIN position_stats ps ON m.fen = ps.fen JOIN game_stats gs ON m.game_id = gs.game_id
            {where_clause} AND m.time_spent_seconds IS NOT NULL AND ps.eval_std_dev IS NOT NULL;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params))
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get decision matrix data: {e}") from e

    async def get_tactical_signature(self, filters: Dict) -> List[Dict]:
        where_clause, params = self._build_filter_clause(filters)
        query = f"""
            SELECT m.classification, ps.tactic_type, COUNT(*) as frequency
            FROM moves m JOIN position_stats ps ON m.fen = ps.fen JOIN game_stats gs ON m.game_id = gs.game_id
            {where_clause} AND ps.tactic_type IS NOT NULL AND m.classification IN ('Blunder', 'Mistake')
            GROUP BY m.classification, ps.tactic_type;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params))
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get tactical signature data: {e}") from e
            
    async def get_opening_performance_table(self, filters: Dict) -> List[Dict]:
        where_clause, params = self._build_filter_clause(filters)
        query = f"""
            SELECT o.name as opening_name, o.opening_id, COUNT(DISTINCT gs.game_id) as games_played,
                   SUM(CASE WHEN (gs.result = '1-0' AND gs.player_color = 'White') OR (gs.result = '0-1' AND gs.player_color = 'Black') THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN gs.result = '1/2-1/2' THEN 1 ELSE 0 END) as draws,
                   AVG(gs.accuracy_percent) as avg_accuracy
            FROM openings o
            JOIN position_to_opening pto ON o.opening_id = pto.opening_id
            JOIN game_stats gs ON pto.fen IN (SELECT fen FROM moves WHERE game_id = gs.game_id)
            {where_clause}
            GROUP BY o.opening_id, o.name HAVING games_played > 0 ORDER BY games_played DESC;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params))
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get opening performance: {e}") from e

    async def get_cognitive_dissonance_positions(self, opening_id: int, filters: Dict) -> List[Dict]:
        where_clause, params = self._build_filter_clause(filters, "gs")
        query = f"""
            SELECT m.fen, m.time_spent_seconds, m.cpl, (m.time_spent_seconds * m.cpl) as dissonance_score
            FROM moves m JOIN position_to_opening pto ON m.fen = pto.fen JOIN game_stats gs ON m.game_id = gs.game_id
            {where_clause} AND pto.opening_id = ? AND m.cpl > 100
            ORDER BY dissonance_score DESC LIMIT 5;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params + [opening_id]))
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get dissonance positions: {e}") from e

    async def get_blunder_reel_data(self, filters: Dict, limit: int = 20) -> List[Dict]:
        where_clause, params = self._build_filter_clause(filters, "gs")
        query = f"""
            SELECT m.game_id, m.ply, m.fen as fen_before_blunder, m.move_uci as played_move_uci, m.cpl
            FROM moves m JOIN game_stats gs ON m.game_id = gs.game_id
            {where_clause} AND m.classification = 'Blunder' ORDER BY m.cpl DESC LIMIT ?;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params + [limit]))
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
        
    async def get_tilt_analysis_data(self, filters: Dict) -> List[Dict]:
        where_clause, params = self._build_filter_clause(filters, "gs")
        # --- CORRECTED: Added the 'gs' alias to the FROM clause ---
        query = f"""
            SELECT gs.game_id, gs.game_date, gs.result, gs.player_color,
                   (SELECT COUNT(*) FROM moves m WHERE m.game_id = gs.game_id AND m.classification = 'Blunder') as blunder_count
            FROM game_stats gs {where_clause}
            ORDER BY gs.game_date, gs.game_id;
        """
        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(params))
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get tilt analysis data: {e}") from e

    async def get_performance_funnel_data(self, filters: Dict) -> Dict:
        """Calculates the stages of the performance funnel using accurate evaluation data."""
        where_clause, params = self._build_filter_clause(filters, "gs")
        
        # We define "advantage" as an evaluation > 150 centipawns (1.5 pawns)
        # We check for this advantage at the end of the opening (ply 24)
        advantage_threshold = 150 
        opening_ply_limit = 24

        query = f"""
            WITH AdvantageousGames AS (
                SELECT DISTINCT m.game_id
                FROM moves m
                JOIN game_stats gs ON m.game_id = gs.game_id
                {where_clause}
                AND m.ply = ?
                AND (
                    (gs.player_color = 'White' AND m.post_move_eval > ?) OR
                    (gs.player_color = 'Black' AND m.post_move_eval < -?)
                )
            )
            SELECT
                (SELECT COUNT(*) FROM game_stats gs {where_clause}) as total_user_games,
                (SELECT COUNT(*) FROM AdvantageousGames) as games_with_advantage,
                (
                    SELECT COUNT(*)
                    FROM game_stats gs
                    WHERE gs.game_id IN (SELECT game_id FROM AdvantageousGames)
                    AND ((gs.result = '1-0' AND gs.player_color = 'White') OR (gs.result = '0-1' AND gs.player_color = 'Black'))
                ) as converted_wins;
        """
        
        # The parameters need to be structured carefully for this query
        full_params = params + [opening_ply_limit, advantage_threshold, advantage_threshold] + params

        try:
            async with aiosqlite.connect(self._db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, tuple(full_params))
                row = await cursor.fetchone()
                return dict(row) if row and row['total_user_games'] > 0 else {}
        except aiosqlite.Error as e:
            raise PersistenceError(f"Failed to get funnel data: {e}") from e
