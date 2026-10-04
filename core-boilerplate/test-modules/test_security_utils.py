import pytest
from unittest.mock import patch
from snippets.security_utils import (
    parse_trivy_report,
    filter_by_severity,
    summarize_vulns,
    has_fix_available,
)

# =====================================================================
# 1. FIXTURES FOR TRIVY DATA MOCKING
# =====================================================================

@pytest.fixture
def mock_trivy_data():
    """Returns a valid Trivy report structure mirroring production schemas."""
    return {
        "Results": [
            {
                "Target": "ubuntu:22.04 (ubuntu 22.04)",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-0001",
                        "PkgName": "openssl",
                        "Severity": "CRITICAL",
                        "InstalledVersion": "3.0.2-0ubuntu1.10",
                        "FixedVersion": "3.0.2-0ubuntu1.11",
                        "Title": "Remote Code Execution in SSL Handshake"
                    },
                    {
                        "VulnerabilityID": "CVE-2026-0002",
                        "PkgName": "libc6",
                        "Severity": "HIGH",
                        "InstalledVersion": "2.35-0ubuntu3.1",
                        "FixedVersion": "",
                        "Title": "Memory Leakage via System Buffers"
                    }
                ]
            },
            {
                "Target": "python-requirements.txt",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-0003",
                        "PkgName": "requests",
                        "Severity": "CRITICAL",
                        "InstalledVersion": "2.28.1",
                        "FixedVersion": "2.31.0",
                        "Title": "SSRF in Session Keep-Alive"
                    }
                ]
            }
        ]
    }


# =====================================================================
# 2. TRIVY REPORT PARSING SUITE
# =====================================================================

@patch("snippets.security_utils.read_json")
def test_parse_trivy_report_success(mock_read, mock_trivy_data):
    """Verify that hierarchical Trivy reports flatten into clear, distinct dictionary lists."""
    mock_read.return_value = mock_trivy_data

    vulns = parse_trivy_report("/opt/reports/trivy.json")
    
    assert len(vulns) == 3
    assert vulns[0]["cve"] == "CVE-2026-0001"
    assert vulns[0]["target"] == "ubuntu:22.04 (ubuntu 22.04)"
    assert vulns[2]["package"] == "requests"


@patch("snippets.security_utils.read_json")
def test_parse_trivy_report_empty_or_failed(mock_read):
    """Verify missing file handling pathways gracefully degrade to an empty array."""
    mock_read.return_value = None
    assert parse_trivy_report("/opt/reports/missing_trivy.json") == []


# =====================================================================
# 3. FILTERING, SUMMARIZATION & FIX DETECTION SUITE
# =====================================================================

def test_filter_by_severity():
    """Verify severity matching works across both uppercase and lowercase arguments."""
    sample_vulns = [
        {"cve": "CVE-1", "severity": "CRITICAL"},
        {"cve": "CVE-2", "severity": "HIGH"},
        {"cve": "CVE-3", "severity": "CRITICAL"},
    ]
    
    critical_cases = filter_by_severity(sample_vulns, severity="critical")
    assert len(critical_cases) == 2
    assert critical_cases[0]["cve"] == "CVE-1"


def test_summarize_vulns():
    """Verify vulnerability severity matrix compilation math handles untracked labels."""
    sample_vulns = [
        {"severity": "CRITICAL"},
        {"severity": "HIGH"},
        {"severity": "CRITICAL"},
        {"severity": "LOW"},
        {"no_severity_key": "malformed"},
    ]
    
    summary = summarize_vulns(sample_vulns)
    
    assert summary["CRITICAL"] == 2
    assert summary["HIGH"] == 1
    assert summary["LOW"] == 1
    assert summary["UNKNOWN"] == 1


def test_has_fix_available():
    """Verify fix indicator validation evaluates empty vs populated strings accurately."""
    # Scenario A: Fix version is available
    assert has_fix_available({"cve": "CVE-1", "fixed": "1.2.3"}) is True
    
    # Scenario B: Fix version field is empty
    assert has_fix_available({"cve": "CVE-2", "fixed": ""}) is False
    
    # Scenario C: Fix version field is omitted/None
    assert has_fix_available({"cve": "CVE-3", "fixed": None}) is False
