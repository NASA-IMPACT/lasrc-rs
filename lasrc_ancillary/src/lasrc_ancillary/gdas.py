"""Produce the GDAS water vapor and ozone file for one acquisition: the processing job's entry point.

The orchestration decides when to run from the granule ID (``lasrc_ancillary.estimate`` and
``lasrc_ancillary.nodd``). This module works from the exact acquisition time and picks its own
files, so a wrong estimate costs a retry, never a wrong result.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from lasrc_ancillary.cycles import gdas_cycles
from lasrc_ancillary.nodd import BUCKET, default_s3_client, fetch_gdas, find_gdas

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger(__name__)

RETRY_CUTOFF = timedelta(hours=24)


class GdasUnavailable(Exception):
    """The GDAS cycles an acquisition needs are not on NODD."""

    def __init__(self, message: str, cycles: tuple[datetime, datetime]):
        super().__init__(message)
        self.cycles = cycles


class GdasNotYetPublished(GdasUnavailable):
    """Not published yet. Retry later."""


class GdasMissing(GdasUnavailable):
    """Still missing ``RETRY_CUTOFF`` after the later cycle, so likely a gap in the archive."""


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
    keys = find_gdas(cycles, s3, resolution, bucket)
    if keys is None:
        names = f"{cycles[0]:%Y-%m-%d %HZ} and {cycles[1]:%Y-%m-%d %HZ}"
        clock = now or (lambda: datetime.now(timezone.utc))
        if clock() < cycles[1] + RETRY_CUTOFF:
            raise GdasNotYetPublished(
                f"GDAS cycles {names} are not both in s3://{bucket} yet", cycles
            )
        raise GdasMissing(
            f"GDAS cycles {names} are still missing from s3://{bucket} more than {RETRY_CUTOFF} "
            "after the later cycle",
            cycles,
        )

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(work_dir) if work_dir is not None else Path(tmp)
        paths = [fetch_gdas(k, work / k.replace("/", "_"), s3, bucket) for k in keys]
        return gdas_to_viirs_shaped(paths, acquisition_time, dest)
