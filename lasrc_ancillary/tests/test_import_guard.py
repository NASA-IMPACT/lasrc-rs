"""The lookup the orchestration runs in a Lambda must not pull in the converters' dependencies.

The top-level package, each provider package and each provider's ``fetch`` module must load only
the standard library. Conversion lives in each provider's ``convert`` module, which imports its
extras.
"""

import os
import pkgutil
import subprocess
import sys

import lasrc_ancillary.providers
import pytest

NEW_THIRD_PARTY = """
import importlib, sys
before = set(sys.modules)
importlib.import_module({module!r})
new = {{m.split(".")[0] for m in set(sys.modules) - before}}
print(",".join(sorted(new - set(sys.stdlib_module_names) - {{"lasrc_ancillary"}})))
"""

PROVIDERS = [
    m.name for m in pkgutil.iter_modules(lasrc_ancillary.providers.__path__) if m.ispkg
]
STANDARD_LIBRARY_ONLY = [
    "lasrc_ancillary",
    "lasrc_ancillary.acquisition",
    *(f"lasrc_ancillary.providers.{p}" for p in PROVIDERS),
    *(f"lasrc_ancillary.providers.{p}.fetch" for p in PROVIDERS),
]


def new_third_party(module: str) -> list[str]:
    out = subprocess.run(
        [sys.executable, "-c", NEW_THIRD_PARTY.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONWARNINGS": "ignore"},
    ).stdout.strip()
    return [m for m in out.split(",") if m]


def test_providers_found():
    assert "gdas" in PROVIDERS


@pytest.mark.parametrize("module", STANDARD_LIBRARY_ONLY)
def test_import_is_standard_library_only(module):
    assert new_third_party(module) == []
