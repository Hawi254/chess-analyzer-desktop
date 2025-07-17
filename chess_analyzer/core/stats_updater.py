# chess_analyzer/core/stats_updater.py
"""
Provides a pure function to update long-term statistics for a chess position.

This module encapsulates the business logic for statistical aggregation for a
single, unique chess position (represented by its FEN). It takes the previous
state of a position's stats and a new analysis result, and calculates the new,
updated statistical state. This is a key part of the application's learning
and data aggregation capability.
"""

from dataclasses import asdict
from typing import Any, Dict, Optional, TYPE_CHECKING

from chess_analyzer.types import MoveClassification

if TYPE_CHECKING:
    from chess_analyzer.config.settings import AnalysisSettings
    from chess_analyzer.types import ClassificationResult, FEN, PositionStats

# A mapping from the MoveClassification enum to the corresponding database column name.
_CLASSIFICATION_TO_COUNTER_MAP: Dict[MoveClassification, str] = {
    MoveClassification.BRILLIANT: "brilliant_count",
    MoveClassification.GREAT_MOVE: "great_move_count",
    MoveClassification.GOOD_MOVE: "good_move_count",
    MoveClassification.DUBIOUS: "dubious_move_count",
    MoveClassification.INACCURACY: "inaccuracy_count",
    MoveClassification.MISTAKE: "mistake_count",
    MoveClassification.BLUNDER: "blunder_count",
}

def calculate_new_position_stats(
    fen: "FEN",
    previous_stats: Optional["PositionStats"],
    new_result: "ClassificationResult",
    eval_std_dev: Optional[float],
    settings: "AnalysisSettings",
) -> Dict[str, Any]:
    """
    Calculates the new state of a position's statistics based on a new analysis result.

    This function handles two cases:
    1.  Genesis Case: If `previous_stats` is None, it creates the initial statistics record.
    2.  Update Case: If `previous_stats` exists, it calculates the new aggregated
        values (e.g., using a streaming average formula for CPL).
    
    Args:
        fen: The FEN string of the position being updated.
        previous_stats: The existing `PositionStats` object for this FEN, or None.
        new_result: The `ClassificationResult` from the analysis of the move played from this FEN.
        eval_std_dev: The calculated standard deviation of the engine's top move evaluations.
        settings: The application settings, used for thresholds like time trouble.

    Returns:
        A dictionary payload ready to be upserted into the `position_stats` table.
    """
    # This setting is not currently defined in AnalysisSettings, but this showcases
    # how it would be used. We'll assume a default value for now.
    time_trouble_threshold = getattr(settings, 'time_trouble_threshold_seconds', 15.0)
    
    time_spent = new_result.time_spent_seconds or 0.0
    in_time_trouble = 1 if 0 < time_spent <= time_trouble_threshold else 0

    if previous_stats is None:
        # This is the first time we've seen this position. Create a new record.
        initial_stats = {
            "fen": fen, "total_occurrences": 1, "average_cpl": 0.0, "brilliant_count": 0,
            "great_move_count": 0, "good_move_count": 0, "dubious_move_count": 0,
            "inaccuracy_count": 0, "mistake_count": 0, "blunder_count": 0,
            "is_critical_tactic": new_result.is_critical_tactic,
            "tactic_type": new_result.tactic_type.value if new_result.tactic_type else None,
            "total_time_spent_seconds": time_spent, "move_count_in_time_trouble": in_time_trouble,
            "eval_std_dev": eval_std_dev,
        }
        if cpl := new_result.centipawn_loss:
            initial_stats["average_cpl"] = float(cpl)
        
        if new_result.classification in _CLASSIFICATION_TO_COUNTER_MAP:
            column = _CLASSIFICATION_TO_COUNTER_MAP[new_result.classification]
            initial_stats[column] = 1
        
        return initial_stats

    # This position has been seen before. Update the existing stats.
    updated_stats = asdict(previous_stats)

    new_occurrences = previous_stats.total_occurrences + 1
    updated_stats["total_occurrences"] = new_occurrences

    if (new_cpl := new_result.centipawn_loss) is not None:
        # Use Welford's algorithm for a stable, streaming average calculation.
        new_avg = previous_stats.average_cpl + (new_cpl - previous_stats.average_cpl) / new_occurrences
        updated_stats["average_cpl"] = new_avg

    if new_result.classification in _CLASSIFICATION_TO_COUNTER_MAP:
        column = _CLASSIFICATION_TO_COUNTER_MAP[new_result.classification]
        updated_stats[column] += 1

    # Update flags (a position is considered tactical if it ever was).
    updated_stats["is_critical_tactic"] = previous_stats.is_critical_tactic or new_result.is_critical_tactic
    if previous_stats.tactic_type is None and new_result.tactic_type:
        updated_stats["tactic_type"] = new_result.tactic_type.value
        
    # Update cumulative time-based metrics.
    updated_stats["total_time_spent_seconds"] += time_spent
    updated_stats["move_count_in_time_trouble"] += in_time_trouble
    if eval_std_dev is not None:
        # For simplicity, we just take the latest standard deviation.
        # A more complex implementation could average this value.
        updated_stats["eval_std_dev"] = eval_std_dev

    return updated_stats