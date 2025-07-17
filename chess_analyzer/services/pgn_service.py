# chess_analyzer/services/pgn_service.py
"""
Provides a service for handling all filesystem interactions with PGN files.

This module acts as a stateless adapter to the filesystem for all things
related to PGN (Portable Game Notation). It encapsulates the I/O logic for
streaming games from a file, extracting game IDs from headers, and appending
annotated games to an output file. This keeps I/O-specific code isolated from
the main application orchestration.
"""

import asyncio
import re
from pathlib import Path
from typing import AsyncGenerator, List, Set, TextIO, Tuple

import aiofiles
import chess.pgn

from chess_analyzer.exceptions import PgnServiceError

class PgnService:
    """A stateless service for handling PGN file I/O operations."""

    # A declarative, data-driven list of patterns for game ID extraction.
    # The patterns are tried in order, prioritizing Lichess and Chess.com URLs.
    _GAME_ID_EXTRACTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
        ("Link", re.compile(r"lichess\.org/([a-zA-Z0-9]{8})")),
        ("Site", re.compile(r"lichess\.org/([a-zA-Z0-9]{8})")),
        ("Link", re.compile(r"chess\.com/game/live/(\d+)")),
        ("Site", re.compile(r"chess\.com/game/live/(\d+)")),
    ]

    @classmethod
    def _extract_game_id(cls, headers: chess.pgn.Headers) -> str:
        """
        Extracts a unique ID from a game's PGN headers.

        It prioritizes extracting IDs from game URLs (e.g., Lichess, Chess.com)
        found in "Link" or "Site" tags. If no URL is found, it falls back to a
        generated ID based on player names and the game date.

        Args:
            headers: The PGN headers for a single game.

        Returns:
            A string representing the unique ID for the game.
        """

        for tag_name, pattern in cls._GAME_ID_EXTRACTION_PATTERNS:
            if header_value := headers.get(tag_name):
                if match := pattern.search(str(header_value)):
                    prefix = "lichess" if "lichess" in str(header_value) else "chesscom"
                    return f"{prefix}_{match.group(1)}"

        # Fallback ID generation if no site URL is found.
        white = headers.get("White", "Unknown").replace(" ", "_")
        black = headers.get("Black", "Unknown").replace(" ", "_")
        date = headers.get("Date", "0000.00.00")
        return f"local_{white}_vs_{black}_{date}"

    def _sync_game_streamer(self, pgn_handle: TextIO) -> "Generator[chess.pgn.Game, None, None]":
        """
        A synchronous generator that yields games from an open file handle.
        
        This is a helper function designed to be run in a separate thread to
        avoid blocking the main asyncio event loop.
        """
        while True:
            try:
                # `chess.pgn.read_game` is a blocking I/O call.
                game = chess.pgn.read_game(pgn_handle)
                if game is None:
                    break # End of file
                yield game
            except (ValueError, RuntimeError):
                # Gracefully skip games that have fundamental format errors.
                continue

    def _get_processed_game_ids_sync(self, pgn_filepath: Path) -> Set[str]:
        """Synchronously scans a PGN file and extracts all game IDs using fast header reads."""
        processed_ids: Set[str] = set()
        try:
            with pgn_filepath.open("r", encoding="utf-8", errors="replace") as pgn_file:
                # `read_headers` is much faster than `read_game` as it doesn't parse the moves.
                while headers := chess.pgn.read_headers(pgn_file):
                    game_id = self._extract_game_id(headers)
                    processed_ids.add(game_id)
        except FileNotFoundError:
            return set()
        except (IOError, OSError) as e:
            raise PgnServiceError(f"Could not read PGN headers from {pgn_filepath}: {e}")
        return processed_ids

    async def get_processed_game_ids(self, pgn_filepath: Path) -> Set[str]:
        """
        Asynchronously scans a PGN file for all game IDs found within it.
        
        This is useful for skipping games that have already been processed in a previous run.
        """
        if not pgn_filepath.exists():
            return set()
        # Run the synchronous scanning function in a thread to avoid blocking.
        return await asyncio.to_thread(self._get_processed_game_ids_sync, pgn_filepath)

    async def stream_games(
        self, pgn_filepath: Path
    ) -> AsyncGenerator[chess.pgn.Game, None]:
        """
        Asynchronously streams games from a PGN file one by one.

        This approach is memory-efficient as it does not load the entire PGN
        file into memory. It uses `asyncio.to_thread` to run the blocking
        I/O operations of the `python-chess` library in a worker thread.

        Args:
            pgn_filepath: The path to the input PGN file.

        Yields:
            `chess.pgn.Game` objects as they are read from the file.
        
        Raises:
            PgnServiceError: If the file cannot be found or read.
        """
        def _get_next_game(generator):
            """Wrapper to catch StopIteration for use with `to_thread`."""
            try:
                return next(generator)
            except StopIteration:
                return None

        try:
            with pgn_filepath.open("r", encoding="utf-8", errors="replace") as pgn_handle:
                game_generator = self._sync_game_streamer(pgn_handle)
                while True:
                    # Offload the blocking `next(generator)` call to a thread.
                    game = await asyncio.to_thread(_get_next_game, game_generator)
                    if game is None:
                        break # Sentinel value indicates end of stream.
                    yield game
        except FileNotFoundError:
            raise PgnServiceError(f"Input PGN file not found: {pgn_filepath}")
        except Exception as e:
            raise PgnServiceError(f"Failed to stream games from {pgn_filepath}: {e}")

    async def export_annotated_game(
        self, game: chess.pgn.Game, output_filepath: Path
    ) -> None:
        """
        Appends a single, fully annotated game to the output PGN file.

        Uses `aiofiles` for non-blocking file I/O.

        Args:
            game: The processed `chess.pgn.Game` object with annotations.
            output_filepath: The path to the output PGN file.
            
        Raises:
            PgnServiceError: If the file cannot be written to.
        """
        try:
            # PGN standard requires two newlines between games.
            game_string = str(game) + "\n\n"
            async with aiofiles.open(output_filepath, "a", encoding="utf-8") as f:
                await f.write(game_string)
        except Exception as e:
            raise PgnServiceError(f"Failed to export game to {output_filepath}: {e}")