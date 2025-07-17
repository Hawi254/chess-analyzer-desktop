# chess_analyzer/utils/system_utils.py
"""
Provides generic, system-level utility functions.
"""
import os
import shutil
from pathlib import Path
from typing import Optional

def find_stockfish_executable(provided_path: Optional[str] = None) -> Path:
    """
    Finds a valid Stockfish executable, raising FileNotFoundError if unsuccessful.

    The search is performed in the following order of precedence:
    1. The path provided via the `provided_path` argument.
    2. The path specified in the `STOCKFISH_PATH` environment variable.
    3. The system's `PATH` environment variable (using `shutil.which`).

    Returns:
        A `pathlib.Path` object to the resolved executable.

    Raises:
        FileNotFoundError: If no Stockfish executable can be found.
    """
    search_paths = []
    if provided_path:
        search_paths.append(Path(provided_path))
    if 'STOCKFISH_PATH' in os.environ:
        search_paths.append(Path(os.environ['STOCKFISH_PATH']))

    for path in search_paths:
        if path.is_file() and os.access(path, os.X_OK):
            return path.resolve()

    if system_path := shutil.which('stockfish'):
        return Path(system_path)

    raise FileNotFoundError(
        "Stockfish executable not found. Please install it, set the STOCKFISH_PATH "
        "environment variable, or use the --stockfish-path argument."
    )