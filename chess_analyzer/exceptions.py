# chess_analyzer/exceptions.py
"""
Defines custom exceptions for the Chess Analyzer application.

Centralizing exceptions in this module prevents circular dependencies that can
arise when different components need to catch errors defined in others. A clear
exception hierarchy, with a common `ChessAnalyzerError` base, allows for flexible
and specific error handling throughout the application.
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from chess_analyzer.types import EngineService


class ChessAnalyzerError(Exception):
    """Base class for all application-specific, catchable errors."""
    pass


class EngineError(ChessAnalyzerError):
    """
    Base class for errors related to a chess engine subprocess.
    
    Attributes:
        engine: An optional reference to the failed engine service instance,
                allowing for targeted cleanup or replacement.
    """
    def __init__(self, message: str, engine: Optional["EngineService"] = None):
        super().__init__(message)
        self.engine = engine


class EngineInitializationError(EngineError):
    """
    Raised when a chess engine process fails to initialize correctly.

    This typically occurs if the executable path is invalid, file permissions
    are incorrect, or the engine process starts but fails to respond to initial
    UCI (Universal Chess Interface) commands.
    """
    pass


class EngineAnalysisError(EngineError):
    """
    Raised when an error occurs during the analysis of a position by an engine.

    This indicates that a previously healthy engine process has become unstable,
    produced unexpected output, or crashed during its analysis task. The engine
    instance is likely no longer usable.
    """
    pass


class CacheError(ChessAnalyzerError):
    """Base class for all cache-related errors."""
    pass


class CacheConnectionError(CacheError):
    """Raised when unable to connect to or initialize the cache database."""
    pass


class CacheReadError(CacheError):
    """Raised when an error occurs while reading from the cache database."""
    pass


class CacheWriteError(CacheError):
    """Raised when an error occurs while writing to the cache database."""
    pass


class PersistenceError(ChessAnalyzerError):
    """Base class for errors related to the training data persistence service."""
    pass


class PgnError(ChessAnalyzerError):
    """Base class for errors related to PGN (Portable Game Notation) handling."""
    pass


class PgnParsingError(PgnError):
    """

    Raised for game-level PGN integrity errors, such as illegal moves.
    
    This indicates a problem with the game record itself rather than a file
    I/O or format-level issue.
    """
    pass


class PgnServiceError(PgnError):
    """
    Raised for file I/O errors when reading from or writing to PGN files.
    
    This typically wraps lower-level exceptions like `FileNotFoundError` or `IOError`.
    """
    pass


class ReportGenerationError(ChessAnalyzerError):
    """Raised for errors encountered during the generation of final summary reports."""
    pass