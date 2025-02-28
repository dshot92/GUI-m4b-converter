import logging
import subprocess
from typing import List, Dict, Optional
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
            f"Duration for {Path(file_path).name}: {duration_secs} seconds"
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

        # If no metadata title, use filename
        if not title:
            title = Path(file_path).stem

        # Clean up the title
        # Remove quotes from start and end
        title = title.strip("\"'")
        # Replace multiple spaces with single space
        title = " ".join(title.split())

        return title

    except subprocess.CalledProcessError:
        logging.warning(f"Failed to get title metadata for {file_path}, using filename")
        # Clean up filename same way
        title = Path(file_path).stem
        title = title.strip("\"'")
        title = " ".join(title.split())
        return title


def process_audio_files(directory: str, recursive: bool = False) -> List[str]:
    """Process audio files in the given directory."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Input directory '{directory}' not found.")

    audio_files = []
    seen_files = set()

    if recursive:
        # Walk through all subdirectories
        for file_path in dir_path.glob('**/*'):
            if file_path.is_file() and file_path.suffix.lower() in (".mp3", ".m4a", ".m4b", ".aac"):
                abs_path = str(file_path.absolute())
                if abs_path not in seen_files:
                    audio_files.append(abs_path)
                    seen_files.add(abs_path)
                    logging.debug(f"Found audio file: {file_path.name}")
    else:
        # Only look in the top directory
        for file_path in dir_path.glob('*'):
            if file_path.is_file() and file_path.suffix.lower() in (".mp3", ".m4a", ".m4b", ".aac"):
                abs_path = str(file_path.absolute())
                if abs_path not in seen_files:
                    audio_files.append(abs_path)
                    seen_files.add(abs_path)
                    logging.debug(f"Found audio file: {file_path.name}")

    if not audio_files:
        raise ValueError("No audio files found in the input directory.")

    # Sort the files to maintain consistent order
    audio_files.sort()
    
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
            escaped_path = str(Path(file).absolute()).replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
            logging.info(f"Adding file: {Path(file).name}")
    return concat_file


def run_ffmpeg_with_progress(cmd: List[str], stop_event=None) -> None:
    """Run ffmpeg command and show progress in real-time."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
    )

    while True:
        if stop_event and stop_event():
            process.terminate()
            process.wait()
            raise RuntimeError("Conversion stopped by user")

        line = process.stderr.readline()
        if not line and process.poll() is not None:
            break
        if line:
            logging.info(line.strip())

    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {stderr}")


def get_audio_codec(file_path: str) -> str:
    """Get audio codec of the file using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-i",
            file_path,
            "-show_entries",
            "stream=codec_name",
            "-select_streams",
            "a:0",
            "-v",
            "quiet",
            "-of",
            "csv=p=0",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        codec = result.stdout.strip()
        return codec.lower() if codec else ""
    except subprocess.CalledProcessError:
        logging.warning(f"Failed to get codec info for {file_path}")
        return ""


def generate_m4b(
    input_dir: str,
    output_file: str,
    metadata: Optional[Dict] = None,
    settings: Optional[Dict] = None,
    chapter_titles: Optional[List[str]] = None,
    stop_event=None,
) -> None:
    """Generate M4B file from input files."""
    if not check_dependencies():
        raise RuntimeError("Required dependencies not found")

    temp_files = []
    try:
        # Ensure output directory exists
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Process input files
        input_files = process_audio_files(input_dir)

        # Check if all files are AAC for copy mode
        can_copy = False
        if settings and settings.get("codec") == "Auto (Copy if possible)":
            can_copy = all(get_audio_codec(f) in ["aac", "mp4a"] for f in input_files)
            if not can_copy:
                logging.info(
                    "Some files are not AAC, will convert to AAC instead of copying"
                )

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
            if codec == "Auto (Copy if possible)" and can_copy:
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "aac"])
                # Bitrate
                bitrate = settings.get("bitrate", "128k")
                if bitrate != "Auto":
                    cmd.extend(["-b:a", bitrate])
                # Sample rate
                sample_rate = settings.get("sample_rate")
                if sample_rate and sample_rate != "Auto":
                    cmd.extend(["-ar", sample_rate])
        else:
            # Default audio settings
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])

        # Add output file
        cmd.append(str(output_path))

        # Run FFmpeg
        run_ffmpeg_with_progress(cmd, stop_event)

        # Add metadata if provided
        if metadata:
            try:
                audio = MP4(str(output_path))

                # Add each metadata field
                for key, value in metadata.items():
                    if key == "cover_path" and value:
                        try:
                            with open(value, "rb") as f:
                                cover_data = f.read()
                            audio["covr"] = [MP4Cover(cover_data)]
                        except Exception as e:
                            logging.error(f"Error adding cover art: {str(e)}")
                    elif value:  # Only add non-empty values
                        audio[key] = value

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
                temp_path = Path(temp_file)
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass  # Ignore cleanup errors
