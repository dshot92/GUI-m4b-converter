import sys
from PyQt6.QtCore import QThread, pyqtSignal
from audiobook_converter.core.m4b_generator import generate_m4b


class ConversionThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, input_dir, output_file, metadata=None, settings=None):
        super().__init__()
        self.input_dir = input_dir
        self.output_file = output_file
        self.metadata = metadata
        self.settings = settings

    def run(self):
        try:
            generate_m4b(
                input_dir=self.input_dir,
                output_file=self.output_file,
                metadata=self.metadata,
                settings=self.settings,
            )
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
