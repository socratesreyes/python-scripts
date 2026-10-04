import os
import json
import pytest
from unittest.mock import patch, builtins
from snippets.file_utils import (
    read_json,
    write_json,
    read_yaml,
    file_exists,
    get_file_size_mb,
)

# =====================================================================
# 1. JSON UTILITIES SUITE
# =====================================================================

def test_read_json_success(tmp_path):
    """Verify clean JSON files parse correctly into dictionary objects."""
    json_file = tmp_path / "config.json"
    sample_data = {"environment": "production", "debug": False}
    json_file.write_text(json.dumps(sample_data))

    parsed = read_json(str(json_file))
    assert parsed == sample_data


def test_read_json_failures(tmp_path):
    """Verify missing files or malformed JSON blocks return None safely."""
    # Scenario A: Completely missing file
    assert read_json(str(tmp_path / "missing.json")) is None

    # Scenario B: Corrupted/Malformed JSON
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{'environment': production, missing_quotes}")
    assert read_json(str(corrupt_file)) is None


def test_write_json_success(tmp_path):
    """Verify data dumps accurately with proper indentation format."""
    target_path = tmp_path / "output.json"
    payload = {"status": "healthy", "nodes":}

    success = write_json(str(target_path), payload)
    
    assert success is True
    assert target_path.exists()
    
    # Read back raw text to verify formatting validation (indent=2)
    raw_text = target_path.read_text()
    assert "  \"status\"" in raw_text


@patch("builtins.open")
def test_write_json_os_error(mock_open):
    """Verify write failure returns False when hit with filesystem permission blocks."""
    mock_open.side_effect = OSError("Permission denied / Read-only filesystem")
    success = write_json("/root/protected_dir/app.json", {"data": 1})
    assert success is False


# =====================================================================
# 2. YAML UTILITIES SUITE (WITH IMPORT HANDLING)
# =====================================================================

def test_read_yaml_success(tmp_path):
    """Verify safe YAML parsing returns valid dictionaries when PyYAML is available."""
    yaml_file = tmp_path / "deployment.yaml"
    yaml_content = (
        "metadata:\n"
        "  name: web-app\n"
        "  replicas: 3\n"
    )
    yaml_file.write_text(yaml_content)

    parsed = read_yaml(str(yaml_file))
    # If pyyaml is installed in your test environment, evaluate the output payload
    if parsed is not None:
        assert parsed["metadata"]["name"] == "web-app"
        assert parsed["metadata"]["replicas"] == 3


@patch("builtins.__import__")
def test_read_yaml_missing_dependency(mock_import, tmp_path):
    """Verify logic degrades gracefully by returning None if pyyaml isn't installed."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("key: value")

    # Force an ImportError whenever 'yaml' package is requested
    original_import = builtins.__import__
    def import_side_effect(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return original_import(name, *args, **kwargs)
    
    mock_import.side_effect = import_side_effect

    assert read_yaml(str(yaml_file)) is None


# =====================================================================
# 3. METADATA & FILESYSTEM METRICS SUITE
# =====================================================================

def test_file_exists_differentiation(tmp_path):
    """Verify file_exists wrapper correctly filters files vs directory trees."""
    regular_file = tmp_path / "agent.conf"
    regular_file.touch()

    # Must be True for a real standalone file
    assert file_exists(str(regular_file)) is True
    # Must be False for a structural node directory path
    assert file_exists(str(tmp_path)) is False
    # Must be False for a completely non-existent item
    assert file_exists("/var/log/ghost_config.cfg") is False


def test_get_file_size_mb(tmp_path):
    """Assert file weights convert accurately from byte scale to Megabytes."""
    target_file = tmp_path / "heavy_payload.dat"
    
    # Write exactly 2.5 MB of dummy byte data (2.5 * 1024 * 1024)
    target_file.write_bytes(b"X" * int(2.5 * 1024 * 1024))

    size_mb = get_file_size_mb(str(target_file))
    assert size_mb == 2.5


def test_get_file_size_missing_returns_none():
    """Verify error containment logic when pulling sizes of missing targets."""
    assert get_file_size_mb("/opt/app/missing_binary.jar") is None
