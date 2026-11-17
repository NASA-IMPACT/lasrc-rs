from datetime import datetime, timezone
from pathlib import Path

import h5py
import pytest
from fake_s3 import FakeS3
from lasrc_ancillary.gdas import GdasMissing, GdasNotYetPublished, prepare_gdas

DATA = Path(__file__).parent / "data"
F00 = DATA / "gdas.20261115.t00z.1p00.grib2"
F06 = DATA / "gdas.20261115.t06z.1p00.grib2"
K00 = "gdas.20261115/00/atmos/gdas.t00z.pgrb2.1p00.f000"
K06 = "gdas.20261115/06/atmos/gdas.t06z.pgrb2.1p00.f000"
T = datetime(2026, 11, 15, 3, tzinfo=timezone.utc)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def fake_nodd(*keys):
    data = {K00: F00.read_bytes(), K06: F06.read_bytes()}
    return FakeS3({k: data[k] for k in keys})


def acquisition(out):
    with h5py.File(out, "r") as f:
        return f.attrs["acquisition_time"]


def test_local_files(tmp_path):
    out = prepare_gdas(T, tmp_path / "g.h5", local_files=[F00, F06], fetch=False)
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_local_files_not_bracketing_without_fetch(tmp_path):
    with pytest.raises(ValueError, match="bracket"):
        prepare_gdas(
            utc(2026, 11, 15, 8), tmp_path / "g.h5", local_files=[F00, F06], fetch=False
        )


def test_no_files_and_no_fetch(tmp_path):
    with pytest.raises(ValueError, match="local"):
        prepare_gdas(T, tmp_path / "g.h5", fetch=False)


def test_fetch(tmp_path):
    out = prepare_gdas(
        T, tmp_path / "g.h5", s3_client=fake_nodd(K00, K06), work_dir=tmp_path
    )
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_fetch_replaces_wrong_local_files(tmp_path):
    out = prepare_gdas(
        T, tmp_path / "g.h5", local_files=[F06, F06], s3_client=fake_nodd(K00, K06)
    )
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_matching_local_files_skip_the_bucket(tmp_path):
    s3 = fake_nodd()
    prepare_gdas(T, tmp_path / "g.h5", local_files=[F00, F06], s3_client=s3)
    assert s3.get_calls == []


def test_not_yet_published(tmp_path):
    with pytest.raises(GdasNotYetPublished) as exc:
        prepare_gdas(
            T,
            tmp_path / "g.h5",
            s3_client=fake_nodd(K00),
            now=lambda: utc(2026, 11, 15, 8),
        )
    assert exc.value.cycles == (utc(2026, 11, 15, 0), utc(2026, 11, 15, 6))
    assert not (tmp_path / "g.h5").exists()


def test_missing_after_cutoff(tmp_path):
    with pytest.raises(GdasMissing):
        prepare_gdas(
            T,
            tmp_path / "g.h5",
            s3_client=fake_nodd(K00),
            now=lambda: utc(2026, 11, 16, 7),
        )
