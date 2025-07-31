# chess_analysis_project/views/run_analysis_view.py
"""
Defines the 'Run Analysis' dashboard view.
"""
from enum import Enum, auto
import os

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QProgressBar,
                               QPushButton, QSpinBox, QTextEdit, QVBoxLayout,
                               QWidget, QFileDialog)

from views.shared.shared_widgets import StretchySplitter

# --- NEW: An explicit state machine enum for clarity and robustness ---
class UIState(Enum):
    INITIALIZING = auto()
    IDLE = auto()
    RUNNING = auto()

class RunAnalysisView(QWidget):
    """The UI for the main 'Run Analysis' dashboard."""
    start_analysis_requested = Signal(dict)
    cancel_analysis_requested = Signal()
    status_update_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._create_widgets()
        self._configure_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        """Instantiate all UI widgets."""
        self.splitter = StretchySplitter(Qt.Orientation.Vertical)
        self.file_list_widget = QListWidget()
        self.browse_button = QPushButton("Select PGN File(s)...")
        self.status_log = QTextEdit()

        self.username_input = QLineEdit()
        self.depth_spinbox = QSpinBox()
        self.multipv_spinbox = QSpinBox()

        self.start_button = QPushButton("Start Analysis")
        self.cancel_button = QPushButton("Cancel")
        self.progress_bar = QProgressBar()

    def _configure_widgets(self):
        """Set initial properties and styles for widgets."""
        self.file_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.status_log.setReadOnly(True)
        self.status_log.setFontFamily("monospace")
        
        self.username_input.setPlaceholderText("Enter your name exactly as it appears in PGN files")
        self.depth_spinbox.setRange(5, 20); self.depth_spinbox.setValue(11)
        self.multipv_spinbox.setRange(1, 8); self.multipv_spinbox.setValue(3)

        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Analyzing game %v of %m")

    def _create_layout(self):
        """Arrange all widgets in a single, logical layout."""
        main_layout = QVBoxLayout(self)
        
        # Top, Stretchy Section
        file_group = QGroupBox("1. Input Files")
        file_layout = QVBoxLayout(file_group)
        file_layout.addWidget(self.file_list_widget)
        file_layout.addWidget(self.browse_button)
        
        log_group = QGroupBox("Status Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.addWidget(self.status_log)
        
        self.splitter.addWidget(file_group)
        self.splitter.addWidget(log_group)
        self.splitter.setSizes([200, 300])

        main_layout.addWidget(self.splitter)

        # Bottom, Fixed-Size Section
        params_group = QGroupBox("2. Analysis Parameters")
        params_layout = QGridLayout(params_group)
        params_layout.addWidget(QLabel("Your Player Name (in PGN):"), 0, 0)
        params_layout.addWidget(self.username_input, 0, 1, 1, 3)
        params_layout.addWidget(QLabel("Analysis Depth:"), 1, 0)
        params_layout.addWidget(self.depth_spinbox, 1, 1)
        params_layout.addWidget(QLabel("Engine Lines (MultiPV):"), 1, 2)
        params_layout.addWidget(self.multipv_spinbox, 1, 3)
        
        exec_group = QGroupBox("3. Execute")
        exec_layout = QHBoxLayout(exec_group)
        exec_layout.addWidget(self.start_button)
        exec_layout.addWidget(self.cancel_button)
        exec_layout.addWidget(self.progress_bar)

        main_layout.addWidget(params_group)
        main_layout.addWidget(exec_group)
    
    def _connect_signals(self):
        """Connect internal widget signals to handler methods."""
        self.start_button.clicked.connect(self._on_start_clicked)
        self.cancel_button.clicked.connect(self.cancel_analysis_requested.emit)
        # The browse button is connected in MainWindow
        self.file_list_widget.model().rowsInserted.connect(self._update_start_button_state)
        self.file_list_widget.model().rowsRemoved.connect(self._update_start_button_state)
        self.username_input.textChanged.connect(self._update_start_button_state)
    
    def _on_start_clicked(self):
        """Gathers config and emits the start_analysis_requested signal."""
        config = {
            "pgn_files": [self.file_list_widget.item(i).text() for i in range(self.file_list_widget.count())],
            "depth": self.depth_spinbox.value(),
            "multipv": self.multipv_spinbox.value(),
            "user_player_name": self.username_input.text().strip()
        }
        self.start_analysis_requested.emit(config)

    def _update_start_button_state(self):
        """Internal logic to determine if the start button should be enabled."""
        has_files = self.file_list_widget.count() > 0
        has_username = bool(self.username_input.text().strip())
        is_ready = has_files and has_username
        self.start_button.setEnabled(is_ready)
        
        # Update the status message based on what's missing
        if not has_files:
            self.status_update_requested.emit("Ready. Please select a PGN file.")
        elif not has_username:
            self.status_update_requested.emit("Please enter your player name to proceed.")
        else:
            self.status_update_requested.emit("Ready to start analysis.")

    # --- REMOVED: All old, conflicting state methods are gone ---
    # set_ui_for_analysis(self, is_running: bool) is removed.
    # set_ui_for_initializing(self, is_initializing: bool) is removed.

    # --- NEW: The single, definitive state management method ---
    @Slot(UIState)
    def set_ui_state(self, state: UIState):
        """Sets the enabled/disabled state of all widgets based on the application state."""
        if state == UIState.INITIALIZING:
            self.setEnabled(False)
            self.status_update_requested.emit("Initializing database...")
        elif state == UIState.RUNNING:
            self.setEnabled(True)
            self.browse_button.setEnabled(False)
            self.username_input.setEnabled(False)
            self.depth_spinbox.setEnabled(False)
            self.multipv_spinbox.setEnabled(False)
            self.start_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.status_update_requested.emit("Analysis in progress...")
        elif state == UIState.IDLE:
            self.setEnabled(True)
            self.browse_button.setEnabled(True)
            self.username_input.setEnabled(True)
            self.depth_spinbox.setEnabled(True)
            self.multipv_spinbox.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)
            self._update_start_button_state()

    # --- NEW: Public API for Presenter Interaction (Decoupling) ---

    def get_config(self) -> dict:
        """
        Returns the current configuration from the UI widgets. This provides a
        public API for the presenter to get the view's state without coupling.
        """
        pgn_file = None
        if self.file_list_widget.count() > 0:
            # Assuming only one file path is relevant for saving settings
            pgn_file = self.file_list_widget.item(0).text()
            
        return {
            "user_player_name": self.username_input.text().strip(),
            "depth": self.depth_spinbox.value(),
            "multipv": self.multipv_spinbox.value(),
            "pgn_file": pgn_file
        }

    def set_config(self, config: dict):
        """
        Sets the UI widget values from a configuration dictionary. This provides
        a public API for the presenter to set the view's state without coupling.
        """
        self.username_input.setText(config.get("player_name", ""))
        self.depth_spinbox.setValue(config.get("depth", 11))
        self.multipv_spinbox.setValue(config.get("multipv", 3))
        
        last_file = config.get("last_file", "")
        if last_file and os.path.exists(last_file):
            self.file_list_widget.clear()
            self.file_list_widget.addItem(last_file)

    def get_player_name(self) -> str:
        """A simple public getter for the player name."""
        return self.username_input.text().strip()

    @Slot(str)
    def append_log_message(self, message: str):
        """Appends a message to the status log text edit."""
        self.status_log.append(message.strip())

    def update_progress(self, current: int, total: int):
        """Updates the progress bar's value during analysis."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)