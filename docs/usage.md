# Usage

Running LaSRC takes three steps:

1. [Get the ancillary data](#1-ancillary-data): look-up tables, static grids, and a daily VIIRS
   atmosphere file for the scene date
2. [Install `lasrc`](#2-install)
3. [Run it](#3-run) with the `lasrc-landsat` / `lasrc-sentinel` CLIs or from Python

## 1. Ancillary data

LaSRC needs **static** inputs, downloaded once and used for every scene, and one **daily** input
that matches each scene's acquisition date.

Static:

| File | CLI option | What it is |
|---|---|---|
| `{LDCMLUT,MSILUT}/ANGLE_NEW.hdf` | `--angle-hdf` | Angle LUT |
| `{LDCMLUT,MSILUT}/RES_LUT_*.hdf` | `--intref-hdf` | Intrinsic (atmospheric path) reflectance LUT |
| `{LDCMLUT,MSILUT}/TRANS_LUT_*.ASCII` | `--transm-hdf` | Transmission LUT |
| `{LDCMLUT,MSILUT}/AERO_LUT_*.ASCII` | `--sphera-hdf` | Spherical albedo / aerosol extinction LUT |
| `CMGDEM.hdf` | `--dem-hdf` | Global elevation on the CMG grid |
| `ratiomapndwiexp.hdf` | `--ratio-hdf` | Band ratio / NDWI climatology |

The LUTs are sensor-specific: use `LDCMLUT/` (`*-V2.0` files) for Landsat 8/9 and `MSILUT/`
(`*-V3.0` files) for Sentinel-2. `CMGDEM.hdf` and `ratiomapndwiexp.hdf` are shared by all
sensors.

Daily:

| File | CLI option | What it is |
|---|---|---|
| `V*04ANC.A<year><doy>.*.h5` | `--wv-oz-hdf` | VIIRS water vapor + ozone for the scene's acquisition date |

### Static files

`CMGDEM.hdf`, `ratiomapndwiexp.hdf`, and the Landsat LUTs come from the USGS
[Landsat Collection 2 Atmospheric Auxiliary Data](https://www.usgs.gov/landsat-missions/landsat-collection-2-atmospheric-auxiliary-data)
page. USGS no longer distributes the Sentinel-2 LUTs, so we host a copy (`MSILUT.tar.gz`) in a
[requester pays](https://docs.aws.amazon.com/AmazonS3/latest/userguide/RequesterPaysBuckets.html)
S3 bucket, `s3://hls-validation-datasets/aux_source/`.

From a checkout of this repo, `scripts/download-aux` downloads all of them, checks them against
`scripts/download-aux.sha256`, and unpacks them (~1.7 GB, mostly `ratiomapndwiexp.hdf`):

```bash
scripts/download-aux ./lasrc_aux
```

```text
lasrc_aux/
  LDCMLUT/                Landsat 8/9 LUTs
  MSILUT/                 Sentinel-2 LUTs
  CMGDEM.hdf
  ratiomapndwiexp.hdf
```

It needs `curl`, `unzip`, and the [AWS CLI](https://aws.amazon.com/cli/) with AWS credentials for
the MSILUT download. With requester pays, your account pays for the transfer (~25 MB; free within
`us-west-2`). Re-running skips files already downloaded.

### Daily VIIRS atmosphere files

Each scene needs the VIIRS ancillary file for its acquisition date (year + day of year), passed
with `--wv-oz-hdf`. Either of two equivalent products works: `VNP04ANC` (Suomi NPP) or `VJ104ANC`
(NOAA-20 / JPSS-1). Download them from NASA Earthdata via the
[LAADS DAAC](https://ladsweb.modaps.eosdis.nasa.gov/) archive. You need a free
[NASA Earthdata Login](https://urs.earthdata.nasa.gov/) account.

The examples below keep them under `lasrc_aux/LADS/<year>/`, but any path works.

### GDAS atmosphere files (opt-in)

Instead of a VIIRS file, `--wv-oz-hdf` also takes water vapor and ozone from NOAA GDAS, converted
by `lasrc-ancillary gdas` into a file with the same layout as a VIIRS file. `lasrc` reads it exactly
as it reads VIIRS. Unlike VIIRS, a GDAS file is made for one acquisition time, so each scene
needs its own.

```shell
uv sync   # lasrc-ancillary[gdas] is part of the dev environment
uv run lasrc-ancillary gdas --metadata $SCENE/LC09_..._MTL.txt gdas.h5
# Sentinel-2: --metadata $SAFE/GRANULE/*/MTD_TL.xml
```

It reads the acquisition time from the metadata (`--acquisition-time 2026-03-14T15:12:34Z` works
too), downloads the two GDAS 0-hour files that bracket it from the public NOAA Open Data bucket
(`s3://noaa-gfs-bdp-pds`), and interpolates them linearly in time and bilinearly onto the CMG grid.
To convert GRIB files you already have, give the two of them before the output path. It exits 0 on
success and 1 on any error (2 for usage errors).

When a cycle is missing, the command prints one line per missing cycle to stderr, in a fixed
`key=value` form for log filters and alerts:

```text
GDAS_MISSING status=not-yet-published cycle=2026-11-15T06:00Z resolution=1p00 acquisition=2026-11-15T03:00:00Z searched=s3://noaa-gfs-bdp-pds/gdas.20261115/06/
```

`status=not-yet-published` means a retry later can succeed. `status=missing-past-cutoff` means
the cycle is still missing 24 hours after its time, most likely a gap in the archive, so it is the
one to alert on. Both exit 1. Deciding when to retry is up to the wrapper (from Python, catch
`GdasNotYetPublished` and `GdasMissing` from `lasrc_ancillary.providers.gdas`).

Fetching uses the default AWS credential chain. The bucket is public, so credentials from any AWS
account work. `--bucket` (or `LASRC_ANCILLARY_GDAS_BUCKET`) points it at another bucket with the
same key layout, for example a mirror holding known files for integration tests.

#### Finding the GDAS files for a granule

A granule needs the GDAS cycle at or before its UTC acquisition time and the one 6 hours later.
The later 0-hour file is published a median 6.8 hours after its cycle (95% within 7.6), so a
granule's GDAS input is ready 7 to 13 hours after acquisition. The functions behind
`lasrc-ancillary gdas` are also the lookup for an orchestration layer. `lasrc_ancillary.acquisition`
and `lasrc_ancillary.providers.gdas` use only the standard library, so a Lambda can install
`lasrc-ancillary` without extras.

- **Orchestration**, knowing only the granule ID: estimate the acquisition time from the UTC date
  and the scene or tile center (`estimate_acquisition_windows`, with the Sentinel-2 datatake start
  as `not_before`), list every cycle the windows touch (`gdas_cycles_for_windows`), and trigger
  once `find_gdas` finds all of them.
- **Processing**: `lasrc-ancillary gdas` (or `lasrc_ancillary.providers.gdas.convert.prepare_gdas` from
  Python) uses the exact time from the metadata and finds the files itself, so a wrong estimate
  only costs a retry (`status=not-yet-published`, or `GdasNotYetPublished`).

[`gdas-support.md`](gdas-support.md) has the details: the NODD key layouts, the gaps in the
archive before 2020, the latency by longitude, and the faster GFS alternative.

## 2. Install

There are no prebuilt wheels yet, so `lasrc` builds from source. You need:

- [rustup](https://rustup.rs/). The build picks up the pinned toolchain from
  `rust-toolchain.toml`.
- Python >= 3.12
- The HDF4 library, if `pip`/`uv` can't find a prebuilt `pyhdf` wheel for your platform:
  `brew install hdf4` (macOS) or `apt install libhdf4-dev` (Debian/Ubuntu)

To install the CLIs as a standalone tool with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install "lasrc @ git+https://github.com/NASA-IMPACT/lasrc-rs#subdirectory=lasrc_py"
lasrc-landsat --help
```

To use it as a library in your own project:

```bash
uv add "lasrc @ git+https://github.com/NASA-IMPACT/lasrc-rs#subdirectory=lasrc_py"
# or: pip install "lasrc @ git+https://github.com/NASA-IMPACT/lasrc-rs#subdirectory=lasrc_py"
```

To work on `lasrc` itself, see "Developer getting started" in the [README](../README.md).

## 3. Run

### Inputs

- **Landsat 8/9**: an unpacked Collection 2 Level-1 scene directory with the `*_MTL.txt` (or
  `*_MTL.json`) and the `*_B<n>.TIF` band files.
- **Sentinel-2**: an unpacked L1C `.SAFE` directory.

The sensor is detected from the directory name (`LC08`/`LC09`, `S2A`/`S2B`/`S2C`). Pass
`--sensor` if your directory is named differently.

### CLI

Landsat 8/9:

```bash
AUX=./lasrc_aux
LUT=$AUX/LDCMLUT

lasrc-landsat \
    --input LC09_L1TP_001066_20260314_20260314_02_T1 \
    --output out/ \
    --angle-hdf  $LUT/ANGLE_NEW.hdf \
    --intref-hdf $LUT/RES_LUT_V3.0-URBANCLEAN-V2.0.hdf \
    --transm-hdf $LUT/TRANS_LUT_V3.0-URBANCLEAN-V2.0.ASCII \
    --sphera-hdf $LUT/AERO_LUT_V3.0-URBANCLEAN-V2.0.ASCII \
    --wv-oz-hdf  $AUX/LADS/2026/VJ104ANC.A2026073.*.h5 \
    --dem-hdf    $AUX/CMGDEM.hdf \
    --ratio-hdf  $AUX/ratiomapndwiexp.hdf
```

Sentinel-2:

```bash
AUX=./lasrc_aux
LUT=$AUX/MSILUT

lasrc-sentinel \
    --input S2B_MSIL1C_20260124T073109_N0511_R049_T38PNC_20260124T092241.SAFE \
    --output out/ \
    --angle-hdf  $LUT/ANGLE_NEW.hdf \
    --intref-hdf $LUT/RES_LUT_V3.0-URBANCLEAN-V3.0.hdf \
    --transm-hdf $LUT/TRANS_LUT_V3.0-URBANCLEAN-V3.0.ASCII \
    --sphera-hdf $LUT/AERO_LUT_V3.0-URBANCLEAN-V3.0.ASCII \
    --wv-oz-hdf  $AUX/LADS/2026/VJ104ANC.A2026024.*.h5 \
    --dem-hdf    $AUX/CMGDEM.hdf \
    --ratio-hdf  $AUX/ratiomapndwiexp.hdf
```

Other options (see `--help`):

| Option | Default | Notes |
|---|---|---|
| `--output-format` | `espa` | `espa`: ENVI `.img` + `.hdr` per band (the ESPA product format). `cog`: Cloud-Optimized GeoTIFF per band (Landsat only). `numpy`: headerless `.bin` per band. |
| `--num-threads` | `0` (all cores) | Also read from `RAYON_NUM_THREADS` |
| `--sensor` | auto-detected | `LANDSAT_8`, `LANDSAT_9`, `SENTINEL_2A`, `SENTINEL_2B`, `SENTINEL_2C` |

### Outputs

`--output` is a directory. Each file is prefixed with the scene's product ID and holds one band:

| Band | dtype | Contents |
|---|---|---|
| `sr_band<n>` | `uint16` | Surface reflectance |
| `sr_aerosol` | `int16` | Retrieved aerosol optical thickness |
| `sr_aerosol_qa` | `uint8` | Aerosol retrieval QA flags |

The values and dtypes match the C LaSRC output. Fill values are exported as
`lasrc.SR_FILL_VALUE` and `lasrc.AERO_FILL`.

### Python

The CLIs are thin wrappers around two pipeline functions, which read the scene, load the aux
data, run the correction, write the output, and also return the result arrays:

```python
from pathlib import Path

from lasrc.pipeline import AuxFilePaths, process_scene

aux = Path("lasrc_aux")
lut = aux / "LDCMLUT"

result = process_scene(
    input_path="LC09_L1TP_001066_20260314_20260314_02_T1",
    aux_files=AuxFilePaths(
        angle_hdf=lut / "ANGLE_NEW.hdf",
        intref_hdf=lut / "RES_LUT_V3.0-URBANCLEAN-V2.0.hdf",
        transm_hdf=lut / "TRANS_LUT_V3.0-URBANCLEAN-V2.0.ASCII",
        sphera_hdf=lut / "AERO_LUT_V3.0-URBANCLEAN-V2.0.ASCII",
        wv_oz_hdf=next((aux / "LADS/2026").glob("V*04ANC.A2026073.*.h5")),
        dem_hdf=aux / "CMGDEM.hdf",
        ratio_hdf=aux / "ratiomapndwiexp.hdf",
    ),
    output_path="out/",
    sensor_name="LANDSAT_9",
    output_format="cog",
)

result["sr_bands"][0]  # (nlines, nsamps) uint16
result["aerosol"]  # (nlines, nsamps) int16
```

For Sentinel-2, `lasrc.pipeline_sentinel.process_sentinel_scene` takes the same inputs as flat
keyword arguments (`safe_dir`, `angle_hdf`, ..., `viirs_aux_path`, `dem_path`, `ratio_path`,
`output_path`, `sensor_name`).

To skip the file I/O, for example to feed in arrays you already have in memory, call the Rust
extension directly: `lasrc.process_surface_reflectance` (Landsat) and
`lasrc.process_sentinel_surface_reflectance` (Sentinel-2). They take TOA arrays, per-pixel angles,
a `PyLookupTables`, and a `PyAuxiliaryData`. `lasrc.aux` has loaders that build the constructor
arguments for those last two from the files above. The pipeline functions show how the pieces fit
together.
