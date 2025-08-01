# tests/core/test_game_phaser.py
import chess
from chess_analyzer.core.game_phaser import determine_game_phase, classify_endgame_type
from chess_analyzer.config.settings import AnalysisSettings, GamePhaserSettingsModel
from chess_analyzer.types import GamePhase

def test_determine_game_phase_opening():
    # Arrange
    board = chess.Board()
    board.fullmove_number = 5
    settings = AnalysisSettings(phaser=GamePhaserSettingsModel(opening_max_fullmoves=10, endgame_max_piece_count=8))
    
    # Act
    phase = determine_game_phase(board, settings)
    
    # Assert
    assert phase == GamePhase.OPENING

def test_determine_game_phase_middlegame():
    # Arrange
    board = chess.Board()
    board.fullmove_number = 15
    settings = AnalysisSettings(phaser=GamePhaserSettingsModel(opening_max_fullmoves=10, endgame_max_piece_count=8))
    
    # Act
    phase = determine_game_phase(board, settings)
    
    # Assert
    assert phase == GamePhase.MIDDLEGAME

def test_determine_game_phase_endgame():
    # Arrange
    board = chess.Board("8/8/8/8/8/8/4k3/4K3 w - - 0 1")
    board.fullmove_number = 40
    settings = AnalysisSettings(phaser=GamePhaserSettingsModel(opening_max_fullmoves=10, endgame_max_piece_count=8))
    
    # Act
    phase = determine_game_phase(board, settings)
    
    # Assert
    assert phase == GamePhase.ENDGAME

def test_classify_endgame_type_rook_and_pawn():
    # Arrange
    fen = "8/8/8/8/k7/P7/8/R3K3 w Q - 0 1"
    
    # Act
    endgame_type = classify_endgame_type(fen)
    
    # Assert
    assert endgame_type == "Rook & Pawn"

def test_classify_endgame_type_opposite_colored_bishops():
    # Arrange
    fen = "8/8/8/8/1k6/8/B7/K1b5 w - - 0 1"
    
    # Act
    endgame_type = classify_endgame_type(fen)
    
    # Assert
    assert endgame_type == "Opposite-Colored Bishops"
