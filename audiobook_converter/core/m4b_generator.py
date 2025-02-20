import os
import logging
import subprocess
from typing import List, Dict, Optional, Tuple
import json
import tempfile
from pathlib import Path
from mutagen.mp4 import MP4, MP4Cover


def check_dependencies() -> bool:
    """Check if required dependencies (ffmpeg and ffprobe) are available."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.error("ffmpeg or ffprobe not found. Please install ffmpeg.")
        return False


def get_audio_duration(file_path: str) -> float:
    """Get duration of audio file in seconds using ffprobe."""
    try:
        # First try to get duration from audio stream
        cmd = [
            "ffprobe",
            "-i",
            file_path,
            "-show_entries",
            "stream=duration",
            "-select_streams",
            "a:0",
            "-v",
            "quiet",
            "-of",
            "csv=p=0",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = result.stdout.strip()

        # If stream duration is empty or 0, try format duration
        if not duration or float(duration) <= 0:
            cmd = [
                "ffprobe",
                "-i",
                file_path,
                "-show_entries",
                "format=duration",
                "-v",
                "quiet",
                "-of",
                "csv=p=0",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = result.stdout.strip()

        duration_secs = float(duration)
        if duration_secs <= 0:
            raise ValueError(f"Invalid duration: {duration_secs}")

        logging.info(
            f"Duration for {os.path.basename(file_path)}: {duration_secs} seconds"
        )
        return duration_secs
    except Exception as e:
        logging.error(f"Error getting duration for {file_path}: {str(e)}")
        raise


def get_audio_title(file_path: str) -> str:
    """Get title from audio metadata or filename."""
    try:
        cmd = [
            "ffprobe",
            "-i",
            file_path,
            "-show_entries",
            "format_tags=title",
            "-v",
            "quiet",
            "-of",
            "csv=p=0",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        title = result.stdout.strip()
        return title if title else Path(file_path).stem
    except subprocess.CalledProcessError:
        logging.warning(f"Failed to get title metadata for {file_path}, using filename")
        return Path(file_path).stem


def process_audio_files(directory: str, recursive: bool = False) -> List[str]:
    """Process audio files in the given directory."""
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Input directory '{directory}' not found.")

    audio_files = []
    seen_files = set()

    for root, _, files in os.walk(directory):
        for file in sorted(files):
            if file.lower().endswith((".mp3", ".m4a", ".m4b", ".aac")):
                full_path = os.path.abspath(os.path.join(root, file))
                if full_path not in seen_files:
                    audio_files.append(full_path)
                    seen_files.add(full_path)
                    logging.debug(f"Found audio file: {file}")
        if not recursive:
            break

    if not audio_files:
        raise ValueError("No audio files found in the input directory.")

    logging.info(f"Found {len(audio_files)} audio files")
    return audio_files


def create_chapter_metadata(
    files: List[str], titles: Optional[List[str]] = None
) -> str:
    """Generate chapter metadata for ffmpeg."""
    if not files:
        return ""

    chapter_file = "chapters.txt"
    start_time = 0

    with open(chapter_file, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")

        for i, file in enumerate(files):
            duration = get_audio_duration(file) * 1000  # Convert to milliseconds
            title = titles[i] if titles and i < len(titles) else get_audio_title(file)

            # Escape special characters in title
            escaped_title = (
                title.replace("=", "\\=")
                .replace(";", "\\;")
                .replace("#", "\\#")
                .replace("\\", "\\\\")
            )

            logging.info(
                f"Chapter {i+1}: {title} (Duration: {duration/1000:.2f} seconds)"
            )

            f.write("\n[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write(f"START={int(start_time)}\n")
            f.write(f"END={int(start_time + duration)}\n")
            f.write(f"title={escaped_title}\n")

            start_time += duration

    return chapter_file


def create_concat_file(files: List[str]) -> str:
    """Create a concat format file for ffmpeg."""
    concat_file = "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for file in files:
            # Escape single quotes and backslashes for FFmpeg's concat protocol
            escaped_path = os.path.abspath(file).replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
            logging.info(f"Adding file: {os.path.basename(file)}")
    return concat_file


def run_ffmpeg_with_progress(cmd: List[str]) -> None:
    """Run ffmpeg command and show progress in real-time."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
    )

    while True:
        line = process.stderr.readline()
        if not line and process.poll() is not None:
            break
        if line:
            logging.info(line.strip())

    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {stderr}")


def generate_m4b(
    input_dir: str,
    output_file: str,
    metadata: Optional[Dict] = None,
    settings: Optional[Dict] = None,
    chapter_titles: Optional[List[str]] = None,
) -> None:
    """Generate M4B file from input files."""
    if not check_dependencies():
        raise RuntimeError("Required dependencies not found")

    temp_files = []
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

        # Process input files
        input_files = process_audio_files(input_dir)

        # Create concat and chapter files
        concat_file = create_concat_file(input_files)
        temp_files.append(concat_file)

        chapter_file = create_chapter_metadata(input_files, chapter_titles)
        temp_files.append(chapter_file)

        # Create M4B with just audio and chapters
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
            "-i",
            chapter_file,
        ]

        # Map streams
        cmd.extend(["-map", "0:a"])  # Map audio from concat
        cmd.extend(["-map_metadata", "1"])  # Map chapter metadata

        # Audio codec settings
        if settings:
            codec = settings.get("codec", "AAC")
            if codec == "Auto (Copy if possible)":
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "aac"])
                # Bitrate
                bitrate = settings.get("bitrate", "128k")
                cmd.extend(["-b:a", bitrate])
                # Sample rate
                sample_rate = settings.get("sample_rate")
                if sample_rate and sample_rate != "Auto":
                    cmd.extend(["-ar", sample_rate])
        else:
            # Default audio settings
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])

        # Add output file
        cmd.extend(["-movflags", "+faststart", output_file])  # Optimize for streaming

        # Run ffmpeg for audio conversion
        logging.info(f"Running audio conversion command: {' '.join(cmd)}")
        run_ffmpeg_with_progress(cmd)

        # Add metadata using mutagen if provided
        if metadata:
            try:
                audio = MP4(output_file)

                # Map metadata fields to MP4 tags
                tag_mapping = {
                    "title": "\xa9nam",
                    "artist": "\xa9ART",
                    "album_artist": "aART",
                    "album": "\xa9alb",
                    "genre": "\xa9gen",
                    "date": "\xa9day",
                    "description": "\xa9des",
                }

                # Set metadata
                for key, value in metadata.items():
                    if key != "cover_path" and value:
                        mp4_key = tag_mapping.get(key)
                        if mp4_key:
                            audio[mp4_key] = value

                # Add cover art if provided
                if metadata.get("cover_path"):
                    with open(metadata["cover_path"], "rb") as f:
                        cover_data = f.read()
                        # Determine image format and set appropriate cover type
                        if metadata["cover_path"].lower().endswith((".jpg", ".jpeg")):
                            cover = MP4Cover(
                                cover_data, imageformat=MP4Cover.FORMAT_JPEG
                            )
                        elif metadata["cover_path"].lower().endswith(".png"):
                            cover = MP4Cover(
                                cover_data, imageformat=MP4Cover.FORMAT_PNG
                            )
                        else:
                            logging.warning("Unsupported cover image format")
                            cover = None

                        if cover:
                            audio["covr"] = [cover]

                # Save changes
                audio.save()
                logging.info("Metadata added successfully")

            except Exception as e:
                logging.error(f"Error adding metadata: {str(e)}")
                raise

        logging.info("Conversion completed successfully!")

    except Exception as e:
        logging.error(f"Error during conversion: {str(e)}")
        raise

    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError:
                pass  # Ignore cleanup errors
