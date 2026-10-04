import socket
import ssl
import datetime
import pytest
from unittest.mock import patch, MagicMock
import requests
from snippets.network_utils import (
    check_http_status,
    check_tcp_port,
    check_dns,
    check_ssl_expiry,
)

# =====================================================================
# 1. HTTP REQUESTS UTILITIES SUITE
# =====================================================================

@patch("snippets.network_utils.requests.get")
def test_check_http_status_success(mock_get):
    """Verify happy-path HTTP execution parses matching status codes."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    is_ok, status, latency, error = check_http_status("https://api.internal", expected_status=200)

    assert is_ok is True
    assert status == 200
    assert latency >= 0
    assert error is None


@patch("snippets.network_utils.requests.get")
def test_check_http_status_timeout(mock_get):
    """Verify Timeout exceptions translate safely into a 504 status code."""
    mock_get.side_effect = requests.exceptions.Timeout()

    is_ok, status, latency, error = check_http_status("https://slow.internal", timeout=3)

    assert is_ok is False
    assert status == 504
    assert latency == 3000  # calculated threshold from timeout limit
    assert error == "Timeout"


@patch("snippets.network_utils.requests.get")
def test_check_http_status_connection_error(mock_get):
    """Verify connection errors map gracefully to a 503 error configuration."""
    mock_get.side_effect = requests.exceptions.ConnectionError()

    is_ok, status, latency, error = check_http_status("https://missing-dns.internal")

    assert is_ok is False
    assert status == 503
    assert error == "Connection error"


# =====================================================================
# 2. RAW TCP & DNS LOOKUP SUITE
# =====================================================================

@patch("snippets.network_utils.socket.create_connection")
def test_check_tcp_port_open(mock_connect):
    """Verify True status when a TCP port socket establishes successfully."""
    # Context manager setup mock configuration
    mock_connect.return_value.__enter__.return_value = MagicMock()
    
    assert check_tcp_port("localhost", 5432) is True
    mock_connect.assert_called_once_with(("localhost", 5432), timeout=3)


@patch("snippets.network_utils.socket.create_connection")
def test_check_tcp_port_closed(mock_connect):
    """Verify False return when connection triggers a socket error or timeout."""
    mock_connect.side_effect = socket.timeout()
    assert check_tcp_port("localhost", 22) is False


@patch("snippets.network_utils.socket.gethostbyname")
def test_check_dns_success(mock_gethost):
    """Verify clean string routing for standard A-record lookup."""
    mock_gethost.return_value = "10.0.0.5"
    assert check_dns("db.local") == "10.0.0.5"


@patch("snippets.network_utils.socket.gethostbyname")
def test_check_dns_failure(mock_gethost):
    """Verify None wrapper encapsulation when socket.gaierror trips."""
    mock_gethost.side_effect = socket.gaierror()
    assert check_dns("ghost-endpoint.internal") is None


# =====================================================================
# 3. SSL EXPIRY SUITE
# =====================================================================

@patch("snippets.network_utils.datetime.datetime")
@patch("snippets.network_utils.ssl.create_default_context")
@patch("snippets.network_utils.socket.create_connection")
def test_check_ssl_expiry_warning(mock_connect, mock_ssl_context, mock_datetime):
    """Verify dictionary parsing logic handles warning conditions properly."""
    # 1. Establish structural boundaries for the mocked peer certificate
    mock_ssock = MagicMock()
    mock_ssock.getpeercert.return_value = {"notAfter": "Nov 01 22:30:00 2026 GMT"}
    
    mock_context_instance = MagicMock()
    mock_context_instance.wrap_socket.return_value.__enter__.return_value = mock_ssock
    mock_ssl_context.return_value = mock_context_instance
    
    # 2. Pin today's execution date to anchor calculated deltas
    mock_datetime.utcnow.return_value = datetime.datetime(2026, 10, 1, 22, 30, 0)
    mock_datetime.strptime = datetime.datetime.strptime

    # 3. Run validation check with warning threshold set to 40 days
    result = check_ssl_expiry("secured-app.internal", warn_days=40)

    # Oct 1 to Nov 1 = 31 days left (which triggers a warning since 31 <= 40)
    assert result["hostname"] == "secured-app.internal"
    assert result["days_left"] == 31
    assert result["expires_on"] == "2026-11-01"
    assert result["is_warning"] is True


@patch("snippets.network_utils.ssl.create_default_context")
def test_check_ssl_expiry_error_containment(mock_ssl_context):
    """Verify that SSL handshakes breaking due to protocol errors return an error key."""
    mock_ssl_context.side_effect = ssl.SSLError("Certificate verification failed")
    
    result = check_ssl_expiry("expired.internal")
    
    assert result["hostname"] == "expired.internal"
    assert "error" in result
