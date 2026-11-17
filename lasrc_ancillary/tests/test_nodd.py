from datetime import datetime, timedelta

import pytest
from fake_s3 import FakeS3
from lasrc_ancillary.cycles import parse_iso
from lasrc_ancillary.nodd import BUCKET, fetch_gdas, find_gdas


def dt(s: str) -> datetime:
    return parse_iso(s)


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
def test_finds_each_layout(day, name, atmos):
    objects = {}
    for hh in ("12", "18"):
        objects.update(distractors(day, hh, atmos))
        objects[cycle_dir(day, hh, atmos) + name.format(hh=hh)] = b"g"
    t = parse_iso(f"{day[:4]}-{day[4:6]}-{day[6:]}T12:00Z")
    keys = find_gdas([t, t + timedelta(hours=6)], FakeS3(objects))
    assert keys == [
        cycle_dir(day, "12", atmos) + name.format(hh="12"),
        cycle_dir(day, "18", atmos) + name.format(hh="18"),
    ]


def test_returns_none_when_later_cycle_missing():
    objects = {"gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000": b"g"}
    cycles = [dt("2026-03-14T12:00Z"), dt("2026-03-14T18:00Z")]
    assert find_gdas(cycles, FakeS3(objects)) is None


def test_18z_later_key_uses_next_day():
    objects = {
        "gdas.20260314/18/atmos/gdas.t18z.pgrb2.1p00.f000": b"g",
        "gdas.20260315/00/atmos/gdas.t00z.pgrb2.1p00.f000": b"g",
    }
    keys = find_gdas(
        [dt("2026-03-14T18:00Z"), dt("2026-03-15T00:00Z")], FakeS3(objects)
    )
    assert keys is not None and keys[1].startswith("gdas.20260315/00/")


def test_0p25():
    objects = {
        "gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000": b"g",
        "gdas.20260314/12/atmos/gdas.t12z.pgrb2.0p25.f000": b"g",
    }
    keys = find_gdas([dt("2026-03-14T12:00Z")], FakeS3(objects), resolution="0p25")
    assert keys == ["gdas.20260314/12/atmos/gdas.t12z.pgrb2.0p25.f000"]


def test_old_layout_has_no_0p25():
    objects = {"gdas.20130601/12/gdas1.t12z.pgrbf00.grib2": b"g"}
    assert (
        find_gdas([dt("2013-06-01T12:00Z")], FakeS3(objects), resolution="0p25") is None
    )


def test_listing_is_paginated():
    objects = distractors("20260314", "12", True)
    objects["gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000"] = b"g"
    keys = find_gdas([dt("2026-03-14T12:00Z")], FakeS3(objects, page_size=2))
    assert keys == ["gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000"]


def test_naive_cycle_rejected():
    with pytest.raises(ValueError):
        find_gdas([datetime(2026, 3, 14, 12)], FakeS3({}))


def test_unknown_resolution_rejected():
    with pytest.raises(ValueError, match="resolution"):
        find_gdas([dt("2026-03-14T12:00Z")], FakeS3({}), resolution="0p50")


KEY = "gdas.20260314/12/atmos/gdas.t12z.pgrb2.1p00.f000"
GRIB = b"AAAA" + b"PWAT-MESSAGE" + b"BBBB" + b"TOZNE-MSG" + b"CCCCCC"
IDX = (
    b"1:0:d=2026031412:PRMSL:mean sea level:anl:\n"
    b"2:4:d=2026031412:PWAT:entire atmosphere (considered as a single layer):anl:\n"
    b"3:16:d=2026031412:CWAT:entire atmosphere (considered as a single layer):anl:\n"
    b"4:20:d=2026031412:TOZNE:entire atmosphere (considered as a single layer):anl:\n"
    b"5:29:d=2026031412:HGT:surface:anl:\n"
)


def test_fetch_uses_idx_ranges(tmp_path):
    s3 = FakeS3({KEY: GRIB, KEY + ".idx": IDX})
    out = fetch_gdas(KEY, tmp_path / "g.grib2", s3)
    assert out.read_bytes() == b"PWAT-MESSAGE" + b"TOZNE-MSG"
    ranges = [c.get("Range") for c in s3.get_calls if c["Key"] == KEY]
    assert ranges == ["bytes=4-15", "bytes=20-28"]
    assert all(c["Bucket"] == BUCKET for c in s3.get_calls)


def test_fetch_last_message_is_open_ended(tmp_path):
    idx = IDX.replace(b"5:29:d=2026031412:HGT:surface:anl:\n", b"")
    s3 = FakeS3({KEY: GRIB, KEY + ".idx": idx})
    out = fetch_gdas(KEY, tmp_path / "g.grib2", s3)
    assert out.read_bytes() == b"PWAT-MESSAGE" + b"TOZNE-MSGCCCCCC"


def test_fetch_whole_file_without_idx(tmp_path):
    old = "gdas.20130601/12/gdas1.t12z.pgrbf00.grib2"
    s3 = FakeS3({old: GRIB})
    out = fetch_gdas(old, tmp_path / "g.grib2", s3)
    assert out.read_bytes() == GRIB
    assert [c.get("Range") for c in s3.get_calls if c["Key"] == old] == [None]


def test_fetch_requires_both_messages(tmp_path):
    idx = IDX.replace(b"TOZNE", b"TCOLW")
    s3 = FakeS3({KEY: GRIB, KEY + ".idx": idx})
    with pytest.raises(ValueError, match="TOZNE"):
        fetch_gdas(KEY, tmp_path / "g.grib2", s3)
