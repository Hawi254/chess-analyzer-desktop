# chess_analyzer/utils/logging_config.py
"""
Configures application-wide structured logging using structlog.
"""

import logging
import sys
from pathlib import Path
from typing import Any, List, Optional

import structlog
from structlog.types import Processor

def setup_logging(
    log_level: str = "INFO",
    log_to_console: bool = True,
    log_file: Optional[Path] = None,
    force_json_console: bool = False,
    extra_processors: Optional[List[Processor]] = None,
    extra_handlers: Optional[List[logging.Handler]] = None
) -> None:
    """
    Configures application-wide structured logging using structlog, ensuring
    it captures and formats logs from all sources, including third-party libraries.
    """
    if extra_processors is None:
        extra_processors = []

    shared_processors: List[Processor] = [
        structlog.contextvars.merge_contextvars,
        # --- CORRECTED: Removed the problematic processor ---
        # structlog.stdlib.filter_by_level, # This processor is redundant and causes crashes with foreign logs.
        # The standard library's level-setting on the handler is the correct way to filter.
        # ---------------------------------------------------
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=shared_processors + extra_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Processor
    if force_json_console:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processor=renderer,
    )

    handlers: List[logging.Handler] = []
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    if log_file:
        file_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=structlog.processors.JSONRenderer(),
        )
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    if extra_handlers: # This loop is now correct for actual handlers
        for handler in extra_handlers:
            handler.setFormatter(formatter) # Ensure GUI handler also gets structured logs
        handlers.extend(extra_handlers)
    
    # Use basicConfig to set up the root logger cleanly
    logging.basicConfig(handlers=handlers, level=log_level.upper(), force=True)