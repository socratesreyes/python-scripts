"""
Disk utilities: space, inodes, mount points, largest files.
All functions are PURE — they return data, they do not print or alert.
"""

import os       # For file paths, stat, walk — basic filesystem access
import shutil   # For disk_usage() — the easiest way to get disk space


def get_disk_usage(path="/"):
    """
    Return disk usage for a single path as a dictionary.
    Uses shutil.disk_usage() which works on Linux, macOS, and Windows.
    """
    try:
        # shutil.disk_usage returns (total_bytes, used_bytes, free_bytes)
        total, used, free = shutil.disk_usage(path)

        # 1024 ** 3 = 1 GB in bytes. Divide raw bytes to get human-readable GB.
        # round(..., 2) keeps it to 2 decimal places so logs stay clean.
        return {
            "path": path,
            "total_gb": round(total / (1024 ** 3), 2),
            "used_gb": round(used / (1024 ** 3), 2),
            "free_gb": round(free / (1024 ** 3), 2),
            # (used/total) * 100 gives a percentage like 87.3
            "percent_used": round((used / total) * 100, 1),
        }
    except FileNotFoundError:
        # If someone passes a bad path, don't crash — return an error field.
        return {"path": path, "error": "Path not found"}


def get_all_mounts(threshold=85):
    """
    Return a list of dicts, one per real mount point.
    Skips pseudo-filesystems (tmpfs, devtmpfs, overlay) to reduce noise.
    Marks each mount as critical if percent_used >= threshold.
    """
    # These are virtual filesystems. They report "full" often but don't matter.
    skip_fs = {"tmpfs", "devtmpfs", "overlay", "squashfs", "proc", "sysfs"}
    mounts = []  # We'll append one dict per mount point here

    try:
        # /proc/mounts is a Linux kernel file listing every mounted filesystem.
        # Each line looks like: /dev/sda1 / ext4 rw,relatime 0 0
        with open("/proc/mounts", "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        # If we're not on Linux (e.g., macOS), just return the root volume.
        usage = get_disk_usage("/")
        usage["is_critical"] = usage.get("percent_used", 0) >= threshold
        return [usage]

    for line in lines:
        # Split on whitespace: [device, mount_point, fs_type, options, dump, pass]
        parts = line.split()
        if len(parts) < 3:
            continue  # Malformed line, skip it

        device, mount_point, fs_type = parts[0], parts[1], parts[2]

        # Skip pseudo-filesystems — they don't represent real storage.
        if fs_type in skip_fs:
            continue

        # ismount() confirms the path is actually a mount point, not a random dir.
        if not os.path.ismount(mount_point):
            continue

        usage = get_disk_usage(mount_point)
        if "error" in usage:
            continue  # Skip mounts we can't read (permission issues, etc.)

        # Enrich the dict with info from /proc/mounts
        usage["device"] = device
        usage["fs_type"] = fs_type
        # The critical flag is what the boilerplate will check when deciding to alert.
        usage["is_critical"] = usage["percent_used"] >= threshold
        mounts.append(usage)

    return mounts


def get_critical_mounts(threshold=85):
    """Return only the mounts that are over the threshold."""
    # List comprehension: build a new list with only items where is_critical is True.
    return [m for m in get_all_mounts(threshold) if m.get("is_critical")]


def get_inode_usage(path="/"):
    """
    Return inode usage. A disk can be 'empty' but still fail if inodes run out.
    """
    try:
        # statvfs returns filesystem stats. f_files = total inodes,
        # f_ffree = free inodes. Yes, inodes are separate from byte space.
        stats = os.statvfs(path)
        total = stats.f_files
        free = stats.f_ffree
        used = total - free

        return {
            "path": path,
            "total_inodes": total,
            "used_inodes": used,
            "free_inodes": free,
            # Guard against divide-by-zero if total is 0
            "percent_used": round((used / total) * 100, 1) if total else 0,
        }
    except OSError as e:
        return {"path": path, "error": str(e)}


def get_largest_files(directory, top_n=10):
    """
    Walk a directory and return the top N largest files.
    Useful for 'what is eating my disk' tickets.
    """
    files = []

    # os.walk recursively visits every subdirectory.
    # root = current folder, filenames = files inside it.
    for root, _, filenames in os.walk(directory):
        for name in filenames:
            # Join folder + filename into a full path
            full_path = os.path.join(root, name)
            try:
                size = os.path.getsize(full_path)
                files.append({
                    "path": full_path,
                    "size_mb": round(size / (1024 ** 2), 2)
                })
            except (OSError, FileNotFoundError):
                # Files can vanish mid-walk or be unreadable — skip them.
                continue

    # Sort by size descending so the biggest files are first.
    files.sort(key=lambda x: x["size_mb"], reverse=True)
    return files[:top_n]  # Return only the top N