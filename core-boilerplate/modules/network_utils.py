"""
Network utilities: HTTP checks, TCP port checks, DNS, SSL expiry.
All functions return structured data — no printing, no alerts.
"""

import socket     # For TCP connections and DNS resolution
import ssl        # For SSL certificate inspection
import datetime   # For calculating SSL cert expiry
import requests   # Third-party library for HTTP — install with pip


def check_http_status(url, timeout=5, expected_status=200):
    """
    Ping a URL. Return (is_ok, status_code, latency_ms, error_message).
    """
    import time
    start = time.time()  # Capture start time BEFORE the request
    try:
        # timeout=5 is CRITICAL. Without it, requests hangs forever
        # if the server never responds.
        response = requests.get(url, timeout=timeout)

        # Convert elapsed time from seconds (float) to milliseconds (int)
        latency = int((time.time() - start) * 1000)

        # Compare to expected — normally 200, but could be 201, 204, etc.
        is_ok = response.status_code == expected_status

        # Return 4 values as a tuple — the caller unpacks them.
        return is_ok, response.status_code, latency, None

    # Each except block catches a specific failure so we can report it clearly.
    except requests.exceptions.Timeout:
        # Server was too slow. 504 is the standard "gateway timeout" code.
        return False, 504, timeout * 1000, "Timeout"
    except requests.exceptions.ConnectionError:
        # DNS failed, host unreachable, or connection refused. 503 = unavailable.
        return False, 503, 0, "Connection error"
    except Exception as e:
        # Catch-all for anything unexpected. Never let a script crash silently.
        return False, 500, 0, str(e)


def check_tcp_port(host, port, timeout=3):
    """
    Check if a TCP port is open. Returns True or False.
    Good for: is Postgres up? Is SSH open? Is Redis reachable?
    """
    try:
        # create_connection does a full TCP handshake in one call.
        # If it succeeds, the port is open. If not, an exception is raised.
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_dns(hostname):
    """
    Resolve a hostname. Returns the IP as a string, or None if it fails.
    """
    try:
        # gethostbyname returns the first IPv4 address for the hostname.
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        # gaierror = "get address info error" — DNS lookup failed.
        return None


def check_ssl_expiry(hostname, port=443, warn_days=30):
    """
    Check how many days until an SSL cert expires.
    Returns a dict with days_left, expires_on, and is_warning.
    """
    try:
        # Create a default SSL context — same as what curl/browsers use.
        context = ssl.create_default_context()

        # Open a TCP connection to the host on port 443.
        with socket.create_connection((hostname, port), timeout=5) as sock:
            # Wrap the raw socket in TLS. server_hostname enables SNI
            # (Server Name Indication) so we get the right cert.
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()  # Returns a dict of cert fields
                expiry_str = cert["notAfter"]  # Format: "Jan 15 12:00:00 2026 GMT"

                # Convert the string into a real datetime object.
                expiry_date = datetime.datetime.strptime(
                    expiry_str, "%b %d %H:%M:%S %Y %Z"
                )

                # Subtract now from expiry to get remaining days.
                days_left = (expiry_date - datetime.datetime.utcnow()).days

                return {
                    "hostname": hostname,
                    "days_left": days_left,
                    "expires_on": expiry_date.strftime("%Y-%m-%d"),
                    # Warn if we're within warn_days of expiration.
                    "is_warning": days_left <= warn_days,
                }
    except Exception as e:
        return {"hostname": hostname, "error": str(e)}