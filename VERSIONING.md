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

- **Source of truth:** `[workspace.package] version` in the root `Cargo.toml`. Both crates inherit
  it.
  - The Release workflow creates the release tag `vX.Y.Z` from it (section 5).
  - The Python package version is read from `Cargo.toml` by maturin. It is exposed as
    `lasrc.__version__`, in the package metadata, and by the CLI's `--version`.
  - The Conda package version is derived from git tags by `scripts/version`. On a release tag it
    equals the `Cargo.toml` version.
- **Distribution:** releases are published only as a Conda package to the project's Conda channel.
  The crates and the Python package are not published to crates.io or PyPI.
- **Scheme:** [SemVer 2.0.0](https://semver.org/). Releases have no pre-release (`-...`) or
  build-metadata (`+...`) suffix, and the Release workflow rejects a version that is not `X.Y.Z`.
- **Development builds:** Conda builds of any commit that is not a release tag carry the last
  release tag plus the commit, `X.Y.Z+g<sha>`, with `.dirty` appended when the checkout has
  uncommitted changes. The Python package inside has the same version. Merges to `main` are
  published this way to the `dev` Conda channel once CI passes on them. Builds from pull requests
  are published there too, after a reviewer approves the `conda` environment deployment.
  Development builds of the same release do not sort in commit order, so install them by exact
  version. Local `uv sync` installs report the `Cargo.toml` version.

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
drawn from. This repo descends from the USGS C implementation at v3.5.1. `v3.5.1.0` is the
NASA-IMPACT C release that added fixes on top of v3.5.1, including masking a pixel if any band has
invalid data (see its `CHANGELOG.md` entry). The Rust port did not change outputs. Later changes
can come from either upstream, and neither follows a release schedule this project controls.

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
| Adopt logic from an upstream source | minor+ | bump (record provenance in CHANGELOG) |
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

Releases use [cargo-release](https://github.com/crate-ci/cargo-release) (`cargo install
cargo-release`), configured in `release.toml` and `lasrc_core/Cargo.toml`.

1. If the release could affect outputs (see section 2.3), run the golden-dataset validation and
   record the result.
2. If science changed since the previous release:
   - confirm `fork_rev` in `lasrc_core/ALGORITHM_VERSION` was bumped once (usually by the first
     science PR)
   - refresh the golden reference outputs
   - confirm the `[Unreleased]` CHANGELOG entry has a `### Science` section (section 6)
3. Review changes to the Python API, CLI, and output metadata since the previous tag and choose
   the version bump from section 4.
4. On a clean branch from `main`, run `cargo release <major|minor|patch>` to preview, then again
   with `--execute`. It sets the `Cargo.toml` version, updates `Cargo.lock`, adds a dated
   `## [X.Y.Z] - YYYY-MM-DD` heading below `## [Unreleased]` in the CHANGELOG, and commits.
5. Open a pull request and merge it to `main`.
6. Run the Release workflow (`.github/workflows/release.yml`) on `main` from the Actions tab or
   with `gh workflow run release.yml`. It checks that the version is not yet released and passes
   `scripts/check-versions`, and runs CI. A reviewer of the `conda` environment then approves the
   publish job, which publishes to the stable Conda channel. Only after all of that succeeds does
   it create the tag `vX.Y.Z` and a GitHub release. The release notes are
   the algorithm version followed by the CHANGELOG entry. If any step fails, fix it on `main`
   and run the workflow again.

---

## 6. CHANGELOG convention

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Changes go under
`## [Unreleased]`, in sections such as `### Added`, `### Changed`, and `### Fixed`, created as
needed.

When the algorithm version changes, the entry has a `### Science` section, before the other
sections. It states the new algorithm version, describes the changes, and links to the release's
validation results (e.g. a wiki page). Links to individual PRs are optional:

```markdown
## [1.4.0] - 2027-02-03

### Science

Algorithm version 3.5.1.1 (was 3.5.1.0). Validation: <link to results>

- Fix <bug> affecting <regime> (#123)
```

The `[v3.5.1.0]` entry predates this repo's package versions: it is the NASA-IMPACT C release, and
its version is the algorithm version.
