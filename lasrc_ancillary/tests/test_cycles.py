from datetime import datetime, timezone

import pytest
from lasrc_ancillary.cycles import cycle_weights, gdas_cycles, parse_iso

UTC = timezone.utc


def dt(s: str) -> datetime:
    return parse_iso(s)


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-11-15T03:00:00Z", datetime(2026, 11, 15, 3, tzinfo=UTC)),
        (
            "2026-01-24T07:45:13.375Z",
            datetime(2026, 1, 24, 7, 45, 13, 375000, tzinfo=UTC),
        ),
        (
            "2026-01-24T07:45:13.1234567Z",
            datetime(2026, 1, 24, 7, 45, 13, 123456, tzinfo=UTC),
        ),
        ("2026-11-15T08:00:00+05:00", datetime(2026, 11, 15, 3, tzinfo=UTC)),
    ],
)
def test_parse_iso_handles_z_and_long_fractions(text, expected):
    assert parse_iso(text) == expected


def test_parse_iso_keeps_naive_naive():
    assert parse_iso("2026-11-15T03:00:00").tzinfo is None
