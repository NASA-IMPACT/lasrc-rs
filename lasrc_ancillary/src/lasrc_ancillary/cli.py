"""Command-line interface: ``lasrc-ancillary gdas``.

Exit codes: 0 done, 1 error, 2 usage error, 75 (EX_TEMPFAIL) when the later GDAS cycle is not on
NODD yet, so the orchestration can retry.
"""

import logging
from datetime import datetime
from pathlib import Path

import click

from lasrc_ancillary.cycles import parse_iso
from lasrc_ancillary.gdas import GdasMissing, GdasNotYetPublished, prepare_gdas
from lasrc_ancillary.metadata import read_acquisition_time
from lasrc_ancillary.nodd import RESOLUTIONS

EX_TEMPFAIL = 75


class _UtcTime(click.ParamType):
    name = "time"

    def convert(
        self, value: object, param: click.Parameter | None, ctx: click.Context | None
    ) -> datetime:
        if isinstance(value, datetime):
            return value
        try:
            t = parse_iso(str(value))
        except ValueError:
            self.fail(f"not an ISO 8601 time: {value!r}", param, ctx)
        if t.tzinfo is None:
            self.fail(
                f"{value!r} has no timezone, add 'Z' or a UTC offset such as +00:00",
                param,
                ctx,
            )
        return t


@click.group()
def main() -> None:
    """Find, fetch and convert ancillary inputs for lasrc."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )


@main.command()
@click.option(
    "--acquisition-time", type=_UtcTime(), help="ISO 8601 time with a timezone."
)
@click.option(
    "--metadata",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Landsat *_MTL.txt or Sentinel-2 tile MTD_TL.xml to read the time from.",
)
@click.option(
    "--fetch",
    is_flag=True,
    help="Find and download the GDAS files from NODD (replaces local files that don't match).",
)
@click.option(
    "--resolution", type=click.Choice(RESOLUTIONS), default="1p00", show_default=True
)
@click.option(
    "--work-dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="Where fetched GDAS files go (default: a temporary directory).",
)
@click.argument(
    "grib", nargs=-1, type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
@click.pass_context
def gdas(
    ctx: click.Context,
    acquisition_time: datetime | None,
    metadata: Path | None,
    fetch: bool,
    resolution: str,
    work_dir: Path | None,
    grib: tuple[Path, ...],
    output: Path,
) -> None:
    """GDAS water vapor and ozone as a VIIRS-shaped file for lasrc --wv-oz-hdf.

    GRIB is the two local GDAS 0-hour files, or none with --fetch.
    """
    if (acquisition_time is None) == (metadata is None):
        raise click.UsageError("give exactly one of --acquisition-time or --metadata")
    if not fetch and len(grib) != 2:
        raise click.UsageError("give two local GDAS files, or --fetch")
    if fetch and len(grib) not in (0, 2):
        raise click.UsageError("give two local GDAS files or none with --fetch")
    obj = ctx.obj or {}
    try:
        if acquisition_time is None:
            assert metadata is not None
            acquisition_time = read_acquisition_time(metadata)
        if work_dir is not None:
            work_dir.mkdir(parents=True, exist_ok=True)
        prepare_gdas(
            acquisition_time,
            output,
            local_files=grib,
            fetch=fetch,
            s3_client=obj.get("s3_client"),
            resolution=resolution,
            work_dir=work_dir,
            now=obj.get("now"),
        )
    except GdasNotYetPublished as e:
        click.echo(f"{e}, retry later", err=True)
        ctx.exit(EX_TEMPFAIL)
    except (GdasMissing, OSError, ValueError) as e:
        click.echo(f"error: {e}", err=True)
        ctx.exit(1)
