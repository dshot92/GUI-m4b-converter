#!/usr/bin/env python3

import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.absolute()))

from PyQt6.QtWidgets import QApplication
from audiobook_converter.gui.main_window import AudiobookConverterGUI


def main():
  app = QApplication(sys.argv)
  window = AudiobookConverterGUI()
  window.show()
  sys.exit(app.exec())


if __name__ == "__main__":
  main()
