import sys
import os
import shutil

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def find_ffmpeg():
    """
    Finds the ffmpeg executable.
    
    Priority Order:
    1. Check for a bundled ffmpeg (in the same directory as the executable).
    2. Check the system's PATH environment variable.
    
    Returns the full path to ffmpeg if found, otherwise None.
    """
    # Determine the executable name based on the OS
    ffmpeg_filename = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    
    # 1. Check for a bundled version first
    bundled_path = resource_path(ffmpeg_filename)
    if os.path.exists(bundled_path):
        return bundled_path
        
    # 2. If not bundled, check the system PATH
    system_path = shutil.which(ffmpeg_filename)
    if system_path:
        return system_path
        
    # 3. If not found anywhere, return None
    return None