# chess_analysis_project/views/dashboard/arsenal_view.py
"""
Defines the "Arsenal" tab for the dashboard, focusing on opening repertoire analysis.
"""
import chess
import chess.svg
import structlog
from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Signal, Qt, Slot
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QListWidget,
                               QListWidgetItem, QSplitter, QTableView,
                               QVBoxLayout, QWidget)

# Step 3: Import the custom delegate.
from views.dashboard.opening_table_delegate import OpeningTableDelegate
from views.dashboard.opening_performance_model import OpeningPerformanceModel
from views.shared.shared_widgets import CardWidget, StretchySplitter

logger = structlog.get_logger(__name__)


class ArsenalView(QWidget):
    """The UI for the 'Arsenal' (Opening Repertoire) dashboard tab."""
    # Emits the selected opening_id to fetch dissonance data for.
    dissonance_data_requested = Signal(int)
    # Emits game_id and ply to navigate to a specific game position.
    game_selected_with_ply = Signal(str, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.opening_model = OpeningPerformanceModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.opening_model)
        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        """Instantiate all UI widgets and their container cards."""
        self.splitter = StretchySplitter(Qt.Orientation.Horizontal)

        # --- Opening Performance Panel ---
        self.table_card = CardWidget("Opening Performance")
        self.opening_table = QTableView()
        self.table_card.set_content(self.opening_table)

        # --- Cognitive Dissonance Panel ---
        self.dissonance_card = CardWidget("Cognitive Dissonance Positions")
        self.dissonance_list = QListWidget()
        self.mini_board_widget = QSvgWidget()
        # --- FIX: Change splitter to be vertical ---
        dissonance_splitter = QSplitter(Qt.Orientation.Vertical)
        dissonance_splitter.addWidget(self.dissonance_list)
        dissonance_splitter.addWidget(self.mini_board_widget)
        dissonance_splitter.setSizes([300, 200]) # Give more initial space to the list
        self.dissonance_card.set_content(dissonance_splitter)
        
        self.opening_table.setModel(self.proxy_model)
        self.opening_table.setSortingEnabled(True)
        self.opening_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.opening_table.setEditTriggers(QAbstractItemView.EditTriggers.NoEditTriggers)
        self.opening_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # --- Step 3: Instantiate and apply the delegate to the table view. ---
        delegate = OpeningTableDelegate(self.opening_table)
        self.opening_table.setItemDelegate(delegate)
        # ---------------------------------------------------------------------

    def _create_layout(self):
        """Arrange the main cards in the layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter.addWidget(self.table_card)
        self.splitter.addWidget(self.dissonance_card)
        self.splitter.setSizes([600, 500])
        main_layout.addWidget(self.splitter)

    def _connect_signals(self):
        """Connects signals for user interaction within this tab."""
        self.opening_table.selectionModel().selectionChanged.connect(self._on_opening_selected)
        self.dissonance_list.currentItemChanged.connect(self._on_dissonance_item_selected)
        self.dissonance_list.itemDoubleClicked.connect(self._on_dissonance_item_double_clicked)

    @Slot(QListWidgetItem)
    def _on_dissonance_item_selected(self, item: QListWidgetItem):
        """Updates the mini-chessboard when a new dissonance item is selected."""
        if not item:
            self.mini_board_widget.load(bytes())
            return
        item_data = item.data(Qt.ItemDataRole.UserRole)
        fen = item_data.get('fen')
        if fen:
            board = chess.Board(fen)
            svg_board = chess.svg.board(board=board)
            self.mini_board_widget.load(svg_board.encode('utf-8'))

    @Slot(QListWidgetItem)
    def _on_dissonance_item_double_clicked(self, item: QListWidgetItem):
        """Handles double-click on a dissonance item to navigate to the game."""
        if (pos_data := item.data(Qt.ItemDataRole.UserRole)):
            game_id = pos_data.get('game_id')
            ply = pos_data.get('ply')
            if game_id and ply is not None:
                self.game_selected_with_ply.emit(game_id, ply)

    def _on_opening_selected(self, selected: QModelIndex, deselected: QModelIndex):
        """Handles single-click on a table row to update the dissonance panel."""
        indexes = self.opening_table.selectionModel().selectedRows()
        if not indexes:
            self.dissonance_list.clear()
            self.mini_board_widget.load(bytes()) # Clear the board as well
            return

        # The user selected a row in the sorted/filtered view (proxy model).
        # We must map this index back to the original model to get the correct data.
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        if source_index.isValid():
            row_data = self.opening_model.get_row_data(source_index.row())
            if row_data and 'opening_id' in row_data:
                self.dissonance_data_requested.emit(row_data['opening_id'])

    @Slot(bool)
    def set_loading_state(self, is_loading: bool):
        """Sets all card widgets in this view to the loading state."""
        if is_loading:
            self.table_card.show_loading()
            self.dissonance_card.show_loading()

    def update_opening_table(self, data: list):
        """Updates the opening performance table with new data."""
        logger.info("UI: ArsenalView received data to update table.", data_count=len(data))
        if self.opening_model.load_data(data):
            self.table_card.show_content()
            if self.opening_model.rowCount() > 0:
                self.opening_table.selectRow(0)
        else:
            self.table_card.show_message("No opening data available.")
            self.dissonance_card.show_message("Select an opening to see details.")

    def update_dissonance_panel(self, data: list):
        logger.info("UI: ArsenalView received data for dissonance panel.", data_count=len(data))
        self.dissonance_list.clear()
        if not data:
            self.dissonance_card.show_message("No notable positions found for this opening.")
            return

        # --- FIX: Use the new, richer data to provide more context ---
        for pos_data in data:
            # Get all the new data points
            fen = pos_data.get('fen')
            # game_id and ply are now available in pos_data but not directly displayed
            played_move_uci = pos_data.get('played_move_uci')
            best_move_san = pos_data.get('best_move_san', 'N/A')
            cpl = pos_data.get('cpl', 0.0)
            time_spent = pos_data.get('time_spent_seconds', 0.0)
            post_move_eval_cp = pos_data.get('post_move_eval')
            dissonance_score = pos_data.get('dissonance_score')

            if not all([fen, played_move_uci, post_move_eval_cp is not None]):
                logger.warning("Skipping dissonance item due to missing data.", item=pos_data)
                continue

            try:
                board = chess.Board(fen)
                played_move_san = board.san(chess.Move.from_uci(played_move_uci))
            except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError):
                played_move_san = played_move_uci

            eval_after_best_move_cp = cpl + post_move_eval_cp
            eval_after_best_move_str = f"{eval_after_best_move_cp / 100.0:+.2f}"

            score_text = f"{dissonance_score:.0f}" if dissonance_score is not None else "N/A"
            cpl_text = f"{cpl:.0f}" if cpl is not None else "N/A"
            time_text = f"{time_spent:.1f}s" if time_spent is not None else "N/A"

            item_text = (
                f"Dissonance Score: {score_text}\n"
                f"  - You played: {played_move_san} (Time: {time_text}, CPL: {cpl_text})\n"
                f"  - Best move was: {best_move_san} (eval {eval_after_best_move_str})"
            )
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.ItemDataRole.UserRole, pos_data)
            self.dissonance_list.addItem(list_item)
        
        self.dissonance_card.show_content()
        if self.dissonance_list.count() > 0:
            self.dissonance_list.setCurrentRow(0)