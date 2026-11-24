"""Find, fetch and convert ancillary inputs for lasrc.

Providers (``lasrc_ancillary.providers``) find and fetch each source and convert it to the
interchange file that ``lasrc_py`` reads (``lasrc_ancillary.interchange``). Importing this package,
a provider package or a provider's ``fetch`` module loads only the standard library, so the
orchestration can run them in a Lambda with no extras installed.
"""

from lasrc_ancillary.acquisition import (
    estimate_acquisition_time,
    estimate_acquisition_windows,
    read_acquisition_time,
)

__all__ = [
    "estimate_acquisition_time",
    "estimate_acquisition_windows",
    "read_acquisition_time",
]
