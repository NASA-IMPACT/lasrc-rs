import datetime as dt

import h5py
import pytest
from conftest import K00, K06
from lasrc_ancillary.providers.gdas.convert import prepare_gdas
from lasrc_ancillary.providers.gdas.fetch import GdasMissing, GdasNotYetPublished

T = dt.datetime(2026, 11, 15, 3, tzinfo=dt.UTC)


def utc(*args):
    return dt.datetime(*args, tzinfo=dt.UTC)


def prepare(s3, tmp_path, **kwargs):
    return prepare_gdas(T, tmp_path / "g.h5", s3_client=s3, work_dir=tmp_path, **kwargs)


def test_fetch(nodd, tmp_path):
    out = prepare(nodd(K00, K06), tmp_path)
    with h5py.File(out, "r") as f:
        assert f.attrs["acquisition_time"] == "2026-11-15T03:00:00Z"


def test_not_yet_published(nodd, tmp_path):
    with pytest.raises(GdasNotYetPublished) as exc:
        prepare(nodd(K00), tmp_path, now=lambda: utc(2026, 11, 15, 8))
    assert exc.value.cycles == (utc(2026, 11, 15, 0), utc(2026, 11, 15, 6))
    assert exc.value.missing == [utc(2026, 11, 15, 6)]
    assert str(exc.value).splitlines() == [
        (
            "GDAS_MISSING status=not-yet-published cycle=2026-11-15T06:00Z resolution=1p00 "
            "acquisition=2026-11-15T03:00:00Z searched=s3://noaa-gfs-bdp-pds/gdas.20261115/06/"
        )
    ]
    assert not (tmp_path / "g.h5").exists()


def test_missing_past_cutoff(nodd, tmp_path):
    with pytest.raises(GdasMissing) as exc:
        prepare(nodd(), tmp_path, now=lambda: utc(2026, 11, 16, 7))
    assert [line.split()[1:3] for line in str(exc.value).splitlines()] == [
        ["status=missing-past-cutoff", "cycle=2026-11-15T00:00Z"],
        ["status=missing-past-cutoff", "cycle=2026-11-15T06:00Z"],
    ]
