# chess_analyzer/core/summary_aggregator.py
"""
Provides a pure function to create a final, game-level summary.

This module contains the business logic for all game-wide statistical
aggregations. It takes a fully processed `GameContext` object and transforms it
into a `GameSummary`, calculating metrics like player accuracy, ACPL, and
evaluation volatility, making the data ready for reporting.
"""

import math
import statistics
from collections import Counter
from typing import Dict, List, Optional, TYPE_CHECKING

from chess_analyzer.types import (GameStatistics, GameSummary, MoveClassification,
                                  PlayerStats)

if TYPE_CHECKING:
    from chess_analyzer.config.settings import AnalysisSettings
    from chess_analyzer.types import GameContext


def _calculate_accuracy(acpl: Optional[float], settings: "AnalysisSettings") -> Optional[float]:
    """
    Calculates Lichess-style accuracy percentage from Average Centipawn Loss (ACPL).

    Uses a standard formula to map ACPL onto a 0-100 scale.

    Args:
        acpl: The calculated ACPL for a player.
        settings: Application settings containing the accuracy formula constants.

    Returns:
        The accuracy as a percentage (0-100), rounded to one decimal place, or None.
    """
    if acpl is None or acpl < 0:
        return None
    consts = settings.accuracy
    # Formula: a * e^(b*x) + c, where x is ACPL.
    raw_accuracy = consts.const_a * math.exp(consts.const_b * acpl) + consts.const_c
    # Clamp the result between 0 and 100.
    return round(max(0.0, min(100.0, raw_accuracy)), 1)

def aggregate_game_summary(
    context: "GameContext", settings: "AnalysisSettings"
) -> "GameSummary":
    """
    Aggregates all analysis data from a GameContext into a final GameSummary.

    Args:
        context: The fully processed GameContext for a single game.
        settings: The application's analysis settings.

    Returns:
        A comprehensive `GameSummary` object containing all statistics for the game.
    """
    if not context.parsed_game:
        # This should not happen in a normal flow, but it's a safe guard.
        raise ValueError("Cannot aggregate summary for a game that has not been parsed.")

    # Separate the analysis results by player color.
    white_results = context.enriched_analyses[0::2]
    black_results = context.enriched_analyses[1::2]
    
    white_cpls = [r.classification.centipawn_loss for r in white_results if r.classification.centipawn_loss is not None]
    black_cpls = [r.classification.centipawn_loss for r in black_results if r.classification.centipawn_loss is not None]
    
    white_acpl = statistics.mean(white_cpls) if white_cpls else 0.0
    black_acpl = statistics.mean(black_cpls) if black_cpls else 0.0

    white_stats = PlayerStats(
        acpl=white_acpl,
        accuracy_percent=_calculate_accuracy(white_acpl, settings),
        move_counts=Counter(r.classification.classification for r in white_results if r.classification)
    )
    black_stats = PlayerStats(
        acpl=black_acpl,
        accuracy_percent=_calculate_accuracy(black_acpl, settings),
        move_counts=Counter(r.classification.classification for r in black_results if r.classification)
    )
    
    # Calculate the standard deviation of board evaluations to measure volatility.
    all_evals = [me.eval_after for me in context.move_evaluations if me.eval_after is not None]
    eval_volatility = round(statistics.stdev(all_evals), 2) if len(all_evals) >= 2 else 0.0
    
    final_stats = GameStatistics(
        white=white_stats, black=black_stats,
        white_cpls=white_cpls, black_cpls=black_cpls,
        opening_name=context.parsed_game.metadata.opening,
        eval_volatility=eval_volatility
    )
    
    return GameSummary(
        game_id=context.game_id,
        metadata=context.parsed_game.metadata,
        stats=final_stats,
        narrative=context.narrative,
    )