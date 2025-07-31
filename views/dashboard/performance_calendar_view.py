# chess_analysis_project/views/dashboard/performance_calendar_view.py
"""
Defines the "Performance Calendar" tab for the main statistics dashboard.
"""
import json
from PySide6.QtCore import Slot, Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QHBoxLayout, QComboBox,
                               QSplitter, QListWidget, QListWidgetItem)
import structlog

from views.dashboard.calendar_heatmap_widget import CalendarHeatmapWidget
from views.shared.shared_widgets import CardWidget, StretchySplitter

logger = structlog.get_logger(__name__)

# ====================================================================================
# Main Performance Calendar View Class
# ====================================================================================

class PerformanceCalendarView(QWidget):
    """The UI for the Performance Calendar tab."""
    game_selected = Signal(str) # Emits game_id when a game in the list is double-clicked
    data_requested = Signal(dict) # Emits filter dictionary when filters change

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        """Instantiate UI widgets."""
        # --- Filter Controls ---
        self.date_range_label = QLabel("Date Range:")
        self.date_range_combo = QComboBox()
        self.date_range_combo.addItems(["All Time", "Last 6 Months", "Last 3 Months"])

        self.granularity_label = QLabel("Granularity:")
        self.granularity_combo = QComboBox()
        self.granularity_combo.addItems(["Weekly", "Daily", "Monthly"]) # Weekly is default

        self.metric_label = QLabel("Metric:")
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(["Accuracy", "Win Rate"])

        # --- Main Content Widgets ---
        self.splitter = StretchySplitter(Qt.Orientation.Horizontal)
        self.calendar_heatmap = CalendarHeatmapWidget()
        
        self.game_list_card = CardWidget("Games in Selected Period")
        self.game_list_widget = QListWidget()
        self.game_list_card.set_content(self.game_list_widget)

    def _create_layout(self):
        """Arrange widgets in the layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Filter Bar ---
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        filter_layout.addWidget(self.date_range_label)
        filter_layout.addWidget(self.date_range_combo)
        filter_layout.addWidget(self.granularity_label)
        filter_layout.addWidget(self.granularity_combo)
        filter_layout.addWidget(self.metric_label)
        filter_layout.addWidget(self.metric_combo)
        filter_layout.addStretch()

        # --- Main Content Splitter ---
        # The calendar is a direct widget, the list is inside a card
        self.splitter.addWidget(self.calendar_heatmap)
        self.splitter.addWidget(self.game_list_card)
        self.splitter.setSizes([700, 300]) # Give calendar more initial space

        main_layout.addLayout(filter_layout)
        main_layout.addWidget(self.splitter, stretch=1)

    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        self.calendar_heatmap.period_clicked.connect(self._on_period_clicked)
        self.game_list_widget.itemDoubleClicked.connect(
            lambda item: self.game_selected.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        self.date_range_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.granularity_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.metric_combo.currentIndexChanged.connect(self._on_filter_changed)

    @Slot(list)
    def _on_period_clicked(self, games: list):
        """Handles a click on the calendar, populating the game list with rich info."""
        self.game_list_widget.clear()
        if not games:
            self.game_list_card.show_message("No games in this period.")
            return

        for game_data in games:
            game_id = game_data.get('game_id')
            opponent_rating = game_data.get('opponent_rating', '????')
            result = game_data.get('result')
            player_color = game_data.get('player_color')

            # Determine win/loss/draw from the player's perspective
            if result == '1/2-1/2':
                result_str = "Draw"
            elif (result == '1-0' and player_color == 'White') or \
                 (result == '0-1' and player_color == 'Black'):
                result_str = "Win"
            else:
                result_str = "Loss"

            display_text = f"vs Opponent ({opponent_rating}) - {result_str}"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, game_id) # Store the ID for navigation
            self.game_list_widget.addItem(item)

        self.game_list_card.show_content()

    @Slot()
    def _on_filter_changed(self):
        """Gathers current filter settings and emits a signal to request new data."""
        self.data_requested.emit(self.get_current_filters())

    def get_current_filters(self) -> dict:
        """
        Returns the current filter settings from the calendar view. This provides a
        public API for the presenter to get the view's state without coupling.
        """
        date_range = self.date_range_combo.currentText()
        return {
            "date_range": date_range if date_range != "All Time" else None,
            "granularity": self.granularity_combo.currentText(),
            "metric": self.metric_combo.currentText()
        }

    @Slot(bool)
    def set_loading_state(self, is_loading: bool):
        """Sets the view to a loading state."""
        # A more robust implementation might use a QStackedWidget or overlay
        self.setEnabled(not is_loading)
        if is_loading:
            self.calendar_heatmap.set_data({}, "Weekly", "Accuracy") # Clear the calendar
            self.game_list_card.show_loading()

    @Slot(list)
    def plot_accuracy_trend(self, data: list):
        # --- REWORKED: This slot is now generic for any trend data ---
        logger.debug("PerformanceCalendarView received trend data.", item_count=len(data))
        
        if not data:
            self.calendar_heatmap.set_data({}, "Weekly", "Accuracy") # Reset with defaults
            self.game_list_card.show_message("No data for this period.")
            self.set_loading_state(False)
            return

        # The backend now returns a generic 'date_key' and 'metric_value'.
        # We now parse the games_json string into a list of dicts.
        heatmap_data = {}
        for item in data:
            if date_key := item.get('date_key'):
                games_list = json.loads(item.get('games_json', '[]'))
                heatmap_data[date_key] = {**item, 'games': games_list}

        # Get current filter settings to pass to the widget for context
        filters = self.get_current_filters()
        granularity = filters.get("granularity", "Weekly")
        metric_name = filters.get("metric", "Accuracy")

        self.calendar_heatmap.set_data(heatmap_data, granularity, metric_name)
        self.game_list_card.show_message("Click a period on the calendar to see games.")
        self.set_loading_state(False)