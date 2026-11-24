# lasrc-rs

Rust port of the Land Surface Reflectance Code (LaSRC) algorithm created by
[Vermote et al (2018)][vermote2018] and initially developed in C by the USGS ESPA team at EROS (see
[espa-surface-reflectance][espa-sr]).

## Documentation

- [Usage](docs/usage.md) - getting the ancillary data, installing, and running LaSRC from the CLI
  or Python
- [LaSRC's semi-empirical code path](docs/lasrc-semi-empirical-code-path.md) - a ~10 minute tour
  of how LaSRC turns TOA reflectance into surface reflectance on the default path used by NASA HLS
- [Glossary](docs/GLOSSARY.md) - what the terse variable names carried over from the C code
  (`roatm`, `xmus`, `erelc`, ...) mean
- [Roadmap](docs/roadmap.md) - planned cleanup, performance, and science work, and how changes get
  accepted
- [Performance roadmap](docs/performance.md) - past optimizations and a ranked list of future ones

## Developer getting started

This repo contains a Rust port of LaSRC with Python bindings:

| Path               | What it is                                                                     |
|--------------------|--------------------------------------------------------------------------------|
| `lasrc_core/`      | Pure Rust LaSRC algorithms (no Python)                                         |
| `lasrc_py/`        | PyO3 bindings + Python package `lasrc` |
| `lasrc_ancillary/` | Python package `lasrc_ancillary`: finds, fetches and converts ancillary inputs (GDAS) |

### Prerequisites

- [rustup](https://rustup.rs/) - Rust toolchain manager.
  - The toolchain version and components are pinned in `rust-toolchain.toml`
  - Run `rustup install` from the repo root to install dependencies.
- [uv](https://docs.astral.sh/uv/) - Python version, virtualenv, and package management

### Set up the environment

From the repo root:

```bash
# Create .venv (Python version from .python-version), build + install the `lasrc` package
# (editable), and install the dev tools
uv sync
```

`uv run` keeps the environment in sync before running a command, including rebuilding the Rust
extension (release profile) when sources in `lasrc_core/` or `lasrc_py/src/` change. Avoid
`maturin develop`: the next `uv run` replaces whatever it installed. To force a rebuild:

```bash
uv sync --reinstall-package lasrc
```

### Run the tests

```bash
scripts/test                 # cargo test --workspace, then pytest lasrc_py lasrc_ancillary
scripts/test rust            # Rust tests only
scripts/test python          # Python tests only
scripts/test -k geometry     # extra arguments are passed to pytest
```

### Lint, format, and type check

```bash
scripts/format         # apply cargo fmt + ruff format, and ruff auto-fixes, in place
scripts/lint           # check-only: cargo fmt --check, clippy -D warnings, ruff
scripts/lint rust      # Rust checks only
scripts/lint python    # Python checks only
scripts/typecheck      # mypy on lasrc_py/python and lasrc_ancillary/src, stubtest on the extension stub
```

CI (`.github/workflows/ci.yml`) runs these same scripts in separate `rust` and `python` jobs, and
builds and publishes the Conda package once they pass.

### Make a release

Releases are GitHub releases. The tag `vX.Y.Z` sets the version, and the release notes are the
changelog. See [VERSIONING.md](VERSIONING.md) section 4 to choose the version and section 5 for
the full checklist, including validation.

1. Keep a draft release up to date as changes merge to `main`. Its notes are the changelog for
   the next release (VERSIONING.md section 6).
2. To release, set the draft's tag to `vX.Y.Z` on `main` and publish it.
3. CI tests that commit. A reviewer of the `conda` environment then approves the publish job,
   which publishes `X.Y.Z` to the stable Conda channel. If the job fails after the release is
   published, fix the cause and re-run the job.

## References

Vermote, E., Roger, J. C., Franch, B., & Skakun, S. (2018). LaSRC (Land Surface Reflectance Code):
Overview, application and validation using MODIS, VIIRS, LANDSAT and Sentinel 2 data's. In
*IGARSS 2018 - 2018 IEEE International Geoscience and Remote Sensing Symposium* (pp. 8173-8176).
Valencia, Spain. <https://doi.org/10.1109/IGARSS.2018.8517622> (NASA NTRS Document ID: 20190001670,
<https://ntrs.nasa.gov/citations/20190001670>)

[espa-sr]: https://github.com/NASA-IMPACT/espa-surface-reflectance/
[vermote2018]: #references
