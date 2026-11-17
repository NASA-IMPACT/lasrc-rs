from datetime import UTC, datetime

import h5py
from click.testing import CliRunner
from conftest import F00, F06, K00, K06
from lasrc_ancillary.cli import EX_TEMPFAIL, main
from lasrc_ancillary.viirs_shaped import WV_DATASET


def utc(*args):
    return datetime(*args, tzinfo=UTC)


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


def mirror(s3):
    s3.create_bucket(Bucket="my-mirror")
    s3.put_object(Bucket="my-mirror", Key=K00, Body=F00.read_bytes())
    s3.put_object(Bucket="my-mirror", Key=K06, Body=F06.read_bytes())
    return s3


def test_bucket_option(s3, tmp_path):
    out = tmp_path / "g.h5"
    args = [
        "--acquisition-time",
        "2026-11-15T03:00:00Z",
        "--fetch",
        "--bucket",
        "my-mirror",
        out,
    ]
    result = run(args, s3_client=mirror(s3))
    assert result.exit_code == 0, result.output


def test_bucket_from_environment(s3, tmp_path):
    out = tmp_path / "g.h5"
    args = ["gdas", "--acquisition-time", "2026-11-15T03:00:00Z", "--fetch", str(out)]
    result = CliRunner().invoke(
        main,
        args,
        obj={"s3_client": mirror(s3)},
        env={"LASRC_ANCILLARY_GDAS_BUCKET": "my-mirror"},
    )
    assert result.exit_code == 0, result.output


def test_bucket_default_is_nodd():
    result = CliRunner().invoke(main, ["gdas", "--help"])
    text = "".join(result.output.split())  # click wraps long values across lines
    assert "default:noaa-gfs-bdp-pds" in text
    assert "LASRC_ANCILLARY_GDAS_BUCKET" in text


def test_missing_cycles_are_reported_one_per_line(nodd, tmp_path):
    args = ["--acquisition-time", "2026-11-15T03:00:00Z", "--fetch", tmp_path / "g.h5"]
    result = run(args, s3_client=nodd(K00), now=lambda: utc(2026, 11, 15, 8))
    assert result.exit_code == EX_TEMPFAIL
    lines = [
        line for line in result.output.splitlines() if line.startswith("GDAS_MISSING")
    ]
    assert lines == [
        (
            "GDAS_MISSING status=not-yet-published cycle=2026-11-15T06:00Z resolution=1p00 "
            "acquisition=2026-11-15T03:00:00Z searched=s3://noaa-gfs-bdp-pds/gdas.20261115/06/"
        )
    ]


def test_not_bracketing_message_is_readable(tmp_path):
    args = ["--acquisition-time", "2026-11-15T08:00:00Z", F00, F06, tmp_path / "g.h5"]
    result = run(args)
    assert result.exit_code == 1
    assert "datetime.datetime(" not in result.output
    assert "do not bracket the acquisition time 2026-11-15T08:00:00Z" in result.output
    assert "gdas.20261115.t00z.1p00.grib2: valid 2026-11-15T00:00Z" in result.output
    assert "gdas.20261115.t06z.1p00.grib2: valid 2026-11-15T06:00Z" in result.output
    assert "needs the cycles 2026-11-15T06:00Z and 2026-11-15T12:00Z" in result.output
