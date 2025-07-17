# chess_analysis_project/views/dashboard/opening_performance_model.py
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

class OpeningPerformanceModel(QAbstractTableModel):
    _HEADERS = ["Opening", "Played", "Score (%)", "Avg. CPL"]
    
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

        if role == Qt.DisplayRole:
            if col == 0: return row_data.get('opening_name')
            if col == 1: return row_data.get('games_played')
            if col == 2:
                wins = row_data.get('wins', 0)
                draws = row_data.get('draws', 0)
                total = row_data.get('games_played', 0)
                if total == 0: return "N/A"
                score = (wins + (0.5 * draws)) / total
                return f"{score:.0%}"
            if col == 3: return f"{row_data.get('average_cpl', 0):.1f}"
        return None
        
    def get_row_data(self, row):
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def load_data(self, data: list):
        self.beginResetModel()
        self._data = data
        self.endResetModel()