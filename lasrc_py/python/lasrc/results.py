"""Result types returned by the ``lasrc.lasrc`` extension."""

from typing import TypedDict

import numpy as np
from numpy.typing import NDArray


class SurfaceReflectanceResult(TypedDict):
    """Output of ``process_surface_reflectance`` / ``process_sentinel_surface_reflectance``.

    Arrays are returned flattened (1-D, row-major); the pipelines reshape them to
    (nlines, nsamps) in place.
    """

    sr_bands: list[NDArray[np.uint16]]
    bt_bands: list[NDArray[np.uint16]]  # empty for Sentinel-2
    aerosol: NDArray[np.int16]
    qa: NDArray[np.uint8]
