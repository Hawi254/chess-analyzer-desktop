from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy, QGridLayout
from PySide6.QtCore import Qt, Signal
from views.dashboard.trend_summary_settings_modal import TrendSummarySettingsModal
from views.dashboard.mini_stat_card import MiniStatCard

class TrendSummaryCard(QWidget):
    """
    A card widget displaying trend information and a summary of statistics.
    Includes a header with collapse/expand functionality and settings.
    """
    settings_requested = Signal()
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setMinimumHeight(150) # Ensure card has a minimum height
        self._is_collapsed = False
        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._create_header()
        self._create_body()

        self.main_layout.addLayout(self.header_layout)
        self.main_layout.addWidget(self.body_frame)

    def _create_header(self):
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(10, 5, 10, 5)
        self.header_layout.setSpacing(5)

        self.collapse_button = QPushButton("▾")
        self.collapse_button.setFixedSize(20, 20)
        self.collapse_button.clicked.connect(self._toggle_collapse)
        self.collapse_button.setFlat(True) # Make it look like part of the title

        self.title_label = QLabel("Trend & Summary")
        self.title_label.setStyleSheet("font-weight: bold;")

        self.settings_button = QPushButton("⚙")
        self.settings_button.setFixedSize(20, 20)
        self.settings_button.clicked.connect(self._open_settings_modal)
        self.settings_button.setFlat(True)

        self.header_layout.addWidget(self.collapse_button)
        self.header_layout.addWidget(self.title_label)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.settings_button)

        # Add a separator line below the header
        self.header_separator = QFrame()
        self.header_separator.setFrameShape(QFrame.HLine)
        self.header_separator.setFrameShadow(QFrame.Sunken)
        self.main_layout.addWidget(self.header_separator)


    def _create_body(self):
        self.body_frame = QFrame(self)
        self.body_layout = QVBoxLayout(self.body_frame)
        self.body_layout.setContentsMargins(10, 10, 10, 10)
        self.body_layout.setSpacing(10)

        # Placeholder for the 2x2 grid of mini-cards
        self.mini_card_grid_layout = QGridLayout()
        self.mini_card_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.mini_card_grid_layout.setSpacing(10) # Spacing between mini-cards

        # Initialize placeholder mini-cards
        self.avg_acc_card = MiniStatCard("Avg Acc")
        self.games_card = MiniStatCard("Games")
        self.best_streak_card = MiniStatCard("Best Streak")
        self.worst_week_card = MiniStatCard("Worst Week")

        self.mini_card_grid_layout.addWidget(self.avg_acc_card, 0, 0)
        self.mini_card_grid_layout.addWidget(self.games_card, 0, 1)
        self.mini_card_grid_layout.addWidget(self.best_streak_card, 1, 0)
        self.mini_card_grid_layout.addWidget(self.worst_week_card, 1, 1)

        self.body_layout.addLayout(self.mini_card_grid_layout)
        self.body_layout.addStretch(1) # Push cards to the top

    def _toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self.body_frame.setVisible(not self._is_collapsed)
        self.collapse_toggle_button.setArrowType(Qt.ArrowType.RightArrow if self._is_collapsed else Qt.ArrowType.DownArrow)
        # Adjust size policy to hint layout manager about content change
        if self._is_collapsed:
            self.body_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.body_frame.setFixedHeight(0)
        else:
            self.body_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            self.body_frame.setMinimumHeight(150) # Restore minimum height or calculate based on content
            self.body_frame.setMaximumHeight(16777215) # Restore maximum height

    def _open_settings_modal(self):
        modal = TrendSummarySettingsModal(self)
        modal.exec()

    

    def set_title(self, title: str):
        self.title_label.setText(title)

    def set_collapsed(self, collapsed: bool):
        if self._is_collapsed != collapsed:
            self._toggle_collapse()
