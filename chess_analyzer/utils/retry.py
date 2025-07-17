# chess_analyzer/utils/retry.py
"""
Provides a generic, asynchronous retry decorator for handling transient errors.

This utility helps make the application more resilient to temporary issues,
such as network glitches or database lock contention, by automatically retrying
a failed operation with an exponential backoff delay.
"""
import asyncio
import functools
import random
from typing import Any, Callable, Coroutine, Tuple, Type

import structlog

from chess_analyzer.utils import metrics # Assumes metrics.py exists and is correct

logger = structlog.get_logger(__name__)

# A tuple of default exception types that are considered "transient" and worth retrying.
DEFAULT_TRANSIENT_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)


def retry_with_backoff(
    attempts: int = 3,
    initial_backoff_s: float = 0.5,
    max_backoff_s: float = 5.0,
    jitter_factor: float = 0.2,
    exceptions_to_catch: Tuple[Type[Exception], ...] = DEFAULT_TRANSIENT_EXCEPTIONS,
    db_type: str = "unknown",
) -> Callable[[Callable[..., Coroutine]], Callable[..., Coroutine]]:
    """
    An async decorator to retry a function with exponential backoff and jitter.

    This decorator will re-execute the decorated asynchronous function if it
    raises one of the specified exceptions. The delay between retries increases
    exponentially and includes a random "jitter" to prevent a "thundering herd"
    of retries from multiple processes all at once.

    Args:
        attempts: The maximum number of times to try the function (including the first attempt).
        initial_backoff_s: The initial delay in seconds for the first retry.
        max_backoff_s: The maximum possible delay in seconds, to cap the backoff time.
        jitter_factor: A factor to add randomness to the delay. A value of 0.2
                       adds or subtracts up to 20% of the current backoff time.
        exceptions_to_catch: A tuple of specific exception classes that should trigger a retry.
        db_type: A label for Prometheus metrics, identifying which system is being retried.

    Returns:
        A decorated asynchronous function.
    """
    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = initial_backoff_s
            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions_to_catch as e:
                    # Increment Prometheus counter for monitoring.
                    if hasattr(metrics, 'DB_TRANSIENT_ERRORS_TOTAL'):
                        metrics.DB_TRANSIENT_ERRORS_TOTAL.labels(db_type=db_type).inc()

                    if attempt == attempts:
                        logger.error(
                            "Function call failed after max attempts.",
                            function=func.__name__,
                            final_attempt=attempt,
                            total_attempts=attempts,
                            error=str(e),
                            exc_info=True,
                        )
                        raise # Re-raise the final exception after all retries fail.

                    # Add a random amount of jitter to the delay.
                    jitter = random.uniform(-current_delay * jitter_factor, current_delay * jitter_factor)
                    wait_time = min(max_backoff_s, current_delay + jitter)

                    logger.warning(
                        "Caught transient error, retrying function.",
                        function=func.__name__,
                        attempt=attempt,
                        total_attempts=attempts,
                        wait_seconds=round(wait_time, 2),
                        error=str(e),
                    )

                    await asyncio.sleep(wait_time)
                    # Double the backoff delay for the next potential attempt.
                    current_delay *= 2
        return wrapper
    return decorator