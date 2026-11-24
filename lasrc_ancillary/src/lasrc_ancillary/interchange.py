"""The water vapor and ozone file that ``lasrc_py`` reads, whatever source the values came from.

A provider hands over one time step on the CMG grid in physical units, and this module encodes
it. The file is currently laid out like a VIIRS ``V*04ANC`` file, so ``lasrc_py`` reads it through
``--wv-oz-hdf`` exactly as it reads VIIRS, and its scale factors, defaults and the water vapor
halving apply unchanged (see docs/plans/standardized-inputs.md for the planned format).

Each file records which source supplied each variable, in the ``ANCILLARY_WATER_VAPOR`` and
``ANCILLARY_OZONE`` attributes.
"""

import datetime as dt
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from lasrc_ancillary.acquisition import to_utc
from lasrc_ancillary.cmg import CMG_SHAPE

GROUP = "/HDFEOS/GRIDS/VIIRS_CMG/Data Fields"
WV_DATASET = f"{GROUP}/Coarse Resolution Water Vapor"
OZ_DATASET = f"{GROUP}/Coarse Resolution Ozone"
WV_SCALE = 0.01  # g cm-2 per DN, as in VIIRS
OZ_SCALE = 0.0025  # cm-atm per DN, as in VIIRS
WATER_VAPOR_SOURCE_ATTR = "ANCILLARY_WATER_VAPOR"
OZONE_SOURCE_ATTR = "ANCILLARY_OZONE"


def iso(t: dt.datetime) -> str:
    """``t`` in UTC as ``YYYY-MM-DDTHH:MM:SSZ``, the form of the file's time attributes."""
    return to_utc(t).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def to_dn(water_vapor: np.ndarray, ozone: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Water vapor (kg m-2) and ozone (DU) as VIIRS water vapor (uint16) and ozone (uint8) DN.

    1 kg m-2 is 0.1 g cm-2, which is 10 DN. 1 DU is 0.001 cm-atm, which is 0.4 DN. A DN of 0
    means fill to lasrc, so values are clipped to at least 1.
    """
    # lasrc reads the DN as int16, so water vapor stops at the int16 maximum.
    wv = np.clip(np.rint(np.asarray(water_vapor) * 10.0), 1, np.iinfo(np.int16).max)
    oz = np.clip(np.rint(np.asarray(ozone) * 0.4), 1, np.iinfo(np.uint8).max)
    return wv.astype(np.uint16), oz.astype(np.uint8)


def write(
    dest: Path,
    water_vapor: np.ndarray,
    ozone: np.ndarray,
    *,
    acquisition_time: dt.datetime,
    water_vapor_source: str,
    ozone_source: str,
    attrs: Mapping[str, Any] | None = None,
) -> Path:
    """Write water vapor (kg m-2) and ozone (DU) on the CMG grid at ``acquisition_time``.

    ``water_vapor_source`` and ``ozone_source`` name where each variable came from, for example
    ``GDAS``. ``attrs`` adds provider-specific file attributes, such as the input files.
    """
    for name, values in (("water vapor", water_vapor), ("ozone", ozone)):
        if np.shape(values) != CMG_SHAPE:
            raise ValueError(
                f"{name} must be on the CMG grid {CMG_SHAPE}, got {np.shape(values)}"
            )

    wv, oz = to_dn(water_vapor, ozone)
    dest = Path(dest)
    partial = dest.with_name(dest.name + ".partial")
    try:
        with h5py.File(partial, "w") as f:
            for dataset, data, scale in (
                (WV_DATASET, wv, WV_SCALE),
                (OZ_DATASET, oz, OZ_SCALE),
            ):
                ds = f.create_dataset(
                    dataset, data=data, chunks=(360, 720), compression="gzip"
                )
                ds.attrs["scale_factor"] = scale
            f.attrs.update(attrs or {})
            f.attrs[WATER_VAPOR_SOURCE_ATTR] = water_vapor_source
            f.attrs[OZONE_SOURCE_ATTR] = ozone_source
            f.attrs["acquisition_time"] = iso(acquisition_time)
            f.attrs["description"] = (
                "Water vapor and ozone for lasrc in the layout of a VIIRS V*04ANC file"
            )
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(dest)
    return dest
