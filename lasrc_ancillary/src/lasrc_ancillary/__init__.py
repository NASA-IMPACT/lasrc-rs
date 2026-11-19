"""Find, fetch and convert ancillary inputs for lasrc.

The names here are the GDAS lookup an orchestration layer needs. Importing this package loads only
the standard library, so it can run in a Lambda with no extras installed. The conversion
(``lasrc_ancillary.gdas.prepare_gdas``) needs the ``gdas`` extra.
"""

from lasrc_ancillary.cycles import cycle_weights, gdas_cycles
from lasrc_ancillary.estimate import (
    estimate_acquisition_time,
    estimate_acquisition_windows,
    gdas_cycles_for_windows,
)
from lasrc_ancillary.metadata import read_acquisition_time
from lasrc_ancillary.nodd import (
    NODD_BUCKET,
    fetch_gdas,
    find_gdas,
    locate_gdas,
)

__all__ = [
    "NODD_BUCKET",
    "cycle_weights",
    "estimate_acquisition_time",
    "estimate_acquisition_windows",
    "fetch_gdas",
    "find_gdas",
    "gdas_cycles",
    "gdas_cycles_for_windows",
    "locate_gdas",
    "read_acquisition_time",
]
