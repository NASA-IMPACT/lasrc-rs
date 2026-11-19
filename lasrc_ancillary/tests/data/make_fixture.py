"""Rebuild the committed GDAS fixtures: PWAT and TOZNE from two consecutive 1 degree cycles.

Run from the repository root:

    uv run python -I lasrc_ancillary/tests/data/make_fixture.py
"""

from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from lasrc_ancillary.nodd import fetch_gdas

HERE = Path(__file__).resolve().parent
KEYS = {
    "gdas.20261115.t00z.1p00.grib2": "gdas.20261115/00/atmos/gdas.t00z.pgrb2.1p00.f000",
    "gdas.20261115.t06z.1p00.grib2": "gdas.20261115/06/atmos/gdas.t06z.pgrb2.1p00.f000",
}


def main() -> None:
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    for name, key in KEYS.items():
        out = fetch_gdas(key, HERE / name, s3)
        print(f"{out.name}: {out.stat().st_size} bytes from {key}")


if __name__ == "__main__":
    main()
