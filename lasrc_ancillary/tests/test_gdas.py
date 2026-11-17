from datetime import datetime, timezone

import h5py
import pytest
from conftest import F00, F06, K00, K06
from lasrc_ancillary.gdas import GdasMissing, GdasNotYetPublished, prepare_gdas

T = datetime(2026, 11, 15, 3, tzinfo=timezone.utc)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


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
            T,
            tmp_path / "g.h5",
            s3_client=nodd(K00),
            now=lambda: utc(2026, 11, 15, 8),
        )
    assert exc.value.cycles == (utc(2026, 11, 15, 0), utc(2026, 11, 15, 6))
    assert not (tmp_path / "g.h5").exists()


def test_missing_after_cutoff(nodd, tmp_path):
    with pytest.raises(GdasMissing):
        prepare_gdas(
            T,
            tmp_path / "g.h5",
            s3_client=nodd(K00),
            now=lambda: utc(2026, 11, 16, 7),
        )
