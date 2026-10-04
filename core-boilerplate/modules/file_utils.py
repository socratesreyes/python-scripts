"""
File utilities: JSON, YAML, existence checks, size checks.
All read functions return the parsed data or None on failure.
"""

import os
import json  # Built-in — no pip install needed


def read_json(path):
    """Read a JSON file and return a dict. Returns None if the file is missing or invalid."""
    try:
        with open(path, "r") as f:
            # json.load parses the file content directly into a Python dict/list.
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Two most common failures: file missing, or file has invalid JSON.
        return None


def write_json(path, data):
    """Write a dict to a JSON file. Returns True on success, False on failure."""
    try:
        with open(path, "w") as f:
            # indent=2 makes the output human-readable instead of one long line.
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


def read_yaml(path):
    """
    Read a YAML file and return a dict. Requires: pip install pyyaml
    Returns None if the file is missing or invalid.
    """
    try:
        # Import inside the function so the module still works if pyyaml
        # isn't installed and the caller never uses this function.
        import yaml
        with open(path, "r") as f:
            # safe_load is the safe version of load — never use plain yaml.load.
            return yaml.safe_load(f)
    except (FileNotFoundError, ImportError, Exception):
        return None


def file_exists(path):
    """Simple wrapper — but reads cleaner in code."""
    return os.path.isfile(path)  # True only for regular files, not directories


def get_file_size_mb(path):
    """Return the size of a file in MB, or None if it does not exist."""
    try:
        # getsize returns size in bytes. Divide by 1024**2 for MB.
        return round(os.path.getsize(path) / (1024 ** 2), 2)
    except (OSError, FileNotFoundError):
        return None