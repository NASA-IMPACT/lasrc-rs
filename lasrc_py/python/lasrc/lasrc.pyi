"""Type stubs for the compiled ``lasrc.lasrc`` extension (``lasrc_py/src/lib.rs``).

Checked against the built module by ``scripts/typecheck`` (mypy stubtest).
"""

from collections.abc import Sequence
from typing import Final, final

import numpy as np
from numpy.typing import NDArray

from lasrc.results import SurfaceReflectanceResult

__all__ = [
    "AERO_FILL",
    "ALGORITHM_VERSION",
    "SR_FILL_VALUE",
    "PyAuxiliaryData",
    "PyLookupTables",
    "__version__",
    "process_sentinel_surface_reflectance",
    "process_surface_reflectance",
]

__version__: Final[str]
ALGORITHM_VERSION: Final[str]
SR_FILL_VALUE: Final[int]
AERO_FILL: Final[int]

@final
class PyLookupTables:
    def __new__(
        cls,
        rolutt: NDArray[np.float64],
        transt: NDArray[np.float64],
        sphalbt: NDArray[np.float64],
        normext: NDArray[np.float64],
        tsmax: NDArray[np.float64],
        tsmin: NDArray[np.float64],
        nbfic: NDArray[np.float64],
        nbfi: NDArray[np.int32],
        ttv: NDArray[np.float64],
        tts: NDArray[np.float64],
        indts: NDArray[np.int32],
        nsr_bands: int,
    ) -> PyLookupTables: ...

@final
class PyAuxiliaryData:
    def __new__(
        cls,
        dem: NDArray[np.int16],
        wv: NDArray[np.int16],
        oz: NDArray[np.int16],
        ratiob1: NDArray[np.int16],
        ratiob2: NDArray[np.int16],
        ratiob7: NDArray[np.int16],
        intratiob1: NDArray[np.int16],
        intratiob2: NDArray[np.int16],
        intratiob7: NDArray[np.int16],
        slpratiob1: NDArray[np.int16],
        slpratiob2: NDArray[np.int16],
        slpratiob7: NDArray[np.int16],
        andwi: NDArray[np.int16],
        sndwi: NDArray[np.int16],
        wv_scale: float,
        oz_scale: float,
        wv_default: float,
        oz_default: float,
    ) -> PyAuxiliaryData: ...

def process_surface_reflectance(
    sensor_name: str,
    toa_bands: Sequence[NDArray[np.float32]],
    bt_bands: Sequence[NDArray[np.float32]],
    solar_zenith: NDArray[np.float32],
    solar_azimuth: NDArray[np.float32],
    view_zenith: NDArray[np.float32],
    view_azimuth: NDArray[np.float32],
    qa_band: NDArray[np.uint16],
    lut: PyLookupTables,
    aux: PyAuxiliaryData,
    ul_corner_x: float,
    ul_corner_y: float,
    pixel_size_x: float,
    pixel_size_y: float,
    utm_zone: int,
    num_threads: int | None = None,
    scene_solar_zenith: float | None = None,
) -> SurfaceReflectanceResult: ...
def process_sentinel_surface_reflectance(
    sensor_name: str,
    toa_bands: Sequence[NDArray[np.float32]],
    solar_zenith: float,
    solar_azimuth: float,
    view_zenith: float,
    view_azimuth: float,
    qa_band: NDArray[np.uint16],
    lut: PyLookupTables,
    aux: PyAuxiliaryData,
    ul_corner_x: float,
    ul_corner_y: float,
    pixel_size_x: float,
    pixel_size_y: float,
    utm_zone: int,
    num_threads: int | None = None,
) -> SurfaceReflectanceResult: ...
