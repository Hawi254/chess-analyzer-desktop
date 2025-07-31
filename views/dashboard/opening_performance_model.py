# chess_analysis_project/views/dashboard/opening_performance_model.py

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

class OpeningPerformanceModel(QAbstractTableModel):
    # --- FIX: Update headers to reflect the new data being displayed. ---
    _HEADERS = ["Opening", "Played", "Win %", "Avg. Accuracy"]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        row_data = self._data[index.row()]
        col = index.column()
        
        if col == 0:
            return row_data.get('opening_name', 'N/A') if role == Qt.DisplayRole else None
        elif col == 1:
            return row_data.get('games_played', 0) if role == Qt.DisplayRole else None
        elif col == 2: # "Win %"
            wins = row_data.get('wins', 0)
            total = row_data.get('games_played', 0)
            if total == 0: return 0.0
            win_pct = (wins / total) * 100
            if role == Qt.DisplayRole:
                return f"{win_pct:.1f}%"
            # --- FIX: Provide the raw numeric value for calculation roles. ---
            elif role == Qt.ItemDataRole.EditRole:
                return win_pct
        elif col == 3: # "Avg. Accuracy"
            accuracy = row_data.get('avg_accuracy')
            if accuracy is None: return "N/A"
            if role == Qt.DisplayRole:
                return f"{accuracy:.1f}%"
            # --- FIX: Provide the raw numeric value for calculation roles. ---
            elif role == Qt.ItemDataRole.EditRole:
                return accuracy
        
        return None
        
    def get_row_data(self, row):
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def load_data(self, data: list):
        """
        Loads new data into the model. Returns True if data was loaded,
        False otherwise. This fixes the primary bug.
        """
        # <<< FIX 1: This method now correctly returns True or False.
        self.beginResetModel()
        self._data = data or [] # Ensure _data is a list, not None
        self.endResetModel()
        return len(self._data) > 0