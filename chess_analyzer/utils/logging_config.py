# chess_analyzer/utils/logging_config.py
"""
Configures application-wide structured logging using structlog.
"""

import logging
import sys
from pathlib import Path
from typing import Any, List, Optional

import structlog
from structlog.types import Processor, EventDict

# ... (QtSignalProcessor is not needed here, so its definition is removed for clarity) ...
# The custom processor for the GUI now only exists in qt_logging.py

def setup_logging(
    log_level: str = "INFO",
    log_to_console: bool = True,
    log_file: Optional[Path] = None,
    force_json_console: bool = False,
    extra_processors: Optional[List[Processor]] = None,
    extra_handlers: Optional[List[logging.Handler]] = None
) -> None:
    """
    Configures application-wide structured logging using structlog.
    Restored to full functionality.
    """
    if extra_processors is None:
        extra_processors = []

    shared_processors: List[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Combine base processors with any extras provided
    all_processors = shared_processors + extra_processors

    structlog.configure(
        processors=all_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handlers: List[logging.Handler] = []
    
    if log_to_console:
        console_renderer: Processor = (
            structlog.processors.JSONRenderer()
            if force_json_console
            else structlog.dev.ConsoleRenderer(colors=True)
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = structlog.stdlib.ProcessorFormatter(processor=console_renderer)
        console_handler.setFormatter(console_formatter)
        handlers.append(console_handler)

    if log_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            file_formatter = structlog.stdlib.ProcessorFormatter(processor=structlog.processors.JSONRenderer())
            file_handler.setFormatter(file_formatter)
            handlers.append(file_handler)
        except (IOError, OSError) as e:
            print(f"FATAL: Could not open log file at {log_file}. Error: {e}", file=sys.stderr)
            raise

    if extra_handlers:
        handlers.extend(extra_handlers)
    
    level_val = logging.getLevelName(log_level.upper())
    # The 'force=True' flag removes any handlers configured by default or from previous calls
    logging.basicConfig(handlers=handlers, level=level_val, force=True)