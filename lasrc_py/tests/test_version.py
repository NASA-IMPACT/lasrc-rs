"""Package and algorithm version exposure (see VERSIONING.md)."""

import importlib.metadata
import re

import lasrc
import pytest
from click.testing import CliRunner
from lasrc.cli import main


def test_package_version_format():
    # X.Y.Z, or X.Y.Z+g<sha>[.dirty] for a build between releases (see scripts/version)
    assert re.fullmatch(r"\d+\.\d+\.\d+(\+g[0-9a-f]+(\.dirty)?)?", lasrc.__version__)


def test_package_version_matches_metadata():
    assert lasrc.__version__ == importlib.metadata.version("lasrc")


def test_algorithm_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", lasrc.ALGORITHM_VERSION)


def test_cli_version():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert lasrc.__version__ in result.output
    assert lasrc.ALGORITHM_VERSION not in result.output


def test_cli_algorithm_version():
    result = CliRunner().invoke(main, ["--algorithm-version"])

    assert result.exit_code == 0
    assert result.output == f"{lasrc.ALGORITHM_VERSION}\n"


def test_cli_ancillary_plugin():
    pytest.importorskip("lasrc_ancillary")

    result = CliRunner().invoke(main, ["ancillary", "gdas", "--help"])

    assert result.exit_code == 0
    assert "--acquisition-time" in result.output


@pytest.mark.parametrize("command", ["landsat", "sentinel"])
def test_cli_sensor_commands(command):
    result = CliRunner().invoke(main, [command, "--help"])

    assert result.exit_code == 0
    assert "--wv-oz-hdf" in result.output
