# chess_analyzer/config/settings.py
"""
Configuration settings for the Chess Analyzer application, powered by Pydantic.

This module centralizes all tunable parameters, default values, and configuration
schemas. Using Pydantic allows for type-safe, self-documenting configuration
that can be loaded from environment variables, providing a clear separation of
configuration from code.
"""
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Nested Models for Configuration Schemas ---
# These models create a hierarchical and organized structure for settings,
# making them easier to manage and understand.

class ClassificationThresholdsModel(BaseModel):
    """
    Defines the Centipawn Loss (CPL) thresholds for move classification.

    The CPL values represent the loss in evaluation compared to the engine's
    best move. A lower CPL indicates a better move.
    """
    best_move: int = Field(5, description="Maximum CPL for a move to be classified as 'Best'.")
    good_move: int = Field(40, description="Maximum CPL for a move to be classified as 'Good'.")
    dubious_move: int = Field(80, description="Maximum CPL for a move to be classified as 'Dubious'.")
    inaccuracy: int = Field(150, description="Maximum CPL for a move to be classified as 'Inaccuracy'.")
    mistake: int = Field(300, description="Maximum CPL for a move to be classified as 'Mistake'.")
    # A move with CPL > mistake threshold is implicitly classified as a 'Blunder'.

    @model_validator(mode='after')
    def validate_thresholds_are_sorted(self) -> 'ClassificationThresholdsModel':
        """Ensures that CPL thresholds are logically sorted in ascending order."""
        values = [self.best_move, self.good_move, self.dubious_move, self.inaccuracy, self.mistake]
        if not all(values[i] <= values[i + 1] for i in range(len(values) - 1)):
            raise ValueError("Configuration error: Classification CPL thresholds must be sorted.")
        return self

class BrilliantMoveCriteriaModel(BaseModel):
    """Defines the criteria for a move to be classified as 'Brilliant' (!!)."""
    max_cpl_for_brilliance: float = Field(10.0, description="A move's CPL cannot exceed this to be considered for brilliance.")
    sacrifice_threshold_cp: float = Field(-150.0, description="A move must result in a material loss of at least this much to be a candidate for brilliance.")
    min_position_eval_cp: float = Field(-200.0, description="The position must not be losing by more than this value before the move is made.")
    max_rank: int = Field(3, description="The move must appear within this rank in the engine's list of top moves.")

class GreatMoveCriteriaModel(BaseModel):
    """Defines the criteria for a move to be classified as a 'Great Move' (!)."""
    only_good_move_threshold_cp: float = Field(150.0, description="Minimum CPL difference between the best move and the second-best move to be considered a great 'only move'.")
    saved_position_min_eval_cp: float = Field(-300.0, description="The minimum evaluation for a position to be considered 'losing' enough to be saved.")
    saved_position_recovery_eval_cp: float = Field(-150.0, description="The evaluation after the move must recover to at least this value to qualify as saving the position.")
    draw_range_min: int = Field(-100, description="Minimum evaluation for a position to be considered 'drawable'.")
    draw_range_max: int = Field(100, description="Maximum evaluation for a position to be considered 'drawable'.")
    win_threshold_cp: float = Field(200.0, description="The evaluation after the move must be at least this value to be considered converting a draw to a win.")
    trivial_recapture_threshold: int = Field(50, description="Recaptures where the material swing is less than this value (in centipawns) are considered trivial and not 'Great'.")

class AccuracyConstantsModel(BaseModel):
    """Constants used in the formula to convert ACPL to a Lichess-style accuracy percentage."""
    const_a: float = 103.1668
    const_b: float = -0.004354
    const_c: float = -3.1668

class NarrativeSettingsModel(BaseModel):
    """Encapsulates all thresholds for generating game narrative archetypes."""
    min_stddev_for_slugfest: float = Field(150.0, description="Minimum CPL standard deviation for a game to be a 'tactical slugfest'.")
    min_blunders_for_slugfest: int = Field(2, description="Minimum combined blunders for a game to be a 'tactical slugfest'.")
    blunder_count_for_decisive: int = Field(1, description="Exact number of combined blunders for a game to be a 'decisive moment' story.")
    max_acpl_for_positional: float = Field(25.0, description="Maximum ACPL for both players for a game to be a 'positional squeeze'.")

class GamePhaserSettingsModel(BaseModel):
    """Encapsulates thresholds for determining the phase of a chess game."""
    opening_max_fullmoves: int = Field(12, description="Moves at or before this fullmove number are considered 'Opening'.")
    endgame_max_piece_count: int = Field(7, description="If total major/minor pieces are at or below this count, the game is in the 'Endgame'.")

class AnalysisSettings(BaseModel):
    """Groups all settings related to the core chess analysis logic."""
    depth: int = Field(11, description="The search depth for the chess engine.")
    multipv: int = Field(3, description="The number of principal variations the engine should find.")
    mate_score_equivalent_cp: int = Field(10000, description="The centipawn value assigned to a forced mate, used for CPL calculations.")
    
    classification_thresholds: ClassificationThresholdsModel = Field(default_factory=ClassificationThresholdsModel)
    brilliant_move: BrilliantMoveCriteriaModel = Field(default_factory=BrilliantMoveCriteriaModel)
    great_move: GreatMoveCriteriaModel = Field(default_factory=GreatMoveCriteriaModel)
    accuracy: AccuracyConstantsModel = Field(default_factory=AccuracyConstantsModel)
    narrative: NarrativeSettingsModel = Field(default_factory=NarrativeSettingsModel)
    phaser: GamePhaserSettingsModel = Field(default_factory=GamePhaserSettingsModel)
    
    absolute_losing_threshold_cp: int = Field(-800, description="Positions with an evaluation at or below this are considered definitively lost.")

class EngineSettings(BaseModel):
    """Configuration for a single chess engine instance."""
    path: str = Field(description="The file path to the Stockfish executable.")
    depth: int = Field(description="The default search depth for this engine.")
    parameters: dict = Field(default_factory=dict, description="A dictionary of UCI parameters to set on engine startup (e.g., {'Threads': 4, 'Hash': 1024}).")

class EnginePoolSettings(BaseModel):
    """Configuration for the pool of chess engine instances."""
    pool_size: int = Field(description="The number of concurrent engine instances to maintain.")
    engine_config: EngineSettings

class CacheSettings(BaseModel):
    """Configuration for the analysis results cache."""
    db_filepath: str = Field(description="The file path for the SQLite cache database.")


class RunConfig(BaseModel):
    """
    Encapsulates all configuration for a single, complete application run.
    
    This object is typically constructed at application startup from command-line
    arguments and the main settings.
    """
    input_pgn_path: str
    output_pgn_path: str
    output_csv_path: str
    db_path: str
    concurrency: int
    max_retries: int
    persistence_queue_size: int
    analysis_settings: AnalysisSettings
    engine_pool_settings: EnginePoolSettings
    cache_settings: CacheSettings
    user_player_name: Optional[str] = None # Add the new field
    analysis_settings: AnalysisSettings

# --- Main Application Settings Class ---

class Settings(BaseSettings):
    """
    Main configuration class for the application.
    
    It loads settings from environment variables with the prefix 'CHESS_ANALYZER_'.
    Nested models can be configured using a double underscore delimiter, e.g.,
    `CHESS_ANALYZER_ANALYSIS__DEPTH=15`.
    """
    model_config = SettingsConfigDict(env_prefix='CHESS_ANALYZER_', env_nested_delimiter='__')
    
    analysis_settings: AnalysisSettings = Field(default_factory=AnalysisSettings)
    default_db_path: str = "data/training_data.db"
    default_cache_db_path: str = "data/cache.db"
    default_csv_report_path: str = "data/analysis_report.csv"
    default_log_level: str = "INFO"

# A singleton instance of the settings, accessible throughout the application.
settings = Settings()

# Rebuild models that use forward references to ensure they are resolved.
# This is a Pydantic v2 feature that finalizes model schemas.
RunConfig.model_rebuild()