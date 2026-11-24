import datetime as dt

import pytest
from lasrc_ancillary.providers.gdas.cycles import cycle_weights, gdas_cycles


def iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def test_mid_cycle():
    assert gdas_cycles(iso("2026-03-14T15:12:34Z")) == (
        iso("2026-03-14T12:00Z"),
        iso("2026-03-14T18:00Z"),
    )


def test_on_cycle_gives_weights_one_and_zero():
    t = iso("2026-03-14T12:00:00Z")
    cycles = gdas_cycles(t)
    assert cycles == (iso("2026-03-14T12:00Z"), iso("2026-03-14T18:00Z"))
    assert cycle_weights(t, cycles) == (1.0, 0.0)


def test_18z_rolls_to_next_day():
    assert gdas_cycles(iso("2026-03-14T21:02Z"))[1] == iso("2026-03-15T00:00Z")


def test_non_utc_offset_is_converted():
    assert gdas_cycles(iso("2026-03-14T01:00+05:00")) == (
        iso("2026-03-13T18:00Z"),
        iso("2026-03-14T00:00Z"),
    )


def test_naive_rejected():
    with pytest.raises(ValueError, match="timezone"):
        gdas_cycles(dt.datetime(2026, 3, 14, 15))


def test_weights_midpoint():
    t = iso("2026-03-14T15:00Z")
    assert cycle_weights(t, gdas_cycles(t)) == (0.5, 0.5)


def test_weights_reject_time_outside_bracket():
    with pytest.raises(ValueError):
        cycle_weights(
            dt.datetime(2026, 3, 14, 19, tzinfo=dt.UTC),
            (iso("2026-03-14T12:00Z"), iso("2026-03-14T18:00Z")),
        )
