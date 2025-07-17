# chess_analysis_project/views/dashboard/arsenal_view.py
"""
Defines the "Arsenal" tab for the dashboard, focusing on opening repertoire analysis.
"""
from PySide6.QtCore import QModelIndex, Signal, Qt
from PySide6.QtWidgets import (QAbstractItemView, QGroupBox, QHeaderView,
                               QListWidget, QSizePolicy, QListWidgetItem, QSplitter,
                               QTableView, QVBoxLayout, QWidget, QLabel, QStackedLayout)

# We will reuse the BlunderReelDelegate for a similar purpose here,
# assuming a mini-board and some text is needed. A more specific delegate
# could be created if the layout differs significantly.
from views.dashboard.blunder_reel_delegate import BlunderReelDelegate
from views.dashboard.opening_performance_model import OpeningPerformanceModel
from views.shared.custom_widgets import StretchySplitter

class ArsenalView(QWidget):
    """The UI for the 'Arsenal' (Opening Repertoire) dashboard tab."""
    dissonance_data_requested = Signal(int)
    game_selected_from_dissonance = Signal(str, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.opening_model = OpeningPerformanceModel()
        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        self.splitter = StretchySplitter(Qt.Orientation.Horizontal)
        
        # Left side: Table of openings
        self.opening_table = QTableView()
        self.opening_table.setModel(self.opening_model)
        self.opening_table.setSortingEnabled(True)
        self.opening_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.opening_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.opening_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.table_container = QWidget()
        self.table_stack = QStackedLayout(self.table_container)
        self.table_stack.addWidget(self.opening_table)
        self.empty_table_label = QLabel("No opening data found.")
        self.empty_table_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_stack.addWidget(self.empty_table_label)

        # Right side: Dissonance panel
        self.dissonance_list = QListWidget()
        # A custom delegate could be created for dissonance items if needed,
        # but for now, simple text is sufficient. A more advanced version
        # would use a delegate similar to the Blunder Reel.

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        table_group = QGroupBox("Opening Performance")
        table_layout = QVBoxLayout(table_group)
        table_layout.addWidget(self.table_container) 
        
        dissonance_group = QGroupBox("Cognitive Dissonance Positions")
        dissonance_layout = QVBoxLayout(dissonance_group)
        dissonance_layout.addWidget(self.dissonance_list)

        # --- CORRECTED: Ensure the groups can expand ---
        # While QGroupBox often expands by default, being explicit is more robust.
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table_group.setSizePolicy(size_policy)
        dissonance_group.setSizePolicy(size_policy)

        self.splitter.addWidget(table_group)
        self.splitter.addWidget(dissonance_group)
        self.splitter.setSizes([600, 400])
        
        main_layout.addWidget(self.splitter)
        
    def _connect_signals(self):
        """Connects signals for user interaction within this tab."""
        # When a row is selected (clicked), get the data for the dissonance panel.
        self.opening_table.selectionModel().selectionChanged.connect(self._on_opening_selected)
        
    def _on_opening_selected(self, selected: QModelIndex, deselected: QModelIndex):
        """When an opening is selected, request the dissonance data for it."""
        indexes = self.opening_table.selectionModel().selectedRows()
        if not indexes:
            self.dissonance_list.clear()
            return
            
        row_data = self.opening_model.get_row_data(indexes[0].row())
        if row_data and 'opening_id' in row_data:
            self.dissonance_data_requested.emit(row_data['opening_id'])
            
    # --- Public Slots to receive data from the controller ---
    
    def update_opening_table(self, data: list):
        """Populates the opening performance table."""
        if data:
            self.opening_model.load_data(data)
            self.table_stack.setCurrentWidget(self.opening_table)
            if self.opening_model.rowCount() > 0:
                self.opening_table.selectRow(0)
        else:
            self.table_stack.setCurrentWidget(self.empty_table_label)

    def update_dissonance_panel(self, data: list):
        """Populates the cognitive dissonance list."""
        self.dissonance_list.clear()

        if not data:
            item = QListWidgetItem("No notable positions found for this opening.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable) # Make it unselectable
            self.dissonance_list.addItem(item)
            return

        for pos_data in data:
            fen = pos_data.get('fen', 'N/A')
            cpl = pos_data.get('cpl', 0.0)
            time = pos_data.get('time_spent_seconds', 0.0)
            score = pos_data.get('dissonance_score') # Get the value, which might be None

            # --- CORRECTED: Handle the case where score is None ---
            score_text = f"{score:.0f}" if score is not None else "N/A"
            cpl_text = f"{cpl:.0f}" if cpl is not None else "N/A"
            time_text = f"{time:.1f}s" if time is not None else "N/A"

            item_text = (
                f"Dissonance Score: {score_text}\n"
                f"  - Time Spent: {time_text}\n"
                f"  - CPL: {cpl_text}\n"
                f"  - FEN: {fen[:30]}..."
            )
            
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.ItemDataRole.UserRole, pos_data)
            self.dissonance_list.addItem(list_item)