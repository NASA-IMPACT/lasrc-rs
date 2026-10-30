# Versioning

`lasrc-rs` has two versions of its own: the package version and the algorithm version. The table
below also describes the HLS product's Collection version as a related example. Each version answers
a different question for a different audience.

| Version | Example | Answers | Audience | Owned by |
|---|---|---|---|---|
| **Package** | `lasrc-rs` 1.4.0 | Will my code and scripts still build and run? | Developers, operators | This repo |
| **Algorithm Specification** | `v3.5.1.0` | Do the same inputs give equivalent outputs (within tolerance)? | Science users, provenance | This repo |
| **Product / collection** | HLS v2.0 | Are products scientifically comparable, or do we reprocess? | Science users | HLS project |

Tracking two versions for this software is more complicated than just one, but in our case it's
important to make a distinction between the algorithmic intent and the implementation itself. The
LaSRC algorithm was originally developed in Fortran, was ported to C by the USGS, and now has been
ported to Rust by the HLS team. It therefore has its own history independent of any one language.
Changes to the algorithm logic are done intentionally, and divergence among the versions of the
algorithm are evaluated by comparison testing on representative samples of data.

The versions are related to one another. A scientific algorithm specification bump implies at least
a minor package bump, but the reverse does not hold. The product version is decided by the HLS
project and can change for reasons outside this repo (other processing steps), so it is not tied to
either version here (see section 3).

---

## 1. Package version (SemVer)

The Rust crates (`lasrc_core`, `lasrc_py`), the Python package (`lasrc`), and the Conda package
(`lasrc-rs`) share **one version** and are released in lockstep.

- **Source of truth:** the release tag `vX.Y.Z`.
  - `[workspace.package] version` in the root `Cargo.toml` must match the tag (CI rejects a
    mismatch). Both crates inherit it.
  - The Python package version is read from `Cargo.toml` by maturin.
  - The Conda package version is derived from the git tag by `scripts/conda-build`.
- **Distribution:** releases are published only as a Conda package to the project's Conda channel.
  The crates and the Python package are not published to crates.io or PyPI.
- **Scheme:** [SemVer 2.0.0](https://semver.org/). No pre-release (`-...`) or build-metadata
  (`+...`) suffixes on releases because Cargo, PEP 440, and Conda handle them inconsistently. Builds
  published to the `dev` Conda channel from pull requests are not releases and carry a
  `X.Y.Z.postN+g<sha>` version.

### Public API

These are covered by SemVer:

- The `lasrc` Python API and its type stubs
- The CLI: the `lasrc-landsat` and `lasrc-sentinel` commands, their options, and exit codes
- The output metadata schema. Adding fields is a minor change. Renaming or removing them is a
  major change.
- Output behavior within the tolerance defined in section 2.3

The Rust crates are internal to this repo and have no direct consumers. Their Rust API is not
covered and can change in any release.

### Bump rules

See the decision table in section 4, which covers both the package and the algorithm version.

---

## 2. Algorithm version

### 2.1 Format

```text
{upstream}.{fork_rev}
```

- `upstream` is the USGS release this lineage forked from (e.g. `3.5.1`).
- `fork_rev` is our revision counter, starting at `0`. It increments by one per release that
  changes the algorithm. Several algorithm changes in one release share a single bump.

The current algorithm version is the one in the newest release entry of `CHANGELOG.md`.

**Lineage:** forked from the USGS C implementation at v3.5.1. USGS has since continued development
privately. `v3.5.1.0` is the NASA-IMPACT C release that added fixes on top of v3.5.1, including
masking a pixel if any band has invalid data (see its `CHANGELOG.md` entry). The Rust port did not
change outputs.

The algorithm version is defined once in `lasrc_core` as `lasrc_core::ALGORITHM_VERSION`. It is
exposed as:

- `lasrc.ALGORITHM_VERSION` in Python
- `LASRC_ALGORITHM_VERSION`, exported when the Conda environment is activated
- a field in every output's metadata

It is a domain value, not a package version: it never appears in `Cargo.toml` or `pyproject.toml`.

### 2.2 When to bump

> **The algorithm version bumps if and only if the same inputs (including ancillary data) produce
> different outputs (beyond tolerance), or the meaning of an output changes.**

Products sharing an algorithm version, given the same inputs, are comparable.

**Bump** for:

- Output-changing bug fixes, including edge cases (water, fill values, high solar zenith angle)
- Changes to static science data: aerosol LUTs, coefficients, ratio files
- Changes to the meaning of an existing QA bit, fill value, or scale factor
- A changed default for a science parameter (threshold, retrieval setting)
- Adopting logic from a newer upstream USGS release

**Do not bump** for:

- Refactors, performance work, or dependency/toolchain updates with outputs within tolerance
- New output bands, or new QA bits in previously unused bit positions (existing outputs and bits
  keep their values and meaning)
- Packaging, build, or API changes

### 2.3 Tolerance and the golden dataset

Whether outputs "changed" is decided by validation against the golden dataset, not by judgment. The
dataset, tolerances, and validation procedure are described in the project wiki:
<https://github.com/NASA-IMPACT/hls-project/wiki/Atmospheric-Correction-Validation>.

Full validation is expensive (~hundreds of compute hours), so it is **not run in CI**. It is run
manually before any release that could affect outputs, including:

- changes to core algorithm code
- changes to static science data
- dependency or toolchain updates that touch numerics
- performance work that reorders floating-point operations (SIMD, parallel reductions, FMA)

Releases that cannot affect outputs, such as packaging, docs, or pure API additions, do not require
a validation run.

Floating-point reordering can change bits without changing the science. The tolerance exists for
that. If a change moves outputs beyond tolerance and is intended, bump the algorithm version and
refresh the golden reference outputs as part of that release.

A fast tripwire runs in CI against small fixture scenes, using the same tolerances:

- Landsat on every PR
- Sentinel-2 on PRs touching S2 or shared code

A tripwire failure does not replace full validation. It signals that a release needs it.

---

## 3. Product / collection version

The product version (e.g. HLS v2.0) is owned by the HLS project, not this repo. Guidance for this
repo:

- An algorithm version bump is the **trigger for a reprocessing decision**. It does not force a
  product version bump on its own.
- Changes validated as within scientific noise at the product level (e.g. VIIRS -> GDAS ancillary
  data) stay within the current product version.
- Link the validation evidence for any such change from the CHANGELOG.

---

## 4. Decision table

| Scenario | Package | Algorithm |
|---|---|---|
| Bug fix or performance refactor, outputs within tolerance | patch | no |
| Toolchain/dependency bump, outputs within tolerance | patch | no |
| New feature, optional parameter, or output metadata field | minor | no |
| New optional output band or QA bit | minor | no |
| New ancillary adapter (e.g. GDAS), opt-in | minor | no |
| New ancillary adapter becomes default, validated within noise | minor | no |
| Dropping a Python version | minor | no |
| Output-changing bug fix | minor+ | bump |
| Updated LUTs or coefficients | minor+ | bump |
| Cherry-pick logic from a newer USGS release | minor+ | bump (record provenance in CHANGELOG) |
| Changed meaning of an existing QA bit or fill value | major | bump |
| Changed default science parameter | major | bump |
| Removing or renaming public API, a CLI option, or a metadata field | major | no |
| Adding a required parameter to a public function or CLI command | major | no |
| Remove an ancillary adapter | major | no |

"minor+" means minor at least. Use major if downstream users are expected to reprocess.

---

## 5. Release checklist

1. Bump `[workspace.package] version` in `Cargo.toml` and update `Cargo.lock`
   (`cargo update --workspace`).
2. If the release could affect outputs (see section 2.3), run the golden-dataset validation and
   record the result.
3. If science changed since the previous release:
   - confirm `fork_rev` in `lasrc_core::ALGORITHM_VERSION` was bumped once (usually by the first
     science PR)
   - refresh the golden reference outputs
   - add a `### Science` section to the CHANGELOG entry (section 6)
4. Review changes to the Python API, CLI, and output metadata since the previous tag and confirm the
   bump matches section 4.
5. Run `scripts/test`, `scripts/typecheck`, and `scripts/check-versions`.
6. Move the `[Unreleased]` CHANGELOG entries into the new release entry (section 6), including:
   - the `**Algorithm version:**` line
   - whether validation was run, with a link to the results.

   Then start a new, empty `[Unreleased]` entry that keeps the `**Algorithm version:**` line.
7. Merge to `main`, then tag `vX.Y.Z` on that commit and push the tag. The Conda workflow checks the
   tag against `Cargo.toml` and publishes to the stable channel.

---

## 6. CHANGELOG convention

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and is the record of
algorithm version history. Every release entry states its algorithm version below the release date:

```markdown
## [1.3.0]

Release Date: November 12, 2026

**Algorithm version:** 3.5.1.0 (unchanged)

### Added

- GDAS ancillary adapter as the default. Validated within noise against VIIRS: <link>
```

When the algorithm version changes, the entry has a `### Science` section, before the other
sections, describing the changes and linking to the release's validation results (e.g. a wiki
page). Links to individual PRs are optional:

```markdown
## [1.4.0]

Release Date: February 3, 2027

**Algorithm version:** 3.5.1.1 (was 3.5.1.0)

### Science

Validation: <link to results>

- Fix <bug> affecting <regime> (#123)
```

The `[v3.5.1.0]` entry predates this repo's package versions: it is the NASA-IMPACT C release, and
its version is the algorithm version. Package release entries start at `[1.0.0]`.

The `[Unreleased]` entry also states the algorithm version, so a change to
`lasrc_core::ALGORITHM_VERSION` updates the CHANGELOG in the same PR. CI (`scripts/check-versions`)
checks that the `**Algorithm version:**` line of the top entry matches
`lasrc_core::ALGORITHM_VERSION`.
