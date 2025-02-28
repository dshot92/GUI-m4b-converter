import os
import logging
from typing import List, Dict, Optional
import ffmpeg
from pathlib import Path
from mutagen.mp4 import MP4, MP4Cover


def check_dependencies() -> bool:
  """Check if required dependencies (ffmpeg and ffprobe) are available."""
  try:
    # Use ffmpeg-python to check if ffmpeg is available
    # This will attempt to get ffmpeg version info
    version_info = ffmpeg.probe('', show_entries='program_version')
    
    # If we get here without an exception, ffmpeg and ffprobe are available
    logging.info(f"Found ffmpeg: {version_info.get('program_version', 'unknown version')}")
    return True
  except ffmpeg.Error as e:
    # ffmpeg.Error will be raised if ffmpeg/ffprobe is not found or has an error
    stderr = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
    logging.error(f"ffmpeg or ffprobe not found or not working properly: {stderr}")
    return False


def get_audio_duration(file_path: str) -> float:
  """Get duration of audio file in seconds using ffprobe."""
  try:
    # Get audio stream info using ffmpeg-python
    probe = ffmpeg.probe(file_path)
    
    # First try to get duration from audio stream
    audio_stream = next((stream for stream in probe['streams'] 
              if stream['codec_type'] == 'audio'), None)
    
    if audio_stream and 'duration' in audio_stream:
      duration_secs = float(audio_stream['duration'])
    else:
      # If stream duration is not available, try format duration
      duration_secs = float(probe['format']['duration'])
    
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
    # Get metadata using ffmpeg-python
    probe = ffmpeg.probe(file_path)
    
    # Try to get title from metadata
    title = ""
    if 'tags' in probe['format'] and 'title' in probe['format']['tags']:
      title = probe['format']['tags']['title']

    # If no metadata title, use filename
    if not title:
      title = Path(file_path).stem

    # Clean up the title
    # Remove quotes from start and end
    title = title.strip("\"'")
    # Replace multiple spaces with single space
    title = " ".join(title.split())

    return title

  except Exception:
    logging.warning(f"Failed to get title metadata for {file_path}, using filename")
    # Clean up filename same way
    title = Path(file_path).stem
    title = title.strip("\"'")
    title = " ".join(title.split())
    return title


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


def get_audio_codec(file_path: str) -> str:
  """Get audio codec of the file using ffprobe."""
  try:
    probe = ffmpeg.probe(file_path)
    audio_stream = next((stream for stream in probe['streams'] 
              if stream['codec_type'] == 'audio'), None)
    
    if audio_stream and 'codec_name' in audio_stream:
      return audio_stream['codec_name'].lower()
    return ""
  except Exception:
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
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

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

    # The ffmpeg-python package has limitations with complex mapping scenarios
    # We'll use a hybrid approach: use ffmpeg-python to build the command
    # but handle the stream mapping more carefully
    
    # Start building the command
    stream = ffmpeg.input(concat_file, format='concat', safe=0)
    
    # Set up codec options
    output_options = {}
    
    # Audio codec settings
    if settings:
      codec = settings.get("codec", "AAC")
      if codec == "Auto (Copy if possible)" and can_copy:
        output_options['c:a'] = 'copy'
      else:
        output_options['c:a'] = 'aac'
        # Bitrate
        bitrate = settings.get("bitrate", "128k")
        if bitrate != "Auto":
          output_options['b:a'] = bitrate
        # Sample rate
        sample_rate = settings.get("sample_rate")
        if sample_rate and sample_rate != "Auto":
          output_options['ar'] = sample_rate
    else:
      # Default audio settings
      output_options['c:a'] = 'aac'
      output_options['b:a'] = '128k'
    
    # Create the ffmpeg command with explicit stream handling
    # We'll use the global_args method to add the mapping options
    ffmpeg_cmd = (
      ffmpeg
      .input(concat_file, format='concat', safe=0)
      .output(output_file, **output_options)
      .global_args(
        '-i', chapter_file,  # Add chapter file as second input
        '-map', '0:a',       # Map audio from first input
        '-map_metadata', '1',  # Map metadata from second input
        '-progress', 'pipe:1'  # For progress monitoring
      )
      .overwrite_output()
    )
    
    # Get the command that would be executed for logging
    cmd_args = ffmpeg_cmd.compile()
    logging.info(f"Executing FFmpeg command: {' '.join(cmd_args)}")
    
    # Run FFmpeg
    try:
      # Run the ffmpeg process
      process = ffmpeg_cmd.run_async(pipe_stdout=True, pipe_stderr=True)
      
      # Monitor progress
      while True:
        if stop_event and stop_event():
          process.terminate()
          process.wait()
          raise RuntimeError("Conversion stopped by user")
          
        # Read output line by line
        line = process.stderr.readline().decode('utf-8', errors='replace')
        if not line and process.poll() is not None:
          break
        if line:
          logging.info(line.strip())
          
      # Wait for process to complete
      process.wait()
      
      if process.returncode != 0:
        stderr = process.stderr.read().decode('utf-8', errors='replace')
        raise RuntimeError(f"FFmpeg error: {stderr}")
        
    except ffmpeg.Error as e:
      stderr = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
      raise RuntimeError(f"FFmpeg error: {stderr}")

    # Add metadata if provided
    if metadata:
      try:
        audio = MP4(output_file)

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
        if os.path.exists(temp_file):
          os.remove(temp_file)
      except OSError:
        pass  # Ignore cleanup errors
