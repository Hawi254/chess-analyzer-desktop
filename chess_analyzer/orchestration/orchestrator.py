# chess_analysis_project/orchestration/orchestrator.py
"""
The top-level application orchestrator.
"""

import asyncio
import uuid
import punq

from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Awaitable, TYPE_CHECKING
import structlog

from chess_analyzer.config.settings import RunConfig
from chess_analyzer.orchestration.game_processor_pool import GameProcessorPool
from chess_analyzer.output.report_generator import ReportGenerator
from chess_analyzer.types import GameSummary
from chess_analyzer.services.engine_pool import EnginePool
from chess_analyzer.services.pgn_service import PgnService
from chess_analyzer.services.sqlite_cache_service import SqliteCacheService
from chess_analyzer.types import ProcessedGameResult, RunReport

if TYPE_CHECKING:
    import chess.pgn

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[int, int], Awaitable[None]]

class PgnIngester:
    """
    Responsible for reading a PGN file and providing a stream of game data.
    """
    def __init__(self, file_path: Path):
        self._file_path = file_path

    def count_games(self) -> int:
        """
        Counts the number of games in the PGN file.
        """
        try:
            with open(self._file_path, 'r', encoding='utf-8', errors='replace') as f:
                return sum(1 for line in f if line.strip().startswith('[Event "'))
        except FileNotFoundError:
            logger.error("Input PGN file not found.", path=self._file_path, show_in_gui=True)
            return 0

    async def stream_games(self):
        """
        Streams games from the PGN file.  This is a placeholder; in a more
        advanced implementation, this could yield `chess.pgn.Game` objects.
        """
        # In a real implementation, this method would read and yield games.
        # For the sake of this example, we'll just log a message.
        logger.info("Streaming games from PGN file.", path=self._file_path)
        yield  # Placeholder: replace with actual game objects


class ReportService:
    """
    Responsible for generating reports from processed game data.
    """
    def __init__(self, config: RunConfig):
        self._config = config

    def generate_summary_report(self, summaries: List[GameSummary]):
        """
        Generates a CSV report from a list of game summaries.
        """
        if summaries:
            logger.info(f"Generating summary report at {self._config.output_csv_path}", show_in_gui=True)
            ReportGenerator().generate_csv_report_from_summaries(summaries, Path(self._config.output_csv_path))

class AnalysisOrchestrator:
    def __init__(
        self,
        config: RunConfig,
        container: punq.Container,
        progress_callback: Optional[ProgressCallback] = None,
        shutdown_event: Optional[asyncio.Event] = None
    ):
        self._config = config
        self._container = container
        self._progress_callback = progress_callback
        self._shutdown_event = shutdown_event or asyncio.Event()
        self._pgn_write_queue: asyncio.Queue["chess.pgn.Game"] = asyncio.Queue()
        self._report_service = ReportService(config)
        self._background_tasks: List[asyncio.Task] = []


    async def _pgn_writer_task(self, service: PgnService, path: Path, queue: asyncio.Queue):
        logger.info("PGN writer task started.", path=str(path))
        try:
            while not self._shutdown_event.is_set():
                try:
                    game = await asyncio.wait_for(queue.get(), timeout=1.0)
                    try:
                        if game is None: break
                        await service.export_annotated_game(game, path)
                    finally:
                        # This ensures task_done is only called after a successful get()
                        queue.task_done()
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.debug("PGN writer task was cancelled.")
        except Exception:
            logger.error("PGN writer task error.", exc_info=True)
        logger.info("PGN writer task finished.")

    async def _shutdown(self):
        if self._background_tasks:
            logger.debug("Cancelling orchestrator background tasks.")
            for task in self._background_tasks:
                if not task.done(): task.cancel()
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

    async def run(self) -> RunReport:
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        logger.info("Starting analysis orchestration.", run_id=run_id, show_in_gui=True)

        pgn_ingester = PgnIngester(Path(self._config.input_pgn_path))
        total_games = pgn_ingester.count_games()
        if total_games == 0:
            return RunReport(results=[], processed_game_count=0, user_found_in_games=False, warnings=["Input PGN file not found."]) # Or handle appropriately
        
        # The EnginePool and SqliteCacheService are now managed as async context managers
        # resolved directly from the container.
        try:
            async with self._container.resolve(SqliteCacheService) as cache, \
                         self._container.resolve(EnginePool) as engine_pool:
                
                self._background_tasks.append(asyncio.create_task(self._pgn_writer_task(PgnService(), Path(self._config.output_pgn_path), self._pgn_write_queue)))
                
                # Resolve the fully configured GameProcessorPool from the container.
                game_pool = self._container.resolve(GameProcessorPool, total_games=total_games, pgn_write_queue=self._pgn_write_queue, progress_callback=self._progress_callback, shutdown_event=self._shutdown_event)
                
                completed_results = await game_pool.run(Path(self._config.input_pgn_path), set(), run_id)
                
                user_found = False
                if self._config.user_player_name:
                    user_name_lower = self._config.user_player_name.strip().lower()
                    for res in completed_results:
                        if res.summary and (
                            res.summary.metadata.white_player.strip().lower() == user_name_lower or
                            res.summary.metadata.black_player.strip().lower() == user_name_lower
                        ):
                            user_found = True
                            break
                
                report = RunReport(
                    results=completed_results, processed_game_count=len(completed_results),
                    user_found_in_games=user_found
                )
                
                logger.info("Main processing complete. Draining writer queues.", show_in_gui=True)
                await self._pgn_write_queue.join()
                await self._pgn_write_queue.put(None)
                
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
                
                if not self._shutdown_event.is_set() and report.results:
                    summaries = [res.summary for res in report.results if res.summary]
                    if summaries:
                        self._report_service.generate_summary_report(summaries)
                return report
        except Exception as e:
            logger.critical("Orchestrator caught unhandled exception.", exc_info=True, show_in_gui=True)
            self._shutdown_event.set()
            return RunReport(results=[], processed_game_count=0, user_found_in_games=False, warnings=[f"Fatal error: {e}"])
        finally:
            await self._shutdown()
            logger.info("Analysis run finished.", run_id=run_id, show_in_gui=True)