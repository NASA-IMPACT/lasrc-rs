# Performance roadmap

This is a record of the performance work done so far and a ranked list of what could come next. The
goal is lower compute cost per scene for HLS. It is one part of the wider [roadmap](roadmap.md),
which also defines how changes get accepted.

**The benefit and effort figures are ballparks.** They come from reading the code and counting
operations, not from profiling. Expect some to be wrong, and replace them with measurements as items
are picked up (see [item 0](#0-measure-first)).

## What matters

| | Sentinel-2 | Landsat |
|---|---|---|
| LaSRC share of job runtime | ~50% | ~33% |
| Job saving if LaSRC gets 10% faster | 5% | 3% |
| Job saving if LaSRC gets 25% faster | 12% | 8% |
| Job saving if LaSRC gets 50% faster | 25% | 16% |

- **CPU time is the target.** Fmask v5 runs in the same jobs and needs more memory than LaSRC, so it
  sets the job's memory floor. Using less memory in LaSRC does not reduce cost on its own.
- **Good core utilization does not mean the work is necessary.** Busy cores can still be doing
  redundant work. Most of the opportunities below reduce the work rather than spread it further.
- **Sentinel-2 has more to gain.** LaSRC is a larger share of its job, and it has the largest
  single hotspot.

The Rust code is already about 26% faster than the C code. The workflow is about 37% faster than
the C workflow because it needs no intermediate file conversions on input and output.

## Past work

| Commit | Change | Mainly helps |
|---|---|---|
| `eae7bfe`, `683d014`, `dab50f0`, `c762b35`, `c1ca74a` | Rayon for aerosol retrieval, final correction, and climatological SR | CPU (wall clock) |
| `5f1977a` | Parallelize pass 1 of `aero_avg_failed_sentinel` | CPU (wall clock) |
| `ab14271` | Landsat: parallel `aerosol_interp`, climatological SR on demand, borrow the QA band | CPU and memory |
| `34f2c95` | S2: climatological SR on demand instead of 13 full-scene bands (~6.3 GB) | Memory, some CPU |
| `78c9a42` | S2: scale to `u16` in the final loop, dropping the `f64` staging buffer (~12.5 GB) | Memory |
| `c1e1e1e` | Landsat: same change (~4 GB) | Memory |
| `a066315` | Pass NumPy arrays to PyO3 instead of Python lists (several GB) | Memory |
| `4b3efd0`, `083b7a8` | S2: borrow the QA band instead of copying it (~241 MB) | Memory |

Rayon spreads work across cores, which reduces wall clock but not total core-seconds. The memory
commits remove allocations and copies, but their main effect is on memory. So far, little has
reduced the amount of computation, and that is where this roadmap starts.

## Where the time probably goes

These are operation counts for a full scene with no fill pixels. Sentinel-2 is 10980 x 10980
(~120.6M pixels) and Landsat uses the 7771 x 7641 test scene (~59M pixels). The "core-seconds"
column multiplies the count by a guessed per-operation cost, so use it only for relative size.

| Step | Sensor | Count | Guessed core-seconds |
|---|---|---|---|
| `aero_avg_failed_sentinel` pass 1: 61 x 61 window per pixel | S2 | ~449B neighbor visits | 300-600 |
| Final correction: `atmcorlamb2_new` for 12 bands | S2 | ~1.45B calls | 50-100 |
| Aerosol retrieval: 6 x 6 windows, 1830 x 1830 | S2 | 3.35M windows, ~0.5-1B `atm_corr` calls | 20-50 |
| `aerosol_interp_sentinel`: 6 x 6 writes per pixel, **serial** | S2 | ~4.3B writes | 5-15 |
| Aerosol retrieval: 3 x 3 windows | Landsat | ~6.6M windows, ~1-2B `atm_corr` calls | 40-100 |
| Final correction: `atmcorlamb2_new` for 7 bands, plus `clim_sr` | Landsat | up to ~416M calls | 20-40 |

Input and output are not in this table and may matter just as much, especially JP2 decoding for
Sentinel-2. Item 0 settles this.

## Roadmap

Output risk uses these levels, based on `VERSIONING.md` section 2:

- **Identical:** outputs should match bit for bit. A byte comparison on a test scene is the check.
- **Tolerance:** bits may change, within the [acceptance
  limit](roadmap.md#how-changes-get-accepted). The change also needs golden-dataset validation
  before release. That costs hundreds of compute hours, so batch these changes into one validation
  run.
- **Science:** outputs change by design. This needs an algorithm version bump and a reprocessing
  decision from the HLS project.

Effort: **S** is hours to a day, **M** is days, and **L** is weeks. Benefit is the share of LaSRC
runtime saved, not job runtime.

| # | Item | S2 benefit | Landsat benefit | Effort | Output risk |
|---|---|---|---|---|---|
| 0 | Measure first | enables the rest | enables the rest | S | Identical |
| 1 | Release profile: LTO, one codegen unit | 0-10% | 0-10% | S | Identical expected |
| 2 | Build for `x86-64-v3` (AVX2) | 3-15% | 3-15% | S | Identical expected |
| 3 | Profile-guided optimization | 3-8% | 3-8% | M | Identical expected |
| 4 | Remove the casts that match C (unlocks items 2 and 10) | 1-5% alone | 1-5% alone | M | Tolerance |
| 5 | Run S2 averaging pass 1 only where needed | 20-60% | none | M | Identical |
| 6 | Tabulate retrieval `powf` and polynomials | 3-8% | 10-25% | S-M | Identical |
| 7 | Remove redundant writes in `aerosol_interp_sentinel` | 3-10% | none | M | Identical |
| 8 | Parallel band reads and writes, smaller ancillary reads | 5-20% | 2-10% | S-M | Identical |
| 9 | Reuse `powf` between neighboring pixels | 2-8% | ~0% | S | Identical |
| 10 | Band-major final loop, then SIMD | 5-20% | 5-20% | M-L | Identical to Tolerance |
| 11 | S2 sliding-window sums for heavily failed scenes | 0-30%, scene dependent | none | M | Tolerance |
| 12 | Cheaper `powf` with `exp` and a stored log | 1-5% | 3-10% | M | Tolerance |
| 13 | Tune cores per job | unknown, job-level | unknown, job-level | S-M | Identical |
| 14 | Remaining serial sections with Rayon | <5% | <5% | S-M | Identical |
| 15 | ARM (Graviton) builds | job-level price | job-level price | L | Tolerance |
| 16 | Native-resolution S2 band correction | 10-25% | none | L | Science |
| 17 | Process S2 at 30 m | 50-85% | none | L | Science |
| 18 | Skip retrieval on known clouds | 5-20% | 5-20% | L | Science |

The benefits overlap and do not add up. For example, once item 5 lands, every other S2 item is a
larger share of what remains.

**Suggested order:** do 0 first, then the build items (1-3), because they need no changes to the
algorithm code and they make every later measurement more realistic. Then do 4, which lets the AVX2
build and later SIMD work pay off. Then do 5 and 6, which are the largest changes that keep outputs
identical. Decide on 10 and later items using the new measurements. Items 16-18 each need a science
conversation rather than an engineering one, and items 16 and 17 are the only ones that could change
the cost by a large factor.

## Item notes

### 0. Measure first

Add per-step wall-clock timing covering input, ancillary loading, each Rust step, and output. Then
profile one clear and one cloudy scene per sensor using the existing `run_test_*.py` scripts with
`perf` or `samply`. Record the results in this file. There is no benchmark harness today, and a
heavy one is not needed.

### 1. Release profile

The workspace has no `[profile.release]`, so it uses Cargo's defaults. Try `lto = "fat"` and
`codegen-units = 1`. This is a few lines, costs some build time, and is worth trying first because
hot calls such as `atmcorlamb2_new` cross modules. Do not use `panic = "abort"`, because a Rust
panic should stay a Python exception.

### 2. Build for `x86-64-v3`

The Conda recipe builds for baseline x86-64 (SSE2). Setting `RUSTFLAGS="-C target-cpu=x86-64-v3"`
in `conda/recipe.yaml` allows AVX2 auto-vectorization. It should also inline `f32::round`, which
baseline x86-64 is expected to handle with a `roundf` library call (1.45B calls per S2 scene,
confirm in the disassembly).

- **Do not expect a large gain alone.** Most hot loops are not written in a form that vectorizes,
  and items 4 and 10 are what unlock that. `powf` also stays in libm, which already selects its own
  CPU variant at runtime.
- **Outputs should not change.** Rust does not fuse `a * b + c` into FMA unless `mul_add` is called,
  and it does not reorder floating-point sums. It is still a toolchain change that touches numerics,
  so include it in a validation run.
- **The current fleet supports it.** The binary crashes on CPUs without AVX2. Production runs on
  `r5d` (Intel Skylake-SP and Cascade Lake) and will likely add `r6id` (Intel Ice Lake). Both have
  AVX2, so `x86-64-v3` is safe. Recheck this if the fleet adds other instance families.
- **Leave `x86-64-v4` (AVX-512) for later.** Both instance families support it, but it gains little
  until items 4 and 10 make the hot loops vectorize. Skylake also lowers its clock speed under heavy
  AVX-512 use, so measure on `r5d` before adopting it. Ice Lake is much less affected. A v4 build
  would also rule out AMD and older Intel instances.

### 3. Profile-guided optimization

Rust supports this through `-C profile-generate` and `-C profile-use`. It would need a
representative profile and extra steps in the Conda build. The later items change the hot code, and
a profile loses its effect on code that has changed, so plan to refresh it as they land. Generating
it during the build from a small fixture scene avoids a stale profile, but it makes the build slower
and needs a scene available to the build.

### 4. Remove the casts that match C

The port rounds values through `f32` and `f64` to reproduce C's results, including 30
`as f32 as f64` round trips, 25 of them in `correction.rs`. The direct saving is small, but this is
what lets most of the SIMD work pay off. The checklist is in the
[roadmap](roadmap.md#1-remove-c-equivalence-code).

- **Vectorization.** The compiler can't optimize a round trip away, because it changes the value.
  An AVX2 register holds 8 `f32` values but only 4 `f64` values, so math in `f64` has half the
  lanes, and conversions between the two widths add instructions and can stop auto-vectorization.
  Without this item, items 2 and 10 gain less.
- **Direct cost.** Each cast is an extra instruction, and some sit on paths that run billions of
  times per scene, such as `atmcorlamb2_new` and `eval_cubic`.
- **Output risk.** Removing a cast changes rounding, so each group goes through the acceptance loop.
  Start with the casts on the hot paths.

### 5. Run S2 averaging pass 1 only where needed

Pass 1 of `aero_avg_failed_sentinel` averages a 61 x 61 window around every non-fill pixel, but only
FAILED pixels ever receive the result. Values at other pixels are read only by the pass 2 fill
loop, and that loop runs only if some pixel has too few valid neighbors.

1. Count valid neighbors for every pixel in O(1) with an integer summed-area table. Integer counts
   are exact, and they give the `smflag`, `one_filled`, and `nbpixnf` decisions without any sums.
2. Compute the `f32` sums, in the existing order, only for FAILED pixels and for pixels within 30
   pixels of one that pass 2 will fill.
3. Return immediately when a scene has no FAILED pixels, after handling the `one_filled` case.

The saving depends on the scene. `ipflag_expand_failed_sentinel` grows each failed window by 12
pixels on every side, so scenes with scattered failures can still mark a large area. This item also
drops two full-scene `f32` buffers.

### 6. Tabulate retrieval `powf` and polynomials

`subaeroret_new` calls `atmcorlamb2_new` for each band at each AOT step, and each call computes
`powf(-eps)` for a base that depends only on the band. Three of the four land retrievals use fixed
`eps` values (1.0, 1.75, 2.5), and water uses a fixed 1.5.

- For fixed `eps`, the scaled AOT at each grid step depends only on band and step. The `powf` result
  and all three cubic polynomials can be computed once per scene into a table, leaving the final
  division per window.
- For the per-window `epsmin` retrieval, compute `powf` once per band per call instead of once per
  step.
- Avoid copying the whole coefficient struct, which `atm_corr` does on every call. Item 4 covers
  the casts in `eval_cubic`, which also run on every call.

This matters most for Landsat, which has twice as many windows as Sentinel-2.

### 7. Remove redundant writes in `aerosol_interp_sentinel`

Like the C code, this function treats every pixel as a window corner and rewrites all 36 pixels of
its window, serially. Most of those writes are overwritten before anything reads them. From reading
the loop, an interior pixel away from fill needs only three of the writes: its own, the one to the
right, and the one below. That is about 12 times fewer.

Fill pixels change which write comes last, so windows near fill should keep the full loop. This
needs a test against a serial reference, like `test_aerosol_interp_matches_serial_scan` for Landsat.

The reads depend on earlier writes, so parallelizing it directly is not safe. Because it is serial,
it costs the same wall clock on any core count.

### 8. Input and output

- **Band reads:** `read_sentinel_safe` decodes 13 JP2 files one at a time. Try a thread pool, since
  rasterio releases the GIL during reads. Check how many threads GDAL already uses for each decode
  first, because nothing in this repo sets `GDAL_NUM_THREADS`.
- **Band writes:** `write_espa_output` writes files one at a time. It could write them in parallel,
  and its `astype` calls could use `copy=False`.
- **Ancillary grids:** every job reads 14 global 3600 x 7200 grids (~720 MB) but uses only the small
  area around one scene. Reading that subset would save a little time per job, though it needs care
  because the Rust code indexes the full grid.

### 9. Reuse `powf` between neighboring pixels

Sentinel-2 `teps` is not interpolated, so it is constant across each 6 x 6 window except at FAILED
pixels. In the final loop, keep the per-band `powf` results and recompute them only when `eps`
changes. That skips roughly 5 of every 6 calls. Landsat interpolates `teps`, so this does not help
it except over water.

### 10. Band-major final loop, then SIMD

The final loop visits one pixel at a time and all bands within it, which touches about 30 memory
locations per pixel and uses a bounds-checked `ndarray` lookup for each band. This blocks
vectorization.

1. Change it to row, then band, then sample, working on plain slices with per-row `raot`, `eps`, and
   fill arrays. This may give a gain by itself, and it is what makes step 2 possible.
2. Vectorize the polynomial evaluation, division, scaling, and rounding. Try auto-vectorization
   first. Consider the `wide` crate or `std::arch` intrinsics only if that falls short.

Each pixel is independent and nothing is summed across pixels, so vector lanes can give the same
bits if the operations stay the same. Two things limit this:

- `powf` has no bit-identical vector form (see item 12), so items 9 and 12 determine how much of the
  loop can vectorize.
- The casts that match C keep parts of this loop in `f64`, including Landsat's `rotoa` and the
  scaled AOT, which halves the lane count there. Item 4 removes this limit, so do it first.

Vectorizing the retrieval search is lower value. Its loop exits early per window and is hard to
vectorize, and item 6 removes much of its cost.

### 11. S2 sliding-window sums

Item 5 does not help scenes where most pixels are FAILED. A running sum, updated as the window
moves, would make the cost O(1) per pixel regardless of window size. This does not reproduce the
current `f32` rounding, so it needs validation. Do this only if measurements show heavily failed
scenes are common.

### 12. Cheaper `powf`

With `ln(base)` stored per band, `base^-eps` becomes `exp(-eps * ln_base)`, which is cheaper and has
vector implementations. After truncation to `f32`, results should nearly always match, but not
always. Landsat benefits most because its `eps` changes at every pixel.

### 13. Tune cores per job

Cost scales with cores times runtime, so high utilization alone does not show the core count is
right. Run the same scene at several `--num-threads` values and compute core-seconds at each. Also
compare physical cores against hyperthreads. If parallel efficiency falls off, a smaller job could
be cheaper per scene, as long as Fmask's memory floor can still be met. This takes no code and can
be done at any time, but item 5 and item 7 will change the answer.

The core count may also be a side effect of memory. `r5d` and `r6id` are memory-optimized, with 8
GiB per vCPU, so a job sized for Fmask's memory gets the cores that come with it. Once the
performance work here and the Fmask memory work are done, reevaluate the instance family as well as
the core count (see the [roadmap](roadmap.md#2-lower-compute-cost)).

### 14. Remaining serial sections

These still run serially: `aerosol_interp_sentinel`, `ipflag_expand_failed_sentinel`, the result
scatter after retrieval, `fix_invalid_aerosols`, and the `aero_avg_failed_sentinel` copy-back and
pass 2. Most are cheap or depend on scan order. Since utilization is already good, expect little
except from `aerosol_interp_sentinel`, which item 7 addresses. Revisit if item 0 shows otherwise.

### 15. ARM builds

Graviton instances are often cheaper for the same throughput. `r6gd` is the Graviton counterpart
to `r6id`, with local NVMe storage. The Conda workflow publishes only `linux-64`. This depends on the whole job, including Fmask and the other HLS steps, and a different
libm and CPU would need validation. It is a job-level decision that goes beyond this repo.

### 16-18. Science-changing options

These change outputs and need the HLS project's agreement, so they are not pure performance work.
Items 16 and 17 could save far more than the engineering items, and they are part of
[Sentinel-2 at 30 m and other sensors](roadmap.md#4-sentinel-2-at-30-m-and-other-sensors) in the
roadmap.

- **16. Native-resolution S2 bands.** Only 4 of 13 bands are natively 10 m. 20 m and 60 m bands are
  replicated to 10 m and corrected per 10 m pixel. Correcting at native resolution cuts band-pixel
  evaluations in the final loop from ~1.45B to ~0.67B. This assumes aerosol can be sampled or
  averaged onto the coarser grid.
- **17. Process S2 at 30 m.** The HLS product is 30 m, but LaSRC runs on a 10 m grid, which is 9
  times the pixels, and the output is later converted to 30 m. This is the largest "do less work"
  option. The trade-off is correcting then aggregating versus aggregating then correcting, which
  will likely change the product significantly.
- **18. Skip retrieval on known clouds.** Windows under cloud are retrieved and often fail, and the
  S2 failure handling adds more work. Fmask runs in the same job, so its mask could skip them, but
  this needs Fmask to run first. Older upstream commits such as `b0d6a7d` suggest a similar idea and
  have not been reviewed.

## Ideas considered and set aside

- **Replacing the allocator, or removing per-window `Vec`s.** There are tens of millions of small
  allocations per scene, which is about a second of CPU. Worth removing as tidy-up when touching
  that code, but not worth its own project.
- **More memory reduction.** It does not lower cost while Fmask sets the memory floor.
