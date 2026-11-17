from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from lasrc_ancillary.grib import read_gdas
from rasterio.transform import from_origin

DATA = Path(__file__).parent / "data"
F00 = DATA / "gdas.20261115.t00z.1p00.grib2"
VALID = int(datetime(2026, 11, 15, tzinfo=UTC).timestamp())


def write_fake(path, bands, shape=(181, 360), step=1.0, values=None):
    """A GeoTIFF whose bands carry GRIB tags. read_gdas checks tags and grid, not the driver."""
    transform = from_origin(-180 - step / 2, 90 + step / 2, step, step)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=shape[1],
        height=shape[0],
        count=len(bands),
        dtype="float32",
        transform=transform,
    ) as dst:
        for i, tags in enumerate(bands, start=1):
            data = (
                np.full(shape, 10.0 * i, np.float32)
                if values is None
                else values[i - 1]
            )
            dst.write(data, i)
            dst.update_tags(i, **tags)
    return path


def band(element, valid=VALID, fcst="0", short="0-EATM"):
    return {
        "GRIB_ELEMENT": element,
        "GRIB_SHORT_NAME": short,
        "GRIB_VALID_TIME": str(valid),
        "GRIB_FORECAST_SECONDS": fcst,
    }


def test_reads_fixture():
    f = read_gdas(F00)
    assert f.valid_time == datetime(2026, 11, 15, tzinfo=UTC)
    assert f.pwat.shape == f.tozne.shape == (181, 360)
    assert f.lat[0] == 90.0 and f.lat[1] == 89.0 and f.lat[-1] == -90.0
    assert f.lon[0] == -180.0 and f.lon[1] == -179.0 and f.lon[-1] == 179.0
    assert np.isfinite(f.pwat).all() and np.isfinite(f.tozne).all()
    assert 0 <= f.pwat.min() and f.pwat.max() < 100
    assert 100 < f.tozne.min() and f.tozne.max() < 700
    assert f.pwat.dtype == np.float64


def test_bands_found_among_many(tmp_path):
    p = write_fake(
        tmp_path / "a.tif",
        [
            band("PRMSL", short="0-MSL"),
            band("TOZNE"),
            band("PWAT"),
            band("PWAT", short="0-SFC"),
        ],
    )
    f = read_gdas(p)
    assert f.tozne[0, 0] == 20.0 and f.pwat[0, 0] == 30.0


def test_quarter_degree(tmp_path):
    p = write_fake(
        tmp_path / "q.tif", [band("PWAT"), band("TOZNE")], shape=(721, 1440), step=0.25
    )
    f = read_gdas(p)
    assert f.lon[1] == -179.75 and f.lat[-1] == -90.0


def test_rejects_forecast_hour_not_zero(tmp_path):
    p = write_fake(
        tmp_path / "a.tif", [band("PWAT", fcst="21600"), band("TOZNE", fcst="21600")]
    )
    with pytest.raises(ValueError, match="forecast"):
        read_gdas(p)


def test_rejects_missing_tozne(tmp_path):
    p = write_fake(tmp_path / "a.tif", [band("PWAT")])
    with pytest.raises(ValueError, match="TOZNE"):
        read_gdas(p)


def test_rejects_duplicate_pwat(tmp_path):
    p = write_fake(tmp_path / "a.tif", [band("PWAT"), band("PWAT"), band("TOZNE")])
    with pytest.raises(ValueError, match="PWAT"):
        read_gdas(p)


def test_rejects_mismatched_valid_times(tmp_path):
    p = write_fake(
        tmp_path / "a.tif", [band("PWAT"), band("TOZNE", valid=VALID + 21600)]
    )
    with pytest.raises(ValueError, match="valid time"):
        read_gdas(p)


def test_rejects_unexpected_grid_shape(tmp_path):
    p = write_fake(
        tmp_path / "a.tif", [band("PWAT"), band("TOZNE")], shape=(90, 180), step=2.0
    )
    with pytest.raises(ValueError, match="grid"):
        read_gdas(p)


def test_rejects_shifted_origin(tmp_path):
    p = tmp_path / "a.tif"
    with rasterio.open(
        p,
        "w",
        driver="GTiff",
        width=360,
        height=181,
        count=2,
        dtype="float32",
        transform=from_origin(-180.0, 90.0, 1.0, 1.0),
    ) as dst:
        for i, tags in enumerate([band("PWAT"), band("TOZNE")], start=1):
            dst.write(np.ones((181, 360), np.float32), i)
            dst.update_tags(i, **tags)
    with pytest.raises(ValueError, match="grid"):
        read_gdas(p)


def test_rejects_nonfinite(tmp_path):
    bad = np.ones((181, 360), np.float32)
    bad[5, 5] = np.nan
    p = write_fake(
        tmp_path / "a.tif",
        [band("PWAT"), band("TOZNE")],
        values=[bad, np.ones((181, 360), np.float32)],
    )
    with pytest.raises(ValueError, match="finite"):
        read_gdas(p)
