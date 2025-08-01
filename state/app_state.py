# chess_analysis_project/state/app_state.py
"""
Defines the central state model for the application.
"""
from typing import Optional

import chess.pgn
from PySide6.QtCore import QObject, Signal
import structlog



class AppState(QObject):
    """Holds and manages shared application state."""
    
    logger = structlog.get_logger()

    results_updated = Signal()
    game_selected = Signal(str) # Emits game_id
    ply_selected = Signal(int) # Emits ply number

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # --- REWORKED: The AppState now only holds the *currently selected* game ---
        self._current_game: Optional[chess.pgn.Game] = None
        self._current_game_id: Optional[str] = None
        self._current_ply: int = 0

    # --- NEW: A simpler method to set the currently active game ---
    def set_current_game(self, game: chess.pgn.Game, initial_ply: int = 0):
        """Sets the currently active game and resets the state."""
        self._current_game = game
        self._current_game_id = game.headers.get("GameId", "unknown")
        self._current_ply = initial_ply
        # Emit signals to notify the UI that a new game is loaded and ready.
        self.game_selected.emit(self._current_game_id)
        self.ply_selected.emit(self._current_ply)

    def select_ply(self, ply: int):
        game = self.get_selected_game()
        if game:
            # Clamp ply to valid range
            # --- CORRECTED: Use mainline_moves() for accurate move count ---
            max_ply = len(list(game.mainline_moves()))
            self.logger.debug("AppState selecting ply", requested_ply=ply, max_ply=max_ply)
            self._current_ply = max(0, min(ply, max_ply))
            self.ply_selected.emit(self._current_ply)
            
    def get_selected_game(self) -> Optional[chess.pgn.Game]:
        return self._current_game

    def get_current_ply(self) -> int:
        return self._current_ply