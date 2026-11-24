"""Convert two GDAS cycles to the interchange file for one acquisition: the processing job's entry point.

Linear in time between the cycles that bracket the acquisition, then bilinear in space onto the
CMG grid.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lasrc_ancillary import interchange
from lasrc_ancillary.acquisition import to_utc
from lasrc_ancillary.cmg import to_cmg
from lasrc_ancillary.providers.gdas.cycles import cycle_weights, gdas_cycles
from lasrc_ancillary.providers.gdas.fetch import (
    NODD_BUCKET,
    Resolution,
    fetch_gdas_pair,
)
from lasrc_ancillary.providers.gdas.grib import GdasField, read_gdas

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger(__name__)

SOURCE = "GDAS"


def _iso_minutes(t: dt.datetime) -> str:
    return to_utc(t).strftime("%Y-%m-%dT%H:%MZ")


def _name(field: GdasField) -> str:
    return Path(field.source).name


def interpolate_to_cmg(
    fields: Sequence[GdasField], acquisition_time: dt.datetime
) -> tuple[np.ndarray, np.ndarray]:
    """PWAT and TOZNE at ``acquisition_time`` on the CMG grid (3600 x 7200, float64)."""
    if len(fields) != 2:
        raise ValueError(f"expected two GDAS fields, got {len(fields)}")

    f1, f2 = sorted(fields, key=lambda f: f.valid_time)
    t = to_utc(acquisition_time)
    needed = gdas_cycles(t)
    if (f1.valid_time, f2.valid_time) != needed:
        files = "\n".join(
            f"  {_name(f)}: valid {_iso_minutes(f.valid_time)}" for f in (f1, f2)
        )
        raise ValueError(
            f"GDAS files do not bracket the acquisition time {t:%Y-%m-%dT%H:%M:%SZ}:\n"
            f"{files}\n"
            f"It needs the cycles {_iso_minutes(needed[0])} and {_iso_minutes(needed[1])}."
        )

    if f1.pwat.shape != f2.pwat.shape or not np.array_equal(f1.lon, f2.lon):
        raise ValueError(
            f"GDAS fields are on different grids: {f1.source}, {f2.source}"
        )

    w1, w2 = cycle_weights(t, (f1.valid_time, f2.valid_time))
    pwat = to_cmg(w1 * f1.pwat + w2 * f2.pwat, f1.lat, f1.lon)
    tozne = to_cmg(w1 * f1.tozne + w2 * f2.tozne, f1.lat, f1.lon)
    return pwat, tozne


def gdas_to_interchange(
    paths: Sequence[Path], acquisition_time: dt.datetime, dest: Path
) -> Path:
    """Interpolate two GDAS files to ``acquisition_time`` and write the interchange file."""
    fields = sorted((read_gdas(Path(p)) for p in paths), key=lambda f: f.valid_time)
    pwat, tozne = interpolate_to_cmg(fields, acquisition_time)
    weights = cycle_weights(
        acquisition_time, (fields[0].valid_time, fields[1].valid_time)
    )
    valid_times = [interchange.iso(field.valid_time) for field in fields]
    log.info(
        "GDAS valid times %s and %s, weights %.4f and %.4f", *valid_times, *weights
    )
    return interchange.write(
        dest,
        pwat,
        tozne,
        acquisition_time=acquisition_time,
        water_vapor_source=SOURCE,
        ozone_source=SOURCE,
        attrs={
            "source_files": ", ".join(field.source for field in fields),
            "valid_times": valid_times,
            "weights": list(weights),
        },
    )


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
    """Fetch the GDAS cycles for ``acquisition_time`` and write the interchange file to ``dest``."""
    paths = fetch_gdas_pair(
        acquisition_time,
        s3_client,
        work_dir,
        resolution=resolution,
        bucket=bucket,
        now=now,
    )
    return gdas_to_interchange(paths, acquisition_time, dest)
