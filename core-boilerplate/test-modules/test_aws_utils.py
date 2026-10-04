import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from snippets.aws_utils import (
    get_client,
    list_ec2_instances,
    get_cloudwatch_metric,
    find_idle_ec2,
    list_s3_buckets
)

@pytest.fixture
def mock_env_localstack():
    """Fixture to simulate a LocalStack environment configuration."""
    with patch.dict(os.environ, {"LOCALSTACK_ENDPOINT": "http://localhost:4566", "AWS_REGION": "us-west-2"}):
        yield

@patch("snippets.aws_utils.boto3.client")
def test_get_client_localstack(mock_boto_client, mock_env_localstack):
    """Ensure get_client respects LocalStack environment variables."""
    get_client("s3")
    mock_boto_client.assert_called_once_with(
        "s3", 
        region_name="us-west-2", 
        endpoint_url="http://localhost:4566"
    )

@patch("snippets.aws_utils.get_client")
def test_list_ec2_instances(mock_get_client):
    """Verify EC2 response parsing and Tag extraction matches AWS schema."""
    mock_ec2 = MagicMock()
    mock_get_client.return_value = mock_ec2
    
    # Mocking AWS's standard nested structure for describe_instances
    mock_ec2.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-0123456789abcdef0",
                        "InstanceType": "t3.micro",
                        "State": {"Name": "running"},
                        "Tags": [{"Key": "Name", "Value": "prod-web-server"}],
                        "LaunchTime": datetime(2026, 10, 1)
                    }
                ]
            }
        ]
    }

    result = list_ec2_instances(region="us-east-1", state="running")
    
    assert len(result) == 1
    assert result[0]["id"] == "i-0123456789abcdef0"
    assert result[0]["name"] == "prod-web-server"
    assert "2026-10-01" in result[0]["launch_time"]

@patch("snippets.aws_utils.get_client")
def test_get_cloudwatch_metric(mock_get_client):
    """Verify average calculation across returned metric datapoints."""
    mock_cw = MagicMock()
    mock_get_client.return_value = mock_cw
    mock_cw.get_metric_statistics.return_value = {
        "Datapoints": [{"Average": 10.0}, {"Average": 20.0}]
    }

    avg = get_cloudwatch_metric("AWS/EC2", "CPUUtilization", [{"Name": "InstanceId", "Value": "i-123"}])
    assert avg == 15.0

@patch("snippets.aws_utils.get_cloudwatch_metric")
@patch("snippets.aws_utils.list_ec2_instances")
def test_find_idle_ec2(mock_list, mock_metric):
    """Test the classic 'cost savings' logic flags sub-threshold instances."""
    mock_list.return_value = [
        {"id": "i-idle", "type": "t3.micro", "state": "running", "name": "zombie-server"}
    ]
    # Simulate an average CPU of 2%, which is below the default 5% threshold
    mock_metric.return_value = 2.0

    idle_servers = find_idle_ec2(cpu_threshold=5)
    assert len(idle_servers) == 1
    assert idle_servers[0]["id"] == "i-idle"
    assert idle_servers[0]["avg_cpu"] == 2.0

@patch("snippets.aws_utils.get_client")
def test_list_s3_buckets(mock_get_client):
    """Verify extraction of S3 bucket names from standard response list."""
    mock_s3 = MagicMock()
    mock_get_client.return_value = mock_s3
    mock_s3.list_buckets.return_value = {
        "Buckets": [{"Name": "company-tf-state"}, {"Name": "user-uploads-bucket"}]
    }

    buckets = list_s3_buckets()
    assert buckets == ["company-tf-state", "user-uploads-bucket"]
