"""Interpolate two GDAS cycles to an acquisition time and onto the CMG grid.

Linear in time, then bilinear in space at the CMG cell centers, by coordinate label with xarray.
"""

import datetime as dt
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import xarray as xr

from lasrc_ancillary.cycles import cycle_weights, gdas_cycles, to_utc
from lasrc_ancillary.grib import GdasField

CMG_STEP = 0.05
CMG_LAT = 89.975 - CMG_STEP * np.arange(3600)
CMG_LON = -179.975 + CMG_STEP * np.arange(7200)


def _to_cmg(values: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    # GDAS has no column at +180, so wrap the -180 column there for cells east of the last one.
    wrapped = xr.DataArray(
        np.concatenate([values, values[:, :1]], axis=1),
        coords={"lat": lat, "lon": np.append(lon, 180.0)},
        dims=("lat", "lon"),
    )
    # Bilinear is linear in latitude, then linear in longitude.
    out = wrapped.interp(lat=CMG_LAT, method="linear").interp(
        lon=CMG_LON, method="linear"
    )
    return np.asarray(out.values, dtype=np.float64)


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
    pwat = _to_cmg(w1 * f1.pwat + w2 * f2.pwat, f1.lat, f1.lon)
    tozne = _to_cmg(w1 * f1.tozne + w2 * f2.tozne, f1.lat, f1.lon)
    return pwat, tozne
