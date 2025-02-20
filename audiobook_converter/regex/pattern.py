import re
import logging
from typing import Tuple, Optional


def format_number(num: int, pattern: str) -> str:
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


def process_replacement_text(replacement_text: str, global_counter: int) -> str:
    """Process replacement text, handling {n} patterns.

    Args:
        replacement_text: The replacement pattern
        global_counter: Current chapter counter

    Returns:
        Processed replacement text with {n} patterns replaced
    """
    try:
        n_pattern = re.compile(r"\{n+(?:\+\d+)?\}")
        actual_replacement = replacement_text

        for n_match in n_pattern.finditer(replacement_text):
            n_pattern_text = n_match.group(0)[1:-1]  # Remove { and }
            formatted_num = format_number(global_counter - 1, n_pattern_text)
            actual_replacement = actual_replacement.replace(
                n_match.group(0), formatted_num
            )

        return actual_replacement
    except Exception as e:
        logging.error(f"Error processing replacement pattern: {str(e)}")
        return replacement_text


def apply_single_pattern(
    title: str, pattern_text: str, replacement_text: str, global_counter: int
) -> Tuple[str, str]:
    """Apply a single regex pattern to a title and generate rich text preview.

    Args:
        title: The title to process
        pattern_text: The regex pattern to match
        replacement_text: The replacement text (may contain {n} placeholders)
        global_counter: Current chapter counter

    Returns:
        Tuple of (processed_title, rich_text_preview)
    """
    try:
        pattern = re.compile(pattern_text)
        matches = list(pattern.finditer(title))
        if not matches:
            return title, ""

        # First process the actual title replacement to get the new title
        def replace_with_counter(m):
            return process_replacement_text(replacement_text, global_counter)

        if re.search(r"\{n+(?:\+\d+)?\}", replacement_text):
            processed_title = pattern.sub(replace_with_counter, title)
        else:
            processed_title = pattern.sub(replacement_text, title)

        # Then generate rich text preview showing the changes
        rich_text = ""
        last_end = 0

        for match in matches:
            # Add text before match
            rich_text += title[last_end : match.start()]

            if replacement_text:
                actual_replacement = process_replacement_text(
                    replacement_text, global_counter
                )
                rich_text += f'<span style="background-color: #E6FFE6; color: #28a745;">{actual_replacement}</span>'
            else:
                # Show match in red if no replacement
                match_text = title[match.start() : match.end()]
                rich_text += f'<span style="background-color: #FFE6E6; color: #FF0000;">{match_text}</span>'

            last_end = match.end()

        # Add remaining text
        rich_text += title[last_end:]

        return processed_title, rich_text

    except (re.error, Exception) as e:
        logging.error(f"Error applying pattern: {str(e)}")
        return title, ""
