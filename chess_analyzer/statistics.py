"""
Manages statistics tracking for the Chess Analyzer application.

This module provides the StatisticsTracker class, a centralized component
for aggregating and reporting metrics from an analysis run. It is designed
to be simple and robust, using a type-safe Enum for keys.
"""
import os
from collections import Counter
from enum import Enum, auto
from typing import Dict

import structlog

logger = structlog.get_logger(__name__)


class StatKey(Enum):
    """Enumeration for keys used in the StatisticsTracker for type safety."""
    GAMES_READ = auto()
    GAMES_ANALYZED = auto()
    GAMES_SKIPPED_TOTAL = auto()
    SKIPPED_ALREADY_PROCESSED = auto()
    SKIPPED_NO_TARGET_PLAYER = auto()
    SKIPPED_NO_MOVES = auto()
    GAMES_WITH_ERRORS = auto()
    FEN_CACHE_HITS = auto()
    FENS_ANALYZED_BY_ENGINE = auto()
    RETRYABLE_ERRORS = auto()


# A mapping for user-friendly display names, decoupled from the keys.
STAT_DISPLAY_NAMES: Dict[StatKey, str] = {
    StatKey.GAMES_READ: "Total Games Read from PGN",
    StatKey.GAMES_ANALYZED: "Games Fully Analyzed",
    StatKey.GAMES_SKIPPED_TOTAL: "Total Games Skipped",
    StatKey.SKIPPED_ALREADY_PROCESSED: "  - Skipped (Already Processed)",
    StatKey.SKIPPED_NO_TARGET_PLAYER: "  - Skipped (Player Not in Game)",
    StatKey.SKIPPED_NO_MOVES: "  - Skipped (Game Had No Moves)",
    StatKey.GAMES_WITH_ERRORS: "Games with Critical Processing Errors",
    StatKey.FEN_CACHE_HITS: "FENs Found in Cache",
    StatKey.FENS_ANALYZED_BY_ENGINE: "FENs Analyzed by Engine",
    StatKey.RETRYABLE_ERRORS: "Total Recoverable Errors (Retried)",
}


class StatisticsTracker:
    """
    A stateful class to aggregate and report statistics for an analysis run.
    """

    def __init__(self):
        """Initializes the StatisticsTracker with all counters set to zero."""
        self.stats: Counter[StatKey] = Counter()
        self.report_path: str = ""
        self.reset()
        logger.debug("StatisticsTracker initialized.")

    def reset(self) -> None:
        """Resets all statistics to their initial state for a new run."""
        self.stats.clear()
        self.report_path = ""

    def add_stat(self, key: StatKey, count: int = 1) -> None:
        """Increments a statistic by a given amount."""
        self.stats[key] += count

    def set_stat(self, key: StatKey, value: int) -> None:
        """Directly sets a statistic to a specific value."""
        self.stats[key] = value

    def set_report_path(self, path: str) -> None:
        """Stores the path to the CSV report file for final reporting."""
        self.report_path = os.path.abspath(path)

    def log_summary(self) -> None:
        """Logs a formatted summary of all collected statistics for the run."""
        logger.info("\n" + "=" * 12 + " Analysis Run Summary " + "=" * 12)

        # Iterating through the enum provides a defined order and ensures
        # no statistic is ever missed in the final report.
        for key in StatKey:
            if key in self.stats:
                display_text = STAT_DISPLAY_NAMES.get(key, key.name.replace("_", " ").title())
                logger.info(f"{display_text:<40}: {self.stats[key]:>6}")

        logger.info("-" * 48)

        num_analyzed = self.stats.get(StatKey.GAMES_ANALYZED, 0)
        if self.report_path:
            if num_analyzed > 0 and os.path.exists(self.report_path):
                logger.info(f"CSV Report Generated ({num_analyzed} games): '{self.report_path}'")
            else:
                logger.info(f"CSV Report Path (not generated): '{self.report_path}'")

        logger.info("=" * 48)