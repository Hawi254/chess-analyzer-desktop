# chess_analysis_project/app_controller.py
"""
Contains the main application logic controller and the background workers.
"""

import asyncio
import io
import punq
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal, QThread, Slot
import chess.pgn

import structlog

from chess_analyzer.config.settings import RunConfig
from chess_analyzer.containers import get_container
from chess_analyzer.orchestration.orchestrator import AnalysisOrchestrator
from chess_analyzer.orchestration.persistence_client import PersistenceClient
from chess_analyzer.orchestration.run_config_factory import RunConfigFactory
from chess_analyzer.persistence.queries import (AccuracyTrendQuery,
    BaseDashboardQuery, BlunderReelQuery, CognitiveDissonanceQuery, KpiQuery,
    OpeningPerformanceQuery
)
from chess_analyzer.types import (
    GameReportRow, RunReport
)
from chess_analyzer.services.database_manager import DatabaseManager
from state.app_state import AppState

logger = structlog.get_logger(__name__)


class AnalysisWorker(QObject):
    """Worker to perform the main game analysis."""
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, run_config: RunConfig, container: punq.Container, shutdown_event: asyncio.Event, parent=None):
        super().__init__(parent)
        self._run_config = run_config
        self._shutdown_event = shutdown_event
        self._container = container

    def run_analysis(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def progress_callback(processed_count: int, total_games: int):
                self.progress.emit(processed_count, total_games)

            orchestrator = AnalysisOrchestrator(
                self._run_config, self._container,
                progress_callback=progress_callback,
                shutdown_event=self._shutdown_event
            )
            report = loop.run_until_complete(orchestrator.run())
            if not self._shutdown_event.is_set():
                self.finished.emit(report)
        except Exception as e:
            logger.error("Analysis worker failed", exc_info=True)
            self.error.emit(f"Failed to run analysis: {e}")
        finally:
            loop.close()


class StatisticsWorker(QObject):
    """Worker to fetch all dashboard data from the database asynchronously."""
    # --- MODIFIED: Added signals for paginated game report data ---
    initial_report_ready = Signal(dict, int, list)  # Emits (filters, total_count, List[GameReportRow])
    report_page_ready = Signal(list)          # Emits (List[GameReportRow])
    
    # --- NEW: Signal to carry the PGN text of a single requested game ---
    annotated_game_data_ready = Signal(str)
    
    kpi_data_ready = Signal(dict)
    trend_data_ready = Signal(list)
    opening_table_ready = Signal(list)
    dissonance_data_ready = Signal(list)
    blunder_reel_data_ready = Signal(list)
    finished = Signal()
    error = Signal(str)

    def __init__(self, db_manager: DatabaseManager, task_queue: asyncio.Queue, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.task_queue = task_queue
        self._task_lock = asyncio.Lock()
        self._is_running = True
        # --- NEW: A dispatch table for tasks ---
        self.task_handlers = {
            'fetch_initial_report': self.fetch_initial_report_data,
            'fetch_report_page': self.fetch_report_page_data,
            'fetch_annotated_game': self.fetch_annotated_game_data,
            'fetch_initial': self.fetch_initial_data,
            'fetch_dissonance': self._async_fetch_dissonance_wrapper
        }

    def stop(self):
        self._is_running = False

    def run(self):
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
        while self._is_running:
            try:
                # Wait for a task. This can be a (name, payload) tuple or a None sentinel.
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                
                # --- NEW: Graceful shutdown logic ---
                if task is None and not self._is_running:
                    logger.info("StatisticsWorker received shutdown sentinel, exiting loop.")
                    break
                
                task_name, payload = task
                logger.debug("StatisticsWorker processing task from queue.", task_name=task_name)
                if handler := self.task_handlers.get(task_name):
                    async with self._task_lock:
                        await handler(payload)
                    self.task_queue.task_done()
                else:
                    logger.warning("Unknown task received in StatisticsWorker", task_name=task_name)

            except asyncio.TimeoutError:
                continue
            except Exception:
                logger.error("Error processing statistics task", exc_info=True)

    async def _async_fetch_dissonance_wrapper(self, payload: tuple):
        await self._async_fetch_dissonance(*payload)

    # --- NEW: Method to fetch initial game report data (count + first page) ---
    async def fetch_initial_report_data(self, payload: tuple):
        filters, limit = payload
        db_service = self.db_manager.get_service()
        try:
            logger.debug("Fetching initial game report data on worker thread.")
            count_task = db_service.get_game_report_count(filters)
            report_task = db_service.get_paginated_game_report(filters, offset=0, limit=limit)
            
            total_count, first_page_data = await asyncio.gather(count_task, report_task, return_exceptions=True)
            
            if isinstance(total_count, Exception):
                raise total_count
            if isinstance(first_page_data, Exception):
                raise first_page_data

            self.initial_report_ready.emit(filters, total_count, first_page_data)
        except Exception as e:
            logger.error("Failed to fetch initial report data", exc_info=True)
            self.error.emit(f"Failed to fetch initial report data: {e}")

    # --- NEW: Method to fetch a subsequent page of game report data ---
    async def fetch_report_page_data(self, payload: tuple):
        filters, offset, limit = payload
        db_service = self.db_manager.get_service()
        try:
            logger.debug("Fetching game report page on worker thread.", offset=offset, limit=limit)
            page_data = await db_service.get_paginated_game_report(filters, offset, limit)
            self.report_page_ready.emit(page_data)
        except Exception as e:
            logger.error("Failed to fetch report page data", exc_info=True)
            self.error.emit(f"Failed to fetch report page data: {e}")

    # --- NEW: Method to fetch a single annotated game ---
    async def fetch_annotated_game_data(self, game_id: str):
        """Fetches the full PGN text for a single game by its ID."""
        db_service = self.db_manager.get_service()
        try:
            logger.debug("Fetching annotated game data on worker thread.", game_id=game_id)
            pgn_text = await db_service.get_annotated_pgn(game_id)
            if pgn_text:
                self.annotated_game_data_ready.emit(pgn_text)
            else:
                logger.warning("Annotated game not found in database.", game_id=game_id)
        except Exception as e:
            logger.error("Failed to fetch annotated game data", exc_info=True)
            self.error.emit(f"Failed to fetch annotated game data for {game_id}: {e}")

    async def fetch_initial_data(self, filters: Dict):
        db_service = self.db_manager.get_service()
        # Create strongly-typed query objects from the generic filter dict. This is
        # now done explicitly to handle different query parameters for each task.

        # KpiQuery ignores the 'color' filter by design, and doesn't need calendar filters.
        kpi_query = KpiQuery(
            player_name=filters["player_name"],
            time_control=filters.get("time_control")
        )
        # The trend query needs all filters, including the new calendar-specific ones.
        # --- FIX: Construct query objects safely to avoid TypeErrors ---
        trend_filters = {k: v for k, v in filters.items() if k in AccuracyTrendQuery.__annotations__ or k in BaseDashboardQuery.__annotations__}
        trend_query = AccuracyTrendQuery(**trend_filters)
        # The opening query uses the base filters.
        opening_query = OpeningPerformanceQuery(
            player_name=filters["player_name"],
            time_control=filters.get("time_control"),
            color=filters.get("color")
        )
        blunder_filters = {k: v for k, v in filters.items() if k in BlunderReelQuery.__annotations__ or k in BaseDashboardQuery.__annotations__}
        blunder_query = BlunderReelQuery(**blunder_filters)

        tasks = {
            "kpi": db_service.get_kpis(kpi_query),
            "trend": db_service.get_accuracy_trend(trend_query),
            "opening_table": db_service.get_opening_performance_table(opening_query),
            "blunder_reel": db_service.get_blunder_reel_data(blunder_query),
        }
        signal_map = {
            "kpi": self.kpi_data_ready, "trend": self.trend_data_ready,
            "opening_table": self.opening_table_ready,
            "blunder_reel": self.blunder_reel_data_ready
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        result_map = dict(zip(tasks.keys(), results))

        for key, result in result_map.items():
            if not self._is_running:
                break
            if isinstance(result, Exception):
                self.error.emit(f"Query failed for {key}: {result}")
            elif key in signal_map:
                logger.debug(f"StatisticsWorker emitting signal for {key}.")
                signal_map[key].emit(result)

    async def _async_fetch_dissonance(self, opening_id: int, filters: Dict):
        db_service = self.db_manager.get_service()
        try:
            query_obj = CognitiveDissonanceQuery(opening_id=opening_id, **filters)
            logger.debug("Fetching dissonance data on worker thread.", opening_id=opening_id)
            data = await db_service.get_cognitive_dissonance_positions(query_obj)
            self.dissonance_data_ready.emit(data)
        except Exception as e:
            logger.error("Failed to fetch dissonance data", exc_info=True)
            self.error.emit(f"Failed to fetch dissonance data: {e}")


class AppController(QObject):
    """Manages application logic and orchestrates background workers."""
    # --- MODIFIED: Added signals to relay report data to the view/model ---
    initial_report_ready = Signal(dict, int, list)  # Emits (filters, total_count, List[GameReportRow])
    report_page_ready = Signal(list)          # Emits (List[GameReportRow])
    game_data_loaded = Signal(object) # NEW: Carries a single parsed chess.pgn.Game

    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)

    stats_finished = Signal()
    kpi_data_ready = Signal(dict)
    trend_data_ready = Signal(list)
    opening_table_ready = Signal(list)
    dissonance_data_ready = Signal(list)
    blunder_reel_data_ready = Signal(list)

    def __init__(self, app_state: AppState, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self._app_state = app_state
        self._db_manager = db_manager
        self._persistence_client = PersistenceClient(self._db_manager.write_queue)
        self.analysis_thread: Optional[QThread] = None
        self.analysis_worker: Optional[AnalysisWorker] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._stats_task_queue = asyncio.Queue()
        self.stats_thread = QThread()
        self.stats_worker = StatisticsWorker(self._db_manager, self._stats_task_queue)
        self.stats_worker.moveToThread(self.stats_thread)
        self.stats_thread.started.connect(self.stats_worker.run)
        self._connect_stats_worker_signals()
        self.stats_thread.start()
    
    def _connect_stats_worker_signals(self):
        """Connects all signals from the persistent stats worker to this controller."""
        # --- MODIFIED: Connect the new report signals ---
        # --- MODIFIED: Intercept raw data with private slots for transformation ---
        self.stats_worker.initial_report_ready.connect(self._on_initial_report_data_received)
        self.stats_worker.report_page_ready.connect(self._on_report_page_data_received)
        # --- NEW: Connect the signal for a single loaded game ---
        self.stats_worker.annotated_game_data_ready.connect(self._on_annotated_game_data_received)

        
        self.stats_worker.kpi_data_ready.connect(self.kpi_data_ready)
        self.stats_worker.trend_data_ready.connect(self.trend_data_ready)
        self.stats_worker.opening_table_ready.connect(self.opening_table_ready)
        self.stats_worker.dissonance_data_ready.connect(self.dissonance_data_ready)
        self.stats_worker.blunder_reel_data_ready.connect(self.blunder_reel_data_ready)
        self.stats_worker.error.connect(self.error)
        self.stats_worker.finished.connect(self.stats_finished)
    
    def start_analysis(self, config: Dict):
        if self.analysis_thread and self.analysis_thread.isRunning():
            logger.warning("Analysis is already running. Ignoring request.")
            return
        try:
            # DECOUPLED: Delegate RunConfig creation to the factory.
            run_config = RunConfigFactory.create_from_ui(config)
            # DECOUPLED: Create the DI container for this specific run.
            container = get_container(run_config, self._persistence_client)
            self._shutdown_event = asyncio.Event()
            self.analysis_thread = QThread()
            self.analysis_worker = AnalysisWorker(run_config, container, self._shutdown_event)
            
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

    def _on_analysis_worker_finished(self, report: RunReport):
        """
        Slot to handle the RunReport object directly from the worker.
        This method updates the application state and then signals the UI.
        """
        logger.debug("Entering processing...")
        try:
            # The lazy-loading model means we no longer push the full result
            # set into the app_state. The controller now manages this data flow.
            # self._app_state.set_results(report.results) 
            self.finished.emit(report)
        except Exception:
            logger.error("Error processing completed RunReport", exc_info=True)
            self.error.emit("A data processing error occurred.")

    @Slot(dict, int, list)
    def _on_initial_report_data_received(self, filters: dict, total_count: int, data: List[GameReportRow]):
        """Relays initial report data directly from the worker."""
        # The data is now a list of DTOs; transformation happens in the model.
        self.initial_report_ready.emit(filters, total_count, data)

    @Slot(list)
    def _on_report_page_data_received(self, data: List[GameReportRow]):
        """Relays a page of report data directly from the worker."""
        # The data is now a list of DTOs; transformation happens in the model.
        self.report_page_ready.emit(data)

    @Slot(str)
    def _on_annotated_game_data_received(self, pgn_text: str):
        """Parses the received PGN text and emits the loaded game object."""
        try:
            # Use io.StringIO to treat the string as a file for the PGN parser.
            pgn_io = io.StringIO(pgn_text)
            game = chess.pgn.read_game(pgn_io)
            if game:
                self.game_data_loaded.emit(game)
            else:
                logger.error("Failed to parse PGN text into a game object.")
                self.error.emit("Could not load the selected game.")
        except Exception as e:
            logger.error("Error parsing PGN text", exc_info=True)
            self.error.emit(f"Error loading game: {e}")

    def _cleanup_analysis_thread(self):
        logger.debug("Entering cleanup...")
        if not self.analysis_thread:
            return
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
        logger.debug("Queueing 'fetch_initial' task for dashboard.", filters=filters)
        self._stats_task_queue.put_nowait(('fetch_initial', filters))

    def request_dissonance_data(self, opening_id: int, filters: dict):
        """Requests cognitive dissonance data, now requiring filters to be passed in."""
        logger.debug("Queueing 'fetch_dissonance' task.", opening_id=opening_id, filters=filters)
        self._stats_task_queue.put_nowait(('fetch_dissonance', (opening_id, filters)))
    
    # --- NEW: Public slot to request the initial game report ---
    @Slot(dict, int)
    def request_initial_game_report(self, filters: Dict, page_size: int):
        """
        Requests the total count and the first page of the game report.
        This will be called by the UI.
        """
        logger.debug("Queueing 'fetch_initial_report' task.", filters=filters, page_size=page_size)
        payload = (filters, page_size)
        self._stats_task_queue.put_nowait(('fetch_initial_report', payload))

    # --- NEW: Public slot to request more data for the game report ---
    @Slot(dict, int, int)
    def request_more_report_data(self, filters: dict, offset: int, limit: int):
        """
        Requests a subsequent page for the game report. This is connected
        to the GameReportModel's 'more_data_requested' signal.
        """
        logger.debug("Queueing 'fetch_report_page' task.", filters=filters, offset=offset, limit=limit)
        payload = (filters, offset, limit)
        self._stats_task_queue.put_nowait(('fetch_report_page', payload))

    # --- NEW: Public slot to request a single annotated game by its ID ---
    @Slot(str)
    def request_annotated_game(self, game_id: str):
        """Requests the full annotated PGN for a single game."""
        logger.debug("Queueing 'fetch_annotated_game' task.", game_id=game_id)
        self._stats_task_queue.put_nowait(('fetch_annotated_game', game_id))
        
    def shutdown_workers(self):
        logger.info("Controller shutting down workers.")
        self.cancel_analysis()
        if self.analysis_thread and self.analysis_thread.isRunning():
            self._cleanup_analysis_thread()
        if self.stats_worker:
            self.stats_worker.stop()
            # --- NEW: Add a sentinel value to the queue ---
            # This unblocks the `task_queue.get()` call and signals a clean exit.
            self._stats_task_queue.put_nowait(None)
        if self.stats_thread and self.stats_thread.isRunning():
            self.stats_thread.quit()
            self.stats_thread.wait(2000)