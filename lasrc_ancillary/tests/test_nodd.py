import datetime as dt

import pytest
from lasrc_ancillary.nodd import fetch_gdas, find_gdas, locate_gdas


def iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def cycle_dir(day: str, hh: str, atmos: bool) -> str:
    return f"gdas.{day}/{hh}/" + ("atmos/" if atmos else "")


def distractors(day: str, hh: str, atmos: bool) -> dict[str, bytes]:
    d = cycle_dir(day, hh, atmos)
    return {
        f"{d}gdas.t{hh}z.pgrb2.1p00.f003": b"x",
        f"{d}gdas.t{hh}z.pgrb2.1p00.anl": b"x",
        f"{d}gdas.t{hh}z.pgrb2.1p00.f000.idx": b"x",
        f"{d}gdas.t{hh}z.pgrb2b.1p00.f000": b"x",
        f"{d}gdas.t{hh}z.sfluxgrbf000.grib2": b"x",
        f"gdas.{day}/{hh}/wave/gdaswave.t{hh}z.global.0p25.f000.grib2": b"x",
    }


@pytest.mark.parametrize(
    ("day", "name", "atmos"),
    [
        ("20130601", "gdas1.t{hh}z.pgrbf00.grib2", False),
        ("20160601", "gdas1.t{hh}z.pgrb2.1p00.f000", False),
        ("20190601", "gdas.t{hh}z.pgrb2.1p00.f000", False),
        ("20260314", "gdas.t{hh}z.pgrb2.1p00.f000", True),
    ],
)
def test_finds_each_layout(s3, put, day, name, atmos):
    for hh in ("12", "18"):
        put(distractors(day, hh, atmos))
        put({cycle_dir(day, hh, atmos) + name.format(hh=hh): b"g"})
    t = iso(f"{day[:4]}-{day[4:6]}-{day[6:]}T12:00Z")
    assert find_gdas([t, t + dt.timedelta(hours=6)], s3) == [
        cycle_dir(day, "12", atmos) + name.format(hh="12"),
        cycle_dir(day, "18", atmos) + name.format(hh="18"),
    ]


def test_returns_none_when_later_cycle_missing(s3, put):
    put({"gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000": b"g"})
    cycles = [iso("2026-03-14T12:00Z"), iso("2026-03-14T18:00Z")]
    assert find_gdas(cycles, s3) is None


def test_18z_later_key_uses_next_day(s3, put):
    put(
        {
            "gdas.20260314/18/atmos/gdas.t18z.pgrb2.1p00.f000": b"g",
            "gdas.20260315/00/atmos/gdas.t00z.pgrb2.1p00.f000": b"g",
        }
    )
    keys = find_gdas([iso("2026-03-14T18:00Z"), iso("2026-03-15T00:00Z")], s3)
    assert keys is not None and keys[1].startswith("gdas.20260315/00/")


def test_0p25(s3, put):
    put(
        {
            "gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000": b"g",
            "gdas.20260314/12/atmos/gdas.t12z.pgrb2.0p25.f000": b"g",
        }
    )
    keys = find_gdas([iso("2026-03-14T12:00Z")], s3, resolution="0p25")
    assert keys == ["gdas.20260314/12/atmos/gdas.t12z.pgrb2.0p25.f000"]


def test_old_layout_has_no_0p25(s3, put):
    put({"gdas.20130601/12/gdas1.t12z.pgrbf00.grib2": b"g"})
    assert find_gdas([iso("2013-06-01T12:00Z")], s3, resolution="0p25") is None


def test_listing_is_paginated(s3, put):
    # S3 returns at most 1000 keys per page, and the 0-hour file sorts after these
    put({f"gdas.20260314/12/atmos/gdas.t12z.aaa{i:04d}": b"x" for i in range(1001)})
    put({"gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000": b"g"})
    keys = find_gdas([iso("2026-03-14T12:00Z")], s3)
    assert keys == ["gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000"]


def test_unknown_resolution_rejected(s3):
    with pytest.raises(ValueError, match="resolution"):
        find_gdas([iso("2026-03-14T12:00Z")], s3, resolution="0p50")


KEY = "gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000"
GRIB = b"AAAA" + b"PWAT-MESSAGE" + b"BBBB" + b"TOZNE-MSG" + b"CCCCCC"
IDX = (
    b"1:0:d=2026031412:PRMSL:mean sea level:anl:\n"
    b"2:4:d=2026031412:PWAT:entire atmosphere (considered as a single layer):anl:\n"
    b"3:16:d=2026031412:CWAT:entire atmosphere (considered as a single layer):anl:\n"
    b"4:20:d=2026031412:TOZNE:entire atmosphere (considered as a single layer):anl:\n"
    b"5:29:d=2026031412:HGT:surface:anl:\n"
)


def test_fetch_uses_idx_ranges(s3, put, tmp_path):
    put({KEY: GRIB, KEY + ".idx": IDX})
    out = fetch_gdas(KEY, tmp_path / "g.grib2", s3)
    assert out.read_bytes() == b"PWAT-MESSAGE" + b"TOZNE-MSG"
    assert not (tmp_path / "g.grib2.partial").exists()


def test_fetch_last_message_is_open_ended(s3, put, tmp_path):
    idx = IDX.replace(b"5:29:d=2026031412:HGT:surface:anl:\n", b"")
    put({KEY: GRIB, KEY + ".idx": idx})
    out = fetch_gdas(KEY, tmp_path / "g.grib2", s3)
    assert out.read_bytes() == b"PWAT-MESSAGE" + b"TOZNE-MSGCCCCCC"


def test_fetch_whole_file_without_idx(s3, put, tmp_path):
    old = "gdas.20130601/12/gdas1.t12z.pgrbf00.grib2"
    put({old: GRIB})
    assert fetch_gdas(old, tmp_path / "g.grib2", s3).read_bytes() == GRIB


def test_fetch_requires_both_messages(s3, put, tmp_path):
    put({KEY: GRIB, KEY + ".idx": IDX.replace(b"TOZNE", b"TCOLW")})
    with pytest.raises(ValueError, match="TOZNE"):
        fetch_gdas(KEY, tmp_path / "g.grib2", s3)


def test_other_bucket(s3, tmp_path):
    s3.create_bucket(Bucket="my-mirror")
    s3.put_object(Bucket="my-mirror", Key=KEY, Body=GRIB)
    s3.put_object(Bucket="my-mirror", Key=KEY + ".idx", Body=IDX)
    assert find_gdas([iso("2026-03-14T12:00Z")], s3) is None
    assert find_gdas([iso("2026-03-14T12:00Z")], s3, bucket="my-mirror") == [KEY]
    out = fetch_gdas(KEY, tmp_path / "g.grib2", s3, bucket="my-mirror")
    assert out.read_bytes() == b"PWAT-MESSAGE" + b"TOZNE-MSG"


def test_locate_gdas_reports_each_cycle(s3, put):
    put({KEY: GRIB})
    cycles = [iso("2026-03-14T12:00Z"), iso("2026-03-14T18:00Z")]
    assert locate_gdas(cycles, s3) == [KEY, None]
