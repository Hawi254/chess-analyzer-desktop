# chess_analyzer/core/heuristics.py
"""
Contains a collection of concrete `Heuristic` implementations.

Each heuristic is a single, composable rule in the move classification
pipeline, adhering to the `Heuristic` protocol defined in `types.py`. This
modular design allows for an extensible classification system where rules can
be easily added, removed, or modified in isolation. Each heuristic performs
a specific check (e.g., based on CPL, sacrifices, or tactical opportunities)
and returns an updated `ClassificationResult`.
"""

from dataclasses import replace
from typing import TYPE_CHECKING

from chess_analyzer.core.chess_utils import interpret_engine_score
from chess_analyzer.types import Heuristic, MoveClassification, TacticType

if TYPE_CHECKING:
    from chess_analyzer.types import ClassificationResult, MoveAnalysisContext


class CplBasedHeuristic(Heuristic):
    """
    The baseline heuristic that assigns a classification based on CPL thresholds.
    
    This is typically the first heuristic in the chain, establishing the initial
    move quality (e.g., Blunder, Mistake, Good) which subsequent heuristics
    can then refine or override.
    """
    def apply(
        self, context: "MoveAnalysisContext", result: "ClassificationResult"
    ) -> "ClassificationResult":
        """
        Applies classification based on configured CPL thresholds.

        Args:
            context: The context of the move being analyzed.
            result: The current classification result to be modified.

        Returns:
            An updated ClassificationResult with a `classification` based on CPL.
        """
        cpl = result.centipawn_loss
        if cpl is None:
            # If CPL can't be calculated, assume it was the best move.
            return replace(result, classification=MoveClassification.BEST_MOVE)
            
        thresholds = context.settings.classification_thresholds
        if cpl <= thresholds.best_move:
            classification = MoveClassification.BEST_MOVE
        elif cpl <= thresholds.good_move:
            classification = MoveClassification.GOOD_MOVE
        elif cpl <= thresholds.dubious_move:
            classification = MoveClassification.DUBIOUS
        elif cpl <= thresholds.inaccuracy:
            classification = MoveClassification.INACCURACY
        elif cpl <= thresholds.mistake:
            classification = MoveClassification.MISTAKE
        else:
            classification = MoveClassification.BLUNDER
            
        return replace(result, classification=classification)


class BrilliantMoveHeuristic(Heuristic):
    """
    An override heuristic that identifies and flags 'Brilliant' (!!) moves.
    
    It checks for significant, non-obvious material sacrifices from positions
    that are not already losing, where the move is also one of the engine's
    top choices.
    """
    def apply(
        self, context: "MoveAnalysisContext", result: "ClassificationResult"
    ) -> "ClassificationResult":
        """
        Applies brilliance criteria to the move.

        Args:
            context: The context of the move being analyzed.
            result: The current classification result.

        Returns:
            An updated ClassificationResult, potentially with `is_brilliant` set
            to True and the classification changed to BRILLIANT.
        """
        s = context.settings.brilliant_move
        # A brilliant move must still be a very low CPL move.
        if result.centipawn_loss is None or result.centipawn_loss > s.max_cpl_for_brilliance:
            return result

        if context.evaluations.eval_after is None or context.evaluations.eval_before is None:
            return result

        # Check for a significant material sacrifice.
        is_sacrifice = context.move_characteristics.material_delta <= s.sacrifice_threshold_cp
        # Check that the position was not already losing.
        is_non_losing = context.evaluations.eval_before >= s.min_position_eval_cp
        
        # Check if the move was found by the engine within the top N ranks.
        played_move_uci = context.move.uci()
        is_engine_approved = any(
            line.pv and line.pv[0] == played_move_uci
            for line in context.top_engine_lines[:s.max_rank]
        )
        
        if is_sacrifice and is_non_losing and is_engine_approved:
            return replace(result, is_brilliant=True, classification=MoveClassification.BRILLIANT)

        return result


class GreatMoveHeuristic(Heuristic):
    """
    An override heuristic that identifies and flags 'Great' (!) moves.
    
    A great move is a strong, often unique, move that significantly improves
    a player's position, such as saving a lost game, converting a draw to a
    win, or finding the only good response to an opponent's blunder.
    """
    def apply(
        self, context: "MoveAnalysisContext", result: "ClassificationResult"
    ) -> "ClassificationResult":
        """
        Applies 'great move' criteria to the move.

        Args:
            context: The context of the move being analyzed.
            result: The current classification result.

        Returns:
            An updated ClassificationResult, potentially with `is_great_move` set
            to True and the classification changed to GREAT_MOVE.
        """
        # A move cannot be both Brilliant and Great. Brilliant takes precedence.
        # A mistake or blunder cannot be a great move.
        if result.is_brilliant or result.classification in [MoveClassification.MISTAKE, MoveClassification.BLUNDER]:
            return result

        if context.evaluations.eval_after is None or context.evaluations.eval_before is None:
            return result

        s = context.settings.great_move
        char = context.move_characteristics
        
        # Trivial recaptures of equal value are not 'great'.
        if char.is_recapture and abs(char.material_delta) < s.trivial_recapture_threshold:
            return result
            
        is_great = False
        # Case 1: Saving a losing position.
        if (context.evaluations.eval_before <= s.saved_position_min_eval_cp and
            context.evaluations.eval_after >= s.saved_position_recovery_eval_cp):
            is_great = True
        # Case 2: Converting a drawn position to a winning one.
        elif (s.draw_range_min <= context.evaluations.eval_before <= s.draw_range_max and
              context.evaluations.eval_after >= s.win_threshold_cp):
            is_great = True
        # Case 3: Finding the "only good move" where other moves are significantly worse.
        elif len(context.top_engine_lines) > 1 and result.classification == MoveClassification.BEST_MOVE:
            best_eval = interpret_engine_score(context.top_engine_lines[0], context.settings)
            second_best_eval = interpret_engine_score(context.top_engine_lines[1], context.settings)
            if best_eval is not None and second_best_eval is not None and (best_eval - second_best_eval) >= s.only_good_move_threshold_cp:
                is_great = True

        # Case 4: Correctly punishing an opponent's blunder.
        if context.previous_move_context and result.classification == MoveClassification.BEST_MOVE:
            if context.previous_move_context.classification == MoveClassification.BLUNDER:
                is_great = True

        return replace(result, is_great_move=True, classification=MoveClassification.GREAT_MOVE) if is_great else result


class ReciprocalBlunderHeuristic(Heuristic):
    """A flagging heuristic that identifies a "reciprocal blunder"."""
    def apply(
        self, context: "MoveAnalysisContext", result: "ClassificationResult"
    ) -> "ClassificationResult":
        """
        Flags a move if it is a blunder that fails to punish an opponent's prior blunder.

        Args:
            context: The context of the move being analyzed.
            result: The current classification result.

        Returns:
            An updated ClassificationResult with `is_reciprocal_blunder` potentially set to True.
        """
        if (result.classification == MoveClassification.BLUNDER and
            context.previous_move_context and
            context.previous_move_context.classification == MoveClassification.BLUNDER):
            return replace(result, is_reciprocal_blunder=True)
        return result


class TacticFlaggingHeuristic(Heuristic):
    """
    A final-pass heuristic that enriches the result with tactical context flags.
    
    This heuristic does not change the primary classification of the move but
    adds extra information, such as identifying a missed mate opportunity.
    """
    def apply(
        self, context: "MoveAnalysisContext", result: "ClassificationResult"
    ) -> "ClassificationResult":
        """
        Checks for and flags specific tactical situations.

        Args:
            context: The context of the move being analyzed.
            result: The current classification result.

        Returns:
            An updated ClassificationResult with tactical flags potentially set.
        """
        if not context.top_engine_lines:
            return result

        is_best_move_mate = context.top_engine_lines[0].score_mate is not None
        
        # `eval_after` being None signifies a mate delivered by the opponent.
        # This check is flawed; a better check would be to see if the board state
        # after the move is_checkmate(). For now, we assume this is the intent.
        was_played_move_a_mate = context.board.is_checkmate()

        # If the best move was a mate but the player did not deliver mate.
        if is_best_move_mate and not was_played_move_a_mate:
            return replace(
                result,
                is_critical_tactic=True,
                tactic_type=TacticType.MATE_OPPORTUNITY
            )
        
        return result