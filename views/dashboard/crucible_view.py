# chess_analysis_project/views/dashboard/crucible_view.py
"""
Defines the "Crucible" tab, focusing on the "Worst Blunder Reel."

This view is streamlined to exclusively feature the "Worst Blunder Reel,"
which displays a user's most significant blunders, providing immediate visual
context for each critical mistake.
"""
import structlog
from PySide6.QtCore import Signal, Qt, Slot
from PySide6.QtWidgets import (QListWidget, QListWidgetItem,
                               QVBoxLayout, QWidget)

from views.dashboard.blunder_reel_delegate import BlunderReelDelegate
from views.shared.shared_widgets import CardWidget

# ====================================================================================
# Logger
# ====================================================================================
logger = structlog.get_logger(__name__)

# ====================================================================================
# Configuration Class
# ====================================================================================

class CrucibleConfig:
    """A single source of truth for all static configuration of the Crucible view."""
    # This class is now empty but retained for structural consistency.
    # Future configurations specific to the Blunder Reel can be added here.
    pass

# ====================================================================================
# Main Crucible View Class
# ====================================================================================

class CrucibleView(QWidget):
    """The UI for the 'Crucible' dashboard tab, now showing only the Blunder Reel."""
    game_selected_with_ply = Signal(str, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = CrucibleConfig()

        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        """Initializes the widgets required for the view."""
        self.blunder_reel_list = QListWidget()
        self.blunder_reel_list.setItemDelegate(BlunderReelDelegate(self))

    def _create_layout(self):
        """Creates the simplified layout containing only the blunder reel."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.blunder_reel_card = CardWidget("Worst Blunder Reel")
        blunder_reel_layout = QVBoxLayout()
        blunder_reel_layout.addWidget(self.blunder_reel_list)
        self.blunder_reel_card.set_content_layout(blunder_reel_layout)
        
        main_layout.addWidget(self.blunder_reel_card)

    def _connect_signals(self):
        """Connects widget signals to corresponding slots."""
        self.blunder_reel_list.itemClicked.connect(self._on_blunder_reel_item_clicked)

    @Slot(bool)
    def set_loading_state(self, is_loading: bool):
        """Sets the loading state for the view's components."""
        if is_loading:
            self.blunder_reel_card.show_loading()

    # --- Blunder Reel ---

    @Slot(list)
    def update_blunder_reel(self, data: list):
        """
        Populates the blunder reel list with data.

        Args:
            data: A list of dictionaries, where each dictionary contains
                  information about a single blunder.
        """
        self.blunder_reel_list.clear()

        if not data:
            self.blunder_reel_card.show_message("No blunders to display for this selection.")
            return

        for blunder_data in data:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, blunder_data)
            self.blunder_reel_list.addItem(item)
            
        self.blunder_reel_card.show_content()

    @Slot(QListWidgetItem)
    def _on_blunder_reel_item_clicked(self, item: QListWidgetItem):
        """
        Handles the click event on a blunder reel item.

        Emits a signal with the game ID and ply number of the selected blunder.
        
        Args:
            item: The QListWidgetItem that was clicked.
        """
        if (blunder_data := item.data(Qt.ItemDataRole.UserRole)):
            logger.debug("Blunder reel clicked, emitting signal.", game_id=blunder_data['game_id'], ply=blunder_data['ply'])
            self.game_selected_with_ply.emit(blunder_data['game_id'], blunder_data['ply'])