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
a minor package bump, and a major bump if outputs are no longer comparable (see section 4), but the
reverse does not hold. The product version is decided by the HLS project and can change for reasons
outside this repo (other processing steps), so it is not tied to either version here (see section
3).

---

## 1. Package version (SemVer)

The Rust crates (`lasrc_core`, `lasrc_py`), the Python package (`lasrc`), and the Conda package
(`lasrc-rs`) share **one version** and are released in lockstep.

- **Source of truth:** the release tag `vX.Y.Z` of a published GitHub release (section 5).
  - `scripts/version` derives the version of a build from git tags. Conda builds use it for the
    Conda package and set the Python package version from it. It is exposed as
    `lasrc.__version__`, in the package metadata, and by the CLI's `--version`.
  - `[workspace.package] version` in the root `Cargo.toml` is a fixed placeholder, `0.0.0`.
- **Distribution:** releases are published only as a Conda package to the project's Conda channel.
  The crates and the Python package are not published to crates.io or PyPI.
- **Scheme:** [SemVer 2.0.0](https://semver.org/). Releases have no pre-release (`-...`) or
  build-metadata (`+...`) suffix, and CI rejects a release tag that is not `vX.Y.Z`.
- **Development builds:** Conda builds of any commit that is not a release tag carry the last
  release tag plus the commit, `X.Y.Z+g<sha>`, with `.dirty` appended when the checkout has
  uncommitted changes. The Python package inside has the same version. Merges to `main` are
  published this way to the `dev` Conda channel once CI passes on them. Builds from pull requests
  are published there too, after a reviewer approves the `conda` environment deployment.
  Development builds of the same release do not sort in commit order, so install them by exact
  version. Local `uv sync` installs report the `Cargo.toml` placeholder, `0.0.0`.

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

- `upstream` is the USGS C release this lineage forked from (`3.5.1`). It identifies the starting
  point and is not expected to change.
- `fork_rev` is our revision counter, starting at `0`. It increments by one per release that
  changes the algorithm, whichever upstream the change came from. Several algorithm changes in one
  release share a single bump.

**Lineage:** the algorithm is developed by its author in Fortran, which both USGS and HLS have
drawn from. This repo descends from the USGS C implementation at v3.5.1. [`v3.5.1.0`][v3510] is
the NASA-IMPACT C release that added fixes on top of v3.5.1, including masking a pixel if any band
has invalid data. The Rust port did not change outputs. Later changes can come from either
upstream, and neither follows a release schedule this project controls.

[v3510]: https://github.com/NASA-IMPACT/espa-surface-reflectance/tree/v3.5.1.0

The algorithm version is defined once, in the file `lasrc_core/ALGORITHM_VERSION`. Tools that do
not compile the code read that file directly. It is exposed as:

- `lasrc_core::ALGORITHM_VERSION` in Rust
- `lasrc.ALGORITHM_VERSION` in Python
- `LASRC_ALGORITHM_VERSION`, exported when the Conda environment is activated
- a field in every output's metadata

It is a domain value, not a package version, so it is kept apart from the package version in
`Cargo.toml`.

### 2.2 When to bump

> **The algorithm version bumps if and only if the same inputs (including ancillary data) produce
> different outputs (beyond tolerance), or the meaning of an output changes.**

Products sharing an algorithm version, given the same inputs, are comparable. See the decision table
in section 4 for how each kind of change affects the package version.

**Bump** for:

- Output-changing bug fixes, including edge cases (water, fill values, high solar zenith angle)
- Changes to static science data: aerosol LUTs, coefficients, ratio files
- Changes to the meaning of an existing QA bit, fill value, or scale factor
- A changed default for a science parameter (threshold, retrieval setting)
- Adopting logic from an upstream source (the algorithm author or USGS)

**Do not bump** for:

- Refactors, performance work, or dependency/toolchain updates with outputs within tolerance
- New output bands, or new QA bits in previously unused bit positions (existing outputs and bits
  keep their values and meaning)
- Packaging, build, or API changes
- Switching to an equivalent ancillary data source (section 2.4)

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

This doesn't replace full validation of new releases, but can signal that a release
needs more attention.

### 2.4 Ancillary data sources

Atmospheric ancillary inputs such as water vapor and ozone can come from more than one source, for
example GDAS, VIIRS, or MODIS. The algorithm version describes the algorithm, not the source of
its inputs. Adding a source, or switching between sources, does not bump the algorithm version
when the sources are equivalent. Equivalent means outputs made from each source agree within the
tolerance in section 2.3, as shown by validation against the golden dataset.

Instead, every output records which source supplied each ancillary input in its metadata, with
one field per input. For example, `ANCILLARY_WATER_VAPOR` is one of `GDAS`, `VIIRS`, or `MODIS`.
The algorithm version together with these fields identifies how a product was made.

A source that moves outputs beyond tolerance is not equivalent. Adopting it is a science change
that bumps the algorithm version (section 2.2).

---

## 3. Product / collection version

The product version (e.g. HLS v2.0) is owned by the HLS project, not this repo. Guidance for this
repo:

- An algorithm version bump is the **trigger for a reprocessing decision**. It does not force a
  product version bump on its own.
- Changes validated as within scientific noise at the product level stay within the current
  product version.
- Link the validation evidence for any such change from the release notes.

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
| Adopt logic from an upstream source | minor+ | bump (record provenance in release notes) |
| Changed meaning of an existing QA bit or fill value | major | bump |
| Changed default science parameter | major | bump |
| Outputs no longer comparable with earlier algorithm versions (e.g. moving off the semi-empirical path) | major | bump |
| Removing or renaming public API, a CLI option, or a metadata field | major | no |
| Adding a required parameter to a public function or CLI command | major | no |
| Remove an ancillary adapter | major | no |

"minor+" means minor at least. Use major if outputs are no longer comparable with earlier algorithm
versions. The HLS project still makes the reprocessing decision (section 3).

---

## 5. Release checklist

1. If the release could affect outputs (see section 2.3), run the golden-dataset validation and
   record the result.
2. If science changed since the previous release:
   - confirm `fork_rev` in `lasrc_core/ALGORITHM_VERSION` was bumped once (usually by the first
     science PR)
   - refresh the golden reference outputs
   - confirm the draft release notes have a `### Science` section (section 6)
3. Review changes to the Python API, CLI, and output metadata since the previous tag and choose
   the version from section 4.
4. Set the draft release's tag to `vX.Y.Z` on `main` and publish it. Only repository admins can
   create `v*` tags.
5. CI tests the tagged commit. A reviewer of the `conda` environment then approves the publish
   job, which publishes `X.Y.Z` to the stable Conda channel. If the job fails after the release
   is published, fix the cause and re-run the job.

### Maintenance releases

A patch release for an older minor version comes from a maintenance branch, `maint/vX.Y.x`:

- An admin creates `maint/vX.Y.x` from the `vX.Y.0` tag the first time a patch is needed. Branch
  rules match `main`: changes go through pull requests that pass CI.
- Fixes land on `main` first and are cherry-picked to `maint/vX.Y.x` in a pull request.
- The release is a GitHub release with tag `vX.Y.Z` targeting `maint/vX.Y.x`, following steps 3 to 5
  above. Its notes cover only the patch.
- A release runs the CI workflow from the tagged commit, so a maintenance branch follows the
  release process of the version it was cut from.
- Pushes to maintenance branches publish to the `dev` channel, like pushes to `main`. A dev build
  takes its version from the nearest tag on its own branch, so until `main` has a newer release,
  maintenance dev builds have higher versions than `main` dev builds. Install dev builds by exact
  version.

---

## 6. Release notes

The notes of each GitHub release are the changelog. They are written for users of the release,
so they describe what changed for them rather than listing commits or pull requests. Between
releases, a draft release collects notes as changes merge to `main`.

Notes start with the algorithm version, then sections such as `### Added`, `### Changed`, and
`### Fixed`, as needed. When the algorithm version changes, a `### Science` section comes first.
It describes the changes and links to the release's validation results (e.g. a wiki page). Links
to individual PRs are optional:

```markdown
**Algorithm version:** 3.5.1.1 (was 3.5.1.0)

### Science

Validation: <link to results>

- Fix <bug> affecting <regime> (#123)
```
