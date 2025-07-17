# chess_analysis_project/views/shared/custom_widgets.py
"""
Defines shared, reusable custom Qt widgets for the application, focusing on
layout and structural components.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QSplitter, QWidget, QStackedWidget, QSizePolicy

class ExpandingStackedWidget(QStackedWidget):
    """
    A QStackedWidget subclass that calculates its size hint based only on the
    currently visible widget. This is crucial for allowing a main window to

    dynamically resize to fit the content of different pages, preventing a large
    page from permanently setting a large minimum size for the window.
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # --- CORRECTED: Create a QSizePolicy instance and then set it ---
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setSizePolicy(policy)
        # -----------------------------------------------------------

        # Adjust the size hint of the stacked widget whenever the current widget changes
        self.currentChanged.connect(self.updateGeometry)


    def sizeHint(self) -> QSize:
        """Overrides the default size hint calculation to use the current widget."""
        if self.currentWidget():
            return self.currentWidget().sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        """Overrides the default minimum size hint calculation."""
        if self.currentWidget():
            return self.currentWidget().minimumSizeHint()
        return super().minimumSizeHint()


class StretchySplitter(QSplitter):
    """
    A QSplitter subclass that does not collapse its children. This prevents
    the splitter from imposing a large, rigid minimum size on its parent layout,
    which is essential for creating truly flexible and resizable UIs.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The key property to prevent the splitter from enforcing a large minimum size
        # based on the combined minimum sizes of its children.
        self.setChildrenCollapsible(False)