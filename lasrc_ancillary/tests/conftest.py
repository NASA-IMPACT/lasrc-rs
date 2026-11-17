from collections.abc import Callable, Iterator
from pathlib import Path

import boto3
import pytest
from lasrc_ancillary.nodd import BUCKET
from moto import mock_aws

DATA = Path(__file__).parent / "data"
F00 = DATA / "gdas.20261115.t00z.1p00.grib2"
F06 = DATA / "gdas.20261115.t06z.1p00.grib2"
K00 = "gdas.20261115/00/atmos/gdas.t00z.pgrb2.1p00.f000"
K06 = "gdas.20261115/06/atmos/gdas.t06z.pgrb2.1p00.f000"


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    """A moto S3 client with an empty NODD bucket."""
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


@pytest.fixture
def put(s3) -> Callable[[dict[str, bytes]], None]:
    """Put ``{key: bytes}`` into the NODD bucket."""

    def _put(objects: dict[str, bytes]) -> None:
        for key, body in objects.items():
            s3.put_object(Bucket=BUCKET, Key=key, Body=body)

    return _put


@pytest.fixture
def nodd(s3, put) -> Callable[..., object]:
    """The NODD bucket holding any of the fixture cycles K00 and K06."""

    def _nodd(*keys: str):
        data = {K00: F00, K06: F06}
        put({k: data[k].read_bytes() for k in keys})
        return s3

    return _nodd
