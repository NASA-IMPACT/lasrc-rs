from datetime import UTC, datetime

import pytest
from lasrc_ancillary.cycles import cycle_weights, gdas_cycles


def dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_mid_cycle():
    assert gdas_cycles(dt("2026-03-14T15:12:34Z")) == (
        dt("2026-03-14T12:00Z"),
        dt("2026-03-14T18:00Z"),
    )


def test_on_cycle_gives_weights_one_and_zero():
    t = dt("2026-03-14T12:00:00Z")
    cycles = gdas_cycles(t)
    assert cycles == (dt("2026-03-14T12:00Z"), dt("2026-03-14T18:00Z"))
    assert cycle_weights(t, cycles) == (1.0, 0.0)


def test_18z_rolls_to_next_day():
    assert gdas_cycles(dt("2026-03-14T21:02Z"))[1] == dt("2026-03-15T00:00Z")


def test_non_utc_offset_is_converted():
    assert gdas_cycles(dt("2026-03-14T01:00+05:00")) == (
        dt("2026-03-13T18:00Z"),
        dt("2026-03-14T00:00Z"),
    )


def test_naive_rejected():
    with pytest.raises(ValueError, match="timezone"):
        gdas_cycles(datetime(2026, 3, 14, 15))


def test_weights_midpoint():
    t = dt("2026-03-14T15:00Z")
    assert cycle_weights(t, gdas_cycles(t)) == (0.5, 0.5)


def test_weights_reject_time_outside_bracket():
    with pytest.raises(ValueError):
        cycle_weights(
            datetime(2026, 3, 14, 19, tzinfo=UTC),
            (dt("2026-03-14T12:00Z"), dt("2026-03-14T18:00Z")),
        )
