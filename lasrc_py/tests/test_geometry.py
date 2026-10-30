"""Validate geometry functions via Python bindings."""


def test_import():
    """Verify the lasrc package imports correctly."""
    import lasrc

    assert hasattr(lasrc, "__version__")
