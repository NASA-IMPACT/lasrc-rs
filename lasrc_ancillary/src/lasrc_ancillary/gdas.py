"""Produce the GDAS water vapor and ozone file for one acquisition: the processing job's entry point.

The orchestration decides when to run from the granule ID (``lasrc_ancillary.estimate`` and
``lasrc_ancillary.nodd``). This module works from the exact acquisition time and picks its own
files, so a wrong estimate costs a retry, never a wrong result.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Self

from lasrc_ancillary.cycles import gdas_cycles, to_utc
from lasrc_ancillary.nodd import (
    BUCKET,
    cycle_prefix,
    default_s3_client,
    fetch_gdas,
    locate_gdas,
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger(__name__)

RETRY_CUTOFF = timedelta(hours=24)


def _iso_minutes(t: datetime) -> str:
    return to_utc(t).strftime("%Y-%m-%dT%H:%MZ")


class GdasUnavailable(Exception):
    """GDAS cycles an acquisition needs are not in the bucket.

    The message has one ``GDAS_MISSING`` line per missing cycle, in ``key=value`` form for log
    filters and alerts.
    """

    status = "unavailable"
    cycles: tuple[datetime, datetime]
    missing: list[datetime]

    @classmethod
    def from_missing(
        cls,
        acquisition_time: datetime,
        cycles: tuple[datetime, datetime],
        missing: list[datetime],
        bucket: str,
        resolution: str,
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


def _local_files_match(
    paths: Sequence[Path], cycles: tuple[datetime, datetime]
) -> bool:
    from lasrc_ancillary.grib import read_gdas

    try:
        times = sorted(read_gdas(p).valid_time for p in paths)
    except (OSError, ValueError) as e:
        log.info("Ignoring local GDAS files: %s", e)
        return False
    return tuple(times) == cycles


def prepare_gdas(
    acquisition_time: datetime,
    dest: Path,
    *,
    local_files: Sequence[Path] = (),
    fetch: bool = True,
    s3_client: S3Client | None = None,
    resolution: str = "1p00",
    bucket: str = BUCKET,
    work_dir: Path | None = None,
    now: Callable[[], datetime] | None = None,
) -> Path:
    """Write the VIIRS-shaped GDAS file for ``acquisition_time`` to ``dest``.

    Uses ``local_files`` when they are the two cycles the acquisition needs. Otherwise, with
    ``fetch``, finds and downloads them from NODD. Without ``fetch``, local files that don't
    bracket the acquisition time raise ``ValueError``.

    Raises ``GdasNotYetPublished`` while a cycle is not on NODD yet, and ``GdasMissing`` once it is
    still missing ``RETRY_CUTOFF`` after the later cycle.
    """
    from lasrc_ancillary.viirs_shaped import gdas_to_viirs_shaped

    cycles = gdas_cycles(acquisition_time)
    if not fetch:
        if len(local_files) != 2:
            raise ValueError("without fetch, give the two local GDAS files")
        return gdas_to_viirs_shaped(local_files, acquisition_time, dest)
    if local_files and _local_files_match(local_files, cycles):
        return gdas_to_viirs_shaped(local_files, acquisition_time, dest)

    s3 = s3_client or default_s3_client()
    located = locate_gdas(cycles, s3, resolution, bucket)
    missing = [c for c, key in zip(cycles, located) if key is None]
    if missing:
        clock = now or (lambda: datetime.now(UTC))
        error = (
            GdasNotYetPublished if clock() < cycles[1] + RETRY_CUTOFF else GdasMissing
        )
        raise error.from_missing(acquisition_time, cycles, missing, bucket, resolution)
    keys = [key for key in located if key is not None]

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(work_dir) if work_dir is not None else Path(tmp)
        paths = [fetch_gdas(k, work / k.replace("/", "_"), s3, bucket) for k in keys]
        return gdas_to_viirs_shaped(paths, acquisition_time, dest)
