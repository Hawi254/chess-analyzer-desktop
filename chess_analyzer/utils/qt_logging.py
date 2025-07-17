# chess_analysis_project/utils/qt_logging.py
"""
Provides a custom structlog processor to integrate with a PySide6 GUI.
"""
from typing import Any

from PySide6.QtCore import QObject, Signal
from structlog.types import EventDict

class QLogEmitter(QObject):
    """A simple QObject that holds and emits a signal for log messages."""
    log_generated = Signal(str)

class QtSignalProcessor:
    """
    A structlog processor that emits a Qt signal for user-facing log events.
    """
    def __init__(self):
        self.emitter = QLogEmitter()

    def __call__(self, logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
        """
        Processes the log event dictionary. If 'show_in_gui' is true, it formats
        a user-friendly message and emits a Qt signal.
        """
        if event_dict.get('show_in_gui', False):
            level = event_dict.get('level', 'info').upper()
            message = event_dict.get('event', 'No message')
            
            # Format a clean string for the GUI status log
            gui_message = f"{level}: {message}"
            
            # Emit the signal for the GUI to pick up
            self.emitter.log_generated.emit(gui_message)

        # Always return the event_dict for the next processor in the chain
        return event_dict