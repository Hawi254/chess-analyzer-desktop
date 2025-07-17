# chess_analysis_project/services/database_manager.py
"""
Provides a centralized, application-wide service for managing database interactions.
"""
import asyncio
from collections import defaultdict
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot  # <--- CORRECTED: Added Slot import
import structlog

from chess_analyzer.persistence.training_data_service import TrainingDataService
from chess_analyzer.types import (
    QueuePayload, QueuedGameComplete, QueuedPosition, QueuedStatUpdate,
    QueuedMove, QueuedGameStat, QueuedOpeningLink
)

logger = structlog.get_logger(__name__)

class DatabaseWorker(QObject):
    """A worker that runs on a dedicated thread to process database write requests."""

    def __init__(self, db_service: TrainingDataService, queue: asyncio.Queue, parent=None):
        super().__init__(parent)
        self._db_service = db_service
        self._queue = queue
        self._is_running = True

    def stop(self):
        """Signals the worker to stop processing."""
        self._is_running = False

    @Slot()
    def initialize_db(self):
        """Runs the async db initialization in the worker's event loop."""
        logger.info("Database initialization requested on worker thread.")
        if not self._is_running: return
        
        # This check is crucial to avoid an error if the loop is not yet running
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._db_service.initialize_db())
        except RuntimeError:
            logger.error("Could not get running event loop in DatabaseWorker. Initialization might be delayed.")

    def run(self):
        """
        The main worker loop. It creates its own event loop to consume from the
        asyncio queue and interact with the async data service.
        """
        logger.info("DatabaseWorker thread started, creating new event loop.")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._process_queue())
        finally:
            logger.info("DatabaseWorker event loop finished.")
            loop.close()

    async def _process_queue(self):
        """Consumes items from the queue and persists them to the database."""
        game_buffers: Dict[str, List[QueuePayload]] = defaultdict(list)
        while self._is_running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                
                game_id = None
                if isinstance(item, QueuedGameComplete):
                    game_id = item.game_id
                elif hasattr(item, 'game_id'):
                    game_id = item.game_id
                elif hasattr(item, 'position_payload'):
                    game_id = item.position_payload.get('game_id')
                elif hasattr(item, 'stats_payload'):
                    game_id = item.stats_payload.get('game_id')
                elif hasattr(item, 'move_payload'):
                    game_id = item.move_payload.get('game_id')
                elif hasattr(item, 'game_stat_payload'):
                    game_id = item.game_stat_payload.get('game_id')

                if game_id:
                    if isinstance(item, QueuedGameComplete):
                        buffer_to_process = game_buffers.pop(game_id, [])
                        if buffer_to_process:
                            logger.debug("Persisting game buffer.", game_id=game_id, item_count=len(buffer_to_process))
                            await self._db_service.persist_complete_game_buffer(buffer_to_process)
                    else:

                        game_buffers[game_id].append(item)
                
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error in DatabaseWorker queue processing.", error=str(e), exc_info=True)


class DatabaseManager(QObject):
    """
    Manages a persistent background thread for all database write operations
    and provides an interface for read operations.
    """
    initialization_requested = Signal()

    def __init__(self, db_path: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._db_service = TrainingDataService(db_path)
        self.write_queue = asyncio.Queue()

        self._worker_thread = QThread()
        self._worker = DatabaseWorker(self._db_service, self.write_queue)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self.initialization_requested.connect(self._worker.initialize_db)
        
        self._worker_thread.start()

    def initialize_db(self):
        """
        Requests that the database schema be initialized on the worker thread.
        This method is non-blocking.
        """
        self.initialization_requested.emit()

    def get_service(self) -> TrainingDataService:
        """Provides access to the underlying service for read operations."""
        return self._db_service
    
    def shutdown(self):
        """Gracefully shuts down the database worker thread."""
        logger.info("DatabaseManager shutdown requested.")
        if self._worker_thread.isRunning():
            self._worker.stop()
            self._worker_thread.quit()
            self._worker_thread.wait(5000)