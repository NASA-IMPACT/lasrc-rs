# Standardized inputs

Status: direction agreed 2026-11-13. The first piece is water vapor and ozone, with GDAS as a new
source.

## Goal

A wall between the processing code and its auxiliary inputs:

- **`lasrc_py` and the Rust core** read a small set of documented, self-describing files, in
  physical units, on fixed grids. They know nothing about where the data came from.
- **Producers** in a separate workspace member (`lasrc_inputs`, working name) find, download and
  convert real sources into those files.

Swapping an input then means writing a producer, with no change to `lasrc_py`.

## Why

- **HDF4.** `pyhdf` is the hardest dependency to install and maintain. It is pinned below 0.11.7
  because those wheels need macOS 26 or glibc 2.28 (`lasrc_py/pyproject.toml`, and a matching
  ignore in `.github/dependabot.yml`). Platforms without a wheel have to build against a system
  HDF4 library (`docs/usage.md`).
- **Source-specific code in the core.** The VIIRS water vapor and ozone scale factors and defaults
  live in the Rust core today. Moving to GDAS showed how much of that has to change for a new
  source.
- **Upstream reader bugs.** The upstream GDAS reader is off by one grid column, and its CMG
  sampling is off by half a cell (see [`gdas-support.md`](../gdas-support.md)). Both come from
  unstated grid conventions. A documented format states the convention once, and each conversion
  lives in one producer with its own tests.
- **Undocumented formats.** Today the format of each input is whatever the reader in
  `lasrc/aux.py` expects.

## Principles

- **One documented format per input**, in a single input formats doc (to be written with the
  first piece).
- **Self-describing files.** CF attributes for units, `standard_name`, packing (`scale_factor`,
  `add_offset`) and fill. The consumer checks them, never assumes them.
- **Physical values.** Algorithm choices, such as the water vapor halving, belong to the consumer,
  not the files.
- **Zipped Zarr** (single `.zarr.zip` file, Zarr format 3) for gridded and array inputs.
- **CMG grid** (0.05 degree, cell centered) for global gridded inputs. Subsets are allowed.
- **Lossless conversion** of existing inputs, so the C-comparison tests still pass.
- **Producers have minimal dependencies.** Anything the orchestration runs (lookups) uses only
  the standard library. Converters pull in heavier libraries as optional extras.

## Inputs

| Input | Today | Target | Status |
|---|---|---|---|
| Water vapor, ozone | `V*04ANC` HDF5 (VIIRS daily CMG) | standard file, CMG grid, from VIIRS or GDAS | in design |
| DEM | `CMGDEM.hdf` (HDF4) | standard file, CMG grid, documented so another DEM can be swapped in | next |
| Band ratio climatology | `ratiomapndwiexp.hdf` (HDF4) | standard file, CMG grid | next |
| Angle LUT | `ANGLE_NEW.hdf` (HDF4) | zipped Zarr | next |
| Intrinsic reflectance LUT | `RES_LUT_*.hdf` (HDF4) | zipped Zarr | next |
| Transmission, spherical albedo LUTs | `TRANS_LUT_*`, `AERO_LUT_*` (ASCII) | zipped Zarr | next |

Once the DEM, ratio climatology and HDF LUTs are converted, `pyhdf` leaves `lasrc_py`. The ASCII
LUTs don't need `pyhdf`, but they move too, so every input has one documented format.

## Long term: regenerating the LUTs

How the 6S LUTs were generated is not documented (6S version, atmosphere and aerosol models,
geometry and AOT grids, band responses). Work that out with the science team, and possibly
the algorithm author, then build tooling (for example with Py6S) that regenerates them in the
standard formats. The first test is reproducing the current LUTs within a tolerance the science
team accepts. After that, LUTs for new sensors or updated band responses become possible (see
section 4 of [`roadmap.md`](../roadmap.md)).
