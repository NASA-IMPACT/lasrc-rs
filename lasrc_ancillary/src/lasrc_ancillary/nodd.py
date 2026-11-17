"""Find and fetch GDAS 0-hour files on the NOAA Open Data Dissemination (NODD) bucket.

Standard library only, so the orchestration can run it in a Lambda. S3 access goes through any
client with boto3's ``list_objects_v2`` and ``get_object``, passed in by the caller.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args

from lasrc_ancillary.cycles import to_utc

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

NODD_BUCKET = "noaa-gfs-bdp-pds"
Resolution = Literal["1p00", "0p25"]
RESOLUTIONS: tuple[Resolution, ...] = get_args(Resolution)
VARIABLES = ("PWAT", "TOZNE")


def _name_pattern(hh: str, resolution: Resolution) -> re.Pattern[str]:
    # The key layout changed over time (see docs/gdas-support.md): gdas1.tHHz.pgrbf00.grib2
    # (1 degree only, until early 2015), then gdas1. and later gdas. with pgrb2.RES.f000, and
    # an atmos/ directory from early 2021.
    forms = [rf"pgrb2\.{resolution}\.f000"]
    if resolution == "1p00":
        forms.append(r"pgrbf00\.grib2")
    return re.compile(rf"^gdas1?\.t{hh}z\.(?:{'|'.join(forms)})$")


def _list_keys(s3_client: S3Client, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    token = None
    while True:
        if token is None:
            page = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        else:
            page = s3_client.list_objects_v2(
                Bucket=bucket, Prefix=prefix, ContinuationToken=token
            )
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
        if not page.get("IsTruncated"):
            return keys
        token = page["NextContinuationToken"]


def cycle_prefix(cycle: datetime) -> str:
    """The key prefix of a GDAS cycle directory, for example ``gdas.20261115/06/``."""
    c = to_utc(cycle)
    return f"gdas.{c:%Y%m%d}/{c.hour:02d}/"


def locate_gdas(
    cycles: Sequence[datetime],
    s3_client: S3Client,
    resolution: Resolution = "1p00",
    bucket: str = NODD_BUCKET,
) -> list[str | None]:
    """The 0-hour file key for each cycle, in order, with None for a cycle that isn't there."""
    if resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {RESOLUTIONS}, got {resolution!r}")
    found: list[str | None] = []
    for cycle in cycles:
        prefix = cycle_prefix(cycle)
        pattern = _name_pattern(f"{to_utc(cycle).hour:02d}", resolution)
        matches = sorted(
            key
            for key in _list_keys(s3_client, bucket, prefix)
            if pattern.match(key.removeprefix(prefix).removeprefix("atmos/"))
        )
        found.append(matches[-1] if matches else None)
    return found


def find_gdas(
    cycles: Sequence[datetime],
    s3_client: S3Client,
    resolution: Resolution = "1p00",
    bucket: str = NODD_BUCKET,
) -> list[str] | None:
    """The 0-hour file key for each cycle, in order, or None while any of them is missing."""
    keys = locate_gdas(cycles, s3_client, resolution, bucket)
    if any(key is None for key in keys):
        return None
    return [key for key in keys if key is not None]


def _idx_ranges(idx_text: str, key: str) -> list[tuple[int, int | None]]:
    entries = []
    for line in idx_text.splitlines():
        parts = line.split(":")
        if len(parts) >= 5:
            entries.append((int(parts[1]), parts[3], parts[4]))
    ranges = []
    for variable in VARIABLES:
        for i, (offset, name, level) in enumerate(entries):
            if name == variable and level.startswith("entire atmosphere"):
                end = entries[i + 1][0] - 1 if i + 1 < len(entries) else None
                ranges.append((offset, end))
                break
        else:
            raise ValueError(
                f"{key}.idx has no {variable} message for the entire atmosphere"
            )
    return ranges


def fetch_gdas(
    key: str, dest: Path, s3_client: S3Client, bucket: str = NODD_BUCKET
) -> Path:
    """Download the PWAT and TOZNE messages of ``key`` into ``dest``.

    With a ``.idx`` inventory, only the two messages are fetched, with range requests. Older
    files have no inventory, so the whole file is fetched.
    """
    dest = Path(dest)
    if key + ".idx" in _list_keys(s3_client, bucket, key + ".idx"):
        idx = s3_client.get_object(Bucket=bucket, Key=key + ".idx")["Body"].read()
        ranges = _idx_ranges(idx.decode(), key)
    else:
        ranges = [(0, None)]
    partial = dest.with_name(dest.name + ".partial")
    with open(partial, "wb") as f:
        for first, last in ranges:
            if (first, last) == (0, None):
                obj = s3_client.get_object(Bucket=bucket, Key=key)
            else:
                rng = f"bytes={first}-{'' if last is None else last}"
                obj = s3_client.get_object(Bucket=bucket, Key=key, Range=rng)
            f.write(obj["Body"].read())
    partial.replace(dest)
    return dest
