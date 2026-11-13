# Roadmap

Port verification is complete. The Rust code reproduces the C code's outputs, using type casts and
duplicate code paths that match C. These removed floating-point differences during verification, so
that logic bugs were easier to find. Now they make the code harder to read and to optimize.

The work ahead has four goals:

1. Remove what was added only for equivalence with C
2. Lower compute cost (see [`performance.md`](performance.md))

We have also discussed goals with much larger scope, including:

1. Process Sentinel-2 at 30 m, which is the resolution of the final product
2. Make the code general enough to support other sensors, possibly including commercial satellites

Separately, the auxiliary inputs are moving to documented, self-describing formats, with source
handling in a separate package (see [`plans/standardized-inputs.md`](plans/standardized-inputs.md)).

The first two goals should leave outputs effectively unchanged. The second set of goals change the
product on purpose and are tracked separately.

## How changes get accepted

Work through the cleanup and performance lists one change at a time:

1. Make one change
2. Verify the absolute mean reflectance difference is within the limit below
3. Accept the change and move to the next one

The methodology and acceptance criteria are in the
[validation wiki page](https://github.com/NASA-IMPACT/hls-project/wiki/Atmospheric-Correction-Validation).

The figures and tables from each verification round will be saved to the HLS project wiki
as part of documenting each release. Outputs may be deleted over time to save cost since
it's possible to regenerate them using older versions of the Docker container.

### Acceptance limit

The limit is an **absolute mean difference of less than 5 DN across all pixels** for each
reflectance band.

LaSRC writes reflectance as `uint16` with a scale factor of 0.0000275 (a multiplier of about
36,364), and the limit is in these units. A difference of 5 DN is 0.0001375 reflectance, or about
1.4 DN at the scale of 10,000 used by the HLS product. That rounds to 1 DN in the product's integer
output, which is how this limit relates to the wiki's 1 DN criterion.

The limit applies to reflectance only. Changes in `sr_aerosol` and `sr_aerosol_qa` have not been
evaluated as better or worse, so they are not part of acceptance.

### What each change is compared against

- **The previous release (incremental change).** This is the main comparison, and the limit applies
  to it.
- **The verified port baseline (cumulative change).** This shows how far outputs have moved in
  total, so that many small changes can't add up unnoticed.

### Localized changes

A mean can hide changes that matter, because a large change over a small area barely moves it. This
can happen in the aerosol retrieval, where a comment on `utm_to_deg` notes that a 1 ULP change can
flip a window's validity. The per-granule histograms and difference images described in the wiki
are how to catch this.

### Test scenes

The science team picked a validation dataset for this effort, "Belmanip2".
[Belmanip2](https://github.com/NASA-IMPACT/hls-project/wiki/Atmospheric-Correction-Validation#belmanip2)
is filtered to less than 30% cloud and more than 50% coverage, so it gives less coverage of failed
aerosol retrievals and fill edges. Keep this in mind for changes to that code, such as
`performance.md` items 5, 7, and 11.

### Full-granule check

The tripwire runs on small fixtures, and full validation takes hundreds of compute hours. Most
changes in this loop are expected to leave outputs unchanged, and for those a check on one full
granule would give an answer within the hour. That makes it the fastest way to check a change.

The check would run at least one Landsat granule on demand for a PR, and compare the reflectance
against the previous release's outputs with the 5 DN limit. It would report the per-band mean
differences in the PR. A Sentinel-2 granule could be added later, at about twice the pixels.

Passing this check is a reason to go ahead with a change, not a replacement for full validation
before release.

## 1. Remove C equivalence code

### Numeric casts

There are 30 `as f32 as f64` round trips, 25 of them in `correction.rs`. About 215 lines mention the
C code, most of them comments explaining a cast. Remove those comments along with the casts they
describe.

Choose one precision for each quantity. `f32` is the better default on hot paths, because it also
helps SIMD.

- [ ] `atmcorlamb2_new` and `eval_cubic`: `f32` values passed as `f64` and cast back on every call
- [ ] `subaeroret_new`: residual accumulation with mixed `f32` and `f64` rounding steps
- [ ] `compute_surface_reflectance`: the mixed-precision `rotoa` calculation and `clim_sr`
- [ ] `precompute_coefficients`: `f32` truncation of values stored as `f64`
- [ ] `lambda_sf`: rounded to `f32` in `atmcorlamb2_new` but `f64` in `atmcorlamb2`
- [ ] `XTV_STEP_C` alongside `XTV_STEP`
- [ ] `lup_decompose_f32` and `lup_solve_f32` in the polynomial fit
- [ ] `_dn_to_toa` in Python: `f32` arithmetic that matches C

### Duplicate paths

- [ ] **`utm_to_deg` and `utm_to_deg_gctp`.** Landsat windows use one and the scene center and
      Sentinel-2 windows use the other, only because C did. They differ by about 1e-7 degrees. Keep
      one. This is a good early test of the window validity flips described above.
- [ ] **`extract_atm_params`.** This is dead code (`#[allow(dead_code)]`) and can be deleted. Moving
      the scene center from nearest-cell to bilinear lookup would be a separate, science change.

## 2. Lower compute cost

[`performance.md`](performance.md) has the ranked list. The new acceptance limit relaxes its
constraints in a few ways:

- **Bit-for-bit output is no longer required.** Items marked Tolerance there are now ordinary
  changes in this loop, though they still go through full validation before release.
- **Removing casts helps performance.** Plain `f32` code vectorizes better, so the numeric cast
  cleanup (`performance.md` item 4) unlocks much of the AVX2 and final-loop SIMD work (items 2 and
  10), and it removes the casts' own cost.
- **Fast-math operations become an option.** `algebraic_add` and related functions, expected around
  Rust 1.98, allow the compiler to reorder floating-point math. They could let the `f32` sums and
  polynomial evaluations vectorize automatically. This needs a toolchain bump from the 1.96 pinned
  in `rust-toolchain.toml` and the matching floor in `conda/recipe.yaml`. Each use is a change to
  put through the loop above.

### Instance type

Production runs on memory-optimized instances (`r5d`, and likely `r6id` later). Fmask's memory use
may be what sets this, and separate work is reducing it. Once that work and the performance work
here are done, the balance of memory and CPU each job needs will have changed.

- [ ] Measure peak memory and core-seconds per scene for the whole job, for both sensors
- [ ] Compare memory-optimized (`r`), general-purpose (`m`), and compute-optimized (`c`)
      instances by cost per scene. `m6id` and `c6id` are the counterparts to `r6id` with local NVMe
      storage.
- [ ] Revisit the core count per job at the same time (`performance.md` item 13)

This is a job-level decision that goes beyond this repo, but the results here feed into it.

## 3. Likely bugs

These were kept for equivalence, and fixing them may exceed the 5 DN limit. All of them are in the C
code, and the Rust code reproduces them, so none is a port error. Any accepted output-changing fix
bumps the algorithm version (`VERSIONING.md` section 2.2).

The Fortran in `espa-surface-reflectance/lasrc/fortran_version` is the reference for intent. It has
the Sentinel-2 main program but not the Landsat one, and USGS has edited it, so it may not match the
algorithm author's current version.

### Also in the Fortran

These come from the algorithm's source and are not C port errors. Ask the algorithm author about
them before changing anything.

- [ ] **`eps` fit truncation ([#21](https://github.com/NASA-IMPACT/lasrc-rs/issues/21)).** `xd`
      truncates -3.1875 to -3, in both the Landsat and Sentinel-2 paths. This directly affects the
      fitted `eps`. It looks accidental: the Fortran declared `xd` as an integer alongside `yd`,
      `zone`, and `sphere`. The C code didn't truncate until 2020,
      when USGS changed it to match the Fortran (`6c66205`).
- [ ] **Sentinel-2 `eps` fallback check
      ([#22](https://github.com/NASA-IMPACT/lasrc-rs/issues/22)).** `resepsmin` evaluates the fit
      with its inputs (`xa`, `xb`, `xc`) instead of its coefficients, so the fallback to `eps1` or
      `eps3` effectively never runs. When the fitted curve opens downward, the retrieval keeps the
      `eps` with the highest fitted residual. The Landsat code has no such check.
- [ ] **Transmission grid.** `comptrans` picks an index into the `tts` table with the view grid for
      `xtv`, then interpolates using the table's solar angles. The Fortran does the same for both
      sensors.

### In C

- [ ] **Edge reads ([#13](https://github.com/NASA-IMPACT/lasrc-rs/issues/13)).** `aerosol_interp`
      reads past the end of a row or the buffer at the right and bottom edges. This doesn't happen
      in production, because Landsat scenes have a fill buffer, but input without one, such as a
      subset of a scene, would panic. Fixing it is a step toward supporting granule subsets, which
      may need other work too.
- [ ] **Fill mask ([#16](https://github.com/NASA-IMPACT/lasrc-rs/issues/16)).** `_fill_mask` marks a
      valid pixel as fill when its TOA is exactly 0. Since Sentinel-2 baseline 04.00 added its
      radiometric offset, this causes no-data speckle over very dark targets.
- [ ] **Sentinel-2 fill neighbors ([#15](https://github.com/NASA-IMPACT/lasrc-rs/issues/15)).**
      `aerosol_interp_sentinel` doesn't check whether the neighbors it reads are fill, and fill
      pixels hold AOT 0, which biases AOT low near fill edges. The Fortran doesn't check either, but
      it writes values to fill pixels where the C code skips them, so the two differ here.

Fixing these in the same release as the 30 m change would avoid asking the HLS project for more than
one reprocessing decision.

## 4. Sentinel-2 at 30 m and other sensors

LaSRC currently processes Sentinel-2 on a 10 m grid, and the result is later converted to 30 m. This
wastes work, since it is 9 times the pixels, but fixing it will likely change the product
significantly. It is therefore not a performance optimization. It needs an algorithm version bump,
likely a major package version, and a reprocessing decision (`VERSIONING.md` section 4).

Three configurations need to be supported, so this is also the time to generalize how input products
are described:

- Landsat at 30 m
- Sentinel-2 at 30 m
- Sentinel-2 at 10 m

### What ties the code to specific sensors today

- **Two scene orchestrators.** `compute_surface_reflectance` and
  `compute_sentinel_surface_reflectance` are about 750 lines each and largely parallel. Some
  differences are real algorithm choices, such as window placement, failed-window handling, and
  interpolation. Those should become explicit options, and the rest should merge.
- **Windows measured in pixels.** Values such as `HALF_FAILED_WIN`, `HALF_EXPAND_WIN`, and
  `SAERO_WINDOW` assume a resolution. They should be defined in meters or set per configuration.
  `Sensor::output_resolution_m` exists, but the correction code doesn't use it.
- **Fixed band indices.** The correction code uses `DNS_BAND*` and `SRL_BAND*` directly.
  `BandIndices` already provides band roles for part of this.
- **Sensor definitions in two places.** `lasrc_core/src/sensor.rs` and
  `lasrc_py/python/lasrc/sensors.py` must stay in sync by hand.
- **Input readers.** The SAFE and MTL readers are sensor-specific and return loosely typed dicts. A
  single input description could cover bands, resolutions, geometry, and fill.
- **Science inputs.** A new sensor needs more than configuration. It needs LUTs built for its
  spectral bands, and the band ratio climatology is defined for specific bands. This is probably
  what limits support for commercial sensors, and it deserves a look before committing to that goal.

### Tasks

- [ ] Merge the shared parts of the two orchestrators. This should pass the 5 DN check and can
      happen before any science change.
- [ ] Define an input product description and move the sensor definitions to one place
- [ ] Express windows independently of resolution, keeping today's values for current products
- [ ] Add Sentinel-2 at 30 m, and decide how to aggregate bands and where aerosol is retrieved
- [ ] Compare the results against the current 10 m to 30 m workflow with the HLS project

`performance.md` item 16 (native-resolution bands) belongs in this work too.

## Suggested order

1. Baseline and comparison tooling, since everything else depends on them
2. Cleanup and performance changes, one at a time through the loop. Do the highest-value performance
   items early, and do the cast cleanup in the code SIMD will touch before starting SIMD.
3. Orchestrator merge, which is easier once the casts and duplicate paths are gone
4. Sentinel-2 at 30 m and the input description, together with any accepted C bug fixes

Avoid large investments in Sentinel-2 10 m code that the 30 m work will replace, but keep in mind
that 10 m remains a supported configuration and that the same code will run at 30 m.
