# chess_analyzer/core/narrative_generator.py
"""
Generates a high-level, human-readable narrative summarizing a game's "story".

This module provides a pure function that takes a completed `GameSummary` and,
based on a set of heuristics and statistical thresholds, assigns the game an
archetype (e.g., "Tactical Slugfest", "Positional Squeeze") and generates a
descriptive paragraph. This follows a "Prepare, Decide, Render" pattern for
clarity and maintainability.
"""

import statistics
from typing import List, TYPE_CHECKING, Callable, Tuple

from chess_analyzer.types import MoveClassification, NarrativeContext

if TYPE_CHECKING:
    from chess_analyzer.config.settings import AnalysisSettings, NarrativeSettings
    from chess_analyzer.types import GameSummary


# --- 1. PREPARE: Metric Calculation and Context Building ---

def _calculate_cpl_std_dev(cpls: List[float]) -> float:
    """Calculates CPL standard deviation. Returns 0.0 if data is insufficient."""
    return statistics.stdev(cpls) if len(cpls) >= 2 else 0.0

def _build_narrative_context(summary: "GameSummary") -> NarrativeContext:
    """
    PREPARE STEP: Calculates all derived metrics needed for narrative generation.
    
    This function centralizes metric calculation, creating an immutable context
    object that is passed to the decision-making heuristics. This avoids
    re-calculating the same values in multiple places.

    Args:
        summary: The completed `GameSummary` for the game.

    Returns:
        A `NarrativeContext` object containing all necessary data for the heuristics.
    """
    white_stats = summary.stats.white
    black_stats = summary.stats.black
    
    return NarrativeContext(
        std_dev_white=_calculate_cpl_std_dev(summary.stats.white_cpls),
        std_dev_black=_calculate_cpl_std_dev(summary.stats.black_cpls),
        combined_blunders=(
            white_stats.move_counts.get(MoveClassification.BLUNDER, 0) +
            black_stats.move_counts.get(MoveClassification.BLUNDER, 0)
        ),
        white_acpl=white_stats.acpl,
        black_acpl=black_stats.acpl,
        white_blunders=white_stats.move_counts.get(MoveClassification.BLUNDER, 0),
        black_blunders=black_stats.move_counts.get(MoveClassification.BLUNDER, 0),
        white_player_name=summary.metadata.white_player,
        black_player_name=summary.metadata.black_player,
        game_result=summary.metadata.result
    )

# --- 2. DECIDE: Archetype Detection Heuristics ---
# These pure functions take the context and settings and return a boolean.

def _is_tactical_slugfest(context: NarrativeContext, settings: "NarrativeSettings") -> bool:
    """Checks if the game was a volatile, high-blunder affair."""
    return (
        context.std_dev_white > settings.min_stddev_for_slugfest or
        context.std_dev_black > settings.min_stddev_for_slugfest
    ) and context.combined_blunders >= settings.min_blunders_for_slugfest

def _is_decisive_moment(context: NarrativeContext, settings: "NarrativeSettings") -> bool:
    """Checks if the game was decided by a single major error."""
    return context.combined_blunders == settings.blunder_count_for_decisive

def _is_positional_squeeze(context: NarrativeContext, settings: "NarrativeSettings") -> bool:
    """Checks if the game was a very clean, low-error affair from both sides."""
    if context.white_acpl is None or context.black_acpl is None:
        return False
    return (
        context.white_acpl <= settings.max_acpl_for_positional and
        context.black_acpl <= settings.max_acpl_for_positional and
        context.white_blunders == 0 and context.black_blunders == 0
    )

# --- 3. RENDER: Narrative String Formatting ---
# These functions are responsible for producing the final user-facing text.

def _render_slugfest_narrative(context: NarrativeContext) -> str:
    """Renders the narrative for a tactical slugfest."""
    return (
        f"This was a tactical slugfest where {context.white_player_name} and "
        f"{context.black_player_name} battled through a highly volatile game marked "
        f"by {context.combined_blunders} combined blunders."
    )

def _render_decisive_moment_narrative(context: NarrativeContext) -> str:
    """Renders the narrative for a game decided by one blunder."""
    return (
        f"This game was defined by a single decisive moment. The outcome hinged on a "
        f"critical blunder, which ultimately determined the result between "
        f"{context.white_player_name} and {context.black_player_name}."
    )

def _render_positional_squeeze_narrative(context: NarrativeContext) -> str:
    """Renders the narrative for a clean, positional game."""
    return (
        f"A clean, positional squeeze. Both {context.white_player_name} and "
        f"{context.black_player_name} played with high accuracy, resulting in a "
        f"methodical game with no major blunders."
    )

def _render_standard_game_narrative(context: NarrativeContext) -> str:
    """Renders the default narrative for a standard game."""
    return (
        f"A standard game between {context.white_player_name} and "
        f"{context.black_player_name}, concluding with a result of {context.game_result}."
    )

# --- Public API ---

# A data-driven pipeline for archetypes, defined by priority order.
# The first detector to return True will have its corresponding renderer used.
ARCHETYPE_PIPELINE: List[Tuple[str, Callable, Callable]] = [
    ("tactical_slugfest", _is_tactical_slugfest, _render_slugfest_narrative),
    ("decisive_moment", _is_decisive_moment, _render_decisive_moment_narrative),
    ("positional_squeeze", _is_positional_squeeze, _render_positional_squeeze_narrative),
]

def generate_game_narrative(
    summary: "GameSummary", settings: "AnalysisSettings"
) -> str:
    """
    Generates a human-readable narrative paragraph summarizing the game.
    
    This function orchestrates the "Prepare, Decide, Render" pattern to create
    a compelling story for the game based on its statistical profile.

    Args:
        summary: The completed GameSummary data contract for the game.
        settings: The application settings containing narrative thresholds.

    Returns:
        A string containing the game's narrative summary.
    """
    # 1. PREPARE: Calculate all metrics once and build the context.
    narrative_context = _build_narrative_context(summary)
    narrative_settings = settings.narrative
    
    # 2. DECIDE: Iterate through the prioritized pipeline of archetype detectors.
    for _name, detector, renderer in ARCHETYPE_PIPELINE:
        if detector(narrative_context, narrative_settings):
            # 3. RENDER: Use the corresponding renderer and return immediately.
            return renderer(narrative_context)
    
    # 4. RENDER (Default): If no specific archetype matched, return the standard narrative.
    return _render_standard_game_narrative(narrative_context)