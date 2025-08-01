# tests/orchestration/test_pipeline_stages.py
import pytest
from unittest.mock import MagicMock, AsyncMock
import chess.pgn

from chess_analyzer.orchestration.pipeline_stages import InitialSetupStage, AnalysisStage, ClassificationStage, PersistenceStage
from chess_analyzer.types import GameContext, ParsedGame, GameMetadata, PersistenceService, GameSlice, EnrichedAnalysis, QueuedStatUpdate, QueuedMove, MoveClassification
from chess_analyzer.services.analysis_provider import AnalysisProvider
from chess_analyzer.services.engine_pool import EngineService
from chess_analyzer.core.move_classifier import MoveClassifier
from chess_analyzer.orchestration.persistence_client import PersistenceClient
from chess_analyzer.config.settings import AnalysisSettings

@pytest.mark.asyncio
async def test_initial_setup_stage():
    # Arrange
    mock_raw_game = MagicMock(spec=chess.pgn.Game)
    mock_raw_game.headers = {"Event": "Test Game"}

    mock_parsed_game = ParsedGame(
        metadata=GameMetadata(
            white_player="Player A", black_player="Player B",
            result="1-0", event="Test Game", site="Test Site", date="2025.01.01"
        ),
        slices=[],
        unique_fens=[]
    )

    mock_pgn_parser_func = MagicMock(return_value=mock_parsed_game)
    stage = InitialSetupStage(pgn_parser_func=mock_pgn_parser_func)

    context = GameContext(
        game_id="test_game",
        raw_game=mock_raw_game,
        settings=MagicMock(),
        run_config=MagicMock(),
        persistence_service=MagicMock()
    )

    # Act
    result_context = await stage.execute(context)

    # Assert
    mock_pgn_parser_func.assert_called_once_with(mock_raw_game)
    assert result_context.parsed_game == mock_parsed_game

@pytest.mark.asyncio
async def test_analysis_stage():
    # Arrange
    mock_analysis_provider = MagicMock(spec=AnalysisProvider)
    mock_persistence_service = MagicMock(spec=PersistenceService)
    mock_engine_service = MagicMock(spec=EngineService)

    mock_parsed_game = ParsedGame(
        metadata=GameMetadata(
            white_player="Player A", black_player="Player B",
            result="1-0", event="Test Game", site="Test Site", date="2025.01.01"
        ),
        slices=[],
        unique_fens=["fen1", "fen2"]
    )

    mock_analysis_results = {"fen1": MagicMock(), "fen2": MagicMock()}
    mock_position_stats = {"fen1": MagicMock(), "fen2": MagicMock()}

    mock_analysis_provider.get_analyses_for_fens.return_value = mock_analysis_results
    mock_persistence_service.get_position_stats_batch.return_value = mock_position_stats

    stage = AnalysisStage(provider=mock_analysis_provider)

    context = GameContext(
        game_id="test_game",
        raw_game=MagicMock(),
        settings=MagicMock(),
        run_config=MagicMock(),
        persistence_service=mock_persistence_service,
        engine_service=mock_engine_service,
        parsed_game=mock_parsed_game
    )

    # Act
    result_context = await stage.execute(context)

    # Assert
    mock_analysis_provider.get_analyses_for_fens.assert_called_once_with(mock_parsed_game.unique_fens, mock_engine_service)
    mock_persistence_service.get_position_stats_batch.assert_called_once_with(mock_parsed_game.unique_fens)
    assert result_context.analysis_results == mock_analysis_results
    assert result_context.position_stats == mock_position_stats

@pytest.mark.asyncio
async def test_classification_stage_time_calculation():
    # Arrange
    mock_classifier = MagicMock(spec=MoveClassifier)
    mock_persistence_client = MagicMock(spec=PersistenceClient)

    # Mock a raw game with TimeControl and CLK tags
    mock_raw_game = MagicMock(spec=chess.pgn.Game)
    mock_raw_game.headers = {"TimeControl": "300+5"}

    # Create mock PGN nodes with CLK comments
    node1 = MagicMock(spec=chess.pgn.GameNode)
    node1.comment = "{ [%clk 0:04:55] }"
    node2 = MagicMock(spec=chess.pgn.GameNode)
    node2.comment = "{ [%clk 0:04:40] }"
    node3 = MagicMock(spec=chess.pgn.GameNode)
    node3.comment = "{ [%clk 0:04:30] }"

    # Create mock GameSlices
    slice1 = MagicMock(spec=GameSlice)
    slice1.fen_before = "rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"
    slice1.move = chess.Move.from_uci("e2e4")
    slice1.player_color = 'w'
    slice1.pgn_node = node1

    slice2 = MagicMock(spec=GameSlice)
    slice2.fen_before = "rnbqkbnr/pppp1ppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    slice2.move = chess.Move.from_uci("e7e5")
    slice2.player_color = 'b'
    slice2.pgn_node = node2

    slice3 = MagicMock(spec=GameSlice)
    slice3.fen_before = "rnbqkbnr/pppp1ppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"
    slice3.move = chess.Move.from_uci("g1f3")
    slice3.player_color = 'w'
    slice3.pgn_node = node3

    mock_parsed_game = ParsedGame(
        metadata=MagicMock(),
        slices=[slice1, slice2, slice3],
        unique_fens=[]
    )

    mock_settings = MagicMock(spec=AnalysisSettings)
    mock_settings.mate_score_equivalent_cp = 10000 # Needed for interpret_engine_score

    context = GameContext(
        game_id="test_game",
        raw_game=mock_raw_game,
        settings=mock_settings,
        run_config=MagicMock(),
        persistence_service=MagicMock(),
        parsed_game=mock_parsed_game,
        analysis_results={
            # FENs before moves
            "rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1": MagicMock(top_engine_lines=[MagicMock(score_cp=100)]),
            "rnbqkbnr/pppp1ppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1": MagicMock(top_engine_lines=[MagicMock(score_cp=100)]),
            "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2": MagicMock(top_engine_lines=[MagicMock(score_cp=100)]),
            # FENs after moves (no repeated keys)
            "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 0 2": MagicMock(top_engine_lines=[MagicMock(score_cp=100)]),
        }
    )

    stage = ClassificationStage(classifier=mock_classifier, client=mock_persistence_client)

    # Act
    result_context = await stage.execute(context)

    # Assert
    # Check that time_spent_seconds was correctly calculated for each move
    assert result_context.enriched_analyses[0].classification.time_spent_seconds == 10.0 # 300 - 295 + 5
    assert result_context.enriched_analyses[1].classification.time_spent_seconds == 20.0 # 295 - 280 + 5
    assert result_context.enriched_analyses[2].classification.time_spent_seconds == 15.0 # 280 - 270 + 5

@pytest.mark.asyncio
async def test_persistence_stage():
    # Arrange
    mock_persistence_client = MagicMock(spec=PersistenceClient)
    mock_persistence_client.queue_item = AsyncMock()

    # Create mock GameContext with some data
    mock_parsed_game = ParsedGame(
        metadata=MagicMock(),
        slices=[
            MagicMock(spec=GameSlice, fen_before="fen1", move=chess.Move.from_uci("e2e4"), player_color='w', move_number=1),
            MagicMock(spec=GameSlice, fen_before="fen2", move=chess.Move.from_uci("e7e5"), player_color='b', move_number=1),
        ],
        unique_fens=[]
    )

    mock_enriched_analysis_1 = MagicMock(spec=EnrichedAnalysis)
    mock_enriched_analysis_1.classification.centipawn_loss = 10
    mock_enriched_analysis_1.classification.classification = MoveClassification.GOOD_MOVE
    mock_enriched_analysis_1.classification.time_spent_seconds = 10.0
    mock_enriched_analysis_1.classification.is_reciprocal_blunder = False
    mock_enriched_analysis_1.formatted_engine_lines = [MagicMock(move_san="e2e4")]
    mock_enriched_analysis_1.game_phase = "Opening"

    mock_enriched_analysis_2 = MagicMock(spec=EnrichedAnalysis)
    mock_enriched_analysis_2.classification.centipawn_loss = 20
    mock_enriched_analysis_2.classification.classification = MoveClassification.INACCURACY
    mock_enriched_analysis_2.classification.time_spent_seconds = 20.0
    mock_enriched_analysis_2.classification.is_reciprocal_blunder = False
    mock_enriched_analysis_2.formatted_engine_lines = [MagicMock(move_san="e7e5")]
    mock_enriched_analysis_2.game_phase = "Opening"

    context = GameContext(
        game_id="test_game_id",
        parsed_game=mock_parsed_game,
        stat_updates=[{"fen": "fen1", "updates": "stat_update_1"}, {"fen": "fen2", "updates": "stat_update_2"}],
        enriched_analyses=[mock_enriched_analysis_1, mock_enriched_analysis_2],
        move_evaluations=[
            MagicMock(eval_after=100),
            MagicMock(eval_after=200),
        ]
    )

    stage = PersistenceStage(client=mock_persistence_client)

    # Act
    result_context = await stage.execute(context)

    # Assert
    assert result_context == context
    assert mock_persistence_client.queue_item.call_count == 4 # 2 stat updates + 2 moves

    # Verify stat updates are queued
    mock_persistence_client.queue_item.assert_any_call(QueuedStatUpdate(game_id="test_game_id", stats_payload={"fen": "fen1", "updates": "stat_update_1"}))
    mock_persistence_client.queue_item.assert_any_call(QueuedStatUpdate(game_id="test_game_id", stats_payload={"fen": "fen2", "updates": "stat_update_2"}))

    # Verify moves are queued (check some key fields)
    # Note: The exact structure of QueuedMove.move_payload needs to match the implementation
    # This is a simplified check.
    mock_persistence_client.queue_item.assert_any_call(QueuedMove(move_payload={
        'game_id': 'test_game_id',
        'fen': 'fen1',
        'ply': 0,
        'move_uci': 'e2e4',
        'move_san': 'e4',
        'line_san': '1. e4',
        'cpl': 10,
        'classification': 'Good Move',
        'time_spent_seconds': 10.0,
        'is_reciprocal_blunder': False,
        'best_move_san': 'e2e4',
        'post_move_eval': 100,
        'game_phase': 'Opening'
    }))
    mock_persistence_client.queue_item.assert_any_call(QueuedMove(move_payload={
        'game_id': 'test_game_id',
        'fen': 'fen2',
        'ply': 1,
        'move_uci': 'e7e5',
        'move_san': 'e5',
        'line_san': '1. e4 e5',
        'cpl': 20,
        'classification': 'Inaccuracy',
        'time_spent_seconds': 20.0,
        'is_reciprocal_blunder': False,
        'best_move_san': 'e7e5',
        'post_move_eval': 200,
        'game_phase': 'Opening'
    }))
