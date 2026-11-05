"""Package and algorithm version exposure (see VERSIONING.md)."""

import re

import lasrc
import pytest
from click.testing import CliRunner
from lasrc.cli import landsat, sentinel


def test_package_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+", lasrc.__version__)


def test_algorithm_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", lasrc.ALGORITHM_VERSION)


@pytest.mark.parametrize("command", [landsat, sentinel])
def test_cli_version(command):
    result = CliRunner().invoke(command, ["--version"])

    assert result.exit_code == 0
    assert lasrc.__version__ in result.output
    assert lasrc.ALGORITHM_VERSION not in result.output


@pytest.mark.parametrize("command", [landsat, sentinel])
def test_cli_algorithm_version(command):
    result = CliRunner().invoke(command, ["--algorithm-version"])

    assert result.exit_code == 0
    assert result.output == f"{lasrc.ALGORITHM_VERSION}\n"
