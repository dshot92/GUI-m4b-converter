import sys
from PyQt6.QtCore import QThread, pyqtSignal
from audiobook_converter.core.m4b_generator import generate_m4b
from typing import Dict, List, Optional


class ConversionThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        input_dir: str,
        output_file: str,
        metadata: Optional[Dict] = None,
        settings: Optional[Dict] = None,
        chapter_titles: Optional[List[str]] = None,
    ):
        super().__init__()
        self.input_dir = input_dir
        self.output_file = output_file
        self.metadata = metadata
        self.settings = settings
        self.chapter_titles = chapter_titles

    def run(self):
        try:
            generate_m4b(
                input_dir=self.input_dir,
                output_file=self.output_file,
                metadata=self.metadata,
                settings=self.settings,
                chapter_titles=self.chapter_titles,
            )
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
