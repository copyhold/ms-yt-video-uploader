# ffmpeg_processor.py
import subprocess
import os
import platform
from path_util import find_ffmpeg

FFMPEG_PATH = find_ffmpeg()

# --- Configuration for audio mixing ---
# These volumes are relative. 1.0 is original volume.
# When translation is primary:
TRANSLATION_PRIMARY_VOL = 1.0
HEBREW_DUCKED_VOL = 0.15 # Hebrew volume when translation is primary

# When Hebrew is primary (e.g., worship, shouts in translation):
HEBREW_PRIMARY_VOL = 1.0
TRANSLATION_SHOUTS_VOL = 0.5 # Translation volume for shouts during Hebrew primary

def _run_ffmpeg_command(command, output_path):
    """A helper to run ffmpeg commands and handle errors."""
    if not FFMPEG_PATH:
        print("FATAL: FFmpeg executable not found. Cannot process video.")
        return False
        
    # Add the discovered ffmpeg path to the command
    command.insert(0, FFMPEG_PATH)
    
    print(f"Running FFmpeg: {' '.join(command)}")
    try:
        # Set up subprocess arguments for cross-platform compatibility
        kwargs = {
            'check': True,
            'capture_output': True,
            'text': True
        }
        if platform.system() == "Windows":
            # This flag prevents a console window from popping up on Windows
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
        subprocess.run(command, **kwargs)
        print(f"Successfully created: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error processing {output_path}:")
        print(f"STDERR: {e.stderr}") # stderr is usually more informative for ffmpeg
        return False

def process_video_hebrew_only(video_path, hebrew_audio_path, output_path):
    """Creates a video with only the Hebrew audio track."""
    command = [
        '-y',
        '-i', video_path,
        '-i', hebrew_audio_path,
        '-c:v', 'copy',
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-c:a', 'aac',
        '-b:a', '192k',
        output_path
    ]
    return _run_ffmpeg_command(command, output_path)

def process_video_with_translation(video_path, hebrew_audio_path, translation_audio_path,
                                   output_path, translation_only_segments):
    """
    Processes video with mixed Hebrew and translation audio.
    translation_only_segments: list of tuples [(start_sec, end_sec), ...]
    """
    filter_complex_parts = []

    # Build the volume filter expressions based on segments
    # Hebrew volume: ducked during translation_only_segments, primary otherwise
    hebrew_vol_expr_conditions = "if("
    conditions_heb = []
    for start, end in translation_only_segments:
        conditions_heb.append(f"between(t,{start},{end})")
    if conditions_heb:
        hebrew_vol_expr_conditions += "+".join(conditions_heb) # any 'between' is true -> sum > 0
        hebrew_vol_expr_conditions += f",{HEBREW_DUCKED_VOL},{HEBREW_PRIMARY_VOL})"
    else: # No translation_only_segments, Hebrew is always primary
        # Condition '0' is false, so it will take the 'else' value (HEBREW_PRIMARY_VOL)
        hebrew_vol_expr_conditions += f"0,{HEBREW_DUCKED_VOL},{HEBREW_PRIMARY_VOL})"
    
    # Corrected FFmpeg volume filter syntax: volume='EXPRESSION':eval=frame
    hebrew_volume_filter = f"volume='{hebrew_vol_expr_conditions}':eval=frame"
    filter_complex_parts.append(f"[1:a]{hebrew_volume_filter}[a_heb_vol]")


    # Translation volume: primary during translation_only_segments, shouts volume otherwise
    translation_vol_expr_conditions = "if("
    conditions_trans = []
    for start, end in translation_only_segments:
        conditions_trans.append(f"between(t,{start},{end})")
    if conditions_trans:
        translation_vol_expr_conditions += "+".join(conditions_trans)
        translation_vol_expr_conditions += f",{TRANSLATION_PRIMARY_VOL},{TRANSLATION_SHOUTS_VOL})"
    else: # No translation_only_segments, translation is always at shouts volume
        # Condition '0' is false, so it will take the 'else' value (TRANSLATION_SHOUTS_VOL)
        translation_vol_expr_conditions += f"0,{TRANSLATION_PRIMARY_VOL},{TRANSLATION_SHOUTS_VOL})"

    # Corrected FFmpeg volume filter syntax: volume='EXPRESSION':eval=frame
    translation_volume_filter = f"volume='{translation_vol_expr_conditions}':eval=frame"
    filter_complex_parts.append(f"[2:a]{translation_volume_filter}[a_trans_vol]")

    # Mix the two adjusted audio streams
    # dropout_transition: helps avoid clicks when one stream volume goes to 0
    filter_complex_parts.append(f"[a_heb_vol][a_trans_vol]amix=inputs=2:duration=longest:dropout_transition=0.5[a_mixed]")

    filter_complex_str = ";".join(filter_complex_parts)

    print(f"Running FFmpeg for mixed audio: {' '.join(command)}")

    command = [
        '-y',
        '-i', video_path,
        '-i', hebrew_audio_path,
        '-i', translation_audio_path,
        '-filter_complex', filter_complex_str,
        '-map', '0:v:0',
        '-map', '[a_mixed]',
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-b:a', '192k',
        output_path
    ]
    return _run_ffmpeg_command(command, output_path)

def parse_segments_string(segments_str):
    """Parses a string like "60-300, 450-600" into [(60,300), (450,600)]"""
    segments = []
    if not segments_str.strip():
        return segments
    parts = segments_str.split(',')
    for part in parts:
        try:
            start, end = map(float, part.strip().split('-'))
            if start < 0 or end < 0 or start >= end:
                raise ValueError("Invalid segment format or order.")
            segments.append((start, end))
        except ValueError as e:
            print(f"Warning: Could not parse segment '{part}'. Skipping. Error: {e}")
            # Optionally, raise an error or show in UI
    return segments