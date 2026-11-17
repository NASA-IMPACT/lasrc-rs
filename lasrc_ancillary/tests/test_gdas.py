from datetime import UTC, datetime

import h5py
import pytest
from conftest import F00, F06, K00, K06
from lasrc_ancillary.gdas import GdasMissing, GdasNotYetPublished, prepare_gdas

T = datetime(2026, 11, 15, 3, tzinfo=UTC)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def acquisition(out):
    with h5py.File(out, "r") as f:
        return f.attrs["acquisition_time"]


def test_local_files(tmp_path):
    out = prepare_gdas(T, tmp_path / "g.h5", local_files=[F00, F06], fetch=False)
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_no_files_and_no_fetch(tmp_path):
    with pytest.raises(ValueError, match="local"):
        prepare_gdas(T, tmp_path / "g.h5", fetch=False)


def test_fetch(nodd, tmp_path):
    out = prepare_gdas(
        T, tmp_path / "g.h5", s3_client=nodd(K00, K06), work_dir=tmp_path
    )
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_fetch_replaces_wrong_local_files(nodd, tmp_path):
    out = prepare_gdas(
        T, tmp_path / "g.h5", local_files=[F06, F06], s3_client=nodd(K00, K06)
    )
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_matching_local_files_skip_the_bucket(s3, tmp_path):
    # the bucket is empty, so reaching it would raise GdasNotYetPublished
    out = prepare_gdas(T, tmp_path / "g.h5", local_files=[F00, F06], s3_client=s3)
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_not_yet_published(nodd, tmp_path):
    with pytest.raises(GdasNotYetPublished) as exc:
        prepare_gdas(
            T, tmp_path / "g.h5", s3_client=nodd(K00), now=lambda: utc(2026, 11, 15, 8)
        )
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
        prepare_gdas(
            T, tmp_path / "g.h5", s3_client=nodd(), now=lambda: utc(2026, 11, 16, 7)
        )
    assert [line.split()[1:3] for line in str(exc.value).splitlines()] == [
        ["status=missing-past-cutoff", "cycle=2026-11-15T00:00Z"],
        ["status=missing-past-cutoff", "cycle=2026-11-15T06:00Z"],
    ]


def test_default_client_when_none_given(nodd, tmp_path):
    nodd(K00, K06)  # moto intercepts the client prepare_gdas builds itself
    out = prepare_gdas(T, tmp_path / "g.h5")
    assert acquisition(out) == "2026-11-15T03:00:00Z"
