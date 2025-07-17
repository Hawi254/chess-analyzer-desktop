# chess_analyzer/core/move_characterizer.py
"""
Provides a pure function to determine the objective tactical characteristics of a move.

This module is a stateless component in the functional core. It takes a board
state and a move and returns a structured data object (`MoveCharacteristics`)
containing factual, non-interpretive properties of that move (e.g., is it a
capture, does it give check). This data is then used by higher-level components
like the `MoveClassifier`.
"""

import chess

from chess_analyzer.core.chess_utils import get_material_diff
from chess_analyzer.types import MoveCharacteristics


def characterize_move(board: chess.Board, move: chess.Move) -> "MoveCharacteristics":
    """
    Analyzes a move to determine its fundamental tactical properties.

    All properties are determined from the perspective of the player whose
    turn it is to move.

    Args:
        board: The `chess.Board` object representing the position *before* the move.
        move: The `chess.Move` object to be characterized.

    Returns:
        A `MoveCharacteristics` dataclass containing objective tactical data.
    """
    pov = board.turn

    # Calculate material delta from the moving player's perspective.
    # Note: This is the material difference *before* the move is made.
    material_delta_in_pawns = get_material_diff(board, pov)
    
    # Determine boolean tactical properties using efficient lookups from python-chess.
    is_capture = board.is_capture(move)
    is_check = board.gives_check(move)
    is_castle = board.is_castling(move)
    is_promotion = move.promotion is not None
    is_en_passant = board.is_en_passant(move)
    is_quiet = not (is_capture or is_check or is_promotion)
    
    is_recapture = False
    if is_capture:
        # A move is a recapture if the opponent's last move was a capture
        # that ended on the same square where our current capture begins.
        if board.move_stack:
            last_move = board.move_stack[-1]
            if board.is_capture(last_move) and last_move.to_square == move.from_square:
                is_recapture = True
    
    return MoveCharacteristics(
        is_capture=is_capture,
        is_check=is_check,
        is_castle=is_castle,
        is_promotion=is_promotion,
        is_en_passant=is_en_passant,
        is_quiet_move=is_quiet,
        material_delta=int(material_delta_in_pawns * 100),
        is_recapture=is_recapture
    )