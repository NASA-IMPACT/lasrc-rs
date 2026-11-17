"""Command-line interface: ``lasrc-ancillary gdas``.

Exit codes: 0 done, 1 error, 2 usage error, 75 (EX_TEMPFAIL) when the later GDAS cycle is not on
NODD yet, so the orchestration can retry.
"""

import logging
from datetime import datetime
from pathlib import Path

import click

from lasrc_ancillary.gdas import GdasMissing, GdasNotYetPublished, prepare_gdas
from lasrc_ancillary.metadata import read_acquisition_time
from lasrc_ancillary.nodd import NODD_BUCKET, RESOLUTIONS, Resolution

EX_TEMPFAIL = 75


# Every format requires a timezone. %z accepts "Z" as well as offsets such as +00:00.
ISO_FORMATS = ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M%z"]


@click.group()
def main() -> None:
    """Find, fetch and convert ancillary inputs for lasrc."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )


@main.command()
@click.option(
    "--acquisition-time",
    type=click.DateTime(formats=ISO_FORMATS),
    help="ISO 8601 time with a timezone, such as 2026-03-14T15:12:34Z.",
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
    "--bucket",
    default=NODD_BUCKET,
    show_default=True,
    envvar="LASRC_ANCILLARY_GDAS_BUCKET",
    show_envvar=True,
    help="S3 bucket with the NODD GDAS layout, for example a mirror for testing.",
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
    resolution: Resolution,
    bucket: str,
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
            bucket=bucket,
            work_dir=work_dir,
            now=obj.get("now"),
        )
    except GdasNotYetPublished as e:
        click.echo(str(e), err=True)
        ctx.exit(EX_TEMPFAIL)
    except GdasMissing as e:
        click.echo(str(e), err=True)
        ctx.exit(1)
    except (OSError, ValueError) as e:
        click.echo(f"error: {e}", err=True)
        ctx.exit(1)
