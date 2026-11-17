from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from lasrc_ancillary.grib import GRIDS, GdasField
from lasrc_ancillary.interp import CMG_LAT, CMG_LON, interpolate_to_cmg

T0 = datetime(2026, 3, 14, 12, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=6)


def grid(step):
    nrows, ncols = GRIDS[step]
    return 90.0 - step * np.arange(nrows), -180.0 + step * np.arange(ncols)


def field(t, step, fn):
    lat, lon = grid(step)
    values = fn(lat[:, None], lon[None, :]) * np.ones((lat.size, lon.size))
    return GdasField(t, lat, lon, values, values * 10.0, source=f"{t:%H}Z")


def test_cmg_coordinates():
    assert CMG_LAT.shape == (3600,) and CMG_LON.shape == (7200,)
    assert CMG_LAT[0] == pytest.approx(89.975) and CMG_LAT[-1] == pytest.approx(-89.975)
    assert CMG_LON[0] == pytest.approx(-179.975) and CMG_LON[-1] == pytest.approx(
        179.975
    )


@pytest.mark.parametrize("step", [1.0, 0.25])
def test_linear_field_exact_away_from_seam(step):
    def fn(lat, lon):
        return 2.0 * lat + 0.5 * lon + 50.0

    pwat, tozne = interpolate_to_cmg([field(T0, step, fn), field(T1, step, fn)], T0)
    expected = fn(CMG_LAT[:, None], CMG_LON[None, :])
    m = CMG_LON < 180.0 - step
    assert np.allclose(pwat[:, m], expected[:, m], atol=1e-9)
    assert np.allclose(tozne[:, m], 10.0 * expected[:, m], atol=1e-8)


def test_constant_field_constant_across_seam():
    pwat, _ = interpolate_to_cmg(
        [field(T0, 1.0, lambda la, lo: 7.0), field(T1, 1.0, lambda la, lo: 7.0)], T0
    )
    assert np.allclose(pwat, 7.0)


def test_seam_interpolates_between_179e_and_180w():
    # 1.0 at 179E and 3.0 at 180W (= 180E): cells between 179E and 180E lie on the line
    def fn(lat, lon):
        return np.where(lon == -180.0, 3.0, np.where(lon == 179.0, 1.0, 0.0))

    pwat, _ = interpolate_to_cmg([field(T0, 1.0, fn), field(T1, 1.0, fn)], T0)
    j = np.where(CMG_LON > 179.0)[0]
    assert np.allclose(pwat[1800, j], 1.0 + 2.0 * (CMG_LON[j] - 179.0))


@pytest.mark.parametrize("step", [1.0, 0.25])
def test_delta_stays_local(step):
    def fn(lat, lon):
        return np.where((lat == 10.0) & (lon == 20.0), 1.0, 0.0)

    pwat, _ = interpolate_to_cmg([field(T0, step, fn), field(T1, step, fn)], T0)
    rows, cols = np.nonzero(pwat)
    assert np.all(np.abs(CMG_LAT[rows] - 10.0) < step)
    assert np.all(np.abs(CMG_LON[cols] - 20.0) < step)
    near = (np.abs(CMG_LAT - 10.0) < step)[:, None] & (np.abs(CMG_LON - 20.0) < step)[
        None, :
    ]
    assert np.count_nonzero(pwat) == np.count_nonzero(near)
    i, j = np.unravel_index(np.argmax(pwat), pwat.shape)
    assert abs(CMG_LAT[i] - 10.0) == pytest.approx(0.025)
    assert abs(CMG_LON[j] - 20.0) == pytest.approx(0.025)


@pytest.mark.parametrize(
    ("t", "expected"),
    [(T0, 10.0), (T0 + timedelta(hours=2), 12.0), (T0 + timedelta(hours=5), 15.0)],
)
def test_time_weights(t, expected):
    f0 = field(T0, 1.0, lambda la, lo: 10.0)
    f1 = field(T1, 1.0, lambda la, lo: 16.0)
    pwat, _ = interpolate_to_cmg([f0, f1], t)
    assert np.allclose(pwat, expected)


def test_reverse_order_accepted():
    f0 = field(T0, 1.0, lambda la, lo: 10.0)
    f1 = field(T1, 1.0, lambda la, lo: 16.0)
    t = T0 + timedelta(hours=3)
    a, _ = interpolate_to_cmg([f0, f1], t)
    b, _ = interpolate_to_cmg([f1, f0], t)
    assert np.array_equal(a, b)


def test_rejects_12_hours_apart():
    f0 = field(T0, 1.0, lambda la, lo: 1.0)
    f2 = field(T0 + timedelta(hours=12), 1.0, lambda la, lo: 1.0)
    with pytest.raises(ValueError, match="needs the cycles"):
        interpolate_to_cmg([f0, f2], T0 + timedelta(hours=3))


def test_rejects_time_outside_bracket():
    f0 = field(T0, 1.0, lambda la, lo: 1.0)
    f1 = field(T1, 1.0, lambda la, lo: 1.0)
    with pytest.raises(ValueError, match="bracket"):
        interpolate_to_cmg([f0, f1], T1 + timedelta(minutes=1))


def test_on_later_cycle_rejected():
    # an acquisition exactly at T1 needs T1 and T1 + 6h, not T0 and T1
    f0 = field(T0, 1.0, lambda la, lo: 1.0)
    f1 = field(T1, 1.0, lambda la, lo: 1.0)
    with pytest.raises(ValueError, match="bracket"):
        interpolate_to_cmg([f0, f1], T1)


def test_rejects_mixed_resolutions():
    f0 = field(T0, 1.0, lambda la, lo: 1.0)
    f1 = field(T1, 0.25, lambda la, lo: 1.0)
    with pytest.raises(ValueError, match="grid"):
        interpolate_to_cmg([f0, f1], T0)


def test_rejects_wrong_number_of_fields():
    with pytest.raises(ValueError, match="two"):
        interpolate_to_cmg([field(T0, 1.0, lambda la, lo: 1.0)], T0)
