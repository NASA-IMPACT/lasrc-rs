"""Produce the GDAS water vapor and ozone file for one acquisition: the processing job's entry point.

The orchestration decides when to run from the granule ID (``lasrc_ancillary.estimate`` and
``lasrc_ancillary.nodd``). This module works from the exact acquisition time and picks its own
files, so a wrong estimate costs a retry, never a wrong result.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Self

from lasrc_ancillary.cycles import gdas_cycles, to_utc
from lasrc_ancillary.nodd import (
    NODD_BUCKET,
    Resolution,
    cycle_prefix,
    fetch_gdas,
    locate_gdas,
)
from lasrc_ancillary.viirs_shaped import gdas_to_viirs_shaped

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger(__name__)

RETRY_CUTOFF = dt.timedelta(hours=24)


def _iso_minutes(t: dt.datetime) -> str:
    return to_utc(t).strftime("%Y-%m-%dT%H:%MZ")


class GdasUnavailable(Exception):
    """GDAS cycles an acquisition needs are not in the bucket.

    The message has one ``GDAS_MISSING`` line per missing cycle, in ``key=value`` form for log
    filters and alerts.
    """

    status = "unavailable"
    cycles: tuple[dt.datetime, dt.datetime]
    missing: list[dt.datetime]

    @classmethod
    def from_missing(
        cls,
        acquisition_time: dt.datetime,
        cycles: tuple[dt.datetime, dt.datetime],
        missing: list[dt.datetime],
        bucket: str,
        resolution: Resolution,
    ) -> Self:
        acquisition = to_utc(acquisition_time).strftime("%Y-%m-%dT%H:%M:%SZ")
        message = "\n".join(
            f"GDAS_MISSING status={cls.status} cycle={_iso_minutes(c)} "
            f"resolution={resolution} acquisition={acquisition} "
            f"searched=s3://{bucket}/{cycle_prefix(c)}"
            for c in missing
        )
        error = cls(message)
        error.cycles = cycles
        error.missing = list(missing)
        return error


class GdasNotYetPublished(GdasUnavailable):
    """Not published yet. Retry later."""

    status = "not-yet-published"


class GdasMissing(GdasUnavailable):
    """Still missing ``RETRY_CUTOFF`` after the later cycle, so likely a gap in the archive."""

    status = "missing-past-cutoff"


def fetch_gdas_pair(
    acquisition_time: dt.datetime,
    s3_client: S3Client,
    work_dir: Path,
    *,
    resolution: Resolution = "1p00",
    bucket: str = NODD_BUCKET,
    now: Callable[[], dt.datetime] | None = None,
) -> list[Path]:
    """Download the two GDAS cycles that bracket ``acquisition_time`` into ``work_dir``.

    Raises ``GdasNotYetPublished`` while a cycle is not in the bucket yet, and ``GdasMissing`` once
    it is still missing ``RETRY_CUTOFF`` after the later cycle.
    """
    cycles = gdas_cycles(acquisition_time)
    located = locate_gdas(cycles, s3_client, resolution, bucket)
    missing = [c for c, key in zip(cycles, located) if key is None]
    if missing:
        clock = now or (lambda: dt.datetime.now(dt.UTC))
        error = (
            GdasNotYetPublished if clock() < cycles[1] + RETRY_CUTOFF else GdasMissing
        )
        raise error.from_missing(acquisition_time, cycles, missing, bucket, resolution)

    return [
        fetch_gdas(key, work_dir / key.replace("/", "_"), s3_client, bucket)
        for key in located
        if key is not None
    ]


def prepare_gdas(
    acquisition_time: dt.datetime,
    dest: Path,
    *,
    s3_client: S3Client,
    work_dir: Path,
    resolution: Resolution = "1p00",
    bucket: str = NODD_BUCKET,
    now: Callable[[], dt.datetime] | None = None,
) -> Path:
    """Fetch the GDAS cycles for ``acquisition_time`` and write the VIIRS-shaped file to ``dest``."""
    paths = fetch_gdas_pair(
        acquisition_time,
        s3_client,
        work_dir,
        resolution=resolution,
        bucket=bucket,
        now=now,
    )
    return gdas_to_viirs_shaped(paths, acquisition_time, dest)
