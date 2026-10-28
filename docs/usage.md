# Usage

Running LaSRC takes three steps:

1. [Get the ancillary data](#1-ancillary-data): look-up tables, static grids, and a daily VIIRS
   atmosphere file for the scene date
2. [Install `lasrc`](#2-install)
3. [Run it](#3-run) with the `lasrc-landsat` / `lasrc-sentinel` CLIs or from Python

## 1. Ancillary data

LaSRC needs two kinds of auxiliary input:

| File | Kind | CLI option | What it is |
|---|---|---|---|
| `{LDCMLUT,MSILUT}/ANGLE_NEW.hdf` | static | `--angle-hdf` | Angle LUT |
| `{LDCMLUT,MSILUT}/RES_LUT_*.hdf` | static | `--intref-hdf` | Intrinsic (atmospheric path) reflectance LUT |
| `{LDCMLUT,MSILUT}/TRANS_LUT_*.ASCII` | static | `--transm-hdf` | Transmission LUT |
| `{LDCMLUT,MSILUT}/AERO_LUT_*.ASCII` | static | `--sphera-hdf` | Spherical albedo / aerosol extinction LUT |
| `CMGDEM.hdf` | static | `--dem-hdf` | Global elevation on the CMG grid |
| `ratiomapndwiexp.hdf` | static | `--ratio-hdf` | Band ratio / NDWI climatology |
| `LADS/<year>/V*04ANC.A<year><doy>.*.h5` | daily | `--wv-oz-hdf` | VIIRS water vapor + ozone for the scene's acquisition date |

The LUTs are sensor-specific: use `LDCMLUT/` (`*-V2.0` files) for Landsat 8/9 and `MSILUT/`
(`*-V3.0` files) for Sentinel-2. `CMGDEM.hdf` and `ratiomapndwiexp.hdf` are shared by all
sensors.

These files come from the USGS
[Landsat Collection 2 Atmospheric Auxiliary Data](https://www.usgs.gov/landsat-missions/landsat-collection-2-atmospheric-auxiliary-data)
distribution, the original source and source of truth. The S3 copy below is a convenience mirror.

### From S3

The static files, plus a collection of the daily VIIRS files, are in a public
[requester pays](https://docs.aws.amazon.com/AmazonS3/latest/userguide/RequesterPaysBuckets.html)
bucket in `us-west-2`, under `s3://hls-validation-datasets/lasrc_aux/`:

```
lasrc_aux/
  CMGDEM.hdf                   ~130 MB
  ratiomapndwiexp.hdf          ~1.5 GB
  LDCMLUT/                     ~40 MB   Landsat 8/9 LUTs
  MSILUT/                      ~65 MB   Sentinel-2 LUTs
  LADS/<year>/V*04ANC.*.h5     ~50 MB per day, partial archive
```

You need AWS credentials, and your account pays for the request and data transfer (transfer is
free within `us-west-2`). The VIIRS files make up most of the bucket, so download the static files
on their own:

```bash
aws s3 sync s3://hls-validation-datasets/lasrc_aux/ ./lasrc_aux/ \
    --request-payer requester \
    --exclude "LADS/*"
```

Skip `LDCMLUT/*` or `MSILUT/*` as well if you only process one sensor family.

### Daily VIIRS atmosphere files

Each scene needs the VIIRS ancillary file for its acquisition date (year + day of year). There are
two equivalent products: `VNP04ANC` (Suomi NPP) and `VJ104ANC` (NOAA-20 / JPSS-1). Either one
works with `--wv-oz-hdf`.

The bucket holds a partial archive of these files as a convenience. NASA Earthdata (below) is the
source for the full record. To fetch the file(s) for one date from the bucket:

```bash
# Scene acquired 2026-01-24 -> year 2026, day of year 024
aws s3 sync s3://hls-validation-datasets/lasrc_aux/LADS/2026/ ./lasrc_aux/LADS/2026/ \
    --request-payer requester \
    --exclude "*" --include "V*04ANC.A2026024.*.h5"
```

If nothing downloads, the bucket doesn't have that date. Get it, and any other date, directly from
NASA Earthdata via the
[LAADS DAAC](https://ladsweb.modaps.eosdis.nasa.gov/) archive, which needs a free
[NASA Earthdata Login](https://urs.earthdata.nasa.gov/) account and a user token (Earthdata
profile -> "Generate Token"):

```bash
export EDL_TOKEN=...   # your Earthdata user token

PRODUCT=VJ104ANC       # or VNP04ANC
YEAR=2026
DOY=024
URL="https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5200/${PRODUCT}/${YEAR}/${DOY}"

# Each day directory holds a single file; look up its name, then download it
NAME=$(curl -s "${URL}.json" | python3 -c "import json,sys; print(json.load(sys.stdin)['content'][0]['name'])")
mkdir -p "lasrc_aux/LADS/${YEAR}"
curl -L -H "Authorization: Bearer ${EDL_TOKEN}" \
    -o "lasrc_aux/LADS/${YEAR}/${NAME}" "${URL}/${NAME}"
```

Day of year for a date: `date -d 2026-01-24 +%j` (GNU) or `date -j -f %Y-%m-%d 2026-01-24 +%j`
(macOS).

## 2. Install

There are no prebuilt wheels yet, so `lasrc` builds from source. You need:

- [rustup](https://rustup.rs/). The build picks up the pinned toolchain from
  `rust-toolchain.toml`.
- Python >= 3.10

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
result["aerosol"]      # (nlines, nsamps) int16
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
