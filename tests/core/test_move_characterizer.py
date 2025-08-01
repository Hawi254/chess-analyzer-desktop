# tests/core/test_move_characterizer.py
import chess
from chess_analyzer.core.move_characterizer import characterize_move

def test_characterize_quiet_move():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    characteristics = characterize_move(board, move)
    assert characteristics.is_quiet_move
    assert not characteristics.is_capture
    assert not characteristics.is_check

def test_characterize_capture():
    board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    move = chess.Move.from_uci("e4d5")
    characteristics = characterize_move(board, move)
    assert characteristics.is_capture
    assert not characteristics.is_quiet_move

def test_characterize_check():
    board = chess.Board("k7/8/8/8/8/8/8/R7 w - - 0 1")
    move = chess.Move.from_uci("a1a7")
    assert board.gives_check(move)

def test_characterize_castle():
    board = chess.Board("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    move = chess.Move.from_uci("e1g1")
    characteristics = characterize_move(board, move)
    assert characteristics.is_castle

def test_characterize_promotion():
    board = chess.Board("8/P7/8/8/8/8/k7/K7 w - - 0 1")
    move = chess.Move.from_uci("a7a8q")
    characteristics = characterize_move(board, move)
    assert characteristics.is_promotion

def test_characterize_en_passant():
    board = chess.Board("rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    board.push(chess.Move.from_uci("e4e5"))
    board.push(chess.Move.from_uci("d7d5"))
    move = chess.Move.from_uci("e5d6")
    characteristics = characterize_move(board, move)
    assert characteristics.is_en_passant
