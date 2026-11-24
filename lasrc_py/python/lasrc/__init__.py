import importlib.metadata as _metadata

from lasrc.lasrc import (
    AERO_FILL,
    ALGORITHM_VERSION,
    SR_FILL_VALUE,
    PyAuxiliaryData,
    PyLookupTables,
    process_landsat_surface_reflectance,
    process_sentinel_surface_reflectance,
)

__version__ = _metadata.version("lasrc")

__all__ = [
    "AERO_FILL",
    "ALGORITHM_VERSION",
    "SR_FILL_VALUE",
    "PyAuxiliaryData",
    "PyLookupTables",
    "__version__",
    "process_landsat_surface_reflectance",
    "process_sentinel_surface_reflectance",
]
