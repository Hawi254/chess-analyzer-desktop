# chess_analysis_project/orchestration/orchestrator.py
"""
The top-level application orchestrator.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Awaitable, TYPE_CHECKING

import structlog

from chess_analyzer.config.settings import RunConfig
from chess_analyzer.orchestration.annotator_client import AnnotatorClient
from chess_analyzer.orchestration.game_processor import GameProcessor
from chess_analyzer.orchestration.game_processor_pool import GameProcessorPool
from chess_analyzer.orchestration.persistence_client import PersistenceClient
from chess_analyzer.orchestration.pipeline_factory import create_pipeline
from chess_analyzer.output.report_generator import ReportGenerator
from chess_analyzer.services.analysis_provider import AnalysisProvider
from chess_analyzer.services.engine_pool import EnginePool
from chess_analyzer.services.pgn_service import PgnService
from chess_analyzer.services.sqlite_cache_service import SqliteCacheService
from chess_analyzer.services.stockfish_service import StockfishService
from chess_analyzer.persistence.training_data_service import TrainingDataService
from chess_analyzer.types import ProcessedGameResult, RunReport
from chess_analyzer.core import (
    move_classifier, narrative_generator, pgn_parser, summary_aggregator
)

if TYPE_CHECKING:
    import chess.pgn

ProgressCallback = Callable[[int, int], Awaitable[None]]
logger = structlog.get_logger(__name__)

class AnalysisOrchestrator:
    """The main application class, orchestrating the entire analysis run."""

    def __init__(
        self,
        config: RunConfig,
        persistence_client: PersistenceClient,
        progress_callback: Optional[ProgressCallback] = None,
        shutdown_event: Optional[asyncio.Event] = None
    ):
        self._config = config
        self._persistence_client = persistence_client
        self._shutdown_event = shutdown_event or asyncio.Event()
        self._pgn_write_queue: asyncio.Queue["chess.pgn.Game"] = asyncio.Queue()
        self._background_tasks: List[asyncio.Task] = []
        self._progress_callback = progress_callback

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

        total_games = 0
        try:
            with open(self._config.input_pgn_path, 'r', encoding='utf-8', errors='replace') as f:
                total_games = sum(1 for line in f if line.strip().startswith('[Event "'))
        except FileNotFoundError:
            logger.error("Input PGN file not found.", path=self._config.input_pgn_path, show_in_gui=True)
            return RunReport(results=[], processed_game_count=0, user_found_in_games=False, warnings=["Input PGN file not found."])
        
        try:

            db_service_for_context = TrainingDataService(self._config.db_path)

            engine_factory = StockfishService.create
            async with SqliteCacheService(self._config.cache_settings) as cache, \
                         EnginePool(self._config.engine_pool_settings, engine_factory) as engine_pool:
                
                self._background_tasks.append(asyncio.create_task(self._pgn_writer_task(PgnService(), Path(self._config.output_pgn_path), self._pgn_write_queue)))
                
                services = {
                    "pgn_service": PgnService(),
                    "engine_pool": engine_pool,
                    "analysis_provider": AnalysisProvider(cache, self._config.analysis_settings),
                    "persistence_client": self._persistence_client,
                    "annotator_client": AnnotatorClient(),
                    "move_classifier": move_classifier.MoveClassifier(),
                    "narrative_generator_func": narrative_generator.generate_game_narrative,
                    "pgn_parser_func": pgn_parser.parse_game_data,
                    "persistence_service": db_service_for_context # Add the required service
                }
                pipeline = create_pipeline(services)
                game_processor = GameProcessor(services, self._config, pipeline)
                
                game_pool = GameProcessorPool(
                    config=self._config, processor=game_processor, engine_pool=engine_pool,
                    pgn_service=services["pgn_service"], pgn_write_queue=self._pgn_write_queue,
                    shutdown_event=self._shutdown_event, progress_callback=self._progress_callback,
                    total_games=total_games,
                )
                
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
                        logger.info(f"Generating summary report at {self._config.output_csv_path}", show_in_gui=True)
                        ReportGenerator().generate_csv_report_from_summaries(summaries, Path(self._config.output_csv_path))
                
                return report
        except Exception as e:
            logger.critical("Orchestrator caught unhandled exception.", exc_info=True, show_in_gui=True)
            self._shutdown_event.set()
            return RunReport(results=[], processed_game_count=0, user_found_in_games=False, warnings=[f"Fatal error: {e}"])
        finally:
            await self._shutdown()
            logger.info("Analysis run finished.", run_id=run_id, show_in_gui=True)