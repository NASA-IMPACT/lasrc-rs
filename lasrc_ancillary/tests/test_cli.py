import datetime as dt

import h5py
from click.testing import CliRunner
from conftest import F00, F06, K00, K06
from lasrc_ancillary.cli import main
from lasrc_ancillary.viirs_shaped import WV_DATASET


def utc(*args):
    return dt.datetime(*args, tzinfo=dt.UTC)


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


def test_needs_a_time(tmp_path):
    assert run([F00, F06, tmp_path / "o.h5"]).exit_code == 2


def test_one_grib_file_is_a_usage_error(tmp_path):
    result = run(["--acquisition-time", "2026-11-15T03:00:00Z", F00, tmp_path / "o.h5"])
    assert result.exit_code == 2


def mirror(s3):
    s3.create_bucket(Bucket="my-mirror")
    s3.put_object(Bucket="my-mirror", Key=K00, Body=F00.read_bytes())
    s3.put_object(Bucket="my-mirror", Key=K06, Body=F06.read_bytes())
    return s3


def test_bucket_from_environment(s3, tmp_path):
    out = tmp_path / "g.h5"
    args = ["gdas", "--acquisition-time", "2026-11-15T03:00:00Z", str(out)]
    mirror(s3)
    result = CliRunner().invoke(
        main, args, env={"LASRC_ANCILLARY_GDAS_BUCKET": "my-mirror"}
    )
    assert result.exit_code == 0, result.output


def test_missing_cycles_are_reported_one_per_line(nodd, tmp_path):
    args = ["--acquisition-time", "2026-11-15T03:00:00Z", tmp_path / "g.h5"]
    nodd(K00)
    result = run(args, now=lambda: utc(2026, 11, 15, 8))
    assert result.exit_code == 1
    lines = [
        line for line in result.output.splitlines() if line.startswith("GDAS_MISSING")
    ]
    assert lines == [
        (
            "GDAS_MISSING status=not-yet-published cycle=2026-11-15T06:00Z resolution=1p00 "
            "acquisition=2026-11-15T03:00:00Z searched=s3://noaa-gfs-bdp-pds/gdas.20261115/06/"
        )
    ]
