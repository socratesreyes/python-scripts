import os
import time
import datetime
import pytest
from unittest.mock import patch, MagicMock
from snippets.time_utils import (
    now_utc,
    file_age_days,
    is_older_than,
    human_duration,
)

# =====================================================================
# 1. TIMESTAMP ISOLATION SUITE
# =====================================================================

@patch("snippets.time_utils.datetime.datetime")
def test_now_utc_format(mock_datetime):
    """Verify ISO 8601 formatting with hardcoded time injection."""
    # Freeze time at a specific clock tick
    mock_datetime.utcnow.return_value = datetime.datetime(2026, 10, 1, 22, 30, 0)
    
    assert now_utc() == "2026-10-01T22:30:00Z"


# =====================================================================
# 2. FILE AGING MATH SUITE (OS INTERACTION)
# =====================================================================

@patch("snippets.time_utils.time.time")
@patch("snippets.time_utils.os.path.getmtime")
def test_file_age_days_calculation(mock_getmtime, mock_time):
    """Verify raw seconds breakdown translates precisely to fractional days."""
    # Mock current system time (Unix epoch representation)
    mock_time.return_value = 1000000.0
    # Mock file mod time to be exactly 2.5 days old (2.5 * 86400 = 216000 seconds ago)
    mock_getmtime.return_value = 1000000.0 - 216000.0

    assert file_age_days("/var/log/app.log") == 2.5


def test_file_age_days_missing_returns_none():
    """Verify error containment path when passing an invalid file reference."""
    assert file_age_days("/opt/missing_system_file.cfg") is None


@patch("snippets.time_utils.file_age_days")
def test_is_older_than_evaluation(mock_age):
    """Verify boolean state transitions based on threshold targets."""
    # Scenario A: File age is higher than target limit
    mock_age.return_value = 10.5
    assert is_older_than("/var/log/nginx.log", days=7) is True

    # Scenario B: File age is lower than target limit
    mock_age.return_value = 3.2
    assert is_older_than("/var/log/nginx.log", days=7) is False

    # Scenario C: File is completely missing (returns None)
    mock_age.return_value = None
    assert is_older_than("/var/log/nginx.log", days=7) is False


# =====================================================================
# 3. HUMAN DURATION REFACTOR SUITE
# =====================================================================

@pytest.mark.parametrize(
    "input_seconds, expected_output",
    [
        (172800 + 14400 + 900, "2d 4h 15m"),  # 2 days, 4 hours, 15 minutes
        (3600 + 120, "1h 2m"),                # 1 hour, 2 minutes
        (45, "45s"),                          # Just seconds boundary
        (0, "0s"),                            # Zero baseline condition
    ],
)
def test_human_duration_conversions(input_seconds, expected_output):
    """Verify conversion structures across various time frames using parameter matrix grids."""
    assert human_duration(input_seconds) == expected_output
