"""End-to-end pipeline validation tests.

These tests require actual test data and auxiliary files.
Skip if test data is not available.
"""

from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).parent / "data"
HAS_TEST_DATA = (
    TEST_DATA_DIR.exists() and any(TEST_DATA_DIR.iterdir())
    if TEST_DATA_DIR.exists()
    else False
)


@pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data not available")
def test_landsat_end_to_end():
    """Process a Landsat test scene and compare output to C reference."""
    # Will be implemented when test data is available


@pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data not available")
def test_output_matches_c_reference():
    """Compare Rust+Python output to C output for numerical validation."""
    # Will compare ESPA-format outputs
