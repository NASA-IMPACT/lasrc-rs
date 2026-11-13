# GDAS ancillary support in the upstream C code

This page describes what the algorithm author's `eros-collection2-3.5.2` branch of
`espa-surface-reflectance` changes, relative to the `eros-collection2-3.5.1` release
(`6051e02`). The main change is support for NOAA GDAS GRIB files as the source of water vapor and
ozone, in place of the daily VIIRS (`V*04ANC`) or MODIS (`L8ANC`) CMG files.

The branch has no description of its own. Everything here comes from reading the diff.

## Commits

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

## Summary of changes

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

## 1. GRIB input path

### Command line

`lasrc` gains an optional `--aux2` argument. The usage example is:

```shell
lasrc --xml=LC08_L1TP_078014_20220306_20220314_02_T1.xml \
    --aux=gdas1.PGrbF00.220306.18z --aux2=gdas1.PGrbF00.220307.00z --verbose
```

`--aux2` is only used when `--aux` is a GRIB file. For VIIRS and MODIS it is ignored.

### Detecting the source

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

### GDAS Variables

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

### Scaling to DN

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

## 2. Temporal interpolation

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

## 3. Spatial interpolation

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

## 4. Sentinel-2 acquisition time

The GDAS path needs the time of day. Landsat already had it (`scene_center_time` in the ESPA XML).
For Sentinel-2 the ESPA XML has no time, and the old code set it to `T00:00:00`.

The new `ad_hoc_XML_reader.c` reads `<PRODUCT_START_TIME>` from the `<Product_Info>` block of
`MTD_MSIL1C.xml`. It opens that file by name in the current working directory, and exits the
process if it isn't there. The comment says it is meant to be thrown away once the ESPA
product formatter reads the time itself.

`PRODUCT_START_TIME` is not the tile's time. In single-tile products, `PRODUCT_START_TIME`,
`PRODUCT_STOP_TIME` and `DATATAKE_SENSING_START` are all the start of the datatake. In
`S2B_MSIL1C_20260124T073109_N0511_R049_T38PNC_20260124T092241` all three are 07:31:09.024, and the
tile's `SENSING_TIME` in `GRANULE/*/MTD_TL.xml` is 07:45:13.375, 14 minutes later.

## 5. Changes not related to GDAS

### Output reflectance scaling

`output.h` changes the surface reflectance scale factor and offset:

| | Before | After |
|---|---|---|
| `SCALE_FACTOR_REFL` | 0.0000275 | 0.0001 |
| `OFFSET_REFL` | -0.20 | 0.0 |

These feed both the XML metadata and the integer conversion of the output bands
(`MULT_FACTOR_REFL = 1 / SCALE_FACTOR_REFL`, `BAND_OFFSET_REFL = -OFFSET_REFL`), so the stored
values change for Landsat and Sentinel-2. lasrc-rs still uses the Collection 2 values
(`lasrc_core/src/constants.rs`).

### Sentinel-2 fill mask fix

In `compute_sentinel_refl.c`, the fill check in the per-pixel auxiliary interpolation loop used the
line index instead of the pixel index:

```c
if (level1_qa_is_fill (qaband[i]))          /* before */
if (level1_qa_is_fill (qaband[curr_pix]))   /* after */
```

That loop only runs for the original aerosol algorithm (`--use_orig_aero_alg`), which lasrc-rs
does not port.

### Aerosol window

`a64c9cf` changed the aerosol retrieval window to 1x1 (`LAERO_WINDOW 1`, `SAERO_WINDOW 1`).
`b271310` restored the production values (3x3 for Landsat, 6 for Sentinel-2). The 1x1 values are
left in a comment. No net change.

### Version and debug output

- `SR_VERSION` goes from `3.5.1.0` to `3.5.2.0`.
- `open_gb_oz_wv_datasets` always prints the acquisition time, file times and weights to stdout.
- Several commented-out `printf` lines and an unused `char xxxxxxxxxx[]` buffer
  ("need some kind of space ... on the cluster") are added.

## GDAS data on the NODD bucket

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
t      = acquisition time, UTC (Landsat DATE_ACQUIRED + SCENE_CENTER_TIME, Sentinel-2 SENSING_TIME)
cycle1 = t floored to 00, 06, 12 or 18 UTC
cycle2 = cycle1 + 6 hours
```

- There is no longitude or local time adjustment. The UTC time already carries it.
- Build both keys from each cycle's own UTC date. `cycle2` is on the next day when `cycle1` is
  18Z. Near the date line the UTC date also differs from the local date, so never use the local
  date.
- A time exactly on a cycle gives that cycle a weight of 1 and the next a weight of 0. The second
  file is still required. This is rare enough to ignore.

The 0-hour files land on NODD about 7 hours after their cycle time. A check of 2026-11-10 and
2026-11-11 gave 6.8 to 7.4 hours for every cycle, for both 1 degree and 0.25 degree. A granule is
ready when `cycle2` lands:

```text
ready ~= cycle2 + 7 hours        (7 to 13 hours after acquisition)
```

The wait depends on where `t` falls within its 6 hour window. A granule imaged just after a cycle
waits about 13 hours, and one imaged just before a cycle waits about 7. Landsat and Sentinel-2
cross the equator at about 10:00 to 10:30 local time, so UTC time mostly follows longitude, and
the wait repeats roughly every 90 degrees of longitude. The local time also shifts with latitude
(about 20 minutes at 30 degrees and an hour at 60 degrees), so the boundaries between short and
long waits move with latitude too. Two examples, assuming 10:30 local:

| Granule | UTC time | Cycles | Ready about | Wait |
|---|---|---|---|---|
| Hawaii, 158W | 21:01 | 18Z, 00Z (next day) | 07:00 | ~10 hours |
| Japan, 140E | 01:11 | 00Z, 06Z | 13:00 | ~12 hours |

A dependency solver should trigger on the `cycle2` file appearing (an S3 event or polling), not
on a fixed delay, since publishing times vary.

Later forecast hours of the same run land within minutes of its 0-hour file. In the same check,
the 00Z `f006` (valid at 06Z) landed at 07:08, while the 06Z `f000` landed at 12:47. Using the
previous cycle's 6 hour forecast for `cycle2` would cut the wait to about 1 to 7 hours. Upstream
does not do this. It assumes 0-hour files.
