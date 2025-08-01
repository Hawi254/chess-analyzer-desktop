# tests/core/test_move_classifier.py
import chess
from chess_analyzer.core.move_classifier import MoveClassifier
from chess_analyzer.types import MoveEvaluations, MoveAnalysisContext, MoveClassification, MoveCharacteristics
from chess_analyzer.config.settings import AnalysisSettings, ClassificationThresholdsModel

def test_classify_blunder():
    # Arrange
    mock_board = chess.Board()
    mock_move_characteristics = MoveCharacteristics(
        is_capture=False,
        is_check=False,
        is_castle=False,
        is_promotion=False,
        is_en_passant=False,
        is_quiet_move=True,
        material_delta=0,
        is_recapture=False
    )
    mock_settings = AnalysisSettings(
        classification_thresholds=ClassificationThresholdsModel(
            best_move=5,
            good_move=40,
            dubious_move=80,
            inaccuracy=150,
            mistake=300
        )
    )
    mock_context = MoveAnalysisContext(
        board=mock_board,
        move=chess.Move.from_uci("a2a3"),
        evaluations=MoveEvaluations(eval_before=100, eval_after=-201),
        move_characteristics=mock_move_characteristics,
        top_engine_lines=[],
        settings=mock_settings,
        previous_move_context=None,
        time_spent_seconds=10.0
    )
    
    classifier = MoveClassifier()
    
    # Act
    result = classifier.classify_move(mock_context)
    
    # Assert
    assert result.classification == MoveClassification.BLUNDER
    assert result.centipawn_loss == 301
