"""The lookup the orchestration runs in a Lambda must not pull in the converter's dependencies."""

import os
import subprocess
import sys

import pytest

LOOKUP = [
    "lasrc_ancillary.cycles",
    "lasrc_ancillary.estimate",
    "lasrc_ancillary.metadata",
    "lasrc_ancillary.nodd",
]
HEAVY = ["numpy", "rasterio", "xarray", "scipy", "h5py", "boto3", "botocore"]


def imported_heavy(modules: list[str]) -> list[str]:
    code = (
        "import importlib, sys\n"
        f"for m in {modules!r}: importlib.import_module(m)\n"
        f"print(','.join(m for m in {HEAVY!r} if m in sys.modules))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONWARNINGS": "ignore"},
    ).stdout.strip()
    return [m for m in out.split(",") if m]


def test_lookup_imports_only_the_standard_library():
    assert imported_heavy(LOOKUP) == []


@pytest.mark.parametrize("module", ["lasrc_ancillary.grib"])
def test_check_detects_heavy_imports(module):
    assert "numpy" in imported_heavy([module])
