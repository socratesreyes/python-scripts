"""
AWS utilities using boto3.
All functions accept an optional region. Credentials come from the
standard AWS chain (env vars, ~/.aws/credentials, IAM role).

Works with LocalStack if you set endpoint_url.
"""

import os
import boto3  # The official AWS SDK for Python
from datetime import datetime, timedelta


def get_client(service, region=None, endpoint_url=None):
    """
    Build a boto3 client. If LOCALSTACK_ENDPOINT is set in env,
    it uses that instead of real AWS.
    """
    region = region or os.environ.get("AWS_REGION", "us-east-1")

    # If LOCALSTACK_ENDPOINT is set, point boto3 at LocalStack instead of AWS.
    # Otherwise, endpoint_url stays None and boto3 talks to real AWS.
    endpoint_url = endpoint_url or os.environ.get("LOCALSTACK_ENDPOINT")

    return boto3.client(service, region_name=region, endpoint_url=endpoint_url)


def list_ec2_instances(region=None, state="running"):
    """
    Return a list of EC2 instances filtered by state.
    Each dict has: id, type, state, name, launch_time.
    """
    ec2 = get_client("ec2", region=region)

    # Filters narrow down which instances we get back.
    # We only ask for instances in the requested state.
    response = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": [state]}]
    )

    instances = []

    # EC2 responses nest instances inside "Reservations" — this is an AWS quirk.
    for reservation in response["Reservations"]:
        for inst in reservation["Instances"]:

            # Find the "Name" tag — the human-friendly label in the console.
            name = ""
            for tag in inst.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break

            instances.append({
                "id": inst["InstanceId"],
                "type": inst["InstanceType"],
                "state": inst["State"]["Name"],
                "name": name,
                # Convert datetime → string so the data is JSON-serializable.
                "launch_time": inst["LaunchTime"].isoformat(),
            })
    return instances


def get_cloudwatch_metric(namespace, metric_name, dimensions, region=None,
                          period=86400, statistic="Average", days=7):
    """
    Fetch a CloudWatch metric's average over the last N days.
    dimensions is a list of dicts like [{"Name": "InstanceId", "Value": "i-123"}].
    Returns a float (the statistic) or None.
    """
    cw = get_client("cloudwatch", region=region)

    # CloudWatch wants an explicit start and end time for the query window.
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    response = cw.get_metric_statistics(
        Namespace=namespace,           # e.g., "AWS/EC2"
        MetricName=metric_name,        # e.g., "CPUUtilization"
        Dimensions=dimensions,         # Which resource to look at
        StartTime=start,
        EndTime=end,
        Period=period,                 # Granularity in seconds (86400 = 1 day)
        Statistics=[statistic],        # "Average", "Maximum", "Sum", etc.
    )

    datapoints = response.get("Datapoints", [])
    if not datapoints:
        return None  # No data → return None instead of crashing.

    # Average across all the datapoints we got back.
    values = [dp[statistic] for dp in datapoints]
    return round(sum(values) / len(values), 2)


def find_idle_ec2(cpu_threshold=5, region=None):
    """
    Find running EC2 instances whose average CPU over 7 days is below
    cpu_threshold. This is the classic 'AWS cost savings' interview question.
    """
    idle = []

    # Loop through every running instance and check its CPU.
    for inst in list_ec2_instances(region=region, state="running"):
        avg_cpu = get_cloudwatch_metric(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions=[{"Name": "InstanceId", "Value": inst["id"]}],
            region=region,
        )
        # Only flag it if we got a number back AND it's below the threshold.
        if avg_cpu is not None and avg_cpu < cpu_threshold:
            inst["avg_cpu"] = avg_cpu  # Enrich the dict with the CPU value
            idle.append(inst)
    return idle


def list_s3_buckets(region=None):
    """Return a list of all S3 bucket names."""
    s3 = get_client("s3", region=region)
    response = s3.list_buckets()
    # get("Buckets", []) handles the case where there are no buckets at all.
    return [b["Name"] for b in response.get("Buckets", [])]