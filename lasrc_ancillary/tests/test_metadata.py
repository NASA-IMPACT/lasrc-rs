import datetime as dt

import pytest
from lasrc_ancillary.metadata import read_acquisition_time

MTD_TL = """<?xml version="1.0" encoding="UTF-8"?>
<n1:Level-1C_Tile_ID xmlns:n1="https://psd-14.sentinel2.eo.esa.int/PSD/S2_PDI_Level-1C_Tile_Metadata.xsd">
  <n1:General_Info>
    <TILE_ID metadataLevel="Brief">S2B_OPER_MSI_L1C_TL_2BPS_20260124T092241_A046102_T38PNC_N05.11</TILE_ID>
    <SENSING_TIME metadataLevel="Standard">2026-01-24T07:45:13.375Z</SENSING_TIME>
  </n1:General_Info>
</n1:Level-1C_Tile_ID>
"""


def test_mtl_seven_digit_time(tmp_path):
    p = tmp_path / "X_MTL.txt"
    p.write_text(
        "GROUP = IMAGE_ATTRIBUTES\n"
        "    DATE_ACQUIRED = 2026-03-14\n"
        '    SCENE_CENTER_TIME = "15:12:34.1234567Z"\n'
        "END_GROUP = IMAGE_ATTRIBUTES\n"
    )
    assert read_acquisition_time(p) == dt.datetime(
        2026, 3, 14, 15, 12, 34, 123456, tzinfo=dt.UTC
    )


def test_mtd_tl_sensing_time(tmp_path):
    p = tmp_path / "MTD_TL.xml"
    p.write_text(MTD_TL)
    assert read_acquisition_time(p) == dt.datetime(
        2026, 1, 24, 7, 45, 13, 375000, tzinfo=dt.UTC
    )


def test_mtl_missing_field_raises(tmp_path):
    p = tmp_path / "X_MTL.txt"
    p.write_text("    DATE_ACQUIRED = 2026-03-14\n")
    with pytest.raises(ValueError, match="SCENE_CENTER_TIME"):
        read_acquisition_time(p)


def test_mtd_tl_missing_field_raises(tmp_path):
    p = tmp_path / "MTD_TL.xml"
    p.write_text(MTD_TL.replace("SENSING_TIME", "OTHER_TIME"))
    with pytest.raises(ValueError, match="SENSING_TIME"):
        read_acquisition_time(p)


def test_unknown_file_type_raises(tmp_path):
    p = tmp_path / "notes.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="notes.json"):
        read_acquisition_time(p)
