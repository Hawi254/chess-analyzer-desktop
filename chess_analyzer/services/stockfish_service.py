# chess_analyzer/services/stockfish_service.py
"""
Provides a concrete implementation of the `EngineService` protocol for Stockfish.

This module acts as an adapter to a live Stockfish chess engine subprocess,
encapsulating the logic for initialization, communication, and analysis. It uses
the `python-stockfish` library to manage the engine process and translates its
output into the application's internal data contracts (`RawEngineLine`).
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

import chess
from stockfish import Stockfish, StockfishException

from chess_analyzer.exceptions import EngineAnalysisError, EngineInitializationError
from chess_analyzer.types import FEN, RawEngineLine, EngineService

if TYPE_CHECKING:
    from chess_analyzer.config.settings import EngineSettings


class StockfishService(EngineService):
    """
    A service that manages and interacts with a Stockfish chess engine subprocess.

    This class provides a thread-safe, asynchronous interface to the synchronous
    `python-stockfish` library by running its blocking calls in a separate
    thread pool via `asyncio.to_thread`.
    """

    def __init__(self, stockfish_instance: Stockfish, version: str, identifier: str):
        """
        Private constructor. Use the `create` class method for safe instantiation.
        
        Args:
            stockfish_instance: An initialized `stockfish.Stockfish` object.
            version: The major version of the Stockfish engine.
            identifier: A unique identifier for the engine executable path.
        """
        self._stockfish: Optional[Stockfish] = stockfish_instance
        self._version = version
        self._identifier = identifier
        self._lock = asyncio.Lock()  # Protects access to the single stockfish instance
        self._is_closed = False

    @classmethod
    def _create_sync(cls, settings: "EngineSettings") -> "StockfishService":
        """
        Synchronous part of the initialization, designed to be run in a thread.
        
        This method handles the blocking I/O of finding and starting the
        Stockfish subprocess.
        """
        stockfish_path = Path(settings.path)
        if not stockfish_path.is_file():
            raise EngineInitializationError(f"Stockfish executable not found at {stockfish_path}")
        
        try:
            stockfish = Stockfish(
                path=str(stockfish_path.resolve()),
                depth=settings.depth,
                parameters=settings.parameters
            )
            # A simple health check to ensure the engine is responsive.
            if not stockfish.is_fen_valid(chess.STARTING_FEN):
                raise EngineInitializationError("Stockfish process started but FEN validation failed.")
            
            version = str(stockfish.get_stockfish_major_version())
            identifier = str(stockfish_path.resolve())
            return cls(stockfish, version, identifier)
        except StockfishException as e:
            raise EngineInitializationError(f"Failed to initialize Stockfish: {e}") from e

    @classmethod
    async def create(cls, settings: "EngineSettings") -> "StockfishService":
        """Asynchronously creates and initializes a StockfishService instance."""
        return await asyncio.to_thread(cls._create_sync, settings)

    def _ensure_engine_ready(self) -> Stockfish:
        """Raises an error if the service is closed or the engine has crashed."""
        if self._is_closed or self._stockfish is None:
            raise EngineAnalysisError("StockfishService is closed or the engine has failed.", engine=self)
        return self._stockfish
    
    def _parse_stockfish_output(self, top_moves: List[Dict]) -> List[RawEngineLine]:
        """Converts the raw dict output from the library into our internal `RawEngineLine` dataclass."""
        lines = []
        for i, move in enumerate(top_moves):
            # The 'PV' from the library is a list of subsequent moves.
            pv = [move.get("Move")] + move.get("PV", [])
            lines.append(
                RawEngineLine(
                    rank=i + 1,
                    score_cp=move.get("Centipawn"),
                    score_mate=move.get("Mate"),
                    pv=[m for m in pv if m], # Filter out potential None values
                )
            )
        return lines

    def _analyze_batch_sync(self, fens: List[FEN]) -> Dict[FEN, List[RawEngineLine]]:
        """Synchronous batch analysis logic, designed to be run in a thread."""
        stockfish = self._ensure_engine_ready()
        results: Dict[FEN, List[RawEngineLine]] = {}
        num_moves = stockfish.get_parameters().get("MultiPV", 1)

        try:
            for fen in fens:
                stockfish.set_fen_position(fen)
                top_moves_raw = stockfish.get_top_moves(num_moves)
                results[fen] = self._parse_stockfish_output(top_moves_raw)
        except StockfishException as e:
            # If the engine crashes mid-analysis, we mark it as unusable.
            self._stockfish = None
            raise EngineAnalysisError("Stockfish process crashed during analysis.", engine=self) from e
        
        return results

    async def analyze_fens_batch(self, fens: List[FEN]) -> Dict[FEN, List[RawEngineLine]]:
        """
        Analyzes a batch of FENs by running the sync logic in a separate thread.
        
        The internal lock ensures that only one analysis batch can be run on this
        engine instance at a time.
        """
        async with self._lock:
            return await asyncio.to_thread(self._analyze_batch_sync, fens)

    async def get_engine_identifier(self) -> str:
        """Returns a unique identifier for this engine configuration, used for caching."""
        return f"{self._identifier}_{self._version}"

    def _is_healthy_sync(self) -> bool:
        """Synchronous health check logic."""
        try:
            stockfish = self._ensure_engine_ready()
            return stockfish.is_fen_valid(chess.STARTING_FEN)
        except EngineAnalysisError:
            return False

    async def is_healthy(self) -> bool:
        """Checks if the Stockfish engine process is responsive."""
        if self._is_closed:
            return False
        return await asyncio.to_thread(self._is_healthy_sync)

    def _close_sync(self) -> None:
        """Synchronous helper to explicitly quit the engine subprocess."""
        if self._stockfish and self._stockfish.is_engine_running():
            self._stockfish.quit()
        self._stockfish = None

    async def close(self) -> None:
        """Gracefully terminates the Stockfish engine subprocess."""
        if self._is_closed:
            return
        self._is_closed = True
        await asyncio.to_thread(self._close_sync)