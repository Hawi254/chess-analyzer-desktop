# chess_analysis_project/views/game_report_view.py
"""
Defines the Game Report View widget.
"""
from PySide6.QtCore import QModelIndex, Qt, QSortFilterProxyModel, Signal
from PySide6.QtWidgets import (QAbstractItemView, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QTableView,
                               QVBoxLayout, QWidget)

from state.app_state import AppState
from views.game_report_model import GameReportModel


class GameReportView(QWidget):
    """UI for displaying the sortable/filterable table of game reports."""
    
    game_selected = Signal(str)

    def __init__(self, app_state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        
        self.game_report_model = GameReportModel(app_state)
        
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.game_report_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        self._create_widgets()
        self._create_layout()
        self._configure_widgets()
        self._connect_signals()

    def _create_widgets(self):
        self.filter_label = QLabel("Filter:")
        self.filter_input = QLineEdit()
        self.table_view = QTableView()

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        
        filter_group = QGroupBox("Game Report")
        filter_layout = QVBoxLayout(filter_group)
        
        hbox = QHBoxLayout()
        hbox.addWidget(self.filter_label)
        hbox.addWidget(self.filter_input)
        filter_layout.addLayout(hbox)
        filter_layout.addWidget(self.table_view)
        
        main_layout.addWidget(filter_group)

    def _configure_widgets(self):
        self.filter_input.setPlaceholderText("Filter by player, opening, etc...")
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    def _connect_signals(self):
        self.filter_input.textChanged.connect(self.proxy_model.setFilterRegularExpression)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)
    
    def _on_row_double_clicked(self, proxy_index: QModelIndex):
        """Handles the double-click event on a table row."""
        source_index = self.proxy_model.mapToSource(proxy_index)
        if not source_index.isValid():
            return
            
        # --- CORRECTED: Use the correct method name ---
        summary = self.game_report_model.get_summary_at_row(source_index.row())
        # ----------------------------------------------
        
        if summary:
            self.game_selected.emit(summary.game_id)