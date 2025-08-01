# chess_analysis_project/services/database_manager.py
"""
Provides a centralized, application-wide service for managing database interactions.
"""
import asyncio
from collections import defaultdict
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal  # <--- CORRECTED: Added Slot import
import structlog

from chess_analyzer.persistence.training_data_service import TrainingDataService
from chess_analyzer.types import (
    QueuePayload, QueuedGameComplete
)

logger = structlog.get_logger(__name__)

class DatabaseWorker(QObject):
    """A worker that runs on a dedicated thread to process database write requests."""

    # --- NEW: Signals for initialization status ---
    db_ready = Signal()
    db_error = Signal(str)

    def __init__(self, db_service: TrainingDataService, queue: asyncio.Queue, parent=None):
        super().__init__(parent)
        self._db_service = db_service
        self._queue = queue
        self._is_running = True

    def stop(self):
        """Signals the worker to stop processing."""
        self._is_running = False

    def run(self):
        """
        The main worker loop. It creates its own event loop to consume from the
        asyncio queue and interact with the async data service.
        """
        logger.info("DatabaseWorker thread started, creating new event loop.")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # --- DEFINITIVE FIX: Initialize DB once at the start ---
            try:
                loop.run_until_complete(self._db_service.initialize_db())
                self.db_ready.emit()
            except Exception as e:
                logger.error("Database initialization failed in worker.", exc_info=True)
                self.db_error.emit(f"DB Init Failed: {e}")
                return # Do not proceed if init fails
            
            # Now, start the main processing loop
            loop.run_until_complete(self._process_queue())
        finally:
            logger.info("DatabaseWorker event loop finished.")
            loop.close()
    
    async def _process_queue(self):
        """Consumes items from the queue and persists them to the database."""
        game_buffers: Dict[str, List[QueuePayload]] = defaultdict(list)
        try:
            while self._is_running:
                item = None # Initialize item to None
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                    
                    # --- NEW: Graceful shutdown logic ---
                    # If we receive a None sentinel, break the loop immediately.
                    if item is None and not self._is_running:
                        logger.info("DatabaseWorker received shutdown sentinel, exiting loop.")
                        break
                    
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
        finally:
            # --- CRITICAL FIX: Flush any remaining buffers on shutdown to prevent data loss ---
            if game_buffers:
                logger.warning("Flushing remaining game buffers on shutdown.", buffer_count=len(game_buffers))
                flush_tasks = [
                    self._db_service.persist_complete_game_buffer(buffer)
                    for game_id, buffer in game_buffers.items()
                ]
                await asyncio.gather(*flush_tasks, return_exceptions=True)
                logger.info("All remaining game buffers flushed successfully.")

class DatabaseManager(QObject):
    """
    Manages a persistent background thread for all database write operations
    and provides an interface for read operations.
    """
    db_ready = Signal()
    db_error = Signal(str)

    def __init__(self, db_path: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._db_service = TrainingDataService(db_path)
        self.write_queue = asyncio.Queue()

        self._worker_thread = QThread()
        self._worker = DatabaseWorker(self._db_service, self.write_queue)
        self._worker.moveToThread(self._worker_thread)

        # --- Simplified Connections ---
        self._worker_thread.started.connect(self._worker.run)
        self._worker.db_ready.connect(self.db_ready)
        self._worker.db_error.connect(self.db_error)
        
        self._worker_thread.start()
    
    def get_service(self) -> TrainingDataService:
        """Provides access to the underlying service for read operations."""
        return self._db_service
    
    def shutdown(self):
        """Gracefully shuts down the database worker thread."""
        logger.info("DatabaseManager shutdown requested.")
        if self._worker and self._worker_thread.isRunning():
            self._worker.stop()
            # --- NEW: Add a sentinel value to the queue ---
            # This unblocks the `queue.get()` call and signals a clean exit.
            self.write_queue.put_nowait(None)
            self._worker_thread.quit()
            self._worker_thread.wait(3000) # Wait for the thread to finish gracefully