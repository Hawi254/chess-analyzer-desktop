# chess_analysis_project/orchestration/game_processor.py
"""
Defines the `GameProcessor`, responsible for executing the analysis
pipeline for a single chess game.
"""

from typing import Any, Dict, List, TYPE_CHECKING
import asyncio

from chess_analyzer.orchestration.pipeline_stages import run_game_processing_pipeline
from chess_analyzer.types import GameContext, ProcessedGameResult, ProcessingStage

if TYPE_CHECKING:
    import chess.pgn
    from chess_analyzer.config.settings import RunConfig
    from chess_analyzer.services.engine_pool import EngineService
    from chess_analyzer.services.pgn_service import PgnService


class GameProcessor:
    """Orchestrates the sequential analysis pipeline for a single game."""

    def __init__(
        self,
        services: Dict[str, Any],
        config: "RunConfig",
        pipeline: List[ProcessingStage]
    ):
        """
        Initializes the GameProcessor.

        Args:
            services: A dictionary of application-wide services.
            config: The complete run configuration object.
            pipeline: A pre-constructed list of `ProcessingStage` objects.
        """
        self._services = services
        self._config = config
        self._pipeline = pipeline
        # --- The line `self._settings = settings` has been removed. ---

    async def process_game(self, game: "chess.pgn.Game", engine: "EngineService", shutdown_event: "asyncio.Event") -> ProcessedGameResult:
        """
        Executes the full analysis pipeline for a single game.
        """
        pgn_service: "PgnService" = self._services["pgn_service"]
        game_id = pgn_service._extract_game_id(game.headers)
        
        context = GameContext(
            game_id=game_id,
            raw_game=game,
            settings=self._config.analysis_settings,
            run_config=self._config,
            persistence_service=self._services["persistence_service"],
            engine_service=engine
        )
        
        final_context = await run_game_processing_pipeline(context, self._pipeline, shutdown_event)
        
        return ProcessedGameResult(
            annotated_game=final_context.annotated_game,
            summary=final_context.summary
        )