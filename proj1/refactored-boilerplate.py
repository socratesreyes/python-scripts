"""
API & Disk Space Healthcheck Script
----------------------
Checks if an API is up and screens system mount points for critical storage usage.
Sends a Slack alert if anomalies are found. Can run as a local CLI tool or an AWS Lambda.

Author: DevOps Engineer
"""

import os
import sys
import json
import logging
import time
import requests
import boto3
from botocore.exceptions import ClientError

# ============================================================
# LEGO BRICK IMPORT
# ============================================================
from snippets.disk_utils import get_critical_mounts

# ============================================================
# BLOCK 1: LOGGING SETUP
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# BLOCK 2: FETCH SECRETS
# ============================================================
def get_secret(secret_name):
    """Fetch configuration payload from local environment or AWS Secrets Manager."""
    if os.environ.get("USE_LOCALSTACK") == "true":
        logger.info("Using local environment variable instead of AWS Secrets Manager")
        return os.environ.get(secret_name)

    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)

    try:
        response = client.get_secret_value(SecretId=secret_name)
        return response["SecretString"]
    except ClientError as e:
        logger.error(f"Could not fetch secret '{secret_name}': {e}")
        raise


# ============================================================
# BLOCK 3: THE HEALTHCHECK LOGIC
# ============================================================
def check_api_health(url, timeout=5):
    """Ping a URL and return a tuple: (is_healthy, message, status_code, latency_ms)."""
    start_time = time.time()
    try:
        logger.info(f"Checking API: {url}")
        response = requests.get(url, timeout=timeout)
        latency_ms = int((time.time() - start_time) * 1000)

        if response.status_code == 200:
            logger.info(f"SUCCESS: {url} is healthy. Latency: {latency_ms}ms")
            return True, "API is healthy", response.status_code, latency_ms
        else:
            logger.warning(f"FAILED: {url} returned {response.status_code}")
            return False, f"API returned {response.status_code}", response.status_code, latency_ms

    except requests.exceptions.Timeout:
        logger.error(f"TIMEOUT: {url} took longer than {timeout} seconds")
        return False, "API Timeout", 504, timeout * 1000
    except requests.exceptions.ConnectionError:
        logger.error(f"CONNECTION ERROR: Could not reach {url}")
        return False, "Connection Error", 503, 0
    except Exception as e:
        logger.error(f"UNKNOWN ERROR checking {url}: {e}")
        return False, str(e), 500, 0


# ============================================================
# BLOCK 4: SEND ALERTS
# ============================================================
def send_alert(webhook_url, message):
    """Send an alert message to a Slack webhook URL."""
    if not webhook_url:
        logger.warning("No webhook URL provided. Skipping alert.")
        return

    payload = {"text": message}  # Keeping text dynamic based on caller criteria

    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("Alert sent to Slack successfully")
        else:
            logger.error(f"Failed to send alert. Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending alert: {e}")


# ============================================================
# BLOCK 5: THE ORCHESTRATOR (Refactored Pattern)
# ============================================================
def run_healthcheck(target_url, webhook_url, disk_threshold=85):
    """
    Run healthchecks for both the API endpoint and system disk spaces.
    Fails the complete transaction if any subset health condition fails.
    """
    results = []

    # --- VECTOR 1: API Check ---
    is_api_healthy, message, status_code, _ = check_api_health(target_url)
    if not is_api_healthy:
        alert_msg = f"API HEALTH ALERT: Target: {target_url} | Status: {status_code} | Reason: {message}"
        send_alert(webhook_url, alert_msg)
    results.append(is_api_healthy)

    # --- VECTOR 2: Disk Space Check (Graceful Fallback handling built-in) ---
    try:
        logger.info(f"Running file system storage validation against threshold: {disk_threshold}%")
        critical_mounts = get_critical_mounts(threshold=disk_threshold)
    except Exception as e:
        logger.error(f"Unexpected disk validation crash: {e}. Defaulting execution matrix to safe.")
        critical_mounts = []

    if critical_mounts:
        results.append(False)  # Mark run execution status bad
        for mount in critical_mounts:
            # String structural matches strict Acceptance Criteria template
            disk_alert_msg = (
                f"DISK CRITICAL: {mount['path']} is at {mount['percent_used']}% "
                f"({mount['used_gb']}GB/{mount['total_gb']}GB)"
            )
            send_alert(webhook_url, disk_alert_msg)
    else:
        logger.info("All scanned disk mount parameters are safe.")
        results.append(True)

    # Returns True only if every entity inside the index checks out completely
    return all(results)


# ============================================================
# BLOCK 6: AWS LAMBDA HANDLER
# ============================================================
def lambda_handler(event, context):
    """Entry point when this script runs as an AWS Lambda function."""
    logger.info("Lambda function started")

    try:
        secret_string = get_secret("devops/healthcheck/config")
        config = json.loads(secret_string)
        target_url = config.get("api_url")
        webhook_url = config.get("slack_webhook")
        disk_threshold = int(config.get("disk_threshold", 85))
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps("Failed to load configuration")
        }

    if not target_url:
        return {
            "statusCode": 400,
            "body": json.dumps("Missing 'api_url' in config")
        }

    is_healthy = run_healthcheck(target_url, webhook_url, disk_threshold)

    return {
        "statusCode": 200 if is_healthy else 500,
        "body": json.dumps({
            "healthy": is_healthy,
            "target": target_url
        })
    }


# ============================================================
# BLOCK 7: CLI ENTRY POINT
# ============================================================
if __name__ == "__main__":
    logger.info("Starting healthcheck as CLI tool")

    target_url = os.environ.get("api_url")
    webhook_url = os.environ.get("slack_webhook")
    # Read custom system threshold limits or drop to default baseplate value
    disk_threshold = int(os.environ.get("disk_threshold", 85))

    if not target_url:
        logger.error("Environment variable 'api_url' is not set")
        sys.exit(1)

    is_healthy = run_healthcheck(target_url, webhook_url, disk_threshold)
    sys.exit(0 if is_healthy else 1)
