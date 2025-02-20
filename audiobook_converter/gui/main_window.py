import os
import re
import logging
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
    QFileDialog,
    QProgressBar,
    QTextEdit,
    QListWidget,
    QTabWidget,
    QFormLayout,
    QComboBox,
    QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

from audiobook_converter.core.converter import ConversionThread
from audiobook_converter.utils.logging import setup_logging
from audiobook_converter.core.m4b_generator import get_mp3_title, process_audio_files


class AudiobookConverterGUI(QMainWindow):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audiobook Converter")
        self.setMinimumSize(800, 600)
        self.chapter_files = []
        self.cover_image_path = None
        self.conversion_thread = None

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create individual tabs
        self.create_main_tab()
        self.create_chapters_tab()
        self.create_metadata_tab()
        self.create_settings_tab()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

        # Set up logging
        setup_logging(self.log_signal)
        self.log_signal.connect(self.update_log)

    def create_main_tab(self):
        main_tab = QWidget()
        layout = QVBoxLayout(main_tab)

        # Input directory selection
        input_layout = QHBoxLayout()
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Input Directory")
        self.input_path.textChanged.connect(self.update_chapter_list)
        input_button = QPushButton("Browse")
        input_button.clicked.connect(self.select_input_directory)
        input_layout.addWidget(QLabel("Input Directory:"))
        input_layout.addWidget(self.input_path)
        input_layout.addWidget(input_button)
        layout.addLayout(input_layout)

        # Output file selection
        output_layout = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Output M4B File")
        output_button = QPushButton("Browse")
        output_button.clicked.connect(self.select_output_file)
        output_layout.addWidget(QLabel("Output File:"))
        output_layout.addWidget(self.output_path)
        output_layout.addWidget(output_button)
        layout.addLayout(output_layout)

        # Convert button
        self.convert_button = QPushButton("Convert to M4B")
        self.convert_button.clicked.connect(self.start_conversion)
        layout.addWidget(self.convert_button)

        layout.addStretch()
        self.tabs.addTab(main_tab, "Input/Output")

    def create_chapters_tab(self):
        chapters_tab = QWidget()
        layout = QVBoxLayout(chapters_tab)

        # Chapter title regex
        regex_layout = QHBoxLayout()
        self.regex_input = QLineEdit()
        self.regex_input.setPlaceholderText(
            "Enter regex pattern for title modification"
        )
        self.regex_input.textChanged.connect(self.update_chapter_preview)
        regex_layout.addWidget(QLabel("Title Regex:"))
        regex_layout.addWidget(self.regex_input)
        layout.addLayout(regex_layout)

        # Chapter list
        chapters_layout = QHBoxLayout()

        # Original titles
        original_layout = QVBoxLayout()
        original_layout.addWidget(QLabel("Original Titles:"))
        self.original_titles = QListWidget()
        original_layout.addWidget(self.original_titles)
        chapters_layout.addLayout(original_layout)

        # Preview titles
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(QLabel("Preview Titles:"))
        self.preview_titles = QListWidget()
        preview_layout.addWidget(self.preview_titles)
        chapters_layout.addLayout(preview_layout)

        layout.addLayout(chapters_layout)
        self.tabs.addTab(chapters_tab, "Chapter Titles")

    def create_metadata_tab(self):
        metadata_tab = QWidget()
        layout = QVBoxLayout(metadata_tab)

        # Form layout for metadata fields
        form_layout = QFormLayout()

        # Metadata fields
        self.metadata_title = QLineEdit()
        self.metadata_author = QLineEdit()
        self.metadata_narrator = QLineEdit()
        self.metadata_series = QLineEdit()
        self.metadata_series_index = QLineEdit()
        self.metadata_genre = QLineEdit()
        self.metadata_year = QLineEdit()
        self.metadata_description = QTextEdit()
        self.metadata_description.setMaximumHeight(100)

        form_layout.addRow("Title:", self.metadata_title)
        form_layout.addRow("Author:", self.metadata_author)
        form_layout.addRow("Narrator:", self.metadata_narrator)
        form_layout.addRow("Series:", self.metadata_series)
        form_layout.addRow("Series Index:", self.metadata_series_index)
        form_layout.addRow("Genre:", self.metadata_genre)
        form_layout.addRow("Year:", self.metadata_year)
        form_layout.addRow("Description:", self.metadata_description)

        layout.addLayout(form_layout)

        # Cover image section
        image_layout = QHBoxLayout()

        # Image preview
        self.cover_image_label = QLabel()
        self.cover_image_label.setFixedSize(200, 200)
        self.cover_image_label.setStyleSheet("border: 1px solid gray")
        self.cover_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_image_label.setText("No image selected")
        image_layout.addWidget(self.cover_image_label)

        # Image buttons layout
        image_buttons_layout = QVBoxLayout()
        select_image_button = QPushButton("Select Cover Image")
        select_image_button.clicked.connect(self.select_cover_image)
        clear_image_button = QPushButton("Clear Image")
        clear_image_button.clicked.connect(self.clear_cover_image)

        image_buttons_layout.addWidget(select_image_button)
        image_buttons_layout.addWidget(clear_image_button)
        image_buttons_layout.addStretch()

        image_layout.addLayout(image_buttons_layout)
        image_layout.addStretch()

        layout.addLayout(image_layout)
        layout.addStretch()

        self.tabs.addTab(metadata_tab, "Metadata")

    def create_settings_tab(self):
        settings_tab = QWidget()
        layout = QVBoxLayout(settings_tab)
        form_layout = QFormLayout()

        # Audio codec selection
        self.codec_combo = QComboBox()
        self.codec_combo.addItems(["Auto (Copy if possible)", "AAC", "AAC-LC"])
        form_layout.addRow("Audio Codec:", self.codec_combo)

        # Bitrate selection
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["64k", "96k", "128k", "192k", "256k"])
        self.bitrate_combo.setCurrentText("128k")
        form_layout.addRow("Bitrate:", self.bitrate_combo)

        # Sample rate selection
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["Auto", "44100", "48000", "22050"])
        form_layout.addRow("Sample Rate:", self.sample_rate_combo)

        # Force conversion checkbox
        self.force_conversion = QCheckBox("Force conversion (ignore source format)")
        self.force_conversion.setChecked(False)
        form_layout.addRow(self.force_conversion)

        layout.addLayout(form_layout)
        layout.addStretch()
        self.tabs.addTab(settings_tab, "Settings")

    def select_cover_image(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select Cover Image",
            "",
            "Image Files (*.png *.jpg *.jpeg);;All Files (*.*)",
        )
        if file_name:
            try:
                rel_path = os.path.relpath(file_name)
                self.cover_image_path = rel_path
            except ValueError:
                self.cover_image_path = file_name
            self.update_cover_preview()

    def clear_cover_image(self):
        self.cover_image_path = None
        self.cover_image_label.setText("No image selected")
        self.cover_image_label.setPixmap(QPixmap())

    def update_cover_preview(self):
        if not self.cover_image_path:
            return

        pixmap = QPixmap(self.cover_image_path)
        scaled_pixmap = pixmap.scaled(
            self.cover_image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.cover_image_label.setPixmap(scaled_pixmap)

    def get_metadata(self):
        metadata = {
            "title": self.metadata_title.text(),
            "artist": self.metadata_author.text(),
            "album_artist": self.metadata_narrator.text(),
            "album": self.metadata_series.text(),
            "track": self.metadata_series_index.text(),
            "genre": self.metadata_genre.text(),
            "date": self.metadata_year.text(),
            "description": self.metadata_description.toPlainText(),
        }

        if self.cover_image_path:
            metadata["cover_path"] = self.cover_image_path

        return metadata

    def get_conversion_settings(self):
        return {
            "codec": self.codec_combo.currentText(),
            "bitrate": self.bitrate_combo.currentText(),
            "sample_rate": self.sample_rate_combo.currentText(),
            "force_conversion": self.force_conversion.isChecked(),
        }

    def update_log(self, message):
        self.log_output.append(message)

    def select_input_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Input Directory")
        if directory:
            try:
                rel_path = os.path.relpath(directory)
                self.input_path.setText(rel_path)
            except ValueError:
                self.input_path.setText(directory)

    def select_output_file(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save M4B File", "", "M4B Files (*.m4b);;All Files (*.*)"
        )
        if file_name:
            if not file_name.lower().endswith(".m4b"):
                file_name += ".m4b"
            try:
                rel_path = os.path.relpath(file_name)
                self.output_path.setText(rel_path)
            except ValueError:
                self.output_path.setText(file_name)

    def start_conversion(self):
        input_dir = self.input_path.text()
        output_file = self.output_path.text()

        if not input_dir or not output_file:
            logging.error("Please select both input directory and output file")
            return

        input_dir = os.path.abspath(input_dir)
        output_file = os.path.abspath(output_file)

        if not os.path.isdir(input_dir):
            logging.error("Invalid input directory")
            return

        self.convert_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        metadata = self.get_metadata()
        if metadata.get("cover_path"):
            metadata["cover_path"] = os.path.abspath(metadata["cover_path"])

        settings = self.get_conversion_settings()

        self.conversion_thread = ConversionThread(
            input_dir, output_file, metadata, settings
        )
        self.conversion_thread.finished.connect(self.conversion_finished)
        self.conversion_thread.error.connect(self.conversion_error)
        self.conversion_thread.start()

    def conversion_finished(self):
        self.progress_bar.setVisible(False)
        self.convert_button.setEnabled(True)
        logging.info("Conversion completed successfully!")

    def conversion_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.convert_button.setEnabled(True)
        logging.error(f"Conversion failed: {error_message}")

    def update_chapter_list(self):
        input_dir = self.input_path.text()
        if not input_dir:
            return

        abs_input_dir = os.path.abspath(input_dir)
        if not os.path.isdir(abs_input_dir):
            return

        try:
            self.chapter_files = process_audio_files(abs_input_dir, False)
            self.original_titles.clear()
            self.preview_titles.clear()

            for file in self.chapter_files:
                title = get_mp3_title(file)
                self.original_titles.addItem(title)
                self.preview_titles.addItem(title)

            self.update_chapter_preview()
        except Exception as e:
            logging.error(f"Error loading chapter titles: {str(e)}")

    def update_chapter_preview(self):
        regex_pattern = self.regex_input.text()
        if not regex_pattern:
            self.preview_titles.clear()
            for i in range(self.original_titles.count()):
                self.preview_titles.addItem(self.original_titles.item(i).text())
            return

        try:
            re.compile(regex_pattern)
            self.preview_titles.clear()

            for i in range(self.original_titles.count()):
                original_title = self.original_titles.item(i).text()
                try:
                    new_title = re.sub(
                        regex_pattern,
                        r"\1" if "(" in regex_pattern else "",
                        original_title,
                    )
                    self.preview_titles.addItem(new_title)
                except Exception as e:
                    self.preview_titles.addItem(f"Error: {str(e)}")
        except re.error:
            self.preview_titles.clear()
            for i in range(self.original_titles.count()):
                self.preview_titles.addItem("Invalid regex pattern")
