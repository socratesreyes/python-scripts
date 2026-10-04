"""
Security utilities: parse vulnerability scan reports.
Supports Trivy JSON output. Easy to extend for Snyk/Grype.
"""

from snippets.file_utils import read_json  # Reuse our JSON reader


def parse_trivy_report(path):
    """
    Parse a Trivy JSON report. Returns a flat list of vulnerabilities
    with fields: cve, package, severity, installed, fixed, title.
    """
    data = read_json(path)
    if not data:
        return []  # Missing or invalid file — return empty list, not a crash.

    vulns = []

    # Trivy groups results by "Target" (like a Docker layer or a file).
    for result in data.get("Results", []):
        target = result.get("Target", "")

        # Vulnerabilities can be null in the JSON — hence the `or []`.
        for v in result.get("Vulnerabilities", []) or []:
            # Flatten into one dict per vuln so it's easy to filter later.
            vulns.append({
                "target": target,
                "cve": v.get("VulnerabilityID"),
                "package": v.get("PkgName"),
                "severity": v.get("Severity"),
                "installed": v.get("InstalledVersion"),
                "fixed": v.get("FixedVersion"),
                "title": v.get("Title"),
            })
    return vulns


def filter_by_severity(vulns, severity="CRITICAL"):
    """Return only vulnerabilities matching a given severity."""
    # .upper() so "critical" and "CRITICAL" both work.
    return [v for v in vulns if v.get("severity") == severity.upper()]


def summarize_vulns(vulns):
    """
    Count vulnerabilities by severity.
    Returns a dict like {"CRITICAL": 3, "HIGH": 12, "MEDIUM": 45}.
    """
    summary = {}
    for v in vulns:
        sev = v.get("severity", "UNKNOWN")
        # Increment the counter for this severity, starting at 0 if new.
        summary[sev] = summary.get(sev, 0) + 1
    return summary


def has_fix_available(vuln):
    """Return True if a fixed version is available."""
    fixed = vuln.get("fixed")
    # bool() converts None or "" to False, and a real string to True.
    return bool(fixed and fixed != "")