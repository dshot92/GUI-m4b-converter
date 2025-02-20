import os
import re
import logging

# Add environment variables to suppress Qt warnings and improve behavior
os.environ["QT_LOGGING_RULES"] = "*=false"
os.environ["XDG_SESSION_TYPE"] = "x11"  # Force X11 mode for better window management
os.environ["QT_QPA_PLATFORM"] = "xcb"  # Use XCB backend for better integration

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
    QListWidgetItem,
    QMenu,
    QStyledItemDelegate,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPixmap, QColor, QTextDocument, QIcon

from audiobook_converter.core.converter import ConversionThread
from audiobook_converter.utils.logging import setup_logging
from audiobook_converter.core.m4b_generator import get_audio_title, process_audio_files


class HTMLDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        options = option
        self.initStyleOption(options, index)

        if options.text:
            doc = QTextDocument()
            doc.setHtml(options.text)
            options.text = ""
            options.widget.style().drawControl(
                options.widget.style().ControlElement.CE_ItemViewItem, options, painter
            )

            painter.save()
            painter.translate(options.rect.left(), options.rect.top())
            clip = QRectF(
                options.rect.translated(-options.rect.left(), -options.rect.top())
            )
            doc.drawContents(painter, clip)
            painter.restore()
        else:
            super().paint(painter, options, index)


class RegexPatternWidget(QFrame):
    patternChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Move buttons
        self.up_button = QPushButton("↑")
        self.up_button.setFixedSize(24, 24)
        self.down_button = QPushButton("↓")
        self.down_button.setFixedSize(24, 24)

        # Pattern input
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("Pattern")
        self.pattern_input.textChanged.connect(self.patternChanged)

        # Replacement input
        self.replacement_input = QLineEdit()
        self.replacement_input.setPlaceholderText("Replace with")
        self.replacement_input.textChanged.connect(self.patternChanged)

        # Remove button
        self.remove_button = QPushButton("×")
        self.remove_button.setFixedSize(24, 24)

        # Add widgets to layout
        layout.addWidget(self.up_button)
        layout.addWidget(self.down_button)
        layout.addWidget(QLabel("Pattern:"))
        layout.addWidget(self.pattern_input, 2)
        layout.addWidget(QLabel("→"))
        layout.addWidget(self.replacement_input, 2)
        layout.addWidget(self.remove_button)

    def get_pattern(self):
        return self.pattern_input.text(), self.replacement_input.text()

    def set_pattern(self, pattern, replacement):
        self.pattern_input.setText(pattern)
        self.replacement_input.setText(replacement)


class RegexListWidget(QListWidget):
    patternsChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setSpacing(4)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

    def get_regex_patterns(self):
        patterns = []
        try:
            for i in range(self.count()):
                item = self.item(i)
                if not item:
                    continue
                widget = self.itemWidget(item)
                if not widget:
                    continue
                try:
                    pattern, replacement = widget.get_pattern()
                    if pattern:  # Only include non-empty patterns
                        patterns.append((pattern, replacement))
                except Exception as e:
                    logging.error(
                        f"Error getting pattern from widget at index {i}: {str(e)}"
                    )
        except Exception as e:
            logging.error(f"Error getting regex patterns: {str(e)}")
        return patterns

    def move_pattern_up(self, item):
        row = self.row(item)
        if row > 0:
            # Store the current pattern and widget state
            current_widget = self.itemWidget(item)
            if not current_widget:
                return
            current_pattern = current_widget.get_pattern()

            # Store the widget above's state
            above_item = self.item(row - 1)
            above_widget = self.itemWidget(above_item)
            if not above_widget:
                return
            above_pattern = above_widget.get_pattern()

            # Create new widgets with the swapped patterns
            new_current = RegexPatternWidget()
            new_current.set_pattern(*above_pattern)
            new_above = RegexPatternWidget()
            new_above.set_pattern(*current_pattern)

            # Connect signals for the current widget (moving down)
            new_current.patternChanged.connect(self.patternsChanged)
            new_current.remove_button.clicked.connect(
                lambda checked=False, i=item: self.remove_pattern(i)
            )
            new_current.up_button.clicked.connect(
                lambda checked=False, i=item: self.move_pattern_up(i)
            )
            new_current.down_button.clicked.connect(
                lambda checked=False, i=item: self.move_pattern_down(i)
            )

            # Connect signals for the above widget (moving up)
            new_above.patternChanged.connect(self.patternsChanged)
            new_above.remove_button.clicked.connect(
                lambda checked=False, i=above_item: self.remove_pattern(i)
            )
            new_above.up_button.clicked.connect(
                lambda checked=False, i=above_item: self.move_pattern_up(i)
            )
            new_above.down_button.clicked.connect(
                lambda checked=False, i=above_item: self.move_pattern_down(i)
            )

            # Set the widgets
            self.setItemWidget(item, new_current)
            self.setItemWidget(above_item, new_above)

            # Update button states and selection
            self.setCurrentItem(above_item)
            self.update_move_buttons()
            self.patternsChanged.emit()

    def move_pattern_down(self, item):
        row = self.row(item)
        if row < self.count() - 1:
            # Store the current pattern and widget state
            current_widget = self.itemWidget(item)
            if not current_widget:
                return
            current_pattern = current_widget.get_pattern()

            # Store the widget below's state
            below_item = self.item(row + 1)
            below_widget = self.itemWidget(below_item)
            if not below_widget:
                return
            below_pattern = below_widget.get_pattern()

            # Create new widgets with the swapped patterns
            new_current = RegexPatternWidget()
            new_current.set_pattern(*below_pattern)
            new_below = RegexPatternWidget()
            new_below.set_pattern(*current_pattern)

            # Connect signals for the current widget (moving down)
            new_current.patternChanged.connect(self.patternsChanged)
            new_current.remove_button.clicked.connect(
                lambda checked=False, i=item: self.remove_pattern(i)
            )
            new_current.up_button.clicked.connect(
                lambda checked=False, i=item: self.move_pattern_up(i)
            )
            new_current.down_button.clicked.connect(
                lambda checked=False, i=item: self.move_pattern_down(i)
            )

            # Connect signals for the below widget (moving up)
            new_below.patternChanged.connect(self.patternsChanged)
            new_below.remove_button.clicked.connect(
                lambda checked=False, i=below_item: self.remove_pattern(i)
            )
            new_below.up_button.clicked.connect(
                lambda checked=False, i=below_item: self.move_pattern_up(i)
            )
            new_below.down_button.clicked.connect(
                lambda checked=False, i=below_item: self.move_pattern_down(i)
            )

            # Set the widgets
            self.setItemWidget(item, new_current)
            self.setItemWidget(below_item, new_below)

            # Update button states and selection
            self.setCurrentItem(below_item)
            self.update_move_buttons()
            self.patternsChanged.emit()

    def update_move_buttons(self):
        for i in range(self.count()):
            item = self.item(i)
            if item:
                widget = self.itemWidget(item)
                if widget:
                    widget.up_button.setEnabled(i > 0)
                    widget.down_button.setEnabled(i < self.count() - 1)

    def add_pattern(self):
        item = QListWidgetItem(self)
        pattern_widget = RegexPatternWidget()

        # Connect signals
        pattern_widget.patternChanged.connect(self.patternsChanged)
        pattern_widget.remove_button.clicked.connect(
            lambda checked=False, item=item: self.remove_pattern(item)
        )
        pattern_widget.up_button.clicked.connect(
            lambda checked=False, item=item: self.move_pattern_up(item)
        )
        pattern_widget.down_button.clicked.connect(
            lambda checked=False, item=item: self.move_pattern_down(item)
        )

        item.setSizeHint(pattern_widget.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, pattern_widget)
        self.update_move_buttons()
        return item

    def remove_pattern(self, item):
        row = self.row(item)
        self.takeItem(row)
        self.update_move_buttons()
        self.patternsChanged.emit()

    def dropEvent(self, event):
        # Store current patterns and widgets before drop
        stored_data = []
        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget:
                pattern = widget.get_pattern()
                stored_data.append((pattern, widget))

        # Handle the drop
        super().dropEvent(event)

        # Restore widgets and patterns after drop
        for i in range(min(len(stored_data), self.count())):
            item = self.item(i)
            if item:
                pattern, old_widget = stored_data[i]
                # Create a new widget to avoid Qt ownership issues
                new_widget = RegexPatternWidget()
                new_widget.set_pattern(*pattern)
                # Connect signals
                new_widget.patternChanged.connect(self.patternsChanged)
                new_widget.remove_button.clicked.connect(
                    lambda checked=False, item=item: self.remove_pattern(item)
                )
                new_widget.up_button.clicked.connect(
                    lambda checked=False, item=item: self.move_pattern_up(item)
                )
                new_widget.down_button.clicked.connect(
                    lambda checked=False, item=item: self.move_pattern_down(item)
                )
                # Set the widget
                item.setSizeHint(new_widget.sizeHint())
                self.setItemWidget(item, new_widget)

        self.update_move_buttons()
        self.patternsChanged.emit()


class AudiobookConverterGUI(QMainWindow):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audiobook Converter")
        self.setMinimumSize(800, 600)

        # Set window to expand by default
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.chapter_files = []
        self.original_titles = []  # Initialize original_titles list
        self.cover_image_path = None
        self.conversion_thread = None
        self.edited_titles = {}  # Change to dict to store original->edited mapping
        self.is_editing = False  # Track if we're currently editing
        self._edit_handler_connected = False  # Track signal connection state

        # Dictionary to store splitters for each tab
        self.tab_splitters = {}

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create main vertical splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(
            False
        )  # Prevent sections from being collapsed
        layout.addWidget(self.main_splitter)

        # Upper section with tabs and progress bar
        upper_widget = QWidget()
        upper_widget.setMinimumHeight(400)  # Set minimum height
        upper_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        upper_layout = QVBoxLayout(upper_widget)
        upper_layout.setContentsMargins(4, 4, 4, 4)

        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_tab_context_menu)
        upper_layout.addWidget(self.tabs)

        # Create individual tabs
        self.create_main_tab()
        self.create_chapters_tab()
        self.create_metadata_tab()
        self.create_settings_tab()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        upper_layout.addWidget(self.progress_bar)

        self.main_splitter.addWidget(upper_widget)

        # Log output
        log_widget = QWidget()
        log_widget.setMinimumHeight(100)  # Set minimum height for console
        log_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(4, 4, 4, 4)

        # Add a label for the console
        console_label = QLabel("Console Output:")
        console_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        log_layout.addWidget(console_label)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(50)  # Set minimum height for text area
        self.log_output.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        log_layout.addWidget(self.log_output)

        self.main_splitter.addWidget(log_widget)

        # Set initial sizes (80% for upper section, 20% for console)
        self.main_splitter.setSizes([800, 200])

        # Store main splitter in tab_splitters for reset functionality
        self.tab_splitters["main"] = [(self.main_splitter, [800, 200])]

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
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a splitter for resizable sections
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)  # Prevent sections from being collapsed
        layout.addWidget(splitter)

        # Preview titles with edit functionality
        titles_widget = QWidget()
        titles_widget.setMinimumHeight(200)  # Set minimum height
        titles_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        preview_layout = QVBoxLayout(titles_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(QLabel("Chapter Titles:"))
        self.preview_titles = QListWidget()
        self.preview_titles.setMinimumHeight(150)  # Set minimum height
        self.preview_titles.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_titles.setItemDelegate(HTMLDelegate(self.preview_titles))
        self.preview_titles.itemDoubleClicked.connect(self.edit_title)
        self.preview_titles.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.preview_titles.customContextMenuRequested.connect(self.show_context_menu)
        preview_layout.addWidget(self.preview_titles)
        splitter.addWidget(titles_widget)

        # Regex patterns panel
        regex_widget = QWidget()
        regex_widget.setMinimumHeight(100)
        regex_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        regex_layout = QVBoxLayout(regex_widget)
        regex_layout.setContentsMargins(0, 0, 0, 0)

        # Header for regex panel
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Regex Patterns:"))
        add_pattern_button = QPushButton("+")
        add_pattern_button.setFixedWidth(30)
        add_pattern_button.clicked.connect(self.add_regex_pattern)
        header_layout.addWidget(add_pattern_button)
        header_layout.addStretch()
        regex_layout.addLayout(header_layout)

        # List widget for patterns
        self.patterns_list = RegexListWidget()
        self.patterns_list.patternsChanged.connect(self.update_chapter_preview)
        regex_layout.addWidget(self.patterns_list)

        splitter.addWidget(regex_widget)

        # Store splitter reference and default sizes
        self.tab_splitters["Chapter Titles"] = [(splitter, [700, 300])]

        # Set initial sizes (70% for titles, 30% for regex)
        splitter.setSizes([700, 300])

        self.tabs.addTab(chapters_tab, "Chapter Titles")

    def create_metadata_tab(self):
        metadata_tab = QWidget()
        layout = QVBoxLayout(metadata_tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create vertical splitter for the whole tab
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setChildrenCollapsible(
            False
        )  # Prevent sections from being collapsed
        layout.addWidget(main_splitter)

        # Upper section with form fields
        form_widget = QWidget()
        form_widget.setMinimumHeight(300)  # Set minimum height
        form_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(4, 4, 4, 4)

        # Form layout for metadata fields
        fields_layout = QFormLayout()

        # Basic metadata fields
        self.metadata_title = QLineEdit()
        self.metadata_author = QLineEdit()
        self.metadata_narrator = QLineEdit()
        self.metadata_series = QLineEdit()
        self.metadata_series_index = QLineEdit()
        self.metadata_genre = QLineEdit()
        self.metadata_year = QLineEdit()

        fields_layout.addRow("Title:", self.metadata_title)
        fields_layout.addRow("Author:", self.metadata_author)
        fields_layout.addRow("Narrator:", self.metadata_narrator)
        fields_layout.addRow("Series:", self.metadata_series)
        fields_layout.addRow("Series Index:", self.metadata_series_index)
        fields_layout.addRow("Genre:", self.metadata_genre)
        fields_layout.addRow("Year:", self.metadata_year)
        form_layout.addLayout(fields_layout)

        # Description section
        form_layout.addWidget(QLabel("Description:"))
        self.metadata_description = QTextEdit()
        form_layout.addWidget(self.metadata_description)

        main_splitter.addWidget(form_widget)

        # Cover image section
        cover_widget = QWidget()
        cover_widget.setMinimumHeight(250)  # Set minimum height
        cover_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        cover_layout = QHBoxLayout(cover_widget)
        cover_layout.setContentsMargins(4, 4, 4, 4)

        # Image preview
        self.cover_image_label = QLabel()
        self.cover_image_label.setMinimumSize(200, 200)
        self.cover_image_label.setStyleSheet("border: 1px solid gray")
        self.cover_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_image_label.setText("No image selected")
        cover_layout.addWidget(self.cover_image_label)

        # Image buttons layout
        button_widget = QWidget()
        button_layout = QVBoxLayout(button_widget)
        select_image_button = QPushButton("Select Cover Image")
        select_image_button.clicked.connect(self.select_cover_image)
        clear_image_button = QPushButton("Clear Image")
        clear_image_button.clicked.connect(self.clear_cover_image)

        button_layout.addWidget(select_image_button)
        button_layout.addWidget(clear_image_button)
        button_layout.addStretch()
        cover_layout.addWidget(button_widget)

        main_splitter.addWidget(cover_widget)

        # Store splitter reference and default sizes
        self.tab_splitters["Metadata"] = [(main_splitter, [700, 300])]

        # Set initial sizes (70% for form, 30% for cover)
        main_splitter.setSizes([700, 300])

        self.tabs.addTab(metadata_tab, "Metadata")

    def create_settings_tab(self):
        settings_tab = QWidget()
        layout = QVBoxLayout(settings_tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create vertical splitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)  # Prevent sections from being collapsed
        layout.addWidget(splitter)

        # Settings section
        settings_widget = QWidget()
        settings_widget.setMinimumHeight(200)  # Set minimum height
        settings_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setContentsMargins(4, 4, 4, 4)
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

        settings_layout.addLayout(form_layout)
        settings_layout.addStretch()
        splitter.addWidget(settings_widget)

        # Add a placeholder widget for future settings sections
        future_widget = QWidget()
        future_layout = QVBoxLayout(future_widget)
        future_layout.setContentsMargins(4, 4, 4, 4)
        splitter.addWidget(future_widget)

        # Store splitter reference and default sizes
        self.tab_splitters["Settings"] = [(splitter, [700, 300])]

        # Set initial sizes
        splitter.setSizes([700, 300])

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

        # Get edited chapter titles after all regex patterns
        chapter_titles = []
        patterns = self.patterns_list.get_regex_patterns()
        global_counter = 1

        for i, original_title in enumerate(self.original_titles):
            current_title = original_title
            # Apply each pattern in sequence
            for pattern_text, replacement_text in patterns:
                if not pattern_text:  # Skip empty patterns
                    continue
                try:
                    pattern = re.compile(pattern_text)
                    if pattern.search(current_title):
                        # Find all {n} patterns in replacement text
                        n_pattern = re.compile(r"\{n+(?:\+\d+)?\}")
                        actual_replacement = replacement_text
                        for n_match in n_pattern.finditer(replacement_text):
                            n_pattern_text = n_match.group(0)[1:-1]  # Remove { and }
                            formatted_num = self.format_number(
                                global_counter - 1, n_pattern_text
                            )
                            actual_replacement = actual_replacement.replace(
                                n_match.group(0), formatted_num
                            )
                        current_title = pattern.sub(actual_replacement, current_title)
                except re.error:
                    continue
            chapter_titles.append(current_title)
            global_counter += 1

        self.conversion_thread = ConversionThread(
            input_dir, output_file, metadata, settings, chapter_titles
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
            self.original_titles = []  # Store original titles in a list
            self.preview_titles.clear()

            for file in self.chapter_files:
                title = get_audio_title(file)
                self.original_titles.append(title)
                item = QListWidgetItem(title)
                self.preview_titles.addItem(item)

            self.update_chapter_preview()
        except Exception as e:
            logging.error(f"Error loading chapter titles: {str(e)}")

    def edit_title(self, item):
        if self.is_editing:  # Prevent multiple edits at once
            return

        self.is_editing = True
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

        # Only connect if not already connected
        if not self._edit_handler_connected:
            self.preview_titles.itemChanged.connect(self.handle_title_edit)
            self._edit_handler_connected = True

        self.preview_titles.editItem(item)

    def handle_title_edit(self, item):
        if not self.is_editing:  # Skip if we're not in edit mode
            return

        index = self.preview_titles.row(item)
        original_title = self.original_titles[index]

        # Store both original and edited title
        self.edited_titles[item.text()] = original_title

        # Show both deletion and addition in the same item
        item.setBackground(QColor(230, 255, 237))  # Light green background
        item.setForeground(QColor(36, 41, 47))  # Dark gray text

        # Only disconnect if connected
        if self._edit_handler_connected:
            try:
                self.preview_titles.itemChanged.disconnect(self.handle_title_edit)
            except TypeError:
                pass  # Ignore if already disconnected
            self._edit_handler_connected = False

        self.is_editing = False

    def show_context_menu(self, position):
        item = self.preview_titles.itemAt(position)
        if item and item.text() in self.edited_titles:
            menu = QMenu()
            reset_action = menu.addAction("Reset to Original")
            action = menu.exec(self.preview_titles.mapToGlobal(position))

            if action == reset_action:
                # Get the index of the current item
                index = self.preview_titles.row(item)
                # Get the original title
                original_title = self.original_titles[index]
                # Remove from edited titles
                self.edited_titles.pop(item.text())
                # Reset the item with a new item to get default colors
                new_item = QListWidgetItem(original_title)
                self.preview_titles.takeItem(index)
                self.preview_titles.insertItem(index, new_item)

    def add_regex_pattern(self):
        self.patterns_list.add_pattern()
        self.update_chapter_preview()

    def update_move_buttons(self):
        self.patterns_list.update_move_buttons()

    def move_pattern_up(self, item):
        self.patterns_list.move_pattern_up(item)
        self.update_chapter_preview()

    def move_pattern_down(self, item):
        self.patterns_list.move_pattern_down(item)
        self.update_chapter_preview()

    def remove_regex_pattern(self, item):
        self.patterns_list.remove_pattern(item)
        self.update_chapter_preview()

    def update_chapter_preview(self):
        if not hasattr(self, "original_titles"):
            self.original_titles = []

        try:
            patterns = self.patterns_list.get_regex_patterns()
            self.preview_titles.clear()

            if not self.original_titles:
                return

            # If no patterns or all patterns are empty, show original titles
            if not patterns or all(not pattern[0] for pattern in patterns):
                for title in self.original_titles:
                    item = QListWidgetItem(title)
                    self.preview_titles.addItem(item)
                return

            # Global counter for each file
            global_counter = 1

            for i, original_title in enumerate(self.original_titles):
                try:
                    current_title = original_title
                    item = QListWidgetItem()
                    rich_text = ""
                    last_end = 0

                    # Apply each pattern in sequence
                    for pattern_text, replacement_text in patterns:
                        if not pattern_text:  # Skip empty patterns
                            continue
                        try:
                            pattern = re.compile(pattern_text)
                            matches = list(pattern.finditer(current_title))

                            if matches:
                                # Build rich text with highlighting
                                rich_text = ""
                                last_end = 0

                                for match in matches:
                                    # Add text before match
                                    rich_text += current_title[last_end : match.start()]

                                    if replacement_text:
                                        # Find all {n} patterns in replacement text
                                        n_pattern = re.compile(r"\{n+(?:\+\d+)?\}")
                                        actual_replacement = replacement_text

                                        for n_match in n_pattern.finditer(
                                            replacement_text
                                        ):
                                            n_pattern_text = n_match.group(0)[
                                                1:-1
                                            ]  # Remove { and }
                                            formatted_num = self.format_number(
                                                global_counter - 1, n_pattern_text
                                            )
                                            actual_replacement = (
                                                actual_replacement.replace(
                                                    n_match.group(0), formatted_num
                                                )
                                            )

                                        # Add the replacement with background color and text color
                                        rich_text += f'<span style="background-color: #E6FFE6; color: #28a745;">{actual_replacement}</span>'
                                    else:
                                        # Show match in red if no replacement
                                        match_text = current_title[
                                            match.start() : match.end()
                                        ]
                                        rich_text += f'<span style="background-color: #FFE6E6; color: #FF0000;">{match_text}</span>'
                                    last_end = match.end()

                                # Add remaining text
                                rich_text += current_title[last_end:]

                                # Update current title for next pattern
                                def replace_with_counter(m):
                                    nonlocal global_counter
                                    # Find all {n} patterns in replacement text
                                    n_pattern = re.compile(r"\{n+(?:\+\d+)?\}")
                                    result = replacement_text
                                    for n_match in n_pattern.finditer(replacement_text):
                                        n_pattern_text = n_match.group(0)[
                                            1:-1
                                        ]  # Remove { and }
                                        formatted_num = self.format_number(
                                            global_counter - 1, n_pattern_text
                                        )
                                        result = result.replace(
                                            n_match.group(0), formatted_num
                                        )
                                    return result

                                current_title = pattern.sub(
                                    (
                                        replace_with_counter
                                        if re.search(
                                            r"\{n+(?:\+\d+)?\}", replacement_text
                                        )
                                        else replacement_text
                                    ),
                                    current_title,
                                )

                        except re.error:
                            # Skip invalid regex patterns
                            continue

                    # Set the final text
                    if rich_text:
                        item.setText(rich_text)
                    else:
                        item.setText(current_title)

                    if current_title != original_title:
                        self.edited_titles[current_title] = original_title

                    self.preview_titles.addItem(item)
                    global_counter += 1

                except Exception as e:
                    logging.error(f"Error processing title: {str(e)}")
                    self.preview_titles.addItem(QListWidgetItem(original_title))

        except Exception as e:
            logging.error(f"Error updating chapter preview: {str(e)}")
            self.preview_titles.clear()
            # Restore original titles
            for title in self.original_titles:
                self.preview_titles.addItem(QListWidgetItem(title))

    def show_tab_context_menu(self, position):
        # Get the tab under the cursor
        tab_bar = self.tabs.tabBar()
        tab_index = tab_bar.tabAt(position)

        if tab_index >= 0:
            menu = QMenu()
            reset_action = menu.addAction("Reset Layout")
            action = menu.exec(self.tabs.mapToGlobal(position))

            if action == reset_action:
                self.reset_tab_layout(tab_index)

    def reset_tab_layout(self, tab_index):
        tab_name = self.tabs.tabText(tab_index)
        splitters = self.tab_splitters.get(tab_name, [])

        # Reset each splitter in the tab
        for splitter, sizes in splitters:
            splitter.setSizes(sizes)

        # Also reset main splitter if we're resetting any tab
        self.main_splitter.setSizes([800, 200])

    def format_number(self, num: int, pattern: str) -> str:
        """Format a number according to the pattern.

        Args:
            num: The number to format
            pattern: Pattern like 'n', 'nn', 'nnn', 'n+5', 'nn+10', etc.

        Returns:
            Formatted number string with proper padding and offset
        """
        # Extract padding and start number from pattern
        padding = pattern.count("n")
        start = 0
        if "+" in pattern:
            start = int(pattern.split("+")[1])
        num = num + start
        return f"{num:0{padding}d}"
