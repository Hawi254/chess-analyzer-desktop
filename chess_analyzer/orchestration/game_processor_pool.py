# chess_analysis_project/orchestration/game_processor_pool.py
"""
The primary worker-management engine of the application.
"""

import asyncio
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, TYPE_CHECKING, Optional, Callable, Awaitable

import structlog

from chess_analyzer.exceptions import EngineError, PgnParsingError
from chess_analyzer.orchestration.game_processor import GameProcessor
from chess_analyzer.tracing import CorrelationID
from chess_analyzer.types import GameSummary, ProcessedGameResult

if TYPE_CHECKING:
    import chess.pgn
    from chess_analyzer.config.settings import RunConfig
    from chess_analyzer.services.engine_pool import EnginePool
    from chess_analyzer.services.pgn_service import PgnService

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[int, int], Awaitable[None]]

class GameProcessorPool:
    """Manages the concurrent processing of a stream of games."""

    def __init__(
        self,
        config: "RunConfig",
        processor: GameProcessor,
        engine_pool: "EnginePool",
        pgn_service: "PgnService",
        pgn_write_queue: asyncio.Queue,
        shutdown_event: asyncio.Event,
        progress_callback: Optional[ProgressCallback] = None,
        total_games: int = 0,
    ):
        self._config = config
        self._processor = processor
        self._engine_pool = engine_pool
        self._pgn_service = pgn_service
        self._pgn_write_queue = pgn_write_queue
        self._shutdown_event = shutdown_event
        self._semaphore = asyncio.Semaphore(config.concurrency)
        self._retry_counts: Dict[str, int] = defaultdict(int)
        self._progress_callback = progress_callback
        self._total_games = total_games

    async def _process_one_game_wrapper(self, game: "chess.pgn.Game", cid: CorrelationID) -> ProcessedGameResult:
        """A safe wrapper for processing a single game."""
        structlog.contextvars.bind_contextvars(correlation_id=cid.short_id)
        engine = None
        try:
            engine = await self._engine_pool.acquire()
            if not await engine.is_healthy():
                raise EngineError("Acquired engine is unhealthy", engine=engine)
            return await self._processor.process_game(game, engine, self._shutdown_event)
        finally:
            if engine: self._engine_pool.release(engine)
            self._semaphore.release()
            structlog.contextvars.clear_contextvars()

    async def run(self, input_pgn_path: Path, processed_ids: Set[str], run_id: str) -> List[ProcessedGameResult]:
        """The main execution loop for the pool."""
        all_results: List[ProcessedGameResult] = []
        pending_tasks: Dict[asyncio.Task, "chess.pgn.Game"] = {}
        work_queue: asyncio.Queue["chess.pgn.Game"] = asyncio.Queue()

        async def _filler():
            async for game in self._pgn_service.stream_games(input_pgn_path):
                if self._shutdown_event.is_set(): break
                await work_queue.put(game)
            await work_queue.put(None)
        filler_task = asyncio.create_task(_filler())

        def _done_callback(task: asyncio.Task) -> None:
            """Callback executed when a game processing task completes or fails."""
            original_game = pending_tasks.pop(task, None)
            if not original_game: return
            
            game_id = self._pgn_service._extract_game_id(original_game.headers)
            try:
                result: ProcessedGameResult = task.result()
                if result and result.summary:
                    all_results.append(result)
                    if self._progress_callback:
                        asyncio.create_task(self._progress_callback(len(all_results), self._total_games))
                    
                    if result.annotated_game and result.summary.narrative:
                        result.annotated_game.comment = f"{{ {result.summary.narrative} }} {result.annotated_game.comment}".strip()
                    
                    if result.annotated_game:
                        self._pgn_write_queue.put_nowait(result.annotated_game)
            
            except PgnParsingError as e:
                logger.warning("Skipped game due to PGN parsing error.", game_id=game_id, error=str(e), show_in_gui=True)
            except EngineError as e:
                logger.error("Engine error processing game.", game_id=game_id, error=str(e), show_in_gui=True)
                if self._retry_counts[game_id] < self._config.max_retries:
                    self._retry_counts[game_id] += 1
                    logger.info("Rescheduling game for analysis.", game_id=game_id, attempt=self._retry_counts[game_id], show_in_gui=True)
                    work_queue.put_nowait(original_game)
                    if e.engine: asyncio.create_task(self._engine_pool.retire_and_replace(e.engine))
                else:
                    logger.error("Max retries exceeded for game.", game_id=game_id, show_in_gui=True)
            except asyncio.CancelledError:
                logger.warning("Game processing task was cancelled.", game_id=game_id)
            except Exception as e:
                logger.error("Unhandled exception in game task.", game_id=game_id, exc_info=e)

        while not self._shutdown_event.is_set():
            try:
                game = await asyncio.wait_for(work_queue.get(), timeout=1.0)
                if game is None: break
                
                if self._shutdown_event.is_set():
                    logger.info("Shutdown signaled, not starting new tasks from queue.")
                    break

                await self._semaphore.acquire()
                cid = CorrelationID(
                    run_id=run_id,
                    game_id=self._pgn_service._extract_game_id(game.headers),
                    task_id=uuid.uuid4().hex[:8]
                )
                task = asyncio.create_task(self._process_one_game_wrapper(game, cid))
                pending_tasks[task] = game
                task.add_done_callback(_done_callback)
            except asyncio.TimeoutError:
                continue

        if pending_tasks:
            for task in pending_tasks:
                task.cancel()
            await asyncio.gather(*list(pending_tasks.keys()), return_exceptions=True)
        if not filler_task.done(): filler_task.cancel()
        
        # --- CORRECTED: Return the correct variable ---
        return all_results