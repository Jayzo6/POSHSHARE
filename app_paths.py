"""
Portable path helpers so the app works as a script or as a frozen .exe on any PC.
Data files (credentials, closets) are stored in a consistent place that doesn't
depend on where the exe is installed.
"""
import os
import sys


def _is_frozen():
    """True when running as a PyInstaller/cx_Freeze exe."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_app_data_dir():
    """
    Directory for saving/loading app data (credentials, closets list).
    - When running as .exe: uses a folder in the user's AppData so it works on any PC.
    - When running as script: uses the folder containing the script/project.
    """
    if _is_frozen():
        # Windows: use LocalAppData so it works for any user on any PC
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if not base:
            base = os.path.expanduser("~")
        path = os.path.join(base, "PoshmarkSharingBot")
        os.makedirs(path, exist_ok=True)
        return path
    # Running as script: use folder containing this file (project root)
    return os.path.dirname(os.path.abspath(__file__))


def get_credentials_path():
    """Path to the saved credentials JSON file."""
    return os.path.join(get_app_data_dir(), "poshmark_credentials.json")


def get_closets_path():
    """Path to the saved closets list file."""
    return os.path.join(get_app_data_dir(), "last_closets.txt")
