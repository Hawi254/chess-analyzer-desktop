# main.py
"""
The main entry point for launching the ChessAnalyzer Desktop application.
"""
import sys



from desktop_app import MainWindow
from chess_analyzer.utils.logging_config import setup_logging
from chess_analyzer.utils.qt_logging import QtSignalProcessor

from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet


def main():
    """Main function to setup and run the application."""
    qt_processor = QtSignalProcessor()
    # Pass it as a processor, not a handler
    setup_logging(log_level="INFO", extra_processors=[qt_processor])

    app = QApplication(sys.argv)
    apply_stylesheet(app, theme='dark_teal.xml')

    # Pass the emitter, but no parent
    window = MainWindow(log_emitter=qt_processor.emitter, parent=None)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()