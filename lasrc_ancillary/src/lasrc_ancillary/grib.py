"""Read and check the PWAT and TOZNE fields of a GDAS 0-hour GRIB2 file.

Uses the GDAL GRIB driver bundled with rasterio. GDAL reports the GDAS grid points as pixel
centers, with the grid shifted to start at longitude -180.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# grid spacing in degrees -> (rows, columns)
GRIDS = {1.0: (181, 360), 0.25: (721, 1440)}
LEVEL = "0-EATM"


@dataclass(frozen=True)
class GdasField:
    valid_time: datetime
    lat: np.ndarray
    lon: np.ndarray
    pwat: np.ndarray
    tozne: np.ndarray
    source: str


def read_gdas(path: Path) -> GdasField:
    """PWAT (kg m-2) and TOZNE (DU) from a GDAS file, on its grid points, as float64."""
    import rasterio

    path = Path(path)
    name = path.name
    with rasterio.open(path) as ds:
        bands: dict[str, list[int]] = {"PWAT": [], "TOZNE": []}
        for i in range(1, ds.count + 1):
            tags = ds.tags(i)
            element = tags.get("GRIB_ELEMENT")
            if element in bands and tags.get("GRIB_SHORT_NAME") == LEVEL:
                bands[element].append(i)
        for element, found in bands.items():
            if len(found) != 1:
                raise ValueError(
                    f"{name}: expected one {element} band at {LEVEL}, found {len(found)}"
                )
        valid = set()
        for element, (i,) in bands.items():
            tags = ds.tags(i)
            if tags.get("GRIB_FORECAST_SECONDS") != "0":
                raise ValueError(
                    f"{name}: {element} forecast seconds is "
                    f"{tags.get('GRIB_FORECAST_SECONDS')}, expected 0 (0-hour forecast)"
                )
            valid.add(int(tags["GRIB_VALID_TIME"]))
        if len(valid) != 1:
            raise ValueError(f"{name}: PWAT and TOZNE have different valid time")

        t = ds.transform
        step = t.a
        if (
            step not in GRIDS
            or ds.shape != GRIDS[step]
            or t.e != -step
            or t.b != 0
            or t.d != 0
            or t.c != -180.0 - step / 2
            or t.f != 90.0 + step / 2
        ):
            raise ValueError(
                f"{name}: unexpected grid {ds.shape} with transform {tuple(t)[:6]}, expected "
                "a global regular grid at 1 or 0.25 degree starting at 90N, 180W"
            )
        pwat = ds.read(bands["PWAT"][0]).astype(np.float64)
        tozne = ds.read(bands["TOZNE"][0]).astype(np.float64)

    if not (np.isfinite(pwat).all() and np.isfinite(tozne).all()):
        raise ValueError(f"{name}: PWAT or TOZNE has values that are not finite")
    nrows, ncols = GRIDS[step]
    return GdasField(
        valid_time=datetime.fromtimestamp(valid.pop(), tz=timezone.utc),
        lat=90.0 - step * np.arange(nrows),
        lon=-180.0 + step * np.arange(ncols),
        pwat=pwat,
        tozne=tozne,
        source=str(path),
    )
