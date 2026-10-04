"""
API Healthcheck Script
----------------------
Checks if an API is up, sends a Slack alert if it's down, and can run
either as a local CLI tool or as an AWS Lambda function.

Author: <your name>
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
# BLOCK 1: LOGGING SETUP
# ============================================================
# Why: We use logging instead of print() so the output includes
# timestamps and severity levels. CloudWatch (in AWS) can read this.
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# BLOCK 2: FETCH SECRETS
# ============================================================
# Why: Never hardcode passwords or webhook URLs in code. We fetch
# them from AWS Secrets Manager. For local testing, we read them
# from environment variables instead.
# ============================================================
def get_secret(secret_name):
    """
    Fetch a secret string from AWS Secrets Manager.
    If USE_LOCALSTACK is 'true', read from environment variables instead.
    """
    # Local testing path: read from environment variable
    if os.environ.get("USE_LOCALSTACK") == "true":
        logger.info("Using local environment variable instead of AWS Secrets Manager")
        return os.environ.get(secret_name)

    # Production path: call AWS Secrets Manager
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
# Why: This is the actual work. Ping the URL, check the status code,
# measure how long it took. Catch network errors so the script
# does not crash.
# ============================================================
def check_api_health(url, timeout=5):
    """
    Ping a URL and return a tuple: (is_healthy, message, status_code, latency_ms).
    """
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
# Why: Automation is useless if nobody knows it failed. Send a
# message to a Slack webhook when the API is down.
# ============================================================
def send_alert(webhook_url, message):
    """
    Send a simple alert message to a Slack webhook URL.
    """
    if not webhook_url:
        logger.warning("No webhook URL provided. Skipping alert.")
        return

    payload = {"text": f"API HEALTH ALERT: {message}"}

    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("Alert sent to Slack successfully")
        else:
            logger.error(f"Failed to send alert. Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending alert: {e}")


# ============================================================
# BLOCK 5: THE ORCHESTRATOR
# ============================================================
# Why: Combine the pieces. This function is called by BOTH the
# CLI entry point and the Lambda handler, so we only write the
# logic once.
# ============================================================
def run_healthcheck(target_url, webhook_url):
    """
    Run the healthcheck. If the API is down, send an alert.
    Returns True if healthy, False if not.
    """
    is_healthy, message, status_code, latency_ms = check_api_health(target_url)

    if not is_healthy:
        alert_message = (
            f"Target: {target_url} | "
            f"Status: {status_code} | "
            f"Reason: {message}"
        )
        send_alert(webhook_url, alert_message)

    return is_healthy


# ============================================================
# BLOCK 6: AWS LAMBDA HANDLER
# ============================================================
# Why: Lambda needs a specific function name and signature. It
# receives an "event" (the trigger data) and a "context" (runtime
# info). It must return a dictionary with statusCode and body.
# ============================================================
def lambda_handler(event, context):
    """
    Entry point when this script runs as an AWS Lambda function.
    """
    logger.info("Lambda function started")

    try:
        secret_string = get_secret("devops/healthcheck/config")
        config = json.loads(secret_string)
        target_url = config.get("api_url")
        webhook_url = config.get("slack_webhook")
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

    is_healthy = run_healthcheck(target_url, webhook_url)

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
# Why: This block runs ONLY when you execute the script directly
# (python healthcheck.py). It does NOT run when Lambda imports
# the file. That is the purpose of the if __name__ check.
# ============================================================
if __name__ == "__main__":
    logger.info("Starting healthcheck as CLI tool")

    # Read from environment variables for local testing
    target_url = os.environ.get("api_url")
    webhook_url = os.environ.get("slack_webhook")

    if not target_url:
        logger.error("Environment variable 'api_url' is not set")
        sys.exit(1)

    is_healthy = run_healthcheck(target_url, webhook_url)

    # Exit code 0 = success, 1 = failure. CI/CD pipelines use this.
    sys.exit(0 if is_healthy else 1)


