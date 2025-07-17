# chess_analyzer/core/pgn_parser.py
"""
Parses `python-chess` game objects into the application's internal data contracts.

This module acts as an Anti-Corruption Layer, translating data from the external
`python-chess` library into our domain's pure data structures (`ParsedGame`,
`GameSlice`, etc.). This isolates our core application from the specifics of the
PGN parsing library and ensures the rest of the app works with a consistent and
predictable data model. It is designed to be resilient to common PGN format
issues, such as games starting from custom positions (FENs).
"""
import structlog
from collections import OrderedDict
from typing import List, TYPE_CHECKING

import chess
import chess.pgn

from chess_analyzer.exceptions import PgnParsingError
from chess_analyzer.types import FEN, GameMetadata, GameSlice, ParsedGame

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

def _get_move_number(ply: int) -> int:
    """Calculates the 1-indexed move number from a 0-indexed ply."""
    return ply // 2 + 1

def parse_game_data(game: chess.pgn.Game) -> ParsedGame:
    """
    Parses a `chess.pgn.Game` object into a structured `ParsedGame`.

    This function iterates through the main line of a game, creating a `GameSlice`
    for each move. It correctly handles games starting from a custom FEN specified
    in the PGN headers and raises a `PgnParsingError` if an illegal move is
    encountered during processing.

    Args:
        game: A game object loaded by the `python-chess` library.

    Returns:
        A `ParsedGame` dataclass containing the game's metadata and a
        structured representation of its moves and positions.

    Raises:
        PgnParsingError: If an illegal move is found, indicating a corrupt PGN record.
    """
    headers = game.headers
    metadata = GameMetadata(
        white_player=headers.get("White", "Unknown Player"),
        black_player=headers.get("Black", "Unknown Player"),
        result=headers.get("Result", "*"),
        event=headers.get("Event", "Unknown Event"),
        site=headers.get("Site", "Unknown Site"),
        date=headers.get("Date", "????.??.??"),
        opening=headers.get("Opening"),
        eco=headers.get("ECO"),
    )

    # Use game.board() instead of chess.Board() to correctly initialize
    # the board from the PGN's FEN header if it exists.
    board = game.board()
    
    game_slices: List[GameSlice] = []
    # Use an OrderedDict to preserve insertion order while guaranteeing uniqueness.
    unique_fens_map: OrderedDict[FEN, None] = OrderedDict([(board.fen(), None)])

    try:
        # Iterate over the game's nodes to keep move and PGN node context synchronized.
        for move_node in game.mainline():
            move = move_node.move
            if move is None:
                continue # Skip the root node, which has no move.

            fen_before = board.fen()
            ply = len(board.move_stack) # Ply is the number of half-moves played.
            
            game_slices.append(
                GameSlice(
                    ply=ply,
                    move_number=_get_move_number(ply),
                    player_color='w' if board.turn == chess.WHITE else 'b',
                    fen_before=fen_before,
                    move=move,
                    pgn_node=move_node
                )
            )
            
            # board.push() is the true validator of a move's legality in sequence.
            board.push(move)
            unique_fens_map[board.fen()] = None

    except (AssertionError, chess.IllegalMoveError, ValueError) as e:
        # This block catches errors if the PGN data is corrupt (e.g., contains
        # a move that is illegal from the current board state).
        game_id_str = f"'{metadata.white_player} vs. {metadata.black_player}'"
        logger.warning(
            "Skipping game due to PGN integrity error during move processing.",
            game=game_id_str, error=str(e)
        )
        raise PgnParsingError(f"Corrupt or illegal game data in game {game_id_str}.") from e

    return ParsedGame(
        metadata=metadata,
        slices=game_slices,
        unique_fens=list(unique_fens_map.keys()),
    )