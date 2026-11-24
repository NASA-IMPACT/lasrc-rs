"""The climate modeling grid (CMG) that lasrc reads global inputs on, and regridding onto it.

The CMG is 0.05 degree, 3600 x 7200, cell centered, starting at 90N, 180W.
"""

import numpy as np
import xarray as xr

CMG_STEP = 0.05
CMG_SHAPE = (3600, 7200)
CMG_LAT = 89.975 - CMG_STEP * np.arange(CMG_SHAPE[0])
CMG_LON = -179.975 + CMG_STEP * np.arange(CMG_SHAPE[1])


def to_cmg(values: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Bilinear interpolation of a global grid to the CMG cell centers (float64).

    ``lat`` and ``lon`` are the coordinates of the grid points. Longitudes must start at -180 and
    stop short of +180, as in GDAS. The -180 column is repeated at +180, so cells east of the last
    column interpolate across the antimeridian.
    """
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
