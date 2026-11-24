from collections.abc import Callable, Iterator
from pathlib import Path

import boto3
import pytest
from lasrc_ancillary.providers.gdas.fetch import NODD_BUCKET
from moto import mock_aws

DATA = Path(__file__).parent / "data"
F00 = DATA / "gdas.20261115.t00z.1p00.grib2"
F06 = DATA / "gdas.20261115.t06z.1p00.grib2"
K00 = "gdas.20261115/00/atmos/gdas.t00z.pgrb2.1p00.f000"
K06 = "gdas.20261115/06/atmos/gdas.t06z.pgrb2.1p00.f000"
REGION = "us-east-1"


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake AWS credentials and region, so no client can reach a real account."""
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def mocked_aws(aws_credentials: None) -> Iterator[None]:
    """moto's in-memory AWS, shared by every boto3 client a test creates."""
    with mock_aws():
        yield


@pytest.fixture
def s3(mocked_aws: None):
    """A moto S3 client with an empty NODD bucket."""
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=NODD_BUCKET)
    return client


@pytest.fixture
def put(s3) -> Callable[..., None]:
    """Put ``{key: bytes}`` into ``bucket`` (default: the NODD bucket), creating it if needed."""

    def _put(objects: dict[str, bytes], bucket: str = NODD_BUCKET) -> None:
        existing = {b["Name"] for b in s3.list_buckets()["Buckets"]}
        if bucket not in existing:
            s3.create_bucket(Bucket=bucket)
        for key, body in objects.items():
            s3.put_object(Bucket=bucket, Key=key, Body=body)

    return _put


@pytest.fixture
def nodd(s3, put) -> Callable[..., object]:
    """A bucket (default: the NODD bucket) holding any of the fixture cycles K00 and K06."""

    def _nodd(*keys: str, bucket: str = NODD_BUCKET):
        data = {K00: F00, K06: F06}
        put({k: data[k].read_bytes() for k in keys}, bucket=bucket)
        return s3

    return _nodd
