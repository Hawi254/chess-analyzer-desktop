# chess_analysis_project/state/app_state.py
"""
Defines the central state model for the application.
"""
from typing import Dict, List, Optional

import chess.pgn
from PySide6.QtCore import QObject, Signal

from chess_analyzer.types import ProcessedGameResult


class AppState(QObject):
    """Holds and manages shared application state."""
    
    results_updated = Signal()
    game_selected = Signal(str) # Emits game_id
    ply_selected = Signal(int) # Emits ply number

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._results: List[ProcessedGameResult] = []
        self._annotated_games: Dict[str, chess.pgn.Game] = {}
        self._current_game_id: Optional[str] = None
        self._current_ply: int = 0

    def set_results(self, results: List[ProcessedGameResult]):
        """Updates the analysis results and emits a signal."""
        self._results = results
        self._annotated_games = {
            res.summary.game_id: res.annotated_game 
            for res in results if res.summary and res.annotated_game
        }
        self.results_updated.emit()

    def get_results(self) -> List[ProcessedGameResult]:
        return self._results
        
    def select_game(self, game_id: str):
        if game_id in self._annotated_games:
            self._current_game_id = game_id
            self._current_ply = 0
            self.game_selected.emit(game_id)
            self.ply_selected.emit(self._current_ply)

    def select_ply(self, ply: int):
        game = self.get_selected_game()
        if game:
            # Clamp ply to valid range
            max_ply = len(list(game.mainline()))
            self._current_ply = max(0, min(ply, max_ply))
            self.ply_selected.emit(self._current_ply)
            
    def get_selected_game(self) -> Optional[chess.pgn.Game]:
        if self._current_game_id:
            return self._annotated_games.get(self._current_game_id)
        return None

    def get_current_ply(self) -> int:
        return self._current_ply