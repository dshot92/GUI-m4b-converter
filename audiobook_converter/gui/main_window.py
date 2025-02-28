import re
import logging
import requests
import tempfile
from pathlib import Path
from urllib.parse import urlparse


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
    QMessageBox,
    QInputDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPixmap, QColor, QTextDocument, QIcon, QImageReader

from audiobook_converter.core.converter import ConversionThread
from audiobook_converter.utils.logging import setup_logging
from audiobook_converter.core.m4b_generator import get_audio_title, process_audio_files
from audiobook_converter.core.book_api import search_google_books
from audiobook_converter.regex import (
    RegexPatternWidget,
    RegexListWidget,
    apply_single_pattern,
    process_replacement_text,
    format_number,
)


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
        console_header = QHBoxLayout()
        console_label = QLabel("Console Output:")
        console_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        console_header.addWidget(console_label)

        # Add clear console button
        clear_console_button = QPushButton("Clear Console")
        clear_console_button.clicked.connect(lambda: self.log_output.clear())
        console_header.addWidget(clear_console_button)

        log_layout.addLayout(console_header)

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
        main_layout = QVBoxLayout(main_tab)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(12)

        # Form layout for inputs
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        # Input directory row
        input_widget = QWidget()
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Input Directory")
        self.input_path.textChanged.connect(self.update_chapter_list)
        self.input_path.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.input_path.customContextMenuRequested.connect(self.show_input_context_menu)

        input_button = QPushButton("Browse")
        input_button.clicked.connect(self.select_input_directory)
        input_button.setFixedWidth(100)

        input_layout.addWidget(self.input_path)
        input_layout.addWidget(input_button)

        # Output file row
        output_widget = QWidget()
        output_layout = QHBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)

        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Output M4B File")
        self.output_path.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.output_path.customContextMenuRequested.connect(
            self.show_output_context_menu
        )

        output_button = QPushButton("Browse")
        output_button.clicked.connect(self.select_output_file)
        output_button.setFixedWidth(100)

        output_layout.addWidget(self.output_path)
        output_layout.addWidget(output_button)

        # Add rows to form layout
        form_layout.addRow("Input Directory:", input_widget)
        form_layout.addRow("Output File:", output_widget)

        main_layout.addWidget(form_widget)

        # Convert/Stop button
        self.convert_stop_button = QPushButton("Convert to M4B")
        self.convert_stop_button.clicked.connect(self.handle_convert_stop)
        main_layout.addWidget(self.convert_stop_button)

        main_layout.addStretch()
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
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Create scroll area for the form
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(16)

        # Form layout for metadata fields
        form_widget = QWidget()
        fields_layout = QFormLayout(form_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(8)
        fields_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        fields_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        # Create and style metadata fields
        self.metadata_title = QLineEdit()
        self.metadata_author = QLineEdit()
        self.metadata_narrator = QLineEdit()
        self.metadata_series = QLineEdit()
        self.metadata_series_index = QLineEdit()
        self.metadata_genre = QLineEdit()
        self.metadata_year = QLineEdit()

        # Set size policies and placeholders
        for widget in [
            self.metadata_title,
            self.metadata_author,
            self.metadata_narrator,
            self.metadata_series,
            self.metadata_series_index,
            self.metadata_genre,
            self.metadata_year,
        ]:
            try:
                widget.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
                widget.setMinimumWidth(300)
            except Exception as e:
                logging.error(f"Error setting widget properties: {str(e)}")

        # Set placeholders
        try:
            self.metadata_title.setPlaceholderText("Book title")
            self.metadata_author.setPlaceholderText("Author name")
            self.metadata_narrator.setPlaceholderText("Narrator name")
            self.metadata_series.setPlaceholderText("Series name (if applicable)")
            self.metadata_series_index.setPlaceholderText("Series book number")
            self.metadata_genre.setPlaceholderText("Book genre")
            self.metadata_year.setPlaceholderText("Publication year")
        except Exception as e:
            logging.error(f"Error setting placeholders: {str(e)}")

        # Create title row with search button
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.addWidget(self.metadata_title)
        quick_match_button = QPushButton("Search")
        quick_match_button.setFixedWidth(100)
        quick_match_button.clicked.connect(self.fetch_book_metadata)
        title_layout.addWidget(quick_match_button)

        # Add fields with labels
        try:
            title_widget = QWidget()
            title_widget.setLayout(title_layout)
            fields_layout.addRow("Title:", title_widget)
            fields_layout.addRow("Author:", self.metadata_author)
            fields_layout.addRow("Narrator:", self.metadata_narrator)
            fields_layout.addRow("Series:", self.metadata_series)
            fields_layout.addRow("Series Index:", self.metadata_series_index)
            fields_layout.addRow("Genre:", self.metadata_genre)
            fields_layout.addRow("Year:", self.metadata_year)

            # Add description field to form layout
            self.metadata_description = QTextEdit()
            self.metadata_description.setMinimumHeight(100)
            self.metadata_description.setPlaceholderText("Book description")
            self.metadata_description.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            fields_layout.addRow("Description:", self.metadata_description)

        except Exception as e:
            logging.error(f"Error adding form fields: {str(e)}")

        scroll_layout.addWidget(form_widget)

        # Cover image section with horizontal layout
        cover_widget = QWidget()
        cover_layout = QHBoxLayout(cover_widget)
        cover_layout.setContentsMargins(0, 12, 0, 0)
        cover_layout.setSpacing(8)

        # Left side: Image preview
        try:
            self.cover_image_label = QLabel()
            self.cover_image_label.setFixedSize(200, 200)
            self.cover_image_label.setStyleSheet(
                """
                QLabel {
                    background-color: #2b2b2b;
                    border-radius: 4px;
                    border: 1px solid #3f3f3f;
                }
            """
            )
            self.cover_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cover_image_label.setText("No image selected")
            self.cover_image_label.mousePressEvent = self.show_image_popout
            cover_layout.addWidget(self.cover_image_label)
        except Exception as e:
            logging.error(f"Error setting up cover image label: {str(e)}")

        # Right side: Buttons and image info in vertical layout
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Image info label
        self.image_info_label = QLabel()
        self.image_info_label.setWordWrap(True)
        info_layout.addWidget(self.image_info_label)

        # Buttons
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(8)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Select button
        select_button = QPushButton("Select Image")
        select_button.setFixedWidth(100)
        select_button.clicked.connect(self.select_cover_image)

        # Clear button
        clear_button = QPushButton("Clear Image")
        clear_button.setFixedWidth(100)
        clear_button.clicked.connect(self.clear_cover_image)

        buttons_layout.addWidget(select_button)
        buttons_layout.addWidget(clear_button)
        info_layout.addLayout(buttons_layout)

        cover_layout.addLayout(info_layout)

        scroll_layout.addWidget(cover_widget)
        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

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
        self.bitrate_combo.addItems(
            [
                "Auto",
                "16k",
                "32k",
                "64k",
                "96k",
                "128k",
                "192k",
                "256k",
                "320k",
            ]
        )
        self.bitrate_combo.setCurrentText("Auto")
        form_layout.addRow("Bitrate:", self.bitrate_combo)

        # Sample rate selection
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(
            ["Auto", "22050", "44100", "48000", "96000", "192000"]
        )
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

    def fetch_book_metadata(self):
        """Fetch book metadata from Google Books API."""
        try:
            # Build search query from existing metadata fields
            query_parts = []

            title = self.metadata_title.text().strip()
            author = self.metadata_author.text().strip()

            if title:
                query_parts.append(title)
            if author:
                query_parts.append(f"author:{author}")

            if not query_parts:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "Please enter at least a book title or author name.",
                )
                return

            # Construct query with exclusions for summaries/study guides
            query = (
                " ".join(query_parts) + " -summary -quicklet -cliffnotes -study guide"
            )

            # Get all matching books
            all_metadata = search_google_books(query, multiple=True)
            if not all_metadata:
                QMessageBox.warning(self, "Warning", "No matching book found.")
                return

            # Filter out summaries/study guides
            valid_books = [
                book
                for book in all_metadata
                if not any(
                    x in book.get("title", "").lower()
                    for x in ["summary", "quicklet", "cliffnotes", "study guide"]
                )
            ]

            if not valid_books:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "Found only summaries/study guides. Please try adding the author name if not specified.",
                )
                return

            # Sort by publication date (ascending) to get the earliest edition first
            valid_books.sort(
                key=lambda x: x.get("date", "9999")
            )  # Default to far future if no date

            # Iterate through valid books to find a cover image
            for metadata in valid_books:
                # Update metadata fields with proper error handling
                if not self.metadata_title.text():
                    self.metadata_title.setText(metadata.get("title", ""))
                if not self.metadata_author.text():
                    self.metadata_author.setText(metadata.get("artist", ""))
                if not self.metadata_narrator.text():
                    self.metadata_narrator.setText(metadata.get("album_artist", ""))
                if not self.metadata_series.text():
                    self.metadata_series.setText(metadata.get("album", ""))
                if not self.metadata_series_index.text():
                    self.metadata_series_index.setText(metadata.get("track", ""))
                if not self.metadata_genre.text():
                    self.metadata_genre.setText(metadata.get("genre", ""))
                if not self.metadata_year.text():
                    self.metadata_year.setText(metadata.get("date", ""))
                if not self.metadata_description.toPlainText():
                    self.metadata_description.setText(metadata.get("description", ""))

                # Handle cover image if available
                if "cover_url" in metadata and metadata["cover_url"]:
                    try:
                        # Download the cover image
                        response = requests.get(metadata["cover_url"])
                        response.raise_for_status()

                        # Create a temporary file for the image with proper extension
                        url_path = urlparse(metadata["cover_url"]).path
                        ext = Path(url_path).suffix or ".jpg"

                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=ext
                        ) as tmp_file:
                            tmp_file.write(response.content)
                            self.cover_image_path = tmp_file.name

                        self.update_cover_preview()
                        logging.info("Cover image downloaded successfully")
                        break  # Exit the loop if a cover image is found

                    except Exception as e:
                        logging.error(f"Error downloading cover image: {str(e)}")
                        self.clear_cover_image()

            if not self.cover_image_path:
                logging.warning("No cover image found")

        except Exception as e:
            logging.error(f"Error fetching book metadata: {str(e)}")
            QMessageBox.warning(
                self, "Error", f"Failed to fetch book metadata: {str(e)}"
            )

    def select_cover_image(self):
        # Create a menu with options
        menu = QMenu(self)
        local_action = menu.addAction("Select Local File")
        url_action = menu.addAction("Enter URL")

        # Show menu at the button's position
        action = menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

        if action == local_action:
            # Handle local file selection
            file_name, _ = QFileDialog.getOpenFileName(
                self,
                "Select Cover Image",
                "",
                "Image Files (*.png *.jpg *.jpeg);;All Files (*.*)",
            )
            if file_name:
                try:
                    rel_path = str(Path(file_name).relative_to(Path.cwd()))
                    self.cover_image_path = rel_path
                    self.update_cover_preview()
                except ValueError:
                    self.cover_image_path = file_name
                    self.update_cover_preview()

        elif action == url_action:
            # Handle URL input
            url, ok = QInputDialog.getText(
                self,
                "Enter Image URL",
                "Please enter the URL of the image:",
                QLineEdit.EchoMode.Normal,
            )
            if ok and url:
                try:
                    # Download the image
                    response = requests.get(url)
                    response.raise_for_status()

                    # Get file extension from URL or default to .jpg
                    url_path = urlparse(url).path
                    ext = Path(url_path).suffix
                    if not ext:
                        # Try to determine format from content type
                        content_type = response.headers.get("content-type", "")
                        if "jpeg" in content_type or "jpg" in content_type:
                            ext = ".jpg"
                        elif "png" in content_type:
                            ext = ".png"
                        else:
                            ext = ".jpg"  # Default to jpg

                    # Save to temporary file
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=ext
                    ) as tmp_file:
                        tmp_file.write(response.content)
                        self.cover_image_path = tmp_file.name

                    self.update_cover_preview()
                    logging.info("Cover image downloaded successfully")

                except Exception as e:
                    logging.error(f"Error downloading image: {str(e)}")
                    QMessageBox.warning(
                        self, "Error", f"Failed to download image: {str(e)}"
                    )

    def clear_cover_image(self):
        self.cover_image_path = None
        self.cover_image_label.setText("No image selected")
        self.cover_image_label.setPixmap(QPixmap())

    def update_cover_preview(self):
        if not self.cover_image_path:
            self.image_info_label.setText("")
            return

        pixmap = QPixmap(self.cover_image_path)
        scaled_pixmap = pixmap.scaled(
            self.cover_image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.cover_image_label.setPixmap(scaled_pixmap)

        # Get image dimensions
        width = pixmap.width()
        height = pixmap.height()

        # Get file size in MB
        file_size_mb = Path(self.cover_image_path).stat().st_size / (1024 * 1024)

        # Get image type
        image_type = QImageReader(self.cover_image_path).format().data().decode()

        # Update image info label
        self.image_info_label.setText(
            f"Dimensions: {width}x{height} pixels\n"
            f"Size: {file_size_mb:.2f} MB\n"
            f"Type: {image_type}"
        )

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
                rel_path = str(Path(directory).relative_to(Path.cwd()))
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
                rel_path = str(Path(file_name).relative_to(Path.cwd()))
                self.output_path.setText(rel_path)
            except ValueError:
                self.output_path.setText(file_name)

    def handle_convert_stop(self):
        if self.conversion_thread and self.conversion_thread.isRunning():
            # Stop conversion
            self.conversion_thread.stop()
            self.convert_stop_button.setEnabled(False)
            self.convert_stop_button.setText("Stopping...")
        else:
            # Start conversion
            self.start_conversion()

    def start_conversion(self):
        input_dir = self.input_path.text()
        output_file = self.output_path.text()

        if not input_dir or not output_file:
            logging.error("Please select both input directory and output file")
            return

        input_dir = str(Path(input_dir).absolute())
        output_file = str(Path(output_file).absolute())

        if not Path(input_dir).is_dir():
            logging.error("Invalid input directory")
            return

        # Update button to show stop state
        self.convert_stop_button.setText("Stop")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        metadata = self.get_metadata()
        if metadata.get("cover_path"):
            metadata["cover_path"] = str(Path(metadata["cover_path"]).absolute())

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
                            try:
                                n_pattern_text = n_match.group(0)[
                                    1:-1
                                ]  # Remove { and }
                                formatted_num = format_number(
                                    global_counter - 1, n_pattern_text
                                )
                                actual_replacement = actual_replacement.replace(
                                    n_match.group(0), formatted_num
                                )
                            except Exception as e:
                                logging.error(f"Error formatting number: {str(e)}")
                                continue

                        # Apply the replacement
                        current_title = pattern.sub(actual_replacement, current_title)
                except re.error as e:
                    logging.error(f"Invalid regex pattern: {str(e)}")
                    continue
                except Exception as e:
                    logging.error(f"Error applying pattern: {str(e)}")
                    continue
            chapter_titles.append(current_title)
            global_counter += 1

        self.conversion_thread = ConversionThread(
            input_dir, output_file, metadata, settings, chapter_titles
        )
        self.conversion_thread.finished.connect(self.conversion_finished)
        self.conversion_thread.stopped.connect(self.conversion_stopped)
        self.conversion_thread.error.connect(self.conversion_error)
        self.conversion_thread.start()

    def conversion_stopped(self):
        self.progress_bar.setVisible(False)
        self.convert_stop_button.setEnabled(True)
        self.convert_stop_button.setText("Convert to M4B")
        logging.info("Conversion stopped by user")

    def conversion_finished(self):
        self.progress_bar.setVisible(False)
        self.convert_stop_button.setEnabled(True)
        self.convert_stop_button.setText("Convert to M4B")
        logging.info("Conversion completed successfully!")

    def conversion_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.convert_stop_button.setEnabled(True)
        self.convert_stop_button.setText("Convert to M4B")
        logging.error(f"Conversion failed: {error_message}")

    def update_chapter_list(self):
        input_dir = self.input_path.text()
        if not input_dir:
            return

        abs_input_dir = str(Path(input_dir).absolute())
        if not Path(abs_input_dir).is_dir():
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
            logging.error(f"Error updating chapter list: {str(e)}")

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

    def _process_single_title(
        self, original_title: str, patterns: list[tuple[str, str]], global_counter: int
    ) -> tuple[QListWidgetItem, int]:
        """Process a single title with all regex patterns in sequence.

        Args:
            original_title: Original chapter title
            patterns: List of (pattern, replacement) tuples
            global_counter: Current chapter counter

        Returns:
            Tuple of (QListWidgetItem, updated_counter)
        """
        try:
            current_title = original_title
            item = QListWidgetItem()
            preview_segments = []  # Store rich text segments for each pattern

            # Apply patterns in sequence
            for pattern_text, replacement_text in patterns:
                if not pattern_text:
                    continue

                # Apply pattern and get both the new title and rich text preview
                new_title, rich_text = apply_single_pattern(
                    current_title,
                    pattern_text,
                    replacement_text,
                    global_counter,
                )

                # Store rich text preview if pattern matched
                if rich_text:
                    preview_segments.append(rich_text)

                # Update current title for next pattern in sequence
                current_title = new_title

            # Set the final text and rich text preview
            if preview_segments:
                # Show the last preview that had changes
                item.setText(preview_segments[-1])
            else:
                item.setText(current_title)

            if current_title != original_title:
                self.edited_titles[current_title] = original_title

            return item, global_counter + 1

        except Exception as e:
            logging.error(f"Error processing title: {str(e)}")
            return QListWidgetItem(original_title), global_counter + 1

    def update_chapter_preview(self):
        """Update the chapter preview list with processed titles."""
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
                    self.preview_titles.addItem(QListWidgetItem(title))
                return

            # Process each title with all patterns
            global_counter = 1
            for original_title in self.original_titles:
                item, global_counter = self._process_single_title(
                    original_title, patterns, global_counter
                )
                self.preview_titles.addItem(item)

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

    def show_input_context_menu(self, position):
        input_dir = self.input_path.text()
        try:
            if input_dir and Path(input_dir).absolute().is_dir():
                menu = QMenu()
                open_action = menu.addAction("Open Directory")
                action = menu.exec(self.input_path.mapToGlobal(position))

                if action == open_action:
                    self.open_input_directory()
        except Exception as e:
            logging.error(f"Error showing context menu: {str(e)}")

    def open_input_directory(self):
        input_dir = self.input_path.text()
        if input_dir:
            try:
                abs_path = Path(input_dir).absolute()
                if abs_path.is_dir():
                    import subprocess

                    # Use xdg-open on Linux
                    subprocess.Popen(["xdg-open", str(abs_path)])
            except Exception as e:
                logging.error(f"Error opening directory: {str(e)}")

    def show_output_context_menu(self, position):
        output_file = self.output_path.text()
        try:
            if output_file:
                # Get the parent directory of the output file
                output_dir = Path(output_file).absolute().parent
                if output_dir.is_dir():
                    menu = QMenu()
                    open_action = menu.addAction("Open Directory")
                    action = menu.exec(self.output_path.mapToGlobal(position))

                    if action == open_action:
                        self.open_output_directory()
        except Exception as e:
            logging.error(f"Error showing output context menu: {str(e)}")

    def open_output_directory(self):
        output_file = self.output_path.text()
        if output_file:
            try:
                # Get the parent directory of the output file
                output_dir = Path(output_file).absolute().parent
                if output_dir.is_dir():
                    import subprocess

                    # Use xdg-open on Linux
                    subprocess.Popen(["xdg-open", str(output_dir)])
            except Exception as e:
                logging.error(f"Error opening directory: {str(e)}")

    def show_image_popout(self, event):
        if self.cover_image_path:
            # Create a new window for the popout
            popout_window = QMainWindow(self)
            popout_window.setWindowTitle("Cover Image")
            popout_window.setMinimumSize(600, 600)

            # Create a label to display the image
            popout_label = QLabel(popout_window)
            popout_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Load and scale the image
            pixmap = QPixmap(self.cover_image_path)
            scaled_pixmap = pixmap.scaled(
                popout_window.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            popout_label.setPixmap(scaled_pixmap)

            # Set the label as the central widget
            popout_window.setCentralWidget(popout_label)

            # Show the popout window
            popout_window.show()
