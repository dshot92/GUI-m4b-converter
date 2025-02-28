import logging
from typing import List, Tuple
from PyQt6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QPushButton,
  QLineEdit,
  QLabel,
  QListWidget,
  QListWidgetItem,
  QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt


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

  def get_pattern(self) -> Tuple[str, str]:
    return self.pattern_input.text(), self.replacement_input.text()

  def set_pattern(self, pattern: str, replacement: str) -> None:
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

  def get_regex_patterns(self) -> List[Tuple[str, str]]:
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

  def move_pattern_up(self, item: QListWidgetItem) -> None:
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

  def move_pattern_down(self, item: QListWidgetItem) -> None:
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

  def update_move_buttons(self) -> None:
    for i in range(self.count()):
      item = self.item(i)
      if item:
        widget = self.itemWidget(item)
        if widget:
          widget.up_button.setEnabled(i > 0)
          widget.down_button.setEnabled(i < self.count() - 1)

  def add_pattern(self) -> QListWidgetItem:
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

  def remove_pattern(self, item: QListWidgetItem) -> None:
    row = self.row(item)
    self.takeItem(row)
    self.update_move_buttons()
    self.patternsChanged.emit()

  def dropEvent(self, event) -> None:
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
