# chess_analyzer/core/move_classifier.py
"""
Contains the central classification engine of the application.

This module provides the `MoveClassifier`, a pure component that runs a
classification pipeline by executing a chain of composable `Heuristic` objects.
This "Chain of Responsibility" pattern allows for a flexible and extensible
rule-based classification system where rules can be added, removed, or re-ordered
easily.
"""
from typing import List, TYPE_CHECKING

from chess_analyzer.core.chess_utils import calculate_cpl
from chess_analyzer.core.heuristics import (BrilliantMoveHeuristic,
                                            CplBasedHeuristic,
                                            GreatMoveHeuristic,
                                            ReciprocalBlunderHeuristic,
                                            TacticFlaggingHeuristic)

if TYPE_CHECKING:
    from chess_analyzer.types import (ClassificationResult, Heuristic,
                                      MoveAnalysisContext)


class MoveClassifier:
    """
    A stateless classifier that runs a chain of heuristics to classify a single chess move.
    
    The classifier first establishes a baseline classification based on centipawn
    loss, then runs a series of override and enrichment heuristics. The order
    of the chain determines the priority of the rules.
    """

    def __init__(self):
        """Initializes the classifier and defines the ordered heuristic chain."""
        self._heuristic_chain: List["Heuristic"] = [
            # <<< FIX: Run flagging heuristics FIRST.
            TacticFlaggingHeuristic(),        # 1. Flagging: Mark missed tactical opportunities
            ReciprocalBlunderHeuristic(),     # 2. Flagging: Mark reciprocal blunders
            
            # <<< FIX: Run baseline classification SECOND.
            CplBasedHeuristic(),              # 3. Baseline classification (Blunder, Mistake, etc.)
            
            # <<< FIX: Run overrides LAST.
            BrilliantMoveHeuristic(),         # 4. Override: Check for brilliance (!!)
            GreatMoveHeuristic(),             # 5. Override: Check for great moves (!)
        ]

    def classify_move(self, context: "MoveAnalysisContext") -> "ClassificationResult":
        """
        Runs the full multi-pass classification pipeline for a single move.

        Args:
            context: A `MoveAnalysisContext` object containing all necessary data
                     for the classification.

        Returns:
            A final `ClassificationResult` object after all heuristics have been applied.
        """
        from chess_analyzer.types import ClassificationResult
        
        cpl = calculate_cpl(
            eval_before=context.evaluations.eval_before,
            eval_after=context.evaluations.eval_after,
            player_color=context.board.turn
        )
        
        # Create the initial result object. It starts with no classification.
        current_result = ClassificationResult(
            classification=None,
            centipawn_loss=cpl,
            is_brilliant=False,
            is_great_move=False,
            is_critical_tactic=False,
            tactic_type=None,
            time_spent_seconds=context.time_spent_seconds,
            is_reciprocal_blunder=False
        )

        # Apply each heuristic in the chain, passing the result of one to the next.
        for heuristic in self._heuristic_chain:
            current_result = heuristic.apply(context, current_result)
            
        return current_result