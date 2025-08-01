from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, QWidget, QLabel

class TrendSummarySettingsModal(QDialog):
    """
    Modal dialog for configuring settings of the Trend & Summary card.
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Trend & Summary Settings")
        self.setMinimumSize(400, 300)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # Tab Widget for different settings categories
        tab_widget = QTabWidget()
        tab_widget.addTab(self._create_general_settings_tab(), "General")
        tab_widget.addTab(self._create_chart_settings_tab(), "Chart Style")
        tab_widget.addTab(self._create_threshold_settings_tab(), "Thresholds")
        
        main_layout.addWidget(tab_widget)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        main_layout.addLayout(button_layout)

    def _create_general_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("General settings options will go here."))
        layout.addStretch()
        return tab

    def _create_chart_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Chart style options (line vs. bars) will go here."))
        layout.addStretch()
        return tab

    def _create_threshold_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Color threshold settings will go here."))
        layout.addStretch()
        return tab
