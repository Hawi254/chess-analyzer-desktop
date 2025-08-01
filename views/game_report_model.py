# chess_analysis_project/views/game_report_model.py
"""
Defines the Qt Table Model for displaying game summary reports.
"""
from typing import Any, Dict, List, Optional

# --- MODIFIED: Added Signal for asynchronous data requests ---
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from chess_analyzer.types import (
    GameMetadata, GameReportRow, GameSummary, GameStatistics,
    MoveClassification, PlayerStats, ProcessedGameResult
)
from state.app_state import AppState


class GameReportModel(QAbstractTableModel):
    """
    A virtual, lazy-loading table model that provides data from GameSummary
    objects to a QTableView, fetching data on demand.
    """
    
    # --- NEW: Custom signal to request more data from the controller ---
    # Emits the offset and limit for the next data chunk required.
    more_data_requested = Signal(dict, int, int)

    _HEADERS = [
        "Game ID", "White", "Black", "Result", "Opening", "White Acc.", "Black Acc.",
        "W Blunders", "B Blunders"
    ]
    FETCH_BATCH_SIZE = 50  # The number of items to fetch per request

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app_state = app_state
        # --- MODIFIED: Internal storage changed for lazy loading ---
        self._total_row_count: int = 0
        self._game_data_cache: List[ProcessedGameResult] = []
        self._current_filters: Dict = {}
        
        # --- REMOVED: The 'results_updated' signal is no longer used directly. ---
        # The controller will now drive updates by calling public methods on this
        # model, like `begin_new_report` and `append_data`.

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        # --- MODIFIED: Return the total count of records, not just the cached count ---
        return self._total_row_count

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        # --- MODIFIED: Now fetches from the cache; returns None if data is not yet loaded ---
        if not index.isValid() or not (summary := self._get_summary_for_index(index)):
            return None
        
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return summary.game_id
            if col == 1:
                return summary.metadata.white_player
            if col == 2:
                return summary.metadata.black_player
            if col == 3:
                return summary.metadata.result
            if col == 4:
                return summary.metadata.opening or "N/A"
            if col == 5:
                return f"{summary.stats.white.accuracy_percent}%" if summary.stats.white.accuracy_percent is not None else "N/A"
            if col == 6:
                return f"{summary.stats.black.accuracy_percent}%" if summary.stats.black.accuracy_percent is not None else "N/A"
            from chess_analyzer.types import MoveClassification
            if col == 7:
                return summary.stats.white.move_counts.get(MoveClassification.BLUNDER, 0)
            if col == 8:
                return summary.stats.black.move_counts.get(MoveClassification.BLUNDER, 0)
        
        if role == Qt.ItemDataRole.ForegroundRole:
            if col in [7, 8] and self.data(index, Qt.ItemDataRole.DisplayRole) > 0:
                return QColor("red")

        return None

    # --- IMPLEMENTED: Built-in Qt method for lazy loading ---
    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        """Returns true if the number of cached items is less than the total row count."""
        if parent.isValid():
            return False
        return len(self._game_data_cache) < self._total_row_count

    # --- IMPLEMENTED: Built-in Qt method for lazy loading ---
    def fetchMore(self, parent: QModelIndex = QModelIndex()):
        """
        Called by the view when more data is required. Emits a signal to
        delegate the actual data fetching to the controller.
        """
        if parent.isValid():
            return

        offset = len(self._game_data_cache)
        remaining = self._total_row_count - offset
        if remaining <= 0:
            return
            
        limit = min(self.FETCH_BATCH_SIZE, remaining)
        self.more_data_requested.emit(self._current_filters, offset, limit)
    
    def _get_summary_for_index(self, index: QModelIndex) -> Optional[GameSummary]:
        """Helper to safely get the summary from the result object in the cache."""
        # --- MODIFIED: Accesses the cache instead of the full results list ---
        if 0 <= index.row() < len(self._game_data_cache):
            return self._game_data_cache[index.row()].summary
        return None

    def get_summary_at_row(self, row: int) -> Optional[GameSummary]:
        """Safely gets the GameSummary object for a given model row from the cache."""
        # --- MODIFIED: Accesses the cache instead of the full results list ---
        if 0 <= row < len(self._game_data_cache):
            return self._game_data_cache[row].summary
        return None

    # --- RE-ARCHITECTED: Public API for controller interaction replaces refresh_data ---
    def begin_new_report(self, total_count: int, filters: dict):
        """
        Resets the model for a new report, specifying the total number of items.
        This clears the cache and prepares the model for lazy loading.
        """
        self.beginResetModel()
        self._game_data_cache.clear()
        self._total_row_count = total_count
        self._current_filters = filters
        self.endResetModel()

    def append_data(self, raw_data: List[GameReportRow]):
        """
        Appends a chunk of fetched data to the model's cache. This method
        should be called by the controller after it fetches data in response
        to the 'more_data_requested' signal.
        """
        if not raw_data:
            return

        transformed_data = self._transform_db_rows_to_results(raw_data)

        start_row = len(self._game_data_cache)
        end_row = start_row + len(transformed_data) - 1

        self.beginInsertRows(QModelIndex(), start_row, end_row)
        self._game_data_cache.extend(transformed_data)
        self.endInsertRows()

        # --- NEW: Data transformation and relaying slots ---
    def _transform_db_rows_to_results(self, rows: List[GameReportRow]) -> List[ProcessedGameResult]:
        """Transforms flat database rows into structured ProcessedGameResult objects."""
        results = []
        for row in rows:
            metadata = GameMetadata(
                white_player=row.white_player or 'N/A',
                black_player=row.black_player or 'N/A',
                result=row.result or '*',
                event="Database Game", site="N/A",
                date=row.game_date or '????.??.??',
                opening=row.opening_name,
                time=None, eco=None
            )
            white_stats = PlayerStats(
                acpl=None,
                accuracy_percent=row.white_accuracy,
                move_counts={MoveClassification.BLUNDER: row.white_blunders}
            )
            black_stats = PlayerStats(
                acpl=None,
                accuracy_percent=row.black_accuracy,
                move_counts={MoveClassification.BLUNDER: row.black_blunders}
            )
            stats = GameStatistics(white=white_stats, black=black_stats)
            summary = GameSummary(game_id=row.game_id, metadata=metadata, stats=stats)
            results.append(ProcessedGameResult(annotated_game=None, summary=summary))
        return results
