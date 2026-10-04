import os
import pytest
from unittest.mock import patch, MagicMock
from snippets.cleanup_utils import (
    find_old_files,
    delete_old_files,
    truncate_file,
    rotate_log,
)

# =====================================================================
# 1. FIXTURES FOR CLEANUP SANDBOX
# =====================================================================

@pytest.fixture
def cleanup_sandbox(tmp_path):
    """
    Creates an isolated workspace with three distinct mock log files.
    """
    log_dir = tmp_path / "var/log"
    log_dir.mkdir(parents=True)
    
    # 1. Standard application log
    app_log = log_dir / "app.log"
    app_log.write_text("line1\nline2\n")
    
    # 2. Database query log
    db_log = log_dir / "db.log"
    db_log.write_text("select * from analytics;")
    
    # 3. System info log (empty text file)
    sys_log = log_dir / "sys.log"
    sys_log.touch()
    
    return log_dir


# =====================================================================
# 2. FIND & DELETE OLD FILES SUITE (WITH FILE_AGE MOCKING)
# =====================================================================

@patch("snippets.cleanup_utils.file_age_days")
def test_find_old_files_filtering(mock_file_age, cleanup_sandbox):
    """Ensure old files are filtered accurately based on age thresholds."""
    # Track file absolute paths to configure the side_effect map
    app_path = os.path.join(str(cleanup_sandbox), "app.log")
    db_path = os.path.join(str(cleanup_sandbox), "db.log")
    
    # Mocking age: app.log is 10 days old, db.log is 2 days old
    def side_effect(path):
        if "app.log" in path:
            return 10
        return 2
    mock_file_age.side_effect = side_effect

    # Scan for files older than 5 days matching the '*.log' pattern
    old_files = find_old_files(str(cleanup_sandbox), days=5, pattern="*.log")
    
    assert len(old_files) == 1
    assert app_path in old_files
    assert db_path not in old_files


@patch("snippets.cleanup_utils.file_age_days")
def test_delete_old_files_dry_run_safety(mock_file_age, cleanup_sandbox):
    """Verify that dry_run=True defaults safely and does NOT drop files."""
    mock_file_age.return_value = 15  # All discovered files are old
    app_path = os.path.join(str(cleanup_sandbox), "app.log")
    
    # Execute with default settings (dry_run=True)
    result = delete_old_files(str(cleanup_sandbox), days=5, pattern="app.log")
    
    assert result["dry_run"] is True
    assert app_path in result["skipped"]
    assert len(result["deleted"]) == 0
    assert os.path.exists(app_path)  # Verify file still exists on disk


@patch("snippets.cleanup_utils.file_age_days")
def test_delete_old_files_destructive_action(mock_file_age, cleanup_sandbox):
    """Verify true purge path when dry_run=False."""
    mock_file_age.return_value = 15
    app_path = os.path.join(str(cleanup_sandbox), "app.log")
    
    # Execute actual deletion
    result = delete_old_files(str(cleanup_sandbox), days=5, pattern="app.log", dry_run=False)
    
    assert result["dry_run"] is False
    assert app_path in result["deleted"]
    assert not os.path.exists(app_path)  # File is successfully removed


# =====================================================================
# 3. TRUNCATION SUITE
# =====================================================================

def test_truncate_file_wipes_content(cleanup_sandbox):
    """Assert truncation zeroes out the file content without altering handles."""
    target_log = cleanup_sandbox / "app.log"
    assert target_log.stat().st_size > 0
    
    success = truncate_file(str(target_log))
    
    assert success is True
    assert target_log.stat().st_size == 0


def test_truncate_missing_file_returns_false():
    """Verify error containment logic when pointing to a missing destination."""
    success = truncate_file("/var/log/nonexistent_file_path.log")
    assert success is False


# =====================================================================
# 4. LOG ROTATION SUITE
# =====================================================================

@patch("snippets.cleanup_utils.get_file_size_mb")
def test_rotate_log_skips_small_files(mock_get_size, cleanup_sandbox):
    """Ensure small files are skipped by log rotation logic."""
    target_log = str(cleanup_sandbox / "db.log")
    mock_get_size.return_value = 12.5  # Below max_size_mb threshold
    
    rotated_path = rotate_log(target_log, max_size_mb=50)
    
    assert rotated_path is None
    assert os.path.exists(target_log)


@patch("snippets.cleanup_utils.now_utc")
@patch("snippets.cleanup_utils.get_file_size_mb")
def test_rotate_log_renames_large_files(mock_get_size, mock_now, cleanup_sandbox):
    """Assert heavy files are renamed with a sanitized ISO timestamp sequence."""
    target_log = str(cleanup_sandbox / "db.log")
    
    mock_get_size.return_value = 150.0  # Above max_size_mb threshold
    mock_now.return_value = "2026-10-01T22:30:00Z"  # Standard Mock ISO format
    
    rotated_path = rotate_log(target_log, max_size_mb=100)
    
    # Expected output switches colons to dashes for multi-OS friendliness
    assert rotated_path == f"{target_log}.2026-10-01T22-30-00Z"
    assert not os.path.exists(target_log)  # Original name cleared
    assert os.path.exists(rotated_path)    # Transferred to timestamp layout
