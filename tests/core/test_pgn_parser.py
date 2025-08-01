# tests/core/test_pgn_parser.py
import chess.pgn
import io
from chess_analyzer.core.pgn_parser import parse_game_data

def test_parse_simple_game():
    pgn_string = """
[Event "Test Game"]
[Site "Test Site"]
[Date "2025.01.01"]
[Round "?"]
[White "Player A"]
[Black "Player B"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0
"""
    pgn_file = io.StringIO(pgn_string)
    game = chess.pgn.read_game(pgn_file)
    
    parsed_game = parse_game_data(game)
    
    assert parsed_game.metadata.white_player == "Player A"
    assert parsed_game.metadata.black_player == "Player B"
    assert parsed_game.metadata.result == "1-0"
    assert parsed_game.metadata.event == "Test Game"
    assert len(parsed_game.slices) == 6

def test_parse_game_from_fen():
    pgn_string = """
[Event "Test Game From FEN"]
[Site "Test Site"]
[Date "2025.01.01"]
[Round "?"]
[White "Player A"]
[Black "Player B"]
[Result "*"]
[FEN "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"]
[SetUp "1"]

2. Nf3 Nc6 3. Bb5 a6 *
"""
    pgn_file = io.StringIO(pgn_string)
    game = chess.pgn.read_game(pgn_file)
    
    parsed_game = parse_game_data(game)
    
    assert parsed_game.metadata.white_player == "Player A"
    assert parsed_game.metadata.black_player == "Player B"
    assert parsed_game.metadata.event == "Test Game From FEN"
    assert len(parsed_game.slices) == 4
    assert parsed_game.slices[0].fen_before == "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
