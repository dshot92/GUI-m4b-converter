#!/usr/bin/env python3

import sys
import os

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from audiobook_converter.gui.main_window import AudiobookConverterGUI


def main():
    app = QApplication(sys.argv)
    window = AudiobookConverterGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
