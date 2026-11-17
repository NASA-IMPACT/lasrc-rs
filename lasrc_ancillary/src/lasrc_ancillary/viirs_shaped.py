"""Write GDAS water vapor and ozone as a file shaped like a VIIRS ``V*04ANC`` file.

``lasrc_py`` reads it through ``--wv-oz-hdf`` exactly as it reads VIIRS, so its scale factors,
defaults and the water vapor halving apply unchanged. This is how the upstream C code adds GDAS:
it converts GDAS to the same DN arrays the VIIRS reader fills.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

from lasrc_ancillary.cycles import cycle_weights, to_utc
from lasrc_ancillary.grib import read_gdas
from lasrc_ancillary.interp import interpolate_to_cmg

log = logging.getLogger(__name__)

GROUP = "/HDFEOS/GRIDS/VIIRS_CMG/Data Fields"
WV_DATASET = f"{GROUP}/Coarse Resolution Water Vapor"
OZ_DATASET = f"{GROUP}/Coarse Resolution Ozone"
WV_SCALE = 0.01  # g cm-2 per DN, as in VIIRS
OZ_SCALE = 0.0025  # cm-atm per DN, as in VIIRS


def _iso(t: datetime) -> str:
    return to_utc(t).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def to_dn(pwat: np.ndarray, tozne: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """PWAT (kg m-2) and TOZNE (DU) as VIIRS water vapor (uint16) and ozone (uint8) DN.

    1 kg m-2 is 0.1 g cm-2, which is 10 DN. 1 DU is 0.001 cm-atm, which is 0.4 DN. A DN of 0
    means fill to lasrc, so values are clipped to at least 1.
    """
    # lasrc reads the DN as int16, so water vapor stops at the int16 maximum.
    wv = np.clip(np.rint(np.asarray(pwat) * 10.0), 1, np.iinfo(np.int16).max)
    oz = np.clip(np.rint(np.asarray(tozne) * 0.4), 1, np.iinfo(np.uint8).max)
    return wv.astype(np.uint16), oz.astype(np.uint8)


def gdas_to_viirs_shaped(
    paths: Sequence[Path], acquisition_time: datetime, dest: Path
) -> Path:
    """Interpolate two GDAS files to ``acquisition_time`` and write a VIIRS-shaped HDF5 file."""
    fields = sorted((read_gdas(Path(p)) for p in paths), key=lambda f: f.valid_time)
    pwat, tozne = interpolate_to_cmg(fields, acquisition_time)
    weights = cycle_weights(
        acquisition_time, (fields[0].valid_time, fields[1].valid_time)
    )
    log.info(
        "GDAS valid times %s and %s, weights %.4f and %.4f",
        _iso(fields[0].valid_time),
        _iso(fields[1].valid_time),
        *weights,
    )
    wv, oz = to_dn(pwat, tozne)

    dest = Path(dest)
    partial = dest.with_name(dest.name + ".partial")
    try:
        with h5py.File(partial, "w") as f:
            for name, data, scale in (
                (WV_DATASET, wv, WV_SCALE),
                (OZ_DATASET, oz, OZ_SCALE),
            ):
                ds = f.create_dataset(
                    name, data=data, chunks=(360, 720), compression="gzip"
                )
                ds.attrs["scale_factor"] = scale
            f.attrs["source"] = ", ".join(field.source for field in fields)
            f.attrs["acquisition_time"] = _iso(acquisition_time)
            f.attrs["valid_times"] = [_iso(field.valid_time) for field in fields]
            f.attrs["weights"] = list(weights)
            f.attrs["description"] = (
                "GDAS water vapor and ozone in the layout of a VIIRS V*04ANC file"
            )
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(dest)
    return dest
