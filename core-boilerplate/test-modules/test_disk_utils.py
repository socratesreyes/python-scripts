import os
import shutil
import pytest
from unittest.mock import patch, mock_open, MagicMock
from snippets.disk_utils import (
    get_disk_usage,
    get_all_mounts,
    get_critical_mounts,
    get_inode_usage,
    get_largest_files,
)

# =====================================================================
# 1. TESTING LOCAL LOGIC (PURE PATHS AND OS INTERACTIONS)
# =====================================================================

@patch("snippets.disk_utils.shutil.disk_usage")
def test_get_disk_usage_success(mock_shutil_usage):
    """Verify byte-to-GB calculation and percentage math."""
    # 100 GB total, 40 GB used, 60 GB free (expressed in bytes)
    mock_shutil_usage.return_value = (
        100 * (1024 ** 3),
        40 * (1024 ** 3),
        60 * (1024 ** 3)
    )
    
    result = get_disk_usage("/")
    
    assert result["total_gb"] == 100.0
    assert result["used_gb"] == 40.0
    assert result["free_gb"] == 60.0
    assert result["percent_used"] == 40.0


def test_get_disk_usage_not_found():
    """Verify error dictionary return when path does not exist."""
    result = get_disk_usage("/nonexistent/directory/structure")
    assert "error" in result
    assert result["path"] == "/nonexistent/directory/structure"


@patch("snippets.disk_utils.os.statvfs")
def test_get_inode_usage(mock_statvfs):
    """Ensure statvfs structs parse correctly into accurate percentages."""
    mock_stats = MagicMock()
    mock_stats.f_files = 1000  # Total
    mock_stats.f_ffree = 200   # Free
    mock_statvfs.return_value = mock_stats
    
    result = get_inode_usage("/")
    
    assert result["total_inodes"] == 1000
    assert result["used_inodes"] == 800
    assert result["percent_used"] == 80.0


# =====================================================================
# 2. TESTING LINUX-SPECIFIC VIRTUAL FILESYSTEMS (/proc/mounts)
# =====================================================================

@patch("snippets.disk_utils.os.path.ismount")
@patch("snippets.disk_utils.get_disk_usage")
def test_get_all_and_critical_mounts(mock_usage, mock_ismount):
    """Mock /proc/mounts streaming to isolate system file evaluation."""
    mock_ismount.return_value = True
    
    # Mock /proc/mounts contents: line 1 matches real fs, line 2 matches virtual fs to skip
    proc_mounts_data = (
        "/dev/sda1 / ext4 rw,relatime 0 0\n"
        "tmpfs /run tmpfs rw,nosuid 0 0\n"
    )
    
    # Simulate low disk usage for normal lookup
    mock_usage.return_value = {"percent_used": 10.0}
    
    with patch("builtins.open", mock_open(read_data=proc_mounts_data)):
        mounts = get_all_mounts(threshold=80)
        
        # Verify tmpfs was safely ignored and /dev/sda1 parsed correctly
        assert len(mounts) == 1
        assert mounts[0]["device"] == "/dev/sda1"
        assert mounts[0]["fs_type"] == "ext4"
        assert mounts[0]["is_critical"] is False

    # Switch disk usage context to simulate a critical warning scenario
    mock_usage.return_value = {"percent_used": 90.0}
    with patch("builtins.open", mock_open(read_data=proc_mounts_data)):
        critical_mounts = get_critical_mounts(threshold=80)
        assert len(critical_mounts) == 1
        assert critical_mounts[0]["is_critical"] is True


# =====================================================================
# 3. USING PYTEST TMP_PATH FIXTURE FOR DIRECTORY WALKING
# =====================================================================

def test_get_largest_files(tmp_path):
    """Safely populate a mock local system path with dynamic file weights."""
    # Create sub-directories under the ephemeral sandbox route
    log_dir = tmp_path / "var/log"
    log_dir.mkdir(parents=True)
    
    # Generate mock log targets with specific sizes
    small_file = log_dir / "small.log"
    large_file = log_dir / "large.log"
    
    # Write different sizes: 1 MB and 5 MB
    small_file.write_bytes(b"0" * (1024 * 1024))
    large_file.write_bytes(b"0" * (5 * 1024 * 1024))
    
    # Run directory crawler scan on the temporary workspace root
    results = get_largest_files(str(tmp_path), top_n=5)
    
    assert len(results) == 2
    # Verify sorting orders largest files first
    assert results[0]["size_mb"] == 5.0
    assert "large.log" in results[0]["path"]
    assert results[1]["size_mb"] == 1.0
