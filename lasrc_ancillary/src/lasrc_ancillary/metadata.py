"""Acquisition time from Landsat and Sentinel-2 metadata, with the standard library only."""

import datetime as dt
import re
from pathlib import Path
from xml.etree import ElementTree


def read_acquisition_time(path: Path) -> dt.datetime:
    """UTC acquisition time from a Landsat MTL (``*_MTL.txt``) or a Sentinel-2 ``MTD_TL.xml``.

    Sentinel-2 uses the tile's ``SENSING_TIME``. ``PRODUCT_START_TIME`` in ``MTD_MSIL1C.xml`` is
    the start of the whole datatake, which can be many minutes earlier.
    """
    path = Path(path)
    if path.name.endswith("_MTL.txt"):
        return _landsat_mtl_time(path)
    if path.suffix.lower() == ".xml":
        return _sentinel_tile_time(path)
    raise ValueError(
        f"{path.name}: expected a Landsat *_MTL.txt or a Sentinel-2 MTD_TL.xml"
    )


def _landsat_mtl_time(path: Path) -> dt.datetime:
    fields: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip().strip('"')
    for name in ("DATE_ACQUIRED", "SCENE_CENTER_TIME"):
        if name not in fields:
            raise ValueError(f"{path.name}: missing {name}")
    m = re.fullmatch(
        r"(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?Z", fields["SCENE_CENTER_TIME"]
    )
    if m is None:
        raise ValueError(
            f"{path.name}: unexpected SCENE_CENTER_TIME {fields['SCENE_CENTER_TIME']}"
        )
    hh, mm, ss, frac = m.groups()
    day = dt.datetime.strptime(fields["DATE_ACQUIRED"], "%Y-%m-%d")
    micro = int((frac or "0")[:6].ljust(6, "0"))
    return day.replace(
        hour=int(hh), minute=int(mm), second=int(ss), microsecond=micro, tzinfo=dt.UTC
    )


def _sentinel_tile_time(path: Path) -> dt.datetime:
    root = ElementTree.parse(path).getroot()
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "SENSING_TIME" and element.text:
            return dt.datetime.fromisoformat(element.text.strip()).astimezone(dt.UTC)
    raise ValueError(f"{path.name}: missing SENSING_TIME")
