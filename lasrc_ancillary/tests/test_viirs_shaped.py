from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from lasrc.aux import load_auxiliary_data
from lasrc_ancillary.viirs_shaped import (
    gdas_to_viirs_shaped,
    to_dn,
)

DATA = Path(__file__).parent / "data"
F00 = DATA / "gdas.20261115.t00z.1p00.grib2"
F06 = DATA / "gdas.20261115.t06z.1p00.grib2"
T = datetime(2026, 11, 15, 3, tzinfo=UTC)


def test_to_dn_rounding_and_clipping():
    wv, oz = to_dn(
        np.array([25.04, 25.06, 0.02, 7000.0]), np.array([300.0, 301.3, 0.1, 700.0])
    )
    assert wv.tolist() == [250, 251, 1, 32767] and wv.dtype == np.uint16
    assert oz.tolist() == [120, 121, 1, 255] and oz.dtype == np.uint8


def test_loads_in_lasrc(tmp_path):
    out = gdas_to_viirs_shaped([F00, F06], T, tmp_path / "g.h5")
    aux = load_auxiliary_data(str(out), "VIIRS")
    assert aux["wv"].shape == aux["oz"].shape == (3600 * 7200,)
    # PWAT up to 100 kg m-2 is DN 1000, and 100 to 637.5 DU of ozone is DN 40 to 255
    assert aux["wv"].min() >= 1 and aux["wv"].max() <= 1000
    assert aux["oz"].min() >= 40 and aux["oz"].max() <= 255
