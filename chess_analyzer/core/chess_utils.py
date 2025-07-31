# chess_analyzer/core/chess_utils.py
"""
Provides a collection of pure, stateless functions for chess-related calculations.

This module acts as the "math library" for the chess domain. It has no
dependencies on other parts of this application except for the data contracts
defined in `types.py` and `settings.py`. Its functions are deterministic and
form the foundational building blocks for more complex analysis.
"""

from typing import Dict, Final, Optional, TYPE_CHECKING
import chess
import chess.pgn

if TYPE_CHECKING:
    from chess_analyzer.config.settings import AnalysisSettings
    from chess_analyzer.types import RawEngineLine

# A constant dictionary mapping piece types to their standard pawn-unit values.
PIECE_VALUES: Final[Dict[chess.PieceType, float]] = {
    chess.PAWN: 1.0,
    chess.KNIGHT: 3.0,
    chess.BISHOP: 3.1,
    chess.ROOK: 5.0,
    chess.QUEEN: 9.0,
    chess.KING: 0.0,
}

# A constant used to scale down mate scores to be comparable with centipawn scores.
MATE_ADJUSTMENT_FACTOR: Final[int] = 10


def calculate_cpl(
    eval_before: Optional[float],
    eval_after: Optional[float],
    player_color: chess.Color
) -> Optional[int]:
    """
    Calculates Centipawn Loss (CPL) from the perspective of the active player.
    """
    if eval_before is None or eval_after is None:
        return None

    if player_color == chess.WHITE:
        cpl = eval_before - eval_after
    else:
        cpl = eval_after - eval_before

    return max(0, int(cpl))

def interpret_engine_score(
    raw_line: Optional["RawEngineLine"], settings: "AnalysisSettings"
) -> Optional[float]:
    """
    Parses a RawEngineLine into a standardized score in centipawns.
    """
    if not raw_line:
        return None

    if raw_line.score_mate is not None:
        sign = 1 if raw_line.score_mate > 0 else -1
        base_score = float(
            settings.mate_score_equivalent_cp - (abs(raw_line.score_mate) * MATE_ADJUSTMENT_FACTOR)
        )
        return sign * base_score
    elif raw_line.score_cp is not None:
        return float(raw_line.score_cp)

    return None

def get_material_value(board: chess.Board, color: chess.Color) -> float:
    """
    Calculates the total material value for a given color on the board.
    """
    material: float = 0.0
    for piece_type, value in PIECE_VALUES.items():
        material += len(board.pieces(piece_type, color)) * value
    return material

def get_material_diff(board: chess.Board, perspective: chess.Color) -> float:
    """
    Calculates the material difference from a given color's perspective.
    """
    diff: float = 0.0
    for piece in board.piece_map().values():
        value = PIECE_VALUES.get(piece.piece_type, 0.0)
        if piece.color == perspective:
            diff += value
        else:
            diff -= value
    return round(diff, 2)

# --- NEW: Helper function for dashboard data population ---
def categorize_time_control(time_control_tag: Optional[str]) -> str:
    """
    Categorizes a PGN TimeControl tag into 'Blitz', 'Rapid', 'Classical', or 'Unknown'.

    The logic is based on the base time per player, adhering to common chess definitions.
    - Bullet: < 3 minutes
    - Blitz: >= 3 minutes and < 10 minutes
    - Rapid: >= 10 minutes and < 60 minutes
    - Classical: >= 60 minutes

    Args:
        time_control_tag: The raw string from the PGN "TimeControl" header.
                          e.g., "300+5", "600", "1800+10".

    Returns:
        A string category: "Bullet", "Blitz", "Rapid", "Classical", or "Unknown".
    """
    if not time_control_tag or time_control_tag == "-":
        return "Unknown"
    
    try:
        # Extract the base time, which is the part before the '+' increment.
        base_time_str = time_control_tag.split('+')[0]
        base_seconds = int(base_time_str)
        
        base_minutes = base_seconds / 60.0
        
        if base_minutes < 3:
            return "Bullet"
        elif base_minutes < 10:
            return "Blitz"
        elif base_minutes < 60:
            return "Rapid"
        else:
            return "Classical"
            
    except (ValueError, IndexError):
        # Gracefully handle non-standard or malformed tags.
        return "Unknown"
    
def get_time_increment(time_control_str: Optional[str]) -> int:
    """
    Extracts the time increment from a TimeControl string (e.g., '600+5' -> 5).
    
    Args:
        time_control_str: The raw string from the PGN "TimeControl" header.
                          e.g., "300+5", "600", "1800+10".
                          
    Returns:
        The increment in seconds as an integer, or 0 if not found.
    """
    if not time_control_str or '+' not in time_control_str:
        return 0
    
    try:
        # Get the part after the '+' and convert it to an integer.
        increment_str = time_control_str.split('+')[1]
        return int(increment_str)
    except (IndexError, ValueError):
        # Handle cases like "600+" or "600+abc"
        return 0

def determine_game_termination(game: chess.pgn.Game) -> str:
    """
    Determines the reason for game termination using heuristic logic,
    including Lichess automatic 3‑fold repetition and 50‑move rule draws.
    """
    termination = game.headers.get("Termination")
    if termination == "Time forfeit":
        return "Time forfeit"

    board = game.board()
    for move in game.mainline_moves():
        board.push(move)

    if board.is_checkmate():
        return "Checkmate"
    if board.is_stalemate():
        return "Stalemate"
    # Lichess auto‐claims 3‑fold repetition draw
    if board.is_repetition(3):
        return "Draw by Threefold Repetition"
    # Lichess auto‐claims 50‑move rule
    if board.halfmove_clock >= 100:
        return "Draw by 50‑move Rule"

    if board.is_insufficient_material():
        return "Draw by Insufficient Material"

    result = game.headers.get("Result")
    if result in ["1-0", "0-1"]:
        return "Resignation"
    if result == "1/2-1/2":
        # If it wasn't auto‑claimed, fall back to agreement
        return "Draw by Agreement"

    return termination or "Unknown"
