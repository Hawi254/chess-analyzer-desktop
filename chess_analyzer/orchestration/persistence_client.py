# chess_analyzer/orchestration/persistence_client.py
"""
Provides a client-side adapter for queueing persistence tasks.

This module defines the data contracts for items to be placed on the persistence
queue and a simple `PersistenceClient` class. The client acts as a clean
interface between the main processing pipeline and the background persistence
system. Its primary responsibility is to place pre-formatted data payloads onto
the `asyncio.Queue` that the background database writer consumes.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional, TypeAlias, Union

import structlog

from chess_analyzer.types import (QueuedAnnotatedGame, QueuedGameComplete,
                                  QueuedGameStat, QueuedMove,
                                  QueuedPosition, QueuedStatUpdate)

logger = structlog.get_logger(__name__)

# A type alias for all valid queue payloads, now imported from types.py
# for a single source of truth. This is a conceptual representation.
QueuePayload: TypeAlias = Union[
    QueuedPosition, QueuedStatUpdate, QueuedMove, QueuedGameStat, QueuedGameComplete, QueuedAnnotatedGame
]

class PersistenceClient:
    """
    An asynchronous adapter that puts data payloads onto an asyncio.Queue.
    
    This client provides a level of indirection, allowing the pipeline stages
    to queue persistence work without needing direct knowledge of the queue itself.
    """

    def __init__(self, queue: asyncio.Queue[QueuePayload]):
        """
        Initializes the PersistenceClient.

        Args:
            queue: The `asyncio.Queue` to which persistence payloads will be sent.
        """
        self._queue = queue

    async def queue_item(self, item: QueuePayload) -> None:
        """
        Asynchronously places a data payload onto the persistence queue.
        
        This method uses `await queue.put()`, which provides natural backpressure.
        If the queue is full, this method will pause until space is available,
        preventing the producer tasks from overwhelming the consumer.
        
        Args:
            item: A valid queue payload object.
        """
        try:
            logger.debug(
                "PersistenceClient: Queuing item.",
                item_type=type(item).__name__,
                game_id=getattr(item, 'game_id', 'N/A')
            )
            await self._queue.put(item)
        except asyncio.CancelledError:
            # Ensure task cancellations are propagated correctly.
            raise
        except Exception:
            # This block should ideally not be hit with queue.put, but is a safeguard.
            logger.error(
                "Unexpected error while queuing persistence item.",
                exc_info=True
            )