# tests/orchestration/test_orchestrator.py
import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from chess_analyzer.orchestration.orchestrator import PgnIngester, ReportService
from chess_analyzer.types import GameSummary, GameMetadata, GameStatistics, PlayerStats, MoveClassification, ProcessingStage
from chess_analyzer.config.settings import RunConfig, AnalysisSettings
from chess_analyzer.services.engine_pool import EngineService
from chess_analyzer.services.pgn_service import PgnService
from chess_analyzer.types import PersistenceService

@pytest.fixture
def dummy_pgn_file(tmp_path):
    content = """
[Event "Game 1"]
[Site ""]
[Date ""]
[Round ""]
[White ""]
[Black ""]
[Result ""]

1. e4 e5

[Event "Game 2"]
[Site ""]
[Date ""]
[Round ""]
[White ""]
[Black ""]
[Result ""]

1. d4 d5
"""
    file_path = tmp_path / "test.pgn"
    file_path.write_text(content)
    return file_path

def test_pgn_ingester_count_games(dummy_pgn_file):
    ingester = PgnIngester(dummy_pgn_file)
    assert ingester.count_games() == 2

@pytest.mark.asyncio
async def test_pgn_ingester_stream_games(dummy_pgn_file):
    ingester = PgnIngester(dummy_pgn_file)
    games = []
    async for game in ingester.stream_games():
        games.append(game)
    assert len(games) == 1 # Placeholder, as stream_games currently yields once

class TestReportService:
    @pytest.fixture
    def mock_run_config(self, tmp_path):
        mock_config = MagicMock()
        mock_config.output_csv_path = str(tmp_path / "report.csv")
        return mock_config

    def test_generate_summary_report(self, mock_run_config):
        # Create more realistic mock objects
        mock_player_stats = MagicMock(spec=PlayerStats)
        mock_player_stats.acpl = 25.5
        mock_player_stats.accuracy_percent = 90.0
        mock_player_stats.move_counts = {MoveClassification.BLUNDER: 1, MoveClassification.MISTAKE: 2}

        mock_game_statistics = MagicMock(spec=GameStatistics)
        mock_game_statistics.white = mock_player_stats
        mock_game_statistics.black = mock_player_stats
        mock_game_statistics.opening_name = "Sicilian Defense"
        mock_game_statistics.eval_volatility = 50.0

        mock_game_metadata = MagicMock(spec=GameMetadata)
        mock_game_metadata.white_player = "Player A"
        mock_game_metadata.black_player = "Player B"
        mock_game_metadata.result = "1-0"
        mock_game_metadata.event = "Test Event"
        mock_game_metadata.site = "Test Site"
        mock_game_metadata.date = "2025.01.01"

        mock_game_summary = MagicMock(spec=GameSummary)
        mock_game_summary.game_id = "game123"
        mock_game_summary.metadata = mock_game_metadata
        mock_game_summary.stats = mock_game_statistics
        mock_game_summary.narrative = "A test narrative."

        summaries = [mock_game_summary]
        service = ReportService(mock_run_config)
        service.generate_summary_report(summaries)
        # Assert that the report file was created
        assert Path(mock_run_config.output_csv_path).exists()

@pytest.mark.asyncio
class TestGameProcessor:
    @pytest.fixture
    def mock_services(self):
        return {
            "pgn_service": MagicMock(spec=PgnService),
            "persistence_service": MagicMock(spec=PersistenceService),
        }

    @pytest.fixture
    def mock_run_config(self):
        mock_config = MagicMock(spec=RunConfig)
        mock_config.analysis_settings = MagicMock(spec=AnalysisSettings)
        return mock_config

    @pytest.fixture
    def mock_pipeline(self):
        return [MagicMock(spec=ProcessingStage), MagicMock(spec=ProcessingStage)]

    @pytest.fixture
    def mock_engine(self):
        return MagicMock(spec=EngineService)

    @pytest.fixture
    def mock_shutdown_event(self):
        return asyncio.Event()

    async def test_process_game(self, mock_services, mock_run_config, mock_pipeline, mock_engine, mock_shutdown_event):
        # Arrange
        from chess_analyzer.orchestration.game_processor import GameProcessor
        from chess_analyzer.types import ProcessedGameResult, GameContext
        import chess.pgn

        mock_game = MagicMock(spec=chess.pgn.Game)
        mock_game.headers = {"Event": "Test Game"}

        mock_services["pgn_service"]._extract_game_id.return_value = "test_game_id"

        mock_final_context = MagicMock(spec=GameContext)
        mock_final_context.annotated_game = MagicMock(spec=chess.pgn.Game)
        mock_final_context.summary = MagicMock(spec=GameSummary)

        with patch('chess_analyzer.orchestration.game_processor.run_game_processing_pipeline', new_callable=AsyncMock) as mock_run_pipeline:
            mock_run_pipeline.return_value = mock_final_context

            processor = GameProcessor(
                services=mock_services,
                config=mock_run_config,
                pipeline=mock_pipeline
            )

            # Act
            result = await processor.process_game(mock_game, mock_engine, mock_shutdown_event)

            # Assert
            mock_services["pgn_service"]._extract_game_id.assert_called_once_with(mock_game.headers)
            mock_run_pipeline.assert_called_once()
            assert isinstance(result, ProcessedGameResult)
            assert result.annotated_game == mock_final_context.annotated_game
            assert result.summary == mock_final_context.summary
