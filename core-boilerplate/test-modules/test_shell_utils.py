import subprocess
import pytest
from unittest.mock import patch, MagicMock
from snippets.shell_utils import (
    run_command,
    run_command_safe,
    command_exists,
)

# =====================================================================
# 1. CORE SUBPROCESS ROUTING SUITE
# =====================================================================

@patch("snippets.shell_utils.subprocess.run")
def test_run_command_success(mock_run):
    """Verify that valid commands capture, split strings, and clean whitespace handles."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "  system-v1.0.0\n"
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    # Send command string to verify internal splitting logic
    code, stdout, stderr = run_command("uname -r", timeout=10)

    assert code == 0
    assert stdout == "system-v1.0.0"  # Verify whitespace .strip() extraction
    assert stderr == ""
    mock_run.assert_called_once_with(
        ["uname", "-r"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False
    )


@patch("snippets.shell_utils.subprocess.run")
def test_run_command_timeout(mock_run):
    """Verify that TimeoutExpired throws standard GNU exit code 124."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["sleep", "60"], timeout=5)

    code, stdout, stderr = run_command(["sleep", "60"], timeout=5)

    assert code == 124
    assert stdout == ""
    assert "Command timed out after 5s" in stderr


@patch("snippets.shell_utils.subprocess.run")
def test_run_command_not_found(mock_run):
    """Verify missing system packages trigger standard shell exit code 127."""
    mock_run.side_effect = FileNotFoundError()

    code, stdout, stderr = run_command(["non_existent_tool"])

    assert code == 127
    assert stdout == ""
    assert "Command not found: non_existent_tool" in stderr


@patch("snippets.shell_utils.subprocess.run")
def test_run_command_generic_exception(mock_run):
    """Verify generic failure catch-all maps safely to standard error exit code 1."""
    mock_run.side_effect = PermissionError("Operation not permitted")

    code, stdout, stderr = run_command(["iptables", "-L"])

    assert code == 1
    assert "Operation not permitted" in stderr


# =====================================================================
# 2. SHELL ABSTRACTION AND UTILITY SANITY SUITE
# =====================================================================

@patch("snippets.shell_utils.run_command")
def test_run_command_safe(mock_run_cmd):
    """Verify safe shell returns stdout strictly on 0, and None on error paths."""
    # Scenario A: Command returns cleanly
    mock_run_cmd.return_value = (0, "active", "")
    assert run_command_safe("systemctl is-active docker") == "active"

    # Scenario B: Command exits non-zero
    mock_run_cmd.return_value = (3, "", "inactive")
    assert run_command_safe("systemctl is-active docker") is None


@patch("snippets.shell_utils.run_command")
def test_command_exists(mock_run_cmd):
    """Verify POSIX 'which' route translates exit code metrics to boolean status maps."""
    # Scenario A: Tool exists on machine paths
    mock_run_cmd.return_value = (0, "/usr/bin/git", "")
    assert command_exists("git") is True
    mock_run_cmd.assert_called_with(["which", "git"])

    # Scenario B: Tool missing from machine paths
    mock_run_cmd.return_value = (1, "", "git not found")
    assert command_exists("git") is False
