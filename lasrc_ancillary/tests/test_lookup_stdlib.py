"""The lookup the orchestration runs in a Lambda must not pull in the converter's dependencies.

``import lasrc_ancillary`` exposes the lookup, so importing it must load only the standard
library. The converters live in submodules that import their extras.
"""

import os
import subprocess
import sys

NEW_THIRD_PARTY = """
import importlib, sys
before = set(sys.modules)
importlib.import_module({module!r})
new = {{m.split(".")[0] for m in set(sys.modules) - before}}
print(",".join(sorted(new - set(sys.stdlib_module_names) - {{"lasrc_ancillary"}})))
"""


def new_third_party(module: str) -> list[str]:
    out = subprocess.run(
        [sys.executable, "-c", NEW_THIRD_PARTY.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONWARNINGS": "ignore"},
    ).stdout.strip()
    return [m for m in out.split(",") if m]


def test_package_import_is_standard_library_only():
    assert new_third_party("lasrc_ancillary") == []


def test_check_detects_third_party_imports():
    import pkgutil

    import lasrc_ancillary

    submodules = [
        m.name
        for m in pkgutil.iter_modules(lasrc_ancillary.__path__, "lasrc_ancillary.")
    ]
    assert any(new_third_party(m) for m in submodules)
