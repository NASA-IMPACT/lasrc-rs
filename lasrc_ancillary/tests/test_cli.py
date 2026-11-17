from datetime import datetime, timezone

import h5py
from click.testing import CliRunner
from conftest import F00, F06, K00, K06
from lasrc_ancillary.cli import EX_TEMPFAIL, main
from lasrc_ancillary.viirs_shaped import WV_DATASET


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def run(args, **obj):
    return CliRunner().invoke(main, ["gdas", *map(str, args)], obj=obj)


def acquisition(out):
    with h5py.File(out, "r") as f:
        assert f[WV_DATASET].shape == (3600, 7200)
        return f.attrs["acquisition_time"]


def test_local_files(tmp_path):
    out = tmp_path / "g.h5"
    result = run(["--acquisition-time", "2026-11-15T03:00:00Z", F00, F06, out])
    assert result.exit_code == 0, result.output
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_metadata_time(tmp_path):
    mtl = tmp_path / "X_MTL.txt"
    mtl.write_text(
        'DATE_ACQUIRED = 2026-11-15\nSCENE_CENTER_TIME = "03:00:00.0000000Z"\n'
    )
    out = tmp_path / "g.h5"
    assert run(["--metadata", mtl, F00, F06, out]).exit_code == 0
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_naive_time_rejected(tmp_path):
    result = run(
        ["--acquisition-time", "2026-11-15T03:00:00", F00, F06, tmp_path / "o.h5"]
    )
    assert result.exit_code == 2
    assert "%z" in result.output


def test_offset_time_is_converted_to_utc(tmp_path):
    out = tmp_path / "g.h5"
    result = run(["--acquisition-time", "2026-11-15T08:00:00+05:00", F00, F06, out])
    assert result.exit_code == 0, result.output
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_needs_a_time(tmp_path):
    assert run([F00, F06, tmp_path / "o.h5"]).exit_code == 2


def test_needs_two_files_without_fetch(tmp_path):
    result = run(["--acquisition-time", "2026-11-15T03:00:00Z", F00, tmp_path / "o.h5"])
    assert result.exit_code == 2


def test_fetch_ok(nodd, tmp_path):
    out = tmp_path / "g.h5"
    work = tmp_path / "new" / "work"
    args = [
        "--acquisition-time",
        "2026-11-15T03:00:00Z",
        "--fetch",
        "--work-dir",
        work,
        out,
    ]
    result = run(args, s3_client=nodd(K00, K06))
    assert result.exit_code == 0, result.output
    assert acquisition(out) == "2026-11-15T03:00:00Z"


def test_fetch_missing_later_cycle_is_tempfail(nodd, tmp_path):
    args = ["--acquisition-time", "2026-11-15T03:00:00Z", "--fetch", tmp_path / "g.h5"]
    result = run(args, s3_client=nodd(K00), now=lambda: utc(2026, 11, 15, 8))
    assert result.exit_code == EX_TEMPFAIL == 75
    assert not (tmp_path / "g.h5").exists()


def test_on_cycle_with_only_earlier_file_is_tempfail(nodd, tmp_path):
    args = ["--acquisition-time", "2026-11-15T00:00:00Z", "--fetch", tmp_path / "g.h5"]
    result = run(args, s3_client=nodd(K00), now=lambda: utc(2026, 11, 15, 8))
    assert result.exit_code == EX_TEMPFAIL


def test_fetch_missing_after_cutoff_is_error(nodd, tmp_path):
    args = ["--acquisition-time", "2026-11-15T03:00:00Z", "--fetch", tmp_path / "g.h5"]
    result = run(args, s3_client=nodd(K00), now=lambda: utc(2026, 11, 16, 7))
    assert result.exit_code == 1


def test_local_files_not_bracketing_without_fetch_is_error(tmp_path):
    args = ["--acquisition-time", "2026-11-15T08:00:00Z", F00, F06, tmp_path / "g.h5"]
    result = run(args)
    assert result.exit_code == 1
    assert "bracket" in result.output


def test_local_files_not_bracketing_with_fetch_are_replaced(nodd, tmp_path):
    out = tmp_path / "g.h5"
    args = ["--acquisition-time", "2026-11-15T03:00:00Z", "--fetch", F06, F06, out]
    assert run(args, s3_client=nodd(K00, K06)).exit_code == 0
    assert acquisition(out) == "2026-11-15T03:00:00Z"
