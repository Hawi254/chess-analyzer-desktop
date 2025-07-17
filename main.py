# main.py
"""
The main entry point for launching the ChessAnalyzer Desktop application.
"""
import sys
import os

# --- CORRECTED: All imports are moved to the top level ---
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

# We need to set the path before these imports
# A better solution might be to properly install the package in editable mode.
# But for now, this ensures it works.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from desktop_app import MainWindow
from chess_analyzer.utils.logging_config import setup_logging
from chess_analyzer.utils.qt_logging import QtSignalProcessor

def main():
    """Main function to setup and run the application."""
    # 1. Create the application-wide GUI log processor.
    qt_processor = QtSignalProcessor()

    # 2. Configure the global logging system, passing the processor.
    setup_logging(log_level="INFO", extra_processors=[qt_processor])

    # 3. Create the Qt Application.
    app = QApplication(sys.argv)

    # 4. Apply a modern theme.
    apply_stylesheet(app, theme='dark_teal.xml')

    # 5. Instantiate the main window, injecting dependencies.
    window = MainWindow(log_emitter=qt_processor.emitter)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()