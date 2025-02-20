#!/usr/bin/env python3
"""
Convert a collection of MP3/M4A files into a single M4B audiobook with chapters.

This script takes a directory of audio files (MP3 or M4A) and combines them into a single
M4B audiobook file with chapter markers. Chapter titles are derived from the audio file
metadata or filenames.

Dependencies:
    - ffmpeg: Required for audio processing and metadata extraction
    - ffprobe: Required for audio file analysis (usually comes with ffmpeg)
"""

import os
import subprocess
import glob
import argparse
from typing import List
import logging
from pathlib import Path
import json


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def check_dependencies() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        logging.error("ffmpeg or ffprobe not found. Please install ffmpeg.")
        return False
    except FileNotFoundError:
        logging.error("ffmpeg or ffprobe not found. Please install ffmpeg.")
        return False


def get_mp3_duration(filename: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-i",
                filename,
                "-show_entries",
                "format=duration",
                "-v",
                "quiet",
                "-of",
                "csv=p=0",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        logging.error(f"Failed to get duration for {filename}: {str(e)}")
        raise


def get_mp3_title(filename: str) -> str:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-i",
                filename,
                "-show_entries",
                "format_tags=title",
                "-v",
                "quiet",
                "-of",
                "csv=p=0",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or Path(filename).stem
    except subprocess.CalledProcessError:
        logging.warning(f"Failed to get title metadata for {filename}, using filename")
        return Path(filename).stem


def create_chapter_file(mp3_files: List[str], output_file: str) -> None:
    start_time = 0
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        for mp3 in mp3_files:
            try:
                duration = get_mp3_duration(mp3) * 1000  # Convert to milliseconds
                title = get_mp3_title(mp3)
                f.write("\n[CHAPTER]\n")
                f.write("TIMEBASE=1/1000\n")
                f.write(f"START={int(start_time)}\n")
                f.write(f"END={int(start_time + duration)}\n")
                f.write(f"title={title}\n")
                start_time += duration
            except (subprocess.CalledProcessError, ValueError) as e:
                logging.error(f"Failed to process chapter for {mp3}: {str(e)}")
                raise


def create_concat_file(mp3_files: List[str], output_file: str) -> None:
    with open(output_file, "w", encoding="utf-8") as f:
        for mp3 in mp3_files:
            path = os.path.abspath(mp3)
            # Escape single quotes and backslashes for FFmpeg's concat protocol
            escaped_path = path.replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")


def create_metadata_file(metadata: dict, output_file: str) -> None:
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        # Write all metadata except cover_path
        for key, value in metadata.items():
            if (
                value and key != "cover_path"
            ):  # Skip cover_path as it's handled separately
                f.write(f"{key}={value}\n")


def process_audio_files(input_dir: str, verbose: bool) -> List[str]:
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory '{input_dir}' not found.")

    audio_files = []
    for ext in ["*.mp3", "*.m4a"]:
        audio_files.extend(glob.glob(os.path.join(input_dir, ext)))
    audio_files = sorted(audio_files)

    if not audio_files:
        raise ValueError("No MP3 or M4A files found in the input directory.")

    if verbose:
        logging.info(f"Found {len(audio_files)} audio files")

    return audio_files


def get_audio_format(filename: str) -> dict:
    """Get audio format information including codec and sample rate."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate",
                "-of",
                "json",
                filename,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        stream_data = data.get("streams", [{}])[0]
        return {
            "codec": stream_data.get("codec_name"),
            "sample_rate": stream_data.get("sample_rate"),
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
        return {"codec": None, "sample_rate": None}


def should_convert_audio(audio_files: List[str], settings: dict) -> bool:
    """Determine if audio conversion is needed based on source files and settings."""
    if settings.get("force_conversion", False):
        return True

    # Check if all files are already in M4B/AAC format
    for audio_file in audio_files:
        format_info = get_audio_format(audio_file)
        if format_info["codec"] not in ["aac", "m4a", "m4b"]:
            return True

    return False


def main(metadata: dict = None, settings: dict = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert a collection of MP3/M4A files into a single M4B audiobook with chapters.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                    # Uses default 'input' directory
    %(prog)s -i audiofiles      # Uses 'audiofiles' as input directory
    %(prog)s -o mybook.m4b      # Specifies custom output filename
        """,
    )

    parser.add_argument(
        "-i",
        "--input-dir",
        default="input",
        help="Directory containing input audio files (default: input)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output.m4b",
        help="Output M4B filename (default: output.m4b)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed processing information",
    )

    args = parser.parse_args()

    try:
        # Setup logging
        setup_logging(args.verbose)

        # Check dependencies
        if not check_dependencies():
            return

        # Process input files
        audio_files = process_audio_files(args.input_dir, args.verbose)

        # Create temporary files
        concat_file = "input.txt"
        chapter_file = "chapters.txt"
        metadata_file = "metadata.txt"
        output_m4b = args.output

        if args.verbose:
            logging.info("Creating concat and chapter files...")

        create_concat_file(audio_files, concat_file)
        create_chapter_file(audio_files, chapter_file)

        # Create metadata file if metadata is provided
        if metadata:
            create_metadata_file(metadata, metadata_file)

        if args.verbose:
            logging.info("Converting files to M4B...")

        # Initialize FFmpeg command
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",  # Force overwrite without asking
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
            "-i",
            chapter_file,
        ]

        if metadata:
            ffmpeg_cmd.extend(["-i", metadata_file])
            ffmpeg_cmd.extend(["-map_metadata", "2"])

            # Add cover art if provided
            if "cover_path" in metadata and metadata["cover_path"]:
                ffmpeg_cmd.extend(
                    [
                        "-i",
                        metadata["cover_path"],
                        "-map",
                        "3",
                        "-disposition:v:0",
                        "attached_pic",
                    ]
                )

        # Handle audio conversion settings
        settings = settings or {}
        needs_conversion = should_convert_audio(audio_files, settings)

        ffmpeg_cmd.extend(
            [
                "-map",
                "0:a",  # Map audio from first input
                "-map_chapters",
                "1",  # Use chapters from the second input
            ]
        )

        if needs_conversion:
            # Apply conversion settings
            codec = settings.get("codec", "Auto (Copy if possible)")
            if codec == "Auto (Copy if possible)" and not needs_conversion:
                ffmpeg_cmd.extend(["-c:a", "copy"])
            else:
                ffmpeg_cmd.extend(
                    [
                        "-c:a",
                        "aac" if codec == "Auto (Copy if possible)" else codec.lower(),
                    ]
                )

                # Apply bitrate if converting
                bitrate = settings.get("bitrate", "128k")
                ffmpeg_cmd.extend(["-b:a", bitrate])

            # Apply sample rate if not Auto
            sample_rate = settings.get("sample_rate", "Auto")
            if sample_rate != "Auto":
                ffmpeg_cmd.extend(["-ar", sample_rate])
        else:
            ffmpeg_cmd.extend(["-c:a", "copy"])

        # Always set output format
        ffmpeg_cmd.extend(["-f", "ipod", output_m4b])

        if not args.verbose:
            ffmpeg_cmd.extend(["-loglevel", "error"])

        try:
            subprocess.run(ffmpeg_cmd, check=True)
            logging.info("Conversion completed successfully!")
        except subprocess.CalledProcessError as e:
            logging.error("Conversion failed!")
            raise

        # Clean up temporary files
        for temp_file in [concat_file, chapter_file, metadata_file]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
