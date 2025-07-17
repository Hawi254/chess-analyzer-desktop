# chess_analyzer/core/game_phaser.py
"""
Provides a pure function for determining the phase of a chess game.

This module uses simple, effective heuristics based on move count and the
number of pieces on the board to classify a given board position as 'Opening',
'Middlegame', or 'Endgame'. This classification can be used for more nuanced
analysis or statistical aggregation.
"""

from typing import TYPE_CHECKING

import chess

from chess_analyzer.types import GamePhase

if TYPE_CHECKING:
    from chess_analyzer.config.settings import AnalysisSettings


def _count_major_minor_pieces(board: chess.Board) -> int:
    """
    Counts the total number of non-pawn, non-king pieces for both sides.

    Args:
        board: The `chess.Board` object to evaluate.

    Returns:
        The total count of knights, bishops, rooks, and queens on the board.
    """
    piece_count = 0
    piece_types = [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]
    
    for piece_type in piece_types:
        # `board.pieces` returns a list-like object of squares containing the piece.
        piece_count += len(board.pieces(piece_type, chess.WHITE))
        piece_count += len(board.pieces(piece_type, chess.BLACK))
        
    return piece_count


def determine_game_phase(
    board: chess.Board, settings: "AnalysisSettings"
) -> GamePhase:
    """
    Classifies the game phase based on move number and material count.

    The heuristics are checked in order of precedence:
    1. Opening: If the game is at or before the configured max opening move number.
    2. Endgame: If the total number of major/minor pieces is at or below the threshold.
    3. Middlegame: Otherwise, it's considered the middlegame.

    Args:
        board: The `chess.Board` object representing the position to classify.
        settings: The application settings containing the phaser thresholds.

    Returns:
        The determined `GamePhase` enum member.
    """
    if board.fullmove_number <= settings.phaser.opening_max_fullmoves:
        return GamePhase.OPENING

    total_pieces = _count_major_minor_pieces(board)
    if total_pieces <= settings.phaser.endgame_max_piece_count:
        return GamePhase.ENDGAME

    return GamePhase.MIDDLEGAME