"""
Cleanup utilities: find/delete old files, truncate, rotate logs.
IMPORTANT: All delete functions default to dry_run=True for safety.
"""

import os
import glob  # For pattern matching files (like *.log)
from snippets.time_utils import file_age_days  # Reuse from another snippet


def find_old_files(directory, days, pattern="*"):
    """
    Find files older than N days matching a pattern.
    Returns a list of full paths. Does NOT delete anything.
    """
    old_files = []
    # glob.glob turns "/var/log/*.log" into the actual list of matching paths.
    search_path = os.path.join(directory, pattern)

    for path in glob.glob(search_path):
        # Skip anything that isn't a regular file (e.g., a subdirectory).
        if not os.path.isfile(path):
            continue
        age = file_age_days(path)
        if age is not None and age > days:
            old_files.append(path)

    return old_files


def delete_old_files(directory, days, pattern="*", dry_run=True):
    """
    Delete files older than N days.
    Returns a dict: {deleted: [...], skipped: [...], dry_run: bool}.
    Defaults to dry_run=True. Always test first.
    """
    old_files = find_old_files(directory, days, pattern)

    # This dict is what the caller inspects to see what happened.
    result = {"deleted": [], "skipped": [], "dry_run": dry_run}

    for path in old_files:
        # In dry-run mode, we "pretend" to delete — just track what we would delete.
        if dry_run:
            result["skipped"].append(path)
            continue
        try:
            os.remove(path)
            result["deleted"].append(path)
        except OSError:
            # If delete fails (permissions), record it as skipped.
            result["skipped"].append(path)

    return result


def truncate_file(path):
    """
    Empty a file WITHOUT deleting it. Useful for logs that services
    hold open — deleting them breaks the file handle.
    """
    try:
        # Open in "w" mode erases the file. truncate(0) forces it to zero bytes.
        with open(path, "w") as f:
            f.truncate(0)
        return True
    except (OSError, FileNotFoundError):
        return False


def rotate_log(log_path, max_size_mb=100):
    """
    If a log file is bigger than max_size_mb, rename it with a timestamp
    and let the service create a fresh one.
    Returns the new path, or None if rotation was not needed.
    """
    from snippets.time_utils import now_utc
    from snippets.file_utils import get_file_size_mb

    size = get_file_size_mb(log_path)

    # No size (missing file) or file is small enough — nothing to do.
    if size is None or size < max_size_mb:
        return None

    # Replace colons in the ISO timestamp because colons are illegal in filenames on Windows.
    timestamp = now_utc().replace(":", "-")
    rotated = f"{log_path}.{timestamp}"

    try:
        # os.rename is atomic on the same filesystem — safe even while the file is open.
        os.rename(log_path, rotated)
        return rotated
    except OSError:
        return None