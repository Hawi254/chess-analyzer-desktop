# chess_analysis_project/app_controller.py
"""
Contains the main application logic controller and the background workers.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import asdict, is_dataclass

from PySide6.QtCore import QObject, Signal, QThread
import structlog

from chess_analyzer.config.settings import (
    AnalysisSettings, CacheSettings, EnginePoolSettings,
    EngineSettings, RunConfig, settings
)
from chess_analyzer.orchestration.orchestrator import AnalysisOrchestrator
from chess_analyzer.orchestration.persistence_client import PersistenceClient
from chess_analyzer.persistence.training_data_service import TrainingDataService
from chess_analyzer.services.database_manager import DatabaseManager
from chess_analyzer.types import (
    ProcessedGameResult, RunReport, GameSummary, GameStatistics, PlayerStats, GameMetadata
)
from chess_analyzer.utils.system_utils import find_stockfish_executable
from state.app_state import AppState

logger = structlog.get_logger(__name__)


class AnalysisWorker(QObject):
    """Worker to perform the main game analysis."""
    # --- CORRECTED: Signal now emits the RunReport object ---
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, run_config: RunConfig, persistence_client: PersistenceClient, shutdown_event: asyncio.Event, parent=None):
        super().__init__(parent)
        self._run_config = run_config
        self._persistence_client = persistence_client
        self._shutdown_event = shutdown_event

    def run_analysis(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def progress_callback(processed_count: int, total_games: int):
                self.progress.emit(processed_count, total_games)

            orchestrator = AnalysisOrchestrator(
                self._run_config,
                persistence_client=self._persistence_client,
                progress_callback=progress_callback,
                shutdown_event=self._shutdown_event
            )
            # The orchestrator now returns a RunReport object
            report = loop.run_until_complete(orchestrator.run())
            if not self._shutdown_event.is_set():
                self.finished.emit(asdict(report))
        except Exception as e:
            logger.error("Analysis worker failed", exc_info=True)
            self.error.emit(f"Failed to run analysis: {e}")
        finally:
            loop.close()



class StatisticsWorker(QObject):
    """Worker to fetch all dashboard data from the database asynchronously."""
    kpi_data_ready = Signal(dict)
    trend_data_ready = Signal(list)
    phase_data_ready = Signal(list)
    decision_matrix_data_ready = Signal(list)
    tactical_signature_data_ready = Signal(list)
    tilt_analysis_data_ready = Signal(list)
    funnel_data_ready = Signal(dict)
    opening_table_ready = Signal(list)
    dissonance_data_ready = Signal(list)
    blunder_reel_data_ready = Signal(list)

    finished = Signal()
    error = Signal(str)

    def __init__(self, db_manager: DatabaseManager, task_queue: asyncio.Queue, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.task_queue = task_queue # The new task queue
        self._is_running = True
        self.filters: Dict = {} # Filters will now be set by a task

    def stop(self):
        self._is_running = False

    def run(self):
        """Creates and runs a persistent event loop to process tasks from a queue."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.process_tasks())
        except Exception as e:
            logger.error("Statistics worker event loop crashed", exc_info=True)
            self.error.emit(f"Statistics service failed: {e}")
        finally:
            self.finished.emit()
            loop.close()

    async def process_tasks(self):
        """The main consumer loop for the worker."""
        while self._is_running:
            try:
                task_name, payload = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                
                if task_name == 'fetch_initial':
                    self.filters = payload # Set the filters for this session
                    await self.fetch_initial_data()
                elif task_name == 'fetch_dissonance':
                    await self._async_fetch_dissonance(payload)
                
                self.task_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception:
                logger.error("Error processing statistics task", exc_info=True)


    async def fetch_initial_data(self):
        db_service = self.db_manager.get_service()
        # --- REWRITTEN FOR CORRECTNESS AND CLARITY ---
        tasks = {
            "kpi": db_service.get_kpis(self.filters),
            "trend": db_service.get_accuracy_trend(self.filters),
            "phase": db_service.get_performance_by_phase(self.filters),
            "matrix": db_service.get_decision_making_matrix_data(self.filters),
            "signature": db_service.get_tactical_signature(self.filters),
            "tilt": db_service.get_tilt_analysis_data(self.filters),
            "funnel": db_service.get_performance_funnel_data(self.filters),
            "opening_table": db_service.get_opening_performance_table(self.filters),
            "blunder_reel": db_service.get_blunder_reel_data(self.filters)
        }
        signal_map = {
            "kpi": self.kpi_data_ready, "trend": self.trend_data_ready,
            "phase": self.phase_data_ready, "matrix": self.decision_matrix_data_ready,
            "signature": self.tactical_signature_data_ready, "tilt": self.tilt_analysis_data_ready,
            "funnel": self.funnel_data_ready, "opening_table": self.opening_table_ready,
            "blunder_reel": self.blunder_reel_data_ready
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        result_map = dict(zip(tasks.keys(), results))

        for key, result in result_map.items():
            if not self._is_running: break
            if isinstance(result, Exception):
                self.error.emit(f"Query failed for {key}: {result}")
            elif key in signal_map:
                signal_map[key].emit(result)

    async def _async_fetch_dissonance(self, opening_id: int):
        """The async part of the on-demand fetch, executed in the worker's loop."""
        db_service = self.db_manager.get_service()
        try:
            logger.debug("Fetching dissonance data on worker thread.", opening_id=opening_id)
            data = await db_service.get_cognitive_dissonance_positions(opening_id, self.filters)
            self.dissonance_data_ready.emit(data)
        except Exception as e:
            logger.error("Failed to fetch dissonance data", exc_info=True)
            self.error.emit(f"Failed to fetch dissonance data: {e}")



class AppController(QObject):
    """Manages application logic and orchestrates background workers."""
    # Analysis signals
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)
    
    # Dashboard signals
    stats_finished = Signal()
    kpi_data_ready = Signal(dict)
    trend_data_ready = Signal(list)
    phase_data_ready = Signal(list)
    decision_matrix_data_ready = Signal(list)
    tactical_signature_data_ready = Signal(list)
    blunder_reel_data_ready = Signal(list)
    tilt_analysis_data_ready = Signal(list)
    funnel_data_ready = Signal(dict)
    opening_table_ready = Signal(list)
    dissonance_data_ready = Signal(list)

    def __init__(self, app_state: AppState, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self._app_state = app_state
        self._db_manager = db_manager
        self._persistence_client = PersistenceClient(self._db_manager.write_queue)
        
        self.analysis_thread: Optional[QThread] = None
        self.analysis_worker: Optional[AnalysisWorker] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._current_filters: Dict = {}

        # The stats worker is persistent and created once.
        self._stats_task_queue = asyncio.Queue()
        self.stats_thread = QThread()
        self.stats_worker = StatisticsWorker(self._db_manager, self._stats_task_queue)
        self.stats_worker.moveToThread(self.stats_thread)
        self._connect_stats_worker_signals()
        self.stats_thread.start()

    def _connect_stats_worker_signals(self):
        """Connects all signals from the persistent stats worker."""
        # --- CORRECTED: All signals are now connected ---
        self.stats_worker.kpi_data_ready.connect(self.kpi_data_ready)
        self.stats_worker.trend_data_ready.connect(self.trend_data_ready)
        self.stats_worker.phase_data_ready.connect(self.phase_data_ready)
        self.stats_worker.decision_matrix_data_ready.connect(self.decision_matrix_data_ready)
        self.stats_worker.tactical_signature_data_ready.connect(self.tactical_signature_data_ready)
        self.stats_worker.blunder_reel_data_ready.connect(self.blunder_reel_data_ready)
        self.stats_worker.tilt_analysis_data_ready.connect(self.tilt_analysis_data_ready)
        self.stats_worker.funnel_data_ready.connect(self.funnel_data_ready)
        self.stats_worker.opening_table_ready.connect(self.opening_table_ready)
        self.stats_worker.dissonance_data_ready.connect(self.dissonance_data_ready)
        
        self.stats_worker.error.connect(self.error)
        # This signal now correctly indicates that the initial batch of work is done.
        self.stats_worker.finished.connect(self.stats_finished)


    def start_analysis(self, config: Dict):
        if self.analysis_thread and self.analysis_thread.isRunning():
            return
            
        try:
            pgn_filepath = Path(config["pgn_files"][0])
            stockfish_path = find_stockfish_executable(None)
            
            output_dir = pgn_filepath.parent
            base_name = pgn_filepath.stem
            output_pgn_path = output_dir / f"{base_name}_analyzed.pgn"
            output_csv_path = output_dir / f"{base_name}_report.csv"
            
            engine_settings = EngineSettings(
                path=str(stockfish_path), depth=config["depth"],
                parameters={"Threads": 1, "Hash": 128, "MultiPV": config["multipv"]}
            )
            analysis_settings = settings.analysis_settings.model_copy(
                update={'depth': config["depth"], 'multipv': config["multipv"]}
            )
            engine_pool_settings = EnginePoolSettings(pool_size=1, engine_config=engine_settings)
            cache_settings = CacheSettings(db_filepath=settings.default_cache_db_path)
            
            run_config = RunConfig(
                input_pgn_path=str(pgn_filepath), output_pgn_path=str(output_pgn_path),
                output_csv_path=str(output_csv_path), db_path=settings.default_db_path,
                concurrency=1, max_retries=1, persistence_queue_size=1000,
                user_player_name=config.get("user_player_name"),
                analysis_settings=analysis_settings,
                engine_pool_settings=engine_pool_settings,
                cache_settings=cache_settings,
            )

            self._shutdown_event = asyncio.Event()
            self.analysis_thread = QThread()
            self.analysis_worker = AnalysisWorker(run_config, self._persistence_client, self._shutdown_event)
            
            self.analysis_worker.moveToThread(self.analysis_thread)
            self._connect_analysis_worker_signals()
            self.analysis_thread.start()
        except Exception as e:
            logger.error("Failed to start analysis", exc_info=True)
            self.error.emit(f"Failed to start analysis: {e}")
    
    def _connect_analysis_worker_signals(self):
        self.analysis_worker.finished.connect(self._on_analysis_worker_finished)
        self.analysis_worker.error.connect(self.error)
        self.analysis_worker.progress.connect(self.progress)
        self.analysis_thread.started.connect(self.analysis_worker.run_analysis)
        self.analysis_worker.finished.connect(self._cleanup_analysis_thread)
        self.analysis_worker.error.connect(self._cleanup_analysis_thread)
    
    def _on_analysis_worker_finished(self, report_dict: dict):
        """
        Slot to handle the report dictionary from the worker.
        It deserializes the entire nested dictionary structure back into the
        correct dataclass instances before updating the application state.
        """
        try:
            # Reconstruct the nested objects first
            reconstructed_results = []
            for res_dict in report_dict.get('results', []):
                summary_obj = None
                summary_dict = res_dict.get('summary')
                if summary_dict:
                    stats_dict = summary_dict.get('stats', {})
                    white_stats = PlayerStats(**stats_dict.get('white', {}))
                    black_stats = PlayerStats(**stats_dict.get('black', {}))
                    game_stats = GameStatistics(
                        white=white_stats,
                        black=black_stats,
                        opening_name=stats_dict.get('opening_name'),
                        eval_volatility=stats_dict.get('eval_volatility')
                    )
                    summary_obj = GameSummary(
                        game_id=summary_dict.get('game_id'),
                        metadata=GameMetadata(**summary_dict.get('metadata', {})),
                        stats=game_stats,
                        narrative=summary_dict.get('narrative')
                    )
                
                # The annotated_game is a complex PyObject that should pass through
                # the dict as-is without being serialized.
                reconstructed_results.append(ProcessedGameResult(
                    annotated_game=res_dict.get('annotated_game'),
                    summary=summary_obj
                ))

            # Now, reconstruct the top-level report
            final_report = RunReport(
                results=reconstructed_results,
                processed_game_count=report_dict.get('processed_game_count', 0),
                user_found_in_games=report_dict.get('user_found_in_games', False),
                warnings=report_dict.get('warnings', [])
            )
            
            # Update the AppState with the fully reconstructed objects
            self._app_state.set_results(final_report.results)
            # Pass the full report object up to the MainWindow
            self.finished.emit(final_report)
            
        except (TypeError, KeyError) as e:
            logger.error("Failed to reconstruct RunReport from dict", error=str(e), data=report_dict)
            self.error.emit("A data processing error occurred.")


    def _cleanup_analysis_thread(self):
        if self.analysis_thread is None: return
        logger.debug("Cleaning up analysis thread.")
        self.analysis_thread.quit()
        self.analysis_thread.wait(2000)
        self.analysis_worker.deleteLater()
        self.analysis_thread.deleteLater()
        self.analysis_thread = None
        self.analysis_worker = None

    def cancel_analysis(self):
        if self._shutdown_event:
            self._shutdown_event.set()

    def request_statistics_update(self, filters: Dict):
        """Puts an 'initial fetch' task onto the persistent worker's queue."""
        self._current_filters = filters
        self._stats_task_queue.put_nowait(('fetch_initial', filters))

    def request_dissonance_data(self, opening_id: int):
        """Puts a 'dissonance fetch' task onto the persistent worker's queue."""
        # The worker now holds the correct filters from the last initial fetch.
        self._stats_task_queue.put_nowait(('fetch_dissonance', opening_id))
    
    def shutdown_workers(self):
        """Gracefully stops all persistent background workers."""
        logger.info("Controller shutting down workers.")
        if self.stats_worker:
            self.stats_worker.stop()
        if self.stats_thread and self.stats_thread.isRunning():
            self.stats_thread.quit()
            self.stats_thread.wait(2000)