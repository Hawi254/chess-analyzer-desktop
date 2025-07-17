# chess_analyzer/utils/signal_manager.py
"""
Provides an asynchronous context manager for graceful shutdown signal handling.

This module helps decouple the main application logic from low-level OS signal
handling. By using the `AsyncSignalManager` in an `async with` block, the
application can listen for SIGINT (Ctrl+C) and SIGTERM signals and respond by
setting a shared `asyncio.Event`, allowing various long-running tasks to shut
down gracefully.
"""

import asyncio
import signal
from typing import Set

import structlog

logger = structlog.get_logger(__name__)


class AsyncSignalManager:
    """
    An async context manager that listens for shutdown signals and sets an event.

    This class provides a clean, event-based mechanism for initiating a
    graceful shutdown across multiple asynchronous tasks.

    Usage:
        shutdown_event = asyncio.Event()
        async with AsyncSignalManager(shutdown_event):
            # Main application logic runs here
            await some_long_running_task(shutdown_event)
    """

    def __init__(self, shutdown_event: asyncio.Event):
        """
        Initializes the signal manager.

        Args:
            shutdown_event: The `asyncio.Event` that will be set when a
                            shutdown signal (SIGINT or SIGTERM) is caught.
        """
        self._shutdown_event = shutdown_event
        self._signals_to_catch: Set[signal.Signals] = {signal.SIGINT, signal.SIGTERM}

    def _signal_handler(self, sig: signal.Signals) -> None:
        """
        The internal callback executed by the event loop when a signal is received.
        
        This method is idempotent; it sets the shutdown event only once.
        
        Args:
            sig: The signal that was caught.
        """
        if not self._shutdown_event.is_set():
            logger.warning("Shutdown signal received. Initiating graceful shutdown.", signal_name=sig.name)
            self._shutdown_event.set()
        else:
            logger.info("Multiple shutdown signals received, already shutting down.", signal_name=sig.name)

    async def __aenter__(self) -> "AsyncSignalManager":
        """Registers the signal handlers with the running asyncio event loop."""
        loop = asyncio.get_running_loop()
        for sig in self._signals_to_catch:
            try:
                loop.add_signal_handler(sig, self._signal_handler, sig)
                logger.debug("Registered signal handler.", signal_name=sig.name)
            except (ValueError, AttributeError, RuntimeError) as e:
                # Some environments (like non-Unix systems) may not support all signals.
                logger.warning("Could not register signal handler.", signal_name=sig.name, error=str(e))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Removes the signal handlers to clean up resources upon exiting the context."""
        loop = asyncio.get_running_loop()
        for sig in self._signals_to_catch:
            try:
                loop.remove_signal_handler(sig)
                logger.debug("Removed signal handler.", signal_name=sig.name)
            except (ValueError, AttributeError, RuntimeError):
                # Fail silently if the handler could not be removed.
                pass