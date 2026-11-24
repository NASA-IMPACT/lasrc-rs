import datetime as dt

import h5py
import numpy as np
import pytest
from lasrc.aux import load_auxiliary_data
from lasrc_ancillary.cmg import CMG_SHAPE

from lasrc_ancillary import interchange

T = dt.datetime(2026, 11, 15, 3, tzinfo=dt.UTC)


def write(path, water_vapor=25.0, ozone=300.0, **kwargs):
    kwargs = {
        "acquisition_time": T,
        "water_vapor_source": "GDAS",
        "ozone_source": "VIIRS",
        **kwargs,
    }
    return interchange.write(
        path,
        np.full(CMG_SHAPE, water_vapor),
        np.full(CMG_SHAPE, ozone),
        **kwargs,
    )


def test_to_dn_rounding_and_clipping():
    wv, oz = interchange.to_dn(
        np.array([25.04, 25.06, 0.02, 7000.0]), np.array([300.0, 301.3, 0.1, 700.0])
    )
    assert wv.tolist() == [250, 251, 1, 32767] and wv.dtype == np.uint16
    assert oz.tolist() == [120, 121, 1, 255] and oz.dtype == np.uint8


def test_records_sources_and_time(tmp_path):
    out = write(tmp_path / "a.h5", attrs={"source_files": "x, y"})
    with h5py.File(out, "r") as f:
        assert f.attrs["ANCILLARY_WATER_VAPOR"] == "GDAS"
        assert f.attrs["ANCILLARY_OZONE"] == "VIIRS"
        assert f.attrs["acquisition_time"] == "2026-11-15T03:00:00Z"
        assert f.attrs["source_files"] == "x, y"


def test_rejects_grid_other_than_cmg(tmp_path):
    with pytest.raises(ValueError, match="CMG"):
        interchange.write(
            tmp_path / "a.h5",
            np.ones((181, 360)),
            np.ones(CMG_SHAPE),
            acquisition_time=T,
            water_vapor_source="GDAS",
            ozone_source="GDAS",
        )
    assert not list(tmp_path.iterdir())


def test_loads_in_lasrc(tmp_path):
    aux = load_auxiliary_data(str(write(tmp_path / "a.h5")), "VIIRS")
    # 25 kg m-2 is 2.5 g cm-2, and 300 DU is 0.3 cm-atm
    assert np.all(aux["wv"] / aux["wv_scale"] == 1.25)
    assert np.all(aux["oz"] / aux["oz_scale"] == 0.3)
