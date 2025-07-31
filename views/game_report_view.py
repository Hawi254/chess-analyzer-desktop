# chess_analysis_project/views/game_report_view.py
"""
Defines the Game Report View widget.
"""
from enum import Enum, auto

from PySide6.QtCore import QModelIndex, Qt, QSortFilterProxyModel, Signal, Slot
# --- MODIFIED: QStackedWidget is now used to manage different view states ---
from PySide6.QtWidgets import (QAbstractItemView, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QStackedWidget,
                               QTableView, QVBoxLayout, QWidget)

from state.app_state import AppState
from views.game_report_model import GameReportModel


class ReportDisplayState(Enum):
    """Defines the possible display states for the GameReportView."""
    LOADING = auto()
    CONTENT = auto()
    EMPTY = auto()


class GameReportView(QWidget):
    """
    UI for displaying the sortable/filterable table of game reports.
    Manages different states (loading, empty, content) using a QStackedWidget.
    """
    
    game_selected = Signal(str)
    
    # --- NEW: Indices for the QStackedWidget for better readability ---
    TABLE_IDX = 0
    LOADING_IDX = 1
    EMPTY_IDX = 2

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
        
        # --- MODIFIED: Create a QStackedWidget and state-specific "cards" ---
        self.stacked_widget = QStackedWidget()
        self.table_view = QTableView()
        self.loading_label = QLabel("Loading game data...")
        self.empty_label = QLabel("No games found in the database.")

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        
        report_group_box = QGroupBox("Game Report")
        report_layout = QVBoxLayout(report_group_box)
        
        filter_hbox = QHBoxLayout()
        filter_hbox.addWidget(self.filter_label)
        filter_hbox.addWidget(self.filter_input)
        
        # --- MODIFIED: Add widgets to the stacked layout ---
        self.stacked_widget.addWidget(self.table_view)      # Index 0
        self.stacked_widget.addWidget(self.loading_label)   # Index 1
        self.stacked_widget.addWidget(self.empty_label)     # Index 2
        
        report_layout.addLayout(filter_hbox)
        # --- MODIFIED: Add the stacked widget instead of the table directly ---
        report_layout.addWidget(self.stacked_widget)
        
        main_layout.addWidget(report_group_box)

    def _configure_widgets(self):
        # Configure filter input
        self.filter_input.setPlaceholderText("Filter by player, opening, etc...")
        
        # Configure state labels
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Configure table view
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        
        # Set the initial state to loading.
        self.set_display_state(ReportDisplayState.LOADING)

    def _connect_signals(self):
        self.filter_input.textChanged.connect(self.proxy_model.setFilterRegularExpression)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)
    
    def _on_row_double_clicked(self, proxy_index: QModelIndex):
        """Handles the double-click event on a table row."""
        source_index = self.proxy_model.mapToSource(proxy_index)
        if not source_index.isValid():
            return
            
        summary = self.game_report_model.get_summary_at_row(source_index.row())
        
        if summary:
            self.game_selected.emit(summary.game_id)
            
    # --- NEW: A single, state-driven method to control the view's appearance ---
    @Slot(ReportDisplayState)
    def set_display_state(self, state: ReportDisplayState):
        """Sets the view to show the appropriate widget based on the state."""
        if state == ReportDisplayState.LOADING:
            self.stacked_widget.setCurrentIndex(self.LOADING_IDX)
        elif state == ReportDisplayState.EMPTY:
            self.stacked_widget.setCurrentIndex(self.EMPTY_IDX)
        elif state == ReportDisplayState.CONTENT:
            self.stacked_widget.setCurrentIndex(self.TABLE_IDX)