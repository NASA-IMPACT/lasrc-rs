# GDAS water vapor and ozone

<!--toc:start-->
- [GDAS water vapor and ozone](#gdas-water-vapor-and-ozone)
  - [Upstream C code](#upstream-c-code)
    - [Commits](#commits)
    - [Summary of changes](#summary-of-changes)
    - [1. GRIB input path](#1-grib-input-path)
      - [Command line](#command-line)
      - [Detecting the source](#detecting-the-source)
      - [GDAS Variables](#gdas-variables)
      - [Scaling to DN](#scaling-to-dn)
    - [2. Temporal interpolation](#2-temporal-interpolation)
    - [3. Spatial interpolation](#3-spatial-interpolation)
    - [4. Sentinel-2 acquisition time](#4-sentinel-2-acquisition-time)
    - [5. Changes not related to GDAS](#5-changes-not-related-to-gdas)
      - [Output reflectance scaling](#output-reflectance-scaling)
      - [Sentinel-2 fill mask fix](#sentinel-2-fill-mask-fix)
      - [Aerosol window](#aerosol-window)
      - [Version and debug output](#version-and-debug-output)
  - [Using GDAS in lasrc-rs](#using-gdas-in-lasrc-rs)
    - [GDAS data on the NODD bucket](#gdas-data-on-the-nodd-bucket)
    - [Finding the files for a granule](#finding-the-files-for-a-granule)
      - [Orchestration: triggering from the granule ID](#orchestration-triggering-from-the-granule-id)
      - [Processing: using the exact time](#processing-using-the-exact-time)
    - [Interpolating without index arithmetic](#interpolating-without-index-arithmetic)
    - [Appendix: latency, GDAS vs GFS](#appendix-latency-gdas-vs-gfs)
<!--toc:end-->

This page has two parts:

- **Upstream C code**: what the algorithm author's GDAS support changes, read from the diff.
- **Using GDAS in lasrc-rs**: the GDAS files on NODD, how to find the ones a granule needs, and
  how long they take to arrive.

## Upstream C code

This part describes what the algorithm author's `eros-collection2-3.5.2` branch of
`espa-surface-reflectance` changes, relative to the `eros-collection2-3.5.1` release
(`6051e02`). The main change is support for NOAA GDAS GRIB files as the source of water vapor and
ozone, in place of the daily VIIRS (`V*04ANC`) or MODIS (`L8ANC`) CMG files.

The branch has no description of its own. Everything here comes from reading the diff.

### Commits

| Commit | Date | Message | Content |
|---|---|---|---|
| `a64c9cf` | 2026-03-26 | grib support | GDAS/GRIB reading, temporal + spatial interpolation, Sentinel-2 acquisition time |
| `76c27a7`, `5085b35` | 2026-03-26 | testpush, pipo | Add and remove `testpush.txt`. No net change |
| `b271310` | 2026-06-26 | restore production aerosol retrieval window size + fix minor bugs | Undo a 1x1 aerosol window test, Sentinel-2 fill bug fix, bilinear spatial interpolation |

`a64c9cf` touches 534 files, but almost all of that is noise. Every file in the repository changed
mode from 644 to 755, and some files changed line endings or whitespace. To see the real changes:

```shell
git -c core.filemode=false diff -w --ignore-cr-at-eol --ignore-blank-lines \
    6051e02 b271310 -- lasrc/c_version/src
```

Nothing outside `lasrc/c_version/src` changes in content.

### Summary of changes

1. **New GRIB input path** for water vapor and ozone, read from two GDAS files that bracket the
   scene acquisition time (`--aux` and a new `--aux2` option).
2. **Temporal interpolation**: linear in time between the two GDAS 0-hour forecasts.
3. **Spatial interpolation**: bilinear from the GDAS grid onto the 0.05 degree CMG grid that the
   rest of LaSRC already uses.
4. **Sentinel-2 acquisition time** is now read from `MTD_MSIL1C.xml`. Before this change it was
   always midnight (`T00:00:00`).
5. Changes **not related to GDAS**:
   - output reflectance scaling changed to `0.0001` with offset `0.0`
   - a Sentinel-2 fill-mask bug fix in the original aerosol path
   - an aerosol window test, added and then removed (no net change)
   - algorithm version string bumped to `3.5.2.0`

The rest of the algorithm is unchanged. The GDAS path produces the same CMG-shaped water vapor and
ozone arrays that the VIIRS and MODIS readers produce, and everything downstream reads them the same
way.

### 1. GRIB input path

#### Command line

`lasrc` gains an optional `--aux2` argument. The usage example is:

```shell
lasrc --xml=LC08_L1TP_078014_20220306_20220314_02_T1.xml \
    --aux=gdas1.PGrbF00.220306.18z --aux2=gdas1.PGrbF00.220307.00z --verbose
```

`--aux2` is only used when `--aux` is a GRIB file. For VIIRS and MODIS it is ignored.

#### Detecting the source

Before this change the source came from the filename (`04ANC` means VIIRS, `L8ANC` means MODIS).
The aux source enum gains `AUXNULL = -1` and `GRIB`. If the filename matches neither VIIRS nor
MODIS, `lasrc` opens `$LASRC_AUX_DIR/LADS/<aux>` and checks for the `GRIB` magic bytes. The byte
at offset 7 (octet 8) holds the GRIB edition, 1 or 2 (`lut_subr.c:3909-3913`). Both GRIB1 and
GRIB2 are supported, through two vendored readers:

- `grib.c` / `grib.h` (GRIB1, about 3,500 lines, adapted from `wgrib`)
- `PGE11_grib2.c` / `PGE11_grib2.h` / `PGE11_grb2.h` (GRIB2, about 6,000 lines, adapted from
  `wgrib2`)

Both files must be the same GRIB edition, or `lasrc` exits with an error.

GRIB files are looked up in `$LASRC_AUX_DIR/LADS/` directly, not in a `<year>/` subdirectory like
VIIRS and MODIS. The comment says the year can't be reliably derived from GRIB filenames. The year
is read from the first file's PWAT message instead, but it is not used for anything once the path
is known.

#### GDAS Variables

From each file, two messages:

| Variable | GRIB name | Level | Units |
|---|---|---|---|
| Water vapor | `PWAT` (precipitable water) | entire atmosphere (single layer) | kg/m^2 (= mm) |
| Ozone | `TOZNE` (total ozone) | entire atmosphere (single layer) | Dobson units |

The reference date/time of each file comes from its `PWAT` message. The forecast hour is read but
ignored, so the files are expected to be analyses or 0-hour forecasts (`F00` / `f000`), where the
reference time equals the valid time.

The GRIB2 reader reorders the grid to run north to south, and rotates each row so it starts near
longitude -180. GDAS stores each row from 0 to 359 degrees east. The rotation is off by one column
(see [section 3](#3-spatial-interpolation)).

#### Scaling to DN

After interpolation (sections 2 and 3), the values are converted to the same integer "DN" arrays
that the VIIRS and MODIS readers fill:

```c
wv[l] = (uint16)(pwat * 10.0);    /* kg/m^2 -> DN */
oz[l] = (uint8)(tozne * 0.40);    /* DU -> cm-atm (/1000) -> DN (x400) */
```

Both casts truncate toward zero. Ozone DN steps are 2.5 DU and water vapor DN steps are 0.1 mm.

The GRIB entries in the per-source constant tables in `common.h` are:

| Constant | MODIS | VIIRS | GRIB |
|---|---|---|---|
| `WV_SCALE_FACTOR` | 200 | 200 | 200 |
| `WV_DEFAULT` (g/cm^2, scene center fallback) | 0.5 | 2.5 | 0.5 |
| `WV_DEFAULT_DN` (fill replacement) | 0 | 250 | 100 |
| `WV_FILL` | 0 | 0 | 0 |
| `OZ_SCALE_FACTOR` | 400 | 400 | 400 |
| `OZ_DEFAULT` (cm-atm) | 0.3 | 0.3 | 0.3 |
| `OZ_DEFAULT_DN` | 120 | 110 | 125 |
| `OZ_FILL` | 0 | 0 | 0 |

Water vapor in g/cm^2 is `DN / WV_SCALE_FACTOR = PWAT * 10 / 200 = PWAT / 20`
(`lut_subr.c:3128`, `common.h:301`, `compute_refl_subr.c:249`). Physically 1 kg/m^2 is
0.1 g/cm^2, so the correct value is `PWAT / 10`. The GRIB path halves water vapor. Ozone is scaled
correctly.

The GRIB path copies the divisor of 200 from the MODIS and VIIRS paths. With VIIRS input it halves
water vapor too: the VIIRS `Coarse Resolution Water Vapor` dataset has `scale_factor=0.01`, so the
physical divisor is 100.

The 200 comes from the algorithm author's Fortran. The history in `espa-surface-reflectance`:

| Where | Date | Scene center | Per-pixel (original aerosol path) |
|---|---|---|---|
| Landsat Fortran, `LDCMSR-v3.5.2.f:864` and `:1123` | by 2017-01 | `wv/200.` | `twvi/100.` |
| Sentinel-2 Fortran, `LaSRCS2AV3.5.5.f:662` and `:786` | 2017-05 | `wv/200.` | `twvi/100.` |
| C port, `8093124` | 2017-01 | `/ 200.0` | `* 0.01` |
| `9b0ea73`, switch from MODIS to VIIRS | 2022-03 | `/ 100.0` | `* 0.01` |
| `18875d4` | 2023-01 | `WV_SCALE_FACTOR {100, 100}`. `{200, 100}` kept as a comment, "USGS OPS with MODIS bug" | |
| `ebea983` (3.5.0) | 2023-08 | `{200, 200}`. Commit message: "reintroduced the WV scale factor bug for both MODIS and VIIRS" | |
| `a64c9cf` | 2026-03 | `{200, 200, 200}`, with the same factor for GRIB | |

Both Fortran programs divide the same `wv` array by 200 at the scene center and by 100 per pixel,
so only one of them can be the physical scaling for a given input.

The two values go through the same gas transmission routine with the same fitted coefficients.
In the current C code (`eros-collection2-3.5.2`):

- The scene center value (`/ 200`, `compute_refl_subr.c:249`) feeds the per-band loop at
  `compute_landsat_refl.c:630`. That loop runs for both aerosol paths.
- With `use_orig_aero`, the per-pixel value (`* 0.01`, `compute_landsat_refl.c:944`) feeds the
  aerosol retrieval (`subaeroret`, line 1298) and the final correction (line 1736).
- Both reach `atmcorlamb2`, which calls `comptg` (`lut_subr.c:333`) with the same `wvtransa` and
  `wvtransb`.

So a run with the original aerosol path uses both scalings with the same coefficients. The
water vapor transmission is `exp(-a * (m * uwv)^b)`, so a different input unit could in principle
be absorbed by the coefficients. But that can't make both 100 and 200 right at once. The halving
is not a one-way path either. `comptg` already applies the air mass for both paths, and computes a
separate half-column transmission (`tgwvhalf`) on top of the `uwv` it is given.

Whether 200 was physical for the original MODIS `L8ANC` input depends on that product's scale
factor, which is not checked here. USGS used 100 for VIIRS from 2022-03 to 2023-08, then restored
200, calling it a bug in the commit message. Neither the code nor the commit says why they restored
it. lasrc-rs has the same factor today (`wv_scale` 200 in `lasrc_py/python/lasrc/aux.py`).

A DN of 0 counts as fill and is replaced by the default. For GDAS that means a PWAT below
0.1 kg/m^2. The smallest value in a sample June 2025 file was 0.16, so this is rare.

### 2. Temporal interpolation

`open_gb_oz_wv_datasets` in `lut_subr.c` reads both files and interpolates linearly in time to the
scene acquisition time `t`:

```text
w2 = (t - t1) / (t2 - t1)
w1 = (t2 - t) / (t2 - t1)
value = w1 * value1 + w2 * value2
```

This runs on the native GDAS grid, for both PWAT and TOZNE, before spatial interpolation.

The function checks:

- the two files' dates are at most one day apart, and the second file is at most one day from the
  acquisition date
- the files are exactly 6 hours apart (`GRIB_WV_SP_TIMERES`)
- `t1 <= t <= t2`, within the same day (a second file at 00Z the next day is handled by adding
  86,400 seconds)

The files must be given in time order (`--aux` earlier, `--aux2` later). A reversed pair fails
the 6 hour check, because the difference comes out negative.

`swapped` is never set. It is declared at `lut_subr.c:2906`. The code that set it, and swapped
reversed files, is commented out at `lut_subr.c:3032-3038`. It is still read at `lut_subr.c:3070`
(`if (swapped == 0)`), which picks which file gets which weight. Reading it is undefined behavior
in C. If it happens to be non-zero, the two files get each other's weights, so the result is
interpolated toward the wrong cycle. Since reversed pairs are already rejected, the fix is to
remove the variable and its `else` branch, or set it to 0.

### 3. Spatial interpolation

The interpolated GDAS grid is resampled onto the CMG grid (3600 x 7200, 0.05 degree). The first
commit used nearest-neighbor replication. `b271310` switched to bilinear interpolation, with the
old code left in behind `whichone = 0`.

The bilinear code (`get_cart_linesamp`, `get_cart_interp`) treats the GDAS grid as points: row `i`
at latitude `90 - i * dlat`, column `j` at longitude `-180 + j * dlon`. The GDAS spacing comes from
the grid size (`180 / (ny - 1)` and `360 / nx`), so it is not tied to 1 degree.

Problems in this code, largest effect first:

- **The GDAS grid is shifted one column east.** `reverse_data` (`PGE11_grib2.c:287-300`) moves
  input column `j` (longitude `j * dlon`) to `jj = j + nx / 2 - 1`. After the rotation, column 0
  holds longitude `-180 + dlon` and column `nx - 1` holds +180. `get_cart_linesamp`
  (`lut_subr.c:3156`) assumes column 0 is -180. So the value used at longitude `L` is the GDAS
  value at `L + dlon`: 1 degree (about 111 km at the equator) for the 1 degree grid. A check
  that simulates the two routines on a row whose values equal their own longitude returns 1.0 for
  a query at 0.0 and 16.12 for a query at 15.12. The GRIB1 reader has the same rotation
  (`grib.c:352`). The fix is `jj = j + nx / 2`, or taking the first longitude from the GRIB grid
  definition.
- **CMG sample points are cell corners, not centers.** Row `i` is sampled at latitude
  `90 - i * 0.05` and column `j` at `-180 + j * 0.05`. CMG cell `(i, j)` is centered on
  `89.975 - i * 0.05`, `-179.975 + j * 0.05` (see below), so the samples are offset by half a CMG
  cell (0.025 degree) north and west.
- **The longitude seam is wrong.** For longitudes in the last GDAS column (179 to 180 degrees at 1
  degree), the "east" neighbor index runs off the end of the row into the first column of the next
  row. Those samples blend in a value one GDAS row south instead of wrapping to the same row.
- **The sample coordinates accumulate in single precision.** `CMGlat` and `CMGlon` start from an
  offset and add or subtract `0.05f` on each step, so they drift slightly over 3600 and 7200 steps.
- Out-of-range neighbors would read as 0 (`get_cart_interp`), but this is not reached. The
  southernmost sample is at -89.95, between the last two GDAS rows.

The GDAS rows are handled correctly. They are treated as points at `90 - k * dlat`, which matches
how GDAS defines them (181 rows from pole to pole, inclusive). The GDAS columns are treated as
points too, which is right, but the rotation puts them one column off. The temporal and bilinear
weights are correct. The errors are the one-column longitude shift, the CMG sample points and the
seam.

The CMG grid is a grid of cells, not points. The VIIRS file's HDF-EOS metadata gives 7200 x 3600
values from (-180, 90) to (180, -90). Points covering both edges would need 7201 x 3601, so each
value is a 0.05 degree cell, and cell `(0, 0)` is centered at (89.975, -179.975). Sampling at
`90 - 0.05 * i`, `-180 + 0.05 * j` therefore takes each cell's value from its north-west corner.

LaSRC only reads water vapor and ozone at the scene center CMG cell. The longitude shift affects
every scene, and is the largest of the three: water vapor in particular can change a lot over 1
degree near fronts and coastlines. The corner offset affects every scene, but by a small amount, a
0.025 degree shift in fields that vary smoothly at 1 degree. The seam only affects scenes whose
center lands between 179 and 180 degrees east.

### 4. Sentinel-2 acquisition time

The GDAS path needs the time of day. Landsat already had it (`scene_center_time` in the ESPA XML).
For Sentinel-2 the ESPA XML has no time, and the old code set it to `T00:00:00`.

The new `ad_hoc_XML_reader.c` reads `<PRODUCT_START_TIME>` from the `<Product_Info>` block of
`MTD_MSIL1C.xml`. It opens that file by name in the current working directory, and exits the
process if it isn't there. The comment says it is meant to be thrown away once the ESPA
product formatter reads the time itself.

This is the wrong time. The right one is the tile's `SENSING_TIME` in `GRANULE/*/MTD_TL.xml`,
which is when the satellite imaged the tile.

`PRODUCT_START_TIME` is the start of the datatake, the continuous imaging strip the tile was cut
from. In single-tile products, `PRODUCT_START_TIME`, `PRODUCT_STOP_TIME` and
`DATATAKE_SENSING_START` all hold that same datatake start. In
`S2B_MSIL1C_20260124T073109_N0511_R049_T38PNC_20260124T092241` all three are 07:31:09.024, and the
tile's `SENSING_TIME` is 07:45:13.375, 14 minutes later. The error grows the further down the
datatake the tile is. Over a 6-hour GDAS interval, 14 minutes moves about 4% of the weight from
one cycle to the other.

The datatake start is also the first timestamp in the product name (`20260124T073109` above), and
so in the granule ID built from it. A granule ID alone gives the datatake start, not the tile time.
The tile was imaged at or after that time, never before.

### 5. Changes not related to GDAS

#### Output reflectance scaling

`output.h` changes the surface reflectance scale factor and offset:

| | Before | After |
|---|---|---|
| `SCALE_FACTOR_REFL` | 0.0000275 | 0.0001 |
| `OFFSET_REFL` | -0.20 | 0.0 |

These feed both the XML metadata and the integer conversion of the output bands
(`MULT_FACTOR_REFL = 1 / SCALE_FACTOR_REFL`, `BAND_OFFSET_REFL = -OFFSET_REFL`), so the stored
values change for Landsat and Sentinel-2. lasrc-rs still uses the Collection 2 values
(`lasrc_core/src/constants.rs`).

#### Sentinel-2 fill mask fix

In `compute_sentinel_refl.c`, the fill check in the per-pixel auxiliary interpolation loop used the
line index instead of the pixel index:

```c
if (level1_qa_is_fill (qaband[i]))          /* before */
if (level1_qa_is_fill (qaband[curr_pix]))   /* after */
```

That loop only runs for the original aerosol algorithm (`--use_orig_aero_alg`), which lasrc-rs
does not port.

#### Aerosol window

`a64c9cf` changed the aerosol retrieval window to 1x1 (`LAERO_WINDOW 1`, `SAERO_WINDOW 1`).
`b271310` restored the production values (3x3 for Landsat, 6 for Sentinel-2). The 1x1 values are
left in a comment. No net change.

#### Version and debug output

- `SR_VERSION` goes from `3.5.1.0` to `3.5.2.0`.
- `open_gb_oz_wv_datasets` always prints the acquisition time, file times and weights to stdout.
- Several commented-out `printf` lines and an unused `char xxxxxxxxxx[]` buffer
  ("need some kind of space ... on the cluster") are added.

## Using GDAS in lasrc-rs

### GDAS data on the NODD bucket

These notes come from spot checks of `s3://noaa-gfs-bdp-pds` (public, no credentials) on
2026-11-11 to 2026-11-13. They are not part of the upstream branch.

- Cycles run every 6 hours (00, 06, 12, 18 UTC). The 0-hour forecast is
  `gdas.tHHz.pgrb2.1p00.f000` (1 degree, 360 x 181). A 0.25 degree version (`0p25`) is also
  available.
- Each GRIB file has a matching `.idx` file listing the byte offset of every message. PWAT and
  TOZNE are about 100 KB each at 1 degree, so they can be fetched with two HTTP range requests
  instead of the whole 40 MB file.
- The key layout changes over time:

| Period (approximate) | Key |
|---|---|
| 2013 to early 2015 | `gdas.YYYYMMDD/HH/gdas1.tHHz.pgrbf00.grib2` |
| mid 2015 to 2017 | `gdas.YYYYMMDD/HH/gdas1.tHHz.pgrb2.1p00.f000` |
| 2017 to early 2021 | `gdas.YYYYMMDD/HH/gdas.tHHz.pgrb2.1p00.f000` |
| early 2021 onward | `gdas.YYYYMMDD/HH/atmos/gdas.tHHz.pgrb2.1p00.f000` |

- The parts of a key are:

| Part | Meaning |
|---|---|
| `gdas.YYYYMMDD/HH/` | Date and cycle hour (UTC) of the run |
| `atmos/` | Atmosphere component directory, added in early 2021 (other components such as `wave/` sit beside it) |
| `gdas1.` or `gdas.` | The GDAS run. `gdas1` is the older prefix for the same run |
| `tHHz` | Cycle time, `t00z`, `t06z`, `t12z` or `t18z` |
| `pgrb` | Post-processed fields on pressure levels, in GRIB. Despite the name it also holds single-level fields such as PWAT and TOZNE (level "entire atmosphere") |
| `pgrb2` | The same, in GRIB edition 2 |
| `1p00`, `0p25` | Grid spacing, 1.00 or 0.25 degree. The older `pgrbf00.grib2` files have no resolution tag and are 1 degree |
| `f00`, `f000` | Forecast hour 0, the "0-hour forecast" upstream uses. `f03`, `f06` and `f09` are later forecast hours from the same run |
| `anl` | The analysis. This is not what upstream uses |
| `.grib2` | GRIB edition 2. The newer keys drop the suffix (the `pgrb2` part says it) |
| `.idx` | Text inventory of the GRIB messages with byte offsets (wgrib2 format) |

- Other files in a cycle directory are not needed: `sfluxgrb` (surface fluxes), `bf`/`sf`,
  `atmf`/`sfcf` and `atmanl`/`sfcanl` (model state on native levels, NetCDF in newer years),
  `bufr_d`/`prepbufr` (observations), `abias`/`satang` (satellite bias corrections).
- The bucket goes back to 2006, so it covers the whole Landsat 8 and Sentinel-2 record. Years
  before 2013 were not checked for these files.
- The older `pgrbf00.grib2` files (checked for 2013-06-01) are the same 1 degree, 360 x 181 GRIB2
  grid, with PWAT and TOZNE at forecast hour 0. They have no `.idx` file, so the whole file
  (about 17 MB) has to be fetched.
- The GDAL GRIB driver bundled with the `rasterio` wheels reads these files. It shifts the grid to
  start at longitude -180 (correctly, unlike the C reader's off-by-one rotation). It exposes the
  times in band tags (`GRIB_REF_TIME`, `GRIB_VALID_TIME`, `GRIB_FORECAST_SECONDS`), along with
  `GRIB_ELEMENT` (`PWAT`, `TOZNE`) and `GRIB_UNIT`.

### Finding the files for a granule

A daily VIIRS or MODIS file has no single valid time. Each cell comes from an overpass at about
the same local solar time, so a granule only needs the file for its day. A GDAS cycle is the
reverse: one instant in UTC for the whole globe. A granule needs the two cycles that bracket its
UTC acquisition time:

```text
t      = acquisition time, UTC (from the scene metadata, see Processing below)
cycle1 = t floored to 00, 06, 12 or 18 UTC
cycle2 = cycle1 + 6 hours
```

- There is no longitude or local time adjustment. The UTC time already carries it.
- Build both keys from each cycle's own UTC date. `cycle2` is on the next day when `cycle1` is
  18Z. Near the date line the UTC date also differs from the local date, so never use the local
  date.
- A time exactly on a cycle gives that cycle a weight of 1 and the next a weight of 0. The second
  file is still required. This is rare enough to ignore.

The 0-hour files land on NODD about 7 hours after their cycle time (median 6.8 hours, 95% within
7.6, over a year of cycles, see the appendix). A granule is ready when `cycle2` lands:

```text
ready ~= cycle2 + 7 hours        (7 to 13 hours after acquisition)
```

The wait depends on where `t` falls within its 6 hour window. A granule imaged just after a cycle
waits about 13 hours, and one imaged just before a cycle waits about 7. Landsat and Sentinel-2
cross the equator at about 10:00 to 10:30 local time, so UTC time mostly follows longitude, and
the wait repeats roughly every 90 degrees of longitude. The local time also shifts with latitude
(about 20 minutes at 30 degrees and an hour at 60 degrees), so the boundaries between short and
long waits move with latitude too. Some examples, assuming 10:30 local and ignoring latitude:

| Granule | UTC time | Cycles | Ready about | Wait |
|---|---|---|---|---|
| Mexico City, 99W | 17:07 | 12Z, 18Z | 01:00 (next day) | ~8 hours |
| Washington, 77W | 15:38 | 12Z, 18Z | 01:00 (next day) | ~9.5 hours |
| Brasilia, 48W | 13:41 | 12Z, 18Z | 01:00 (next day) | ~11.5 hours |
| London, 0 | 10:30 | 06Z, 12Z | 19:00 | ~8.5 hours |
| Nairobi, 37E | 08:03 | 06Z, 12Z | 19:00 | ~11 hours |
| Tehran, 51E | 07:04 | 06Z, 12Z | 19:00 | ~12 hours |
| New Delhi, 77E | 05:21 | 00Z, 06Z | 13:00 | ~7.5 hours |
| Tokyo, 140E | 01:11 | 00Z, 06Z | 13:00 | ~12 hours |
| Canberra, 149E | 00:34 | 00Z, 06Z | 13:00 | ~12.5 hours |
| Wellington, 175E | 22:51 (previous day) | 18Z, 00Z | 07:00 | ~8 hours |

The wait drops from about 13 hours to about 7 where the UTC time crosses a cycle, near 112.5W,
22.5W, 67.5E and 157.5E, then grows again going east.

Later forecast hours of the same run land within minutes of its 0-hour file. On 2026-11-10,
the 00Z `f006` (valid at 06Z) landed at 07:08, while the 06Z `f000` landed at 12:47. Using the
previous cycle's 6 hour forecast for `cycle2` would cut the wait to about 1 to 7 hours. Upstream
does not do this. It assumes 0-hour files.

Finding the files happens twice, in two layers that know different things. The orchestration layer
decides when a granule can run, and knows only the granule ID. The processing layer picks the
files the result depends on, and has the scene metadata with the exact time.

#### Orchestration: triggering from the granule ID

The granule ID doesn't carry the acquisition time:

- A Landsat product ID has the UTC date and the WRS-2 path/row, but no time. The USGS SNS message
  for a new scene doesn't add one.
- A Sentinel-2 product name has the MGRS tile and the datatake start (section 4), not the tile's
  `SENSING_TIME`. The tile was imaged at or after the datatake start, never before.

So the orchestration layer estimates the time. Landsat 8/9 and Sentinel-2 are sun-synchronous, so
the UTC time at a point follows from the platform's inclination and descending node time, and the
latitude and longitude of the scene or tile center:

```text
u     = 180 - asin(sin(lat) / sin(inc))             # descending pass, argument of latitude
dra   = atan2(cos(inc) * sin(u), cos(u)) - 180      # wrapped to [-180, 180)
local = node_time + dra / 15                         # hours
utc   = local - lon / 15                             # hours, on the UTC date from the ID
```

| Platform | Inclination | Descending node time (nominal) |
|---|---|---|
| Landsat 8 | 98.2 | 10:00 (10:12 measured in 2019-2020) |
| Landsat 9 | 98.2 | 10:00 |
| Sentinel-2 | 98.62 | 10:30 |

Longitude alone is not enough. The latitude term shifts the local time by about 19 minutes at 30
degrees and 58 minutes at 60 degrees. Checked against two Landsat 8 scenes, with a node time of
10:12:

| Scene | Center | Actual UTC | Estimate | Longitude-only estimate |
|---|---|---|---|---|
| 027039, 2019-09-01 | 30.3N, 97.8W | 17:03:12 | 0.5 min early | 20 min early |
| 231089, 2020-08-07 | 41.8S, 70.2W | 14:23:41 | 0.6 min early | 29 min late |

The orchestration layer then:

1. Takes a window of the estimate plus or minus 30 minutes, clipped to the UTC date in the ID. For
   Sentinel-2 it also clips the start to the datatake start. The margin covers node time drift and
   the approximations. The estimate is not yet checked on Sentinel-2.
2. Lists every cycle the window touches. That is two cycles, or three when the window spans a
   cycle boundary (about 1 granule in 6).
3. Triggers the granule when the last of those cycles appears on NODD (an S3 event or polling),
   not after a fixed delay, since publishing times vary.

Waiting for all the cycles in the window is conservative. A granule whose window spans a boundary
waits up to 6 hours longer than it needs to, but the processing layer almost never has to retry.

The estimate is only a gate. It decides when to run, never which files the result uses.

#### Processing: using the exact time

The processing layer reads the exact UTC time from the scene metadata:

- Landsat: `DATE_ACQUIRED` plus `SCENE_CENTER_TIME` from the MTL.
- Sentinel-2: the tile's `SENSING_TIME` from `GRANULE/*/MTD_TL.xml`, not `PRODUCT_START_TIME` or
  the time in the product name.

From that time it computes `cycle1` and `cycle2` with the rule above, and finds or fetches those
two files itself. It doesn't take a file list from the orchestration layer, so a wrong estimate
can't select the wrong files. It checks each file's valid time from the GRIB metadata, and that the
two valid times bracket the acquisition time, before interpolating.

When the orchestration layer was wrong:

| Case | What happens |
|---|---|
| Triggered early: `cycle2` is not on NODD yet | Exit with code 75 (`EX_TEMPFAIL`) so the orchestration retries |
| Still missing well past the expected latency (for example 24 hours after `cycle2`) | Fail with a normal error, so a gap in the archive doesn't retry forever |
| Staged files that don't bracket the acquisition time | Ignore them and fetch the right pair, or fail with a clear error when fetching is off |

An estimate that is late only delays the granule. It can't change the result.

### Interpolating without index arithmetic

Every upstream interpolation bug in sections 2 and 3 (the one-column shift, sampling CMG cells at a
corner, the longitude seam, `float32` coordinate drift) comes from hand-written index arithmetic.
lasrc-rs doesn't port any of it. The GDAS data gets labeled with its real coordinates, in
`float64`, and `xarray` interpolates by label (`DataArray.interp`): linearly in time to the
acquisition time, then bilinearly in space to the CMG cell centers. That leaves two things to get
right:

- **The coordinates.** GDAS point `(k, l)` is at latitude `90 - k * d` and longitude
  `-180 + l * d`. GDAL reports these points as pixel centers (for the 1 degree grid, the
  geotransform origin is -180.5, 90.5), so the labels must be the pixel centers, not the corners.
  Using the corners shifts everything by half a grid step.
- **The seam.** `interp` doesn't wrap longitude, so append a copy of the -180 column at +180
  first.

### Appendix: latency, GDAS vs GFS

**GDAS cycles are slow by design.** GDAS waits about 6 hours after each cycle for late
observations before it runs. Its 0-hour file is published about 7 hours after the cycle. Hours
from cycle to the NODD `LastModified` time for the 1460 cycles from 2025-11-16 to 2026-11-15, with
none missing:

| `f000` file | Median | 95% | 99% | Max |
|---|---|---|---|---|
| GDAS 1p00 | 6.84 | 7.60 | 7.98 | 9.73 |
| GDAS 0p25 | 6.85 | 7.61 | 7.92 | 9.73 |
| GFS 1p00 | 3.56 | 3.80 | 3.83 | 7.46 |
| GFS 0p25 | 3.57 | 3.81 | 3.85 | 13.45 |

The GDAS 18Z cycle is the slowest (median 7.21, 95% within 7.85), and 12 of the 14 GDAS cycles over
8 hours were 18Z. The resolutions land together. `LastModified` is the time of the last write, so a
file that was rewritten shows the later time.

**A granule needs the later of its two cycles.** Interpolating to the acquisition time `t` needs
the cycles before and after `t`, so the inputs are ready at `cycle2 + 7 h`, 7 to 13 hours after
acquisition (median about 10). For Sentinel-2, whose L1C enters our bucket about 4.3 hours after
sensing (median, May to September 2026), that is 2.7 to 8.7 hours after entry.

**NODD adds almost nothing.** The NODD copies trail NOMADS (NCEP's own server) by about a minute.
The worst case seen was 46 minutes, once in 15 cycles. The NCEP FTP server publishes the same
files as NOMADS. There is no faster public source of GDAS.

**An earlier estimate appears incorrect.** A 2026 latency study of Sentinel-2 measured the wait
from bucket entry to the next GDAS 0-hour file to be published, whatever its cycle. That wait is
uniform over 0 to 6 hours, and the study's results match it (median about 3 hours, 90% of
granules published within 6 hours of entry). The measure isn't tied to the granule's cycles, and
most likely never looked for `cycle2` at all. With entry at about `t + 4.3 h` and files landing
at `cycle + 7 h`, the next file to land is `cycle1` for about 45% of granules and `cycle2` for
the rest, by coincidence. Waiting for `cycle2` every time, the median wait after entry is about
5.7 hours, and about 45% of granules are published within 6 hours of entry, not 90%. GDAS is
still far faster than VIIRS (about 39 hours from sensing to publish in the same study).

**GFS is the low-latency alternative.** GFS runs the same model on the same cycles with an early
observation cutoff (about 2h45m), and its 0-hour file has `PWAT` and `TOZNE` on the same grid,
published about 3.5 hours after the cycle (table above). It has fewer observations than GDAS.
Whether that matters for water vapor and ozone is for the science team, and it is a different input
from upstream.

| Input for `cycle2` | Ready after acquisition | Wait after Sentinel-2 entry (median) |
|---|---|---|
| GDAS `f000` (upstream) | 7 to 13 h | about 5.7 h |
| GFS `f000` | 3.5 to 9.5 h | about 2.2 h |
| GDAS `f006` from `cycle1` | 1 to 7 h | about 0 |
| GFS `f006` from `cycle1` | 0 to 3.6 h | about 0 |

GDAS and GFS share many of the same properties (NODD bucket, file formats, naming conventions)
so switching between them should not be very difficult, but will likely require rerunning
sensitivity analyses.
