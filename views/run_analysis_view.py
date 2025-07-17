# chess_analysis_project/views/run_analysis_view.py
"""
Defines the 'Run Analysis' dashboard view.

This QWidget acts as the main control panel for the application. It is a
'Humble Object' responsible only for displaying widgets and emitting signals
for user interactions.
"""
from pathlib import Path
from typing import List

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QLabel, QLineEdit, QFileDialog,
                               QListWidget, QGridLayout, QProgressBar, QPushButton,
                               QSpinBox, QTextEdit, QVBoxLayout, QWidget, QSizePolicy)

from views.shared.custom_widgets import StretchySplitter

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
        self.browse_button.clicked.connect(self._browse_and_update)
        
        # --- CORRECTED: Connect to the actual, existing signals ---
        self.file_list_widget.model().rowsInserted.connect(self._update_ui_state)
        self.file_list_widget.model().rowsRemoved.connect(self._update_ui_state)
        # --------------------------------------------------------
        
        self.username_input.textChanged.connect(self._update_ui_state)
    
    def _browse_and_update(self):
        """Custom slot to handle browsing, clearing, and then adding new items."""
        # This is triggered by the browse button click
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open PGN Files", "", "PGN Files (*.pgn);;All Files (*)")
        # We must clear the list *before* adding new items to ensure the model
        # signals are processed in a predictable order.
        self.file_list_widget.clear() 
        if file_paths:
            self.file_list_widget.addItems(file_paths)
        # Manually call update state in case no file was selected, to reset the status message.
        self._update_ui_state()
        
    def _on_start_clicked(self):
        """Gathers config and emits the start_analysis_requested signal."""
        config = {
            "pgn_files": [self.file_list_widget.item(i).text() for i in range(self.file_list_widget.count())],
            "depth": self.depth_spinbox.value(),
            "multipv": self.multipv_spinbox.value(),
            "user_player_name": self.username_input.text().strip()
        }
        self.start_analysis_requested.emit(config)

    def _update_ui_state(self):
        """Updates the UI state based on input validity and provides user guidance."""
        has_files = self.file_list_widget.count() > 0
        has_username = bool(self.username_input.text().strip())

        is_ready_to_start = has_files and has_username
        self.start_button.setEnabled(is_ready_to_start)

        if not has_files:
            self.status_update_requested.emit("Ready. Please select a PGN file.")
        elif not has_username:
            self.status_update_requested.emit("Please enter your player name to proceed.")
        else:
            self.status_update_requested.emit("Ready to start analysis.")
    
    def set_ui_for_analysis(self, is_running: bool):
        """Toggles the UI state between idle and running."""
        # Disable all input controls when running
        self.browse_button.setEnabled(not is_running)
        self.username_input.setEnabled(not is_running)
        self.depth_spinbox.setEnabled(not is_running)
        self.multipv_spinbox.setEnabled(not is_running)
        
        # Manage execution buttons
        self.cancel_button.setEnabled(is_running)
        self.progress_bar.setVisible(is_running)

        if is_running:
            self.start_button.setEnabled(False)
            self.status_update_requested.emit("Analysis in progress...")
        else:
            self.progress_bar.setValue(0)
            self._update_ui_state() # Reset start button state and status message

    def append_log_message(self, message: str):
        self.status_log.append(message.strip())

    def update_progress(self, current: int, total: int):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)