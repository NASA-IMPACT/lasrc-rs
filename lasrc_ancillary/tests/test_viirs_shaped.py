from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
from lasrc.aux import load_auxiliary_data
from lasrc_ancillary.grib import read_gdas
from lasrc_ancillary.interp import interpolate_to_cmg
from lasrc_ancillary.viirs_shaped import (
    OZ_DATASET,
    WV_DATASET,
    gdas_to_viirs_shaped,
    to_dn,
)

DATA = Path(__file__).parent / "data"
F00 = DATA / "gdas.20261115.t00z.1p00.grib2"
F06 = DATA / "gdas.20261115.t06z.1p00.grib2"
T = datetime(2026, 11, 15, 3, tzinfo=timezone.utc)


def test_to_dn_rounding_and_clipping():
    wv, oz = to_dn(
        np.array([25.04, 25.06, 0.02, 7000.0]), np.array([300.0, 301.3, 0.1, 700.0])
    )
    assert wv.tolist() == [250, 251, 1, 32767] and wv.dtype == np.uint16
    assert oz.tolist() == [120, 121, 1, 255] and oz.dtype == np.uint8


def test_end_to_end_loads_in_lasrc(tmp_path):
    out = gdas_to_viirs_shaped([F00, F06], T, tmp_path / "g.h5")
    aux = load_auxiliary_data(str(out), "VIIRS")
    assert aux["wv"].shape == (3600 * 7200,) and aux["oz"].shape == (3600 * 7200,)
    assert (aux["wv"] > 0).all() and (aux["oz"] > 0).all()

    pwat, tozne = interpolate_to_cmg([read_gdas(F00), read_gdas(F06)], T)
    wv_dn, oz_dn = to_dn(pwat, tozne)
    cell = 1799 * 7200 + 3600
    assert aux["wv"][cell] == wv_dn[1799, 3600]
    assert aux["oz"][cell] == oz_dn[1799, 3600]


def test_attributes(tmp_path):
    out = gdas_to_viirs_shaped([F06, F00], T, tmp_path / "g.h5")
    with h5py.File(out, "r") as f:
        wv, oz = f[WV_DATASET], f[OZ_DATASET]
        assert wv.dtype == np.uint16 and oz.dtype == np.uint8
        assert wv.shape == oz.shape == (3600, 7200)
        assert float(wv.attrs["scale_factor"]) == 0.01
        assert float(oz.attrs["scale_factor"]) == 0.0025
        assert f.attrs["acquisition_time"] == "2026-11-15T03:00:00Z"
        assert list(f.attrs["valid_times"]) == [
            "2026-11-15T00:00:00Z",
            "2026-11-15T06:00:00Z",
        ]
        assert list(f.attrs["weights"]) == [0.5, 0.5]
        assert "gdas.20261115.t00z.1p00.grib2" in f.attrs["source"]
