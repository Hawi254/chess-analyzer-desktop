# chess_analyzer/services/engine_pool.py
"""
Provides a robust, asynchronous resource pool for managing chess engine instances.

This module contains the `EnginePool`, an async context manager responsible for
the entire lifecycle of multiple `EngineService` instances. It handles concurrent
access via an `asyncio.Queue`, creates new engine processes on startup, closes them
on shutdown, and provides a mechanism to retire and replace failed engine instances
during a run, ensuring the application is resilient to engine crashes.
"""

import asyncio
from typing import Awaitable, Callable, List, Optional, TYPE_CHECKING

import structlog

from chess_analyzer.exceptions import EngineInitializationError
from chess_analyzer.types import EngineService

if TYPE_CHECKING:
    from chess_analyzer.config.settings import EnginePoolSettings

# A factory function type hint for creating engine instances.
EngineFactory = Callable[..., Awaitable[EngineService]]
logger = structlog.get_logger(__name__)


class EnginePool:
    """
    An async context manager for a pool of chess engine services.

    This class provides a classic resource pool pattern for managing engine
    processes, which are expensive to create. It allows multiple concurrent
    tasks to "check out" (acquire) and "check in" (release) engine instances.
    """

    def __init__(self, settings: "EnginePoolSettings", engine_factory: EngineFactory):
        """
        Initializes the EnginePool.

        Args:
            settings: Configuration for the pool, including size and engine settings.
            engine_factory: An async callable (e.g., `StockfishService.create`)
                            that will be used to create new engine instances.
        """
        self._settings = settings
        self._engine_factory = engine_factory
        self._pool: asyncio.Queue[EngineService] = asyncio.Queue(maxsize=settings.pool_size)
        self._instances: List[EngineService] = []
        self._lock = asyncio.Lock()
        self._is_closed = True

    async def _create_new_instance(self) -> Optional[EngineService]:
        """
        Internal factory method to create and initialize a single new engine instance.

        Returns:
            A healthy `EngineService` instance, or `None` if creation fails.
        """
        try:
            engine = await self._engine_factory(self._settings.engine_config)
            identifier = await engine.get_engine_identifier()
            logger.info("New engine instance created.", identifier=identifier)
            return engine
        except Exception:
            logger.error("Failed to create new engine instance.", exc_info=True)
            return None

    async def __aenter__(self) -> "EnginePool":
        """
        Initializes the pool by creating all engine instances concurrently.

        This is called at the start of an `async with` block.

        Returns:
            The initialized EnginePool instance.
        
        Raises:
            RuntimeError: If no engine instances could be successfully created.
        """
        self._is_closed = False
        logger.info("Initializing engine pool.", size=self._settings.pool_size)

        # Concurrently create all engine instances.
        tasks = [self._create_new_instance() for _ in range(self._settings.pool_size)]
        results = await asyncio.gather(*tasks)

        async with self._lock:
            for engine in results:
                if engine:
                    self._instances.append(engine)
                    self._pool.put_nowait(engine)
        
        if not self._instances:
            raise RuntimeError("Could not initialize any engine instances for the pool. Aborting.")
            
        logger.info("Engine pool initialized.", active_instances=len(self._instances))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Closes the pool and terminates all managed engine instances.
        
        This is called at the end of an `async with` block.
        """
        if self._is_closed:
            return
        
        self._is_closed = True
        logger.info("Closing engine pool and terminating all instances.")
        
        async with self._lock:
            # Concurrently close all running engine instances.
            tasks = [instance.close() for instance in self._instances]
            await asyncio.gather(*tasks, return_exceptions=True)
            self._instances.clear()
            
        # Clear the queue of any remaining engine objects.
        while not self._pool.empty():
            self._pool.get_nowait()
            
        logger.info("Engine pool closed.")

    async def acquire(self) -> EngineService:
        """
        Acquires an engine from the pool, waiting if none are available.

        Raises:
            RuntimeError: If the pool is already closed.
        
        Returns:
            An available `EngineService` instance.
        """
        if self._is_closed:
            raise RuntimeError("Cannot acquire engine from a closed pool.")
        return await self._pool.get()

    def release(self, engine: EngineService) -> None:
        """
        Releases an engine back to the pool, making it available for other tasks.

        Args:
            engine: The `EngineService` instance to release.
        """
        if self._is_closed:
            return # Don't re-add an engine to a closed pool.
        self._pool.put_nowait(engine)

    async def retire_and_replace(self, failed_engine: EngineService) -> None:
        """
        Retires a failed engine instance, closes it, and attempts to replace it.

        This method is designed to be called when an analysis task detects that
        an engine has crashed or become unresponsive. It is safe to call
        concurrently from multiple tasks.

        Args:
            failed_engine: The engine instance that has failed.
        """
        logger.warning("Retiring failed engine instance.")
        
        try:
            await failed_engine.close()
        except Exception:
            logger.error("Error during shutdown of failed engine.", exc_info=True)

        async with self._lock:
            # Use a try/except block in case multiple tasks try to retire the same engine.
            try:
                self._instances.remove(failed_engine)
            except ValueError:
                return # Engine was already removed by another task.

            logger.info("Attempting to replace retired engine.")
            new_engine = await self._create_new_instance()
            if new_engine:
                self._instances.append(new_engine)
                self.release(new_engine) # Add the new healthy engine to the pool.
            else:
                logger.error("Failed to replace engine. Pool size has been reduced.")