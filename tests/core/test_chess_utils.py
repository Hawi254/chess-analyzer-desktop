# tests/core/test_chess_utils.py
import chess
import chess.pgn
import io
from chess_analyzer.core.chess_utils import (
    calculate_cpl,
    interpret_engine_score,
    get_material_value,
    get_material_diff,
    categorize_time_control,
    get_time_increment,
    determine_game_termination
)
from chess_analyzer.types import RawEngineLine
from chess_analyzer.config.settings import AnalysisSettings

def test_calculate_cpl():
    assert calculate_cpl(100, 50, chess.WHITE) == 50
    assert calculate_cpl(100, 150, chess.BLACK) == 50
    assert calculate_cpl(100, 150, chess.WHITE) == 0  # No negative CPL

def test_interpret_engine_score():
    settings = AnalysisSettings()
    assert interpret_engine_score(RawEngineLine(rank=1, score_cp=100, score_mate=None, pv=[]), settings) == 100
    assert interpret_engine_score(RawEngineLine(rank=1, score_cp=None, score_mate=2, pv=[]), settings) > 9000
    assert interpret_engine_score(RawEngineLine(rank=1, score_cp=None, score_mate=-2, pv=[]), settings) < -9000

def test_get_material_value():
    board = chess.Board()
    assert get_material_value(board, chess.WHITE) == 39.2

def test_get_material_diff():
    board = chess.Board()
    assert get_material_diff(board, chess.WHITE) == 0
    board.remove_piece_at(chess.E2)
    assert get_material_diff(board, chess.WHITE) == -1.0

def test_categorize_time_control():
    assert categorize_time_control("60+0") == "Bullet"
    assert categorize_time_control("180+0") == "Blitz"
    assert categorize_time_control("600+5") == "Rapid"
    assert categorize_time_control("3600+0") == "Classical"
    assert categorize_time_control("-") == "Unknown"

def test_get_time_increment():
    assert get_time_increment("600+5") == 5
    assert get_time_increment("600") == 0
    assert get_time_increment("-") == 0

def test_determine_game_termination():
    pgn = io.StringIO("1. e4 e5 2. Nf3 Nf6 3. Nxe5 Nxe4 4. Qe2 Nf6 5. Nc6+ Qe7 6. Nxe7 1-0")
    game = chess.pgn.read_game(pgn)
    assert determine_game_termination(game) == "Resignation"

    pgn = io.StringIO("1. e4 e5 2. Ke2 Ke7 3. Ke1 Ke8 4. Ke2 Ke7 5. Ke1 Ke8 1/2-1/2")
    game = chess.pgn.read_game(pgn)
    # The board state is a draw by repetition, but the PGN termination is by agreement
    assert determine_game_termination(game) == "Draw by Agreement"
