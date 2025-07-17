# chess_analyzer/core/board_analyzer.py
"""
Provides pure, stateless functions for high-level, interpretive board analysis.

This module is part of the functional core and serves a dual purpose:

1.  **Data Enrichment:** It performs context-dependent transformations on raw
    analysis data. Its primary function is to convert the engine's UCI (Universal
    Chess Interface) move notation into human-readable SAN (Standard Algebraic
    Notation), which requires the context of the current board state.

2.  **Tactical Interpretation:** It includes simple functions to identify common
    tactical motifs (e.g., forks, pins) that might have been missed, adding a
    layer of interpretive insight to the raw engine evaluation.
"""

from typing import List, Optional, TYPE_CHECKING
import chess

if TYPE_CHECKING:
    from chess_analyzer.config.settings import AnalysisSettings
    from chess_analyzer.types import (ClassificationResult, EnrichedAnalysis,
                                      FormattedEngineLine, RawEngineLine)


def enrich_analysis_with_san(
    board: chess.Board,
    classification: "ClassificationResult",
    engine_lines: List["RawEngineLine"],
    settings: "AnalysisSettings"
) -> "EnrichedAnalysis":
    """
    Enriches raw analysis results with human-readable formatting.

    This function iterates through the raw engine lines, converts the primary
    move from UCI to SAN, and formats the evaluation score into a consistent
    string representation (e.g., "+1.23" or "M5").

    Args:
        board: The board state *before* the move, needed for SAN resolution.
        classification: The result object from the `MoveClassifier`.
        engine_lines: The list of raw lines from the engine service.
        settings: Application settings for mate score representation.

    Returns:
        An `EnrichedAnalysis` dataclass containing the original classification
        and a new list of `FormattedEngineLine` objects.
    """
    from chess_analyzer.types import EnrichedAnalysis, FormattedEngineLine

    formatted_lines: List[FormattedEngineLine] = []

    for line in engine_lines:
        # Skip any empty or invalid lines from the engine.
        if not line.pv:
            continue

        try:
            # Convert the first move of the Principal Variation from UCI to SAN.
            move_obj = chess.Move.from_uci(line.pv[0])
            move_san = board.san(move_obj)

            # Format the score string for display.
            eval_str: str
            if line.score_mate is not None:
                eval_str = f"M{abs(line.score_mate)}"
            elif line.score_cp is not None:
                eval_str = f"{line.score_cp / 100.0:+.2f}"
            else:
                eval_str = "N/A" # Should not happen with valid engine output.
            
            formatted_lines.append(
                FormattedEngineLine(move_san=move_san, eval_str=eval_str)
            )
        except (ValueError, IndexError):
            # Gracefully skip any line that has an invalid move UCI string.
            continue
    
    return EnrichedAnalysis(
        classification=classification,
        formatted_engine_lines=formatted_lines
    )

def find_missed_tactic_motif(
    board_after_best_move: chess.Board, best_move: chess.Move
) -> Optional[str]:
    """
    Performs a simple, one-move check for common tactical motifs.

    This is not a comprehensive tactical solver but a heuristic check for
    obvious patterns like forks, pins, or discovered attacks that might have
    been created by the engine's recommended best move.

    Args:
        board_after_best_move: The board state *after* the optimal move has been played.
        best_move: The optimal move that was played to reach this board state.

    Returns:
        A string representing the tactical motif (e.g., "FORK", "PIN"), or None if
        no simple motif is found.
    """
    piece = board_after_best_move.piece_at(best_move.to_square)
    if not piece:
        return None

    # Check for Knight forks on valuable pieces.
    if piece.piece_type == chess.KNIGHT:
        attacked_squares = board_after_best_move.attacks(best_move.to_square)
        valuable_pieces_attacked = sum(
            1 for sq in attacked_squares
            if (p := board_after_best_move.piece_at(sq)) and p.piece_type > chess.PAWN
        )
        if valuable_pieces_attacked >= 2:
            return "FORK"

    # Check for pins created by sliding pieces.
    if piece.piece_type in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
        opponent_color = not piece.color
        for sq in chess.SQUARES:
            if board_after_best_move.is_pinned(opponent_color, sq):
                # Check if the piece that just moved is the pinning piece.
                if best_move.to_square in board_after_best_move.pin(opponent_color, sq):
                    return "PIN"

    # Check for discovered attacks.
    if board_after_best_move.is_check():
        king_sq = board_after_best_move.king(not piece.color)
        if king_sq:
            # Find the piece(s) giving check.
            attackers = board_after_best_move.attackers(piece.color, king_sq)
            # If the piece that just moved is NOT the one giving check, it was a discovered attack.
            if attackers and best_move.to_square not in attackers:
                return "DISCOVERED_ATTACK"

    return None