# Audiobook Converter

A GUI application for converting audiobooks to M4B format with chapter support and metadata editing capabilities.

## Features

- Convert audio files to M4B format
- Edit chapter titles using regex patterns
  - Use `{n}` in your pattern to insert an auto-incrementing number
  - Control padding by adding zeros: `{nn}` or `{nnn}` for 2 or 3 digit padding
    - Example: "Chapter {nn}" will generate "Chapter 01", "Chapter 02", etc.
    - Example: "Chapter {nnn}" will generate "Chapter 001", "Chapter 002", etc.
  - Customize increment using `{n+X}` where X is the starting number
    - Example: "Chapter {n+5}" will generate "Chapter 5", "Chapter 6", etc.
  - Combine padding and custom start: `{nnn+10}` generates "010", "011", etc.
  - The increment increases by 1 for each chapter by default
- Add metadata (title, author, narrator, series, etc.)
- Add cover images
- Customize audio settings (codec, bitrate, sample rate)
- User-friendly GUI interface

## Quick Start

Clone the repository:
```bash
git clone https://github.com/yourusername/audiobook-converter.git
cd audiobook-converter
```

Run from the project directory:
```bash
uv run audiobook_converter
```

## Development Setup

1. Create a virtual environment (recommended):
```bash
uv pip install .
```

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

This means you can:
- Use the software for any purpose
- Change the software to suit your needs
- Share the software with your friends and neighbors
- Share the changes you make

The GPL-3.0 ensures that these freedoms are preserved in any derivative works. 