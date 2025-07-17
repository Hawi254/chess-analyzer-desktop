# chess_analyzer/tracing.py

"""
tracing
~~~~~~~

This module provides components for application-wide traceability and
context-aware logging.
"""

import functools
from dataclasses import asdict, dataclass
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)

@dataclass(frozen=True, slots=True)
class CorrelationID:
    """A unique identifier for a single unit of work."""
    run_id: str
    game_id: str
    task_id: str

    @property
    def short_id(self) -> str:
        """A short, human-readable version of the full ID."""
        return f"{self.game_id}:{self.task_id}"

    def as_dict(self) -> dict:
        """Returns the ID as a dictionary suitable for logging."""
        return asdict(self)


def trace_stage(func: Callable) -> Callable:
    """A decorator to add structured tracing to a processing stage."""
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        stage_name = args[0].__class__.__name__
        logger.info("Entering processing stage.", stage=stage_name)
        result = await func(*args, **kwargs)
        logger.info("Exiting processing stage.", stage=stage_name)
        return result
    return wrapper