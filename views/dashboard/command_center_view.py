# chess_analysis_project/views/dashboard/command_center_view.py
"""
Defines the "Command Center" tab for the main statistics dashboard.
"""
import pyqtgraph as pg
from PySide6.QtCore import Signal, Qt, Slot
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget)
import structlog

from views.shared.shared_widgets import CardWidget

logger = structlog.get_logger(__name__)

# Constants for styling plots (ensure these are consistent with theme)
RESULT_COLOR_CODES = { "win": "#2ECC71", "loss": "#E74C3C", "draw": "#F39C18" }
DEFAULT_POINT_COLOR_CODE = "#1E90FF"

class CommandCenterView(QWidget):
    """The UI for the main 'Command Center' dashboard tab."""
    game_selected = Signal(str) # Emits game_id when a data point on a chart is clicked.
    filters_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Configure pyqtgraph global options for consistent styling
        pg.setConfigOption('background', 'w') # White background for plots
        pg.setConfigOption('foreground', 'k') # Black foreground for text/axes
        self._brush_cache = {} # Cache for QBrush objects to optimize rendering

        # --- Style for KPI value labels, scoped to this view ---
        self.setStyleSheet("""
            #KPIValueLabel {
                font-size: 28px;
                font-weight: bold;
            }
        """)

        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        """Instantiate all UI widgets and their container cards."""
        # --- Filter Widgets ---
        self.time_control_filter_label = QLabel("Time Control:")
        self.time_control_filter_combo = QComboBox()
        self.color_filter_label = QLabel("Color:")
        self.color_filter_combo = QComboBox()
        self.time_control_filter_combo.addItems(["All", "Blitz", "Rapid", "Classical"])
        self.color_filter_combo.addItems(["All", "White", "Black"])

        # --- KPI Cards ---
        self.kpi_accuracy_card = CardWidget("Overall Accuracy")
        self.kpi_record_card = CardWidget("Record (W/L/D)")
        self.kpi_games_card = CardWidget("Total Games")
        
        # Labels to display the actual KPI values
        self.acc_value_label = QLabel("")
        self.rec_value_label = QLabel("")
        self.games_value_label = QLabel("")


    def _create_layout(self):
        """Arrange all widgets and cards in the layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15) # Spacing between major sections
        main_layout.setContentsMargins(0, 0, 0, 0) # Use full available space

        # --- Filter Bar Layout ---
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        filter_layout.addWidget(self.time_control_filter_label)
        filter_layout.addWidget(self.time_control_filter_combo)
        filter_layout.addWidget(self.color_filter_label)
        filter_layout.addWidget(self.color_filter_combo)
        filter_layout.addStretch() # Pushes filters to the left

        # --- KPI Section Layout (Horizontal for the three cards) ---
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(15)
        kpi_layout.addWidget(self.kpi_accuracy_card)
        kpi_layout.addWidget(self.kpi_record_card)
        kpi_layout.addWidget(self.kpi_games_card)
        kpi_layout.addStretch() # Pushes cards to the left if space allows
        
        # --- DEFINITIVE FIX: Set content layout for each KPI Card directly ---
        self.kpi_accuracy_card.set_content_layout(self._create_kpi_content_layout(self.acc_value_label))
        self.kpi_record_card.set_content_layout(self._create_kpi_content_layout(self.rec_value_label))
        self.kpi_games_card.set_content_layout(self._create_kpi_content_layout(self.games_value_label))
        # ---------------------------------------------------------------------
        
        # --- Add all major sections to the main vertical layout ---
        main_layout.addLayout(filter_layout)
        main_layout.addLayout(kpi_layout)
        main_layout.addStretch(1) # Add stretch to push content to the top

    def _create_kpi_content_layout(self, value_label: QLabel) -> QVBoxLayout:
        """Helper to create a layout for a KPI card's content, applying styling to the label."""
        """Helper to create a layout for a KPI card's content."""
        value_label.setObjectName("KPIValueLabel")  # Set an object name for styling
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Keep the alignment setting
        
        layout = QVBoxLayout()
        layout.addWidget(value_label, alignment=Qt.AlignmentFlag.AlignCenter, stretch=1)
        return layout

    def _connect_signals(self):
        """Connects signals for user interaction within this tab."""
        self.time_control_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.color_filter_combo.currentIndexChanged.connect(self._on_filter_changed)

    @Slot()
    def _on_filter_changed(self):
        """
        A private slot that is triggered when any filter combo box changes.
        It emits the public `filters_changed` signal to notify the application.
        """
        self.filters_changed.emit()

    def get_current_filters(self) -> dict:
        """
        Returns the current filter settings from the UI widgets. This provides a
        public API for the presenter to get the view's state without coupling.
        """
        time_control = self.time_control_filter_combo.currentText()
        color = self.color_filter_combo.currentText()
        return {
            "time_control": time_control if time_control != "All" else None,
            "color": color if color != "All" else None
        }

    @Slot(bool)
    def set_loading_state(self, is_loading: bool):
        """Sets all card widgets in this view to the loading state."""
        if is_loading:
            self.kpi_accuracy_card.show_loading()
            self.kpi_record_card.show_loading()
            self.kpi_games_card.show_loading()

    def _get_brush(self, color_code: str) -> QBrush:
        """Helper to get or create a QBrush for plotting, with alpha for transparency."""
        if color_code not in self._brush_cache:
            self._brush_cache[color_code] = pg.mkBrush(color_code + 'B4')
        return self._brush_cache[color_code]

    # --- Public Slots to Update UI ---
    
    @Slot(dict)
    def update_kpis(self, data: dict):
        """Updates the KPI labels and transitions KPI cards from loading to content/message."""
        logger.debug("CommandCenterView received KPI data for update.", data=data)
        
        # Check if data is truly empty or indicates no games
        if not data or data.get('total_games', 0) == 0:
            message = "No data available.\nAnalyze some games!"
            self.kpi_accuracy_card.show_message(message)
            self.kpi_record_card.show_message(message)
            self.kpi_games_card.show_message(message)
            return

        # Extract and format KPI values
        overall_acc = data.get('overall_avg_accuracy')
        recent_acc = data.get('recent_avg_accuracy')
        wins = data.get('overall_wins', 0)
        losses = data.get('overall_losses', 0)
        draws = data.get('overall_draws', 0)
        total_games = data.get('total_games', 0)

        # Update accuracy label with optional delta
        self.acc_value_label.setText(f"<b>{overall_acc:.1f}%</b>" if overall_acc is not None else "<b>N/A</b>")
        if overall_acc is not None and recent_acc is not None:
            acc_delta = overall_acc - recent_acc
            color = 'green' if acc_delta > 0 else ('red' if acc_delta < 0 else 'gray')
            self.acc_value_label.setText(f"{self.acc_value_label.text()} <span style='font-size:16px; color:{color};'>({acc_delta:+.1f}%)</span>")
        
        # Update total games label
        self.games_value_label.setText(f"<b>{total_games}</b>")
        
        # --- ENHANCEMENT: Add data validation to detect inconsistencies from the backend ---
        # This directly helps diagnose the issue you're seeing. If the backend
        # miscounts games based on color, this check will likely fail.
        if wins + losses + draws != total_games:
            logger.warning(
                "KPI data inconsistency detected: W/L/D sum does not match total games.",
                wins=wins, losses=losses, draws=draws, total=total_games
            )
            # Display an error message to the user to make the problem visible.
            self.rec_value_label.setText("Data Error!")
            self.kpi_record_card.show_message(f"Inconsistent Data:\nSum of W/L/D ({wins+losses+draws}) does not match total games ({total_games}).")
        else:
            # Only update the record if the data is consistent.
            self.rec_value_label.setText(f"<b>{wins} / {losses} / {draws}</b>")
            self.kpi_record_card.show_content()

        # Transition cards to show content
        self.kpi_accuracy_card.show_content()
        self.kpi_games_card.show_content()