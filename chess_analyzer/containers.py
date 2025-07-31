# chess_analyzer/containers.py
"""
Defines the Dependency Injection (DI) container for the application.

This module uses the `punq` library to manage the creation and wiring of
all services and components for the analysis pipeline. This centralizes the
application's dependency graph, making it more maintainable, testable,
and extensible.
"""

import punq

from chess_analyzer.config.settings import RunConfig
from chess_analyzer.core import (
    move_classifier, narrative_generator, pgn_parser
)
from chess_analyzer.orchestration.annotator_client import AnnotatorClient
from chess_analyzer.orchestration.game_processor import GameProcessor
from chess_analyzer.orchestration.game_processor_pool import GameProcessorPool
from chess_analyzer.orchestration.persistence_client import PersistenceClient
from chess_analyzer.orchestration.pipeline_factory import create_pipeline
from chess_analyzer.orchestration.pipeline_stages import (
    AnalysisStage, AnnotationStage, ClassificationStage, InitialSetupStage,
    PersistenceStage, SummaryStage
)
from chess_analyzer.services.analysis_provider import AnalysisProvider
from chess_analyzer.services.engine_pool import EnginePool
from chess_analyzer.services.pgn_service import PgnService
from chess_analyzer.services.sqlite_cache_service import SqliteCacheService
from chess_analyzer.services.stockfish_service import StockfishService
from chess_analyzer.persistence.training_data_service import TrainingDataService


def get_container(run_config: RunConfig, persistence_client: PersistenceClient) -> punq.Container:
    """
    Initializes and returns a DI container configured for a specific analysis run.
    """
    container = punq.Container()

    # Register instances that are created outside the container's control.
    container.register(RunConfig, instance=run_config)
    container.register(PersistenceClient, instance=persistence_client)

    # Register services and their dependencies. `punq` will automatically
    # inject dependencies based on type hints.
    container.register(TrainingDataService, factory=lambda: TrainingDataService(run_config.db_path))
    # Register SqliteCacheService as a singleton to ensure a single instance is shared.
    container.register(SqliteCacheService, factory=lambda: SqliteCacheService(run_config.cache_settings), scope=punq.Scope.singleton)

    # --- DEFINITIVE FIX: Register EnginePool as a single instance per container ---
    # This ensures the orchestrator and the game pool share the exact same pool object.
    container.register(
        EnginePool, factory=lambda: EnginePool(run_config.engine_pool_settings, StockfishService.create), scope=punq.Scope.singleton
    )
    container.register(AnalysisProvider, factory=lambda: AnalysisProvider(container.resolve(SqliteCacheService), run_config.analysis_settings))
    container.register(PgnService)
    container.register(AnnotatorClient)
    container.register(move_classifier.MoveClassifier)

    # Register pipeline stages
    container.register(InitialSetupStage, factory=lambda: InitialSetupStage(pgn_parser.parse_game_data))
    container.register(AnalysisStage, factory=lambda: AnalysisStage(container.resolve(AnalysisProvider)))
    container.register(ClassificationStage) # Depends on MoveClassifier and PersistenceClient
    container.register(PersistenceStage) # Depends on PersistenceClient
    container.register(SummaryStage, factory=lambda: SummaryStage(narrative_generator.generate_game_narrative, container.resolve(PersistenceClient)))
    container.register(AnnotationStage) # Depends on AnnotatorClient and PersistenceClient

    # Register the main processor and pool
    def create_game_processor() -> GameProcessor:
        # This dictionary bridges the gap between the DI container and the older
        # service-dictionary pattern used by the pipeline factory and processor.
        # A future refactor could involve making the pipeline stages and processor
        # directly injectable by the container.
        services = {
            "persistence_service": container.resolve(TrainingDataService),
            "pgn_parser_func": pgn_parser.parse_game_data,
            "analysis_provider": container.resolve(AnalysisProvider),
            "move_classifier": container.resolve(move_classifier.MoveClassifier),
            "persistence_client": container.resolve(PersistenceClient),
            "annotator_client": container.resolve(AnnotatorClient),
            "narrative_generator_func": narrative_generator.generate_game_narrative,
            "pgn_service": container.resolve(PgnService)
        }
        pipeline = create_pipeline(services)
        return GameProcessor(services, run_config, pipeline)

    container.register(GameProcessor, factory=create_game_processor)
    container.register(GameProcessorPool)

    return container