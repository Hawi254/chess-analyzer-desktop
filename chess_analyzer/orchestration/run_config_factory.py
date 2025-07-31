# chess_analyzer/orchestration/run_config_factory.py
"""
A factory for creating RunConfig objects from various sources.
"""
from pathlib import Path
from typing import Dict

from chess_analyzer.config.settings import (
    CacheSettings, EnginePoolSettings,
    EngineSettings, RunConfig, settings
)
from chess_analyzer.utils.system_utils import find_stockfish_executable


class RunConfigFactory:
    """A factory class to centralize the creation of RunConfig objects."""

    @staticmethod
    def create_from_ui(ui_config: Dict) -> RunConfig:
        """
        Creates a RunConfig object from the configuration provided by the UI.

        This method encapsulates the logic of determining file paths, finding
        the engine, and assembling the various settings objects.

        Args:
            ui_config: A dictionary of settings from the RunAnalysisView.

        Returns:
            A fully populated RunConfig object.
        """
        pgn_filepath = Path(ui_config["pgn_files"][0])
        stockfish_path = find_stockfish_executable(None)

        output_dir = pgn_filepath.parent
        base_name = pgn_filepath.stem
        output_pgn_path = output_dir / f"{base_name}_analyzed.pgn"
        output_csv_path = output_dir / f"{base_name}_report.csv"

        engine_settings = EngineSettings(path=str(stockfish_path), depth=ui_config["depth"], parameters={"Threads": 1, "Hash": 128, "MultiPV": ui_config["multipv"]})
        analysis_settings = settings.analysis_settings.model_copy(update={'depth': ui_config["depth"], 'multipv': ui_config["multipv"]})
        engine_pool_settings = EnginePoolSettings(pool_size=1, engine_config=engine_settings)
        cache_settings = CacheSettings(db_filepath=settings.default_cache_db_path)

        return RunConfig(input_pgn_path=str(pgn_filepath), output_pgn_path=str(output_pgn_path), output_csv_path=str(output_csv_path), db_path=settings.default_db_path, concurrency=1, max_retries=1, persistence_queue_size=1000, user_player_name=ui_config.get("user_player_name"), analysis_settings=analysis_settings, engine_pool_settings=engine_pool_settings, cache_settings=cache_settings)