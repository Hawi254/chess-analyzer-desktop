# chess_analysis_project/views/game_report_model.py
"""
Defines the Qt Table Model for displaying game summary reports.
"""
from typing import Any, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from chess_analyzer.types import GameSummary, ProcessedGameResult # GameSummary is still used for type checks
from state.app_state import AppState


class GameReportModel(QAbstractTableModel):
    """A table model that provides data from GameSummary objects to a QTableView."""
    
    _HEADERS = [
        "Game ID", "White", "Black", "Result", "Opening", "White Acc.", "Black Acc.",
        "W Blunders", "B Blunders"
    ]

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app_state = app_state
        self._results: List[ProcessedGameResult] = []
        
        # --- CORRECTED: Connect to the correct signal name ---
        self._app_state.results_updated.connect(self.refresh_data)
        # ---------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._results)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (summary := self._get_summary_for_index(index)):
            return None
        
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0: return summary.game_id
            if col == 1: return summary.metadata.white_player
            if col == 2: return summary.metadata.black_player
            if col == 3: return summary.metadata.result
            if col == 4: return summary.metadata.opening or "N/A"
            if col == 5: return f"{summary.stats.white.accuracy_percent}%" if summary.stats.white.accuracy_percent is not None else "N/A"
            if col == 6: return f"{summary.stats.black.accuracy_percent}%" if summary.stats.black.accuracy_percent is not None else "N/A"
            # In GameSummary, move_counts uses MoveClassification enums. The backend report generator uses strings.
            # We will assume the enums are available for robustness.
            from chess_analyzer.types import MoveClassification
            if col == 7: return summary.stats.white.move_counts.get(MoveClassification.BLUNDER, 0)
            if col == 8: return summary.stats.black.move_counts.get(MoveClassification.BLUNDER, 0)
        
        if role == Qt.ItemDataRole.ForegroundRole:
            if col in [7, 8] and self.data(index, Qt.ItemDataRole.DisplayRole) > 0:
                return QColor("red")

        return None
    
    def _get_summary_for_index(self, index: QModelIndex) -> Optional[GameSummary]:
        """Helper to safely get the summary from the result object."""
        if 0 <= index.row() < len(self._results):
            return self._results[index.row()].summary
        return None

    def get_summary_at_row(self, row: int) -> Optional[GameSummary]:
        """Safely gets the GameSummary object for a given model row."""
        if 0 <= row < len(self._results):
            return self._results[row].summary
        return None

    def refresh_data(self):
        """Resets the model with fresh data from the AppState."""
        self.beginResetModel()
        self._results = self._app_state.get_results()
        self.endResetModel()