# lasrc-rs

Rust port of the Land Surface Reflectance Code (LaSRC) algorithm created by Vermote et al (2018)
and initially developed in C by the USGS ESPA team at EROS (see [espa-surface-reflectance][espa-sr]).

## Developer getting started

This repo contains a Rust port of LaSRC with Python bindings:

| Path               | What it is                                                                     |
|--------------------|--------------------------------------------------------------------------------|
| `lasrc_core/`      | Pure Rust LaSRC algorithms (no Python)                                         |
| `lasrc_py/`        | PyO3 bindings + Python package `lasrc` (I/O, CLI: `lasrc-landsat`, `lasrc-sentinel`) |
| `lasrc_cref/`      | C-vs-Rust differential test harness (separate Cargo workspace)                 |

### Prerequisites

Required:

- [rustup](https://rustup.rs/) - installs the stable Rust toolchain (`cargo`, `rustfmt`, `clippy`)
- [uv](https://docs.astral.sh/uv/) - Python version, virtualenv, and package management

Optional (only for `lasrc_cref` stage 1+ tests, which compile C code against the ESPA/HDF
libraries):

- [pixi](https://pixi.sh/) on linux-64, **or** Docker on macOS (the conda C packages are linux-64
  only)
- AWS credentials that can read the private `s3://hls-conda-channels` conda channel

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
scripts/test                 # cargo test --workspace, then pytest lasrc_py
scripts/test -k geometry     # extra arguments are passed to pytest
```

`lasrc_cref` is a separate Cargo workspace and is not run by `scripts/test`:

```bash
# C-vs-Rust differential tests, stage 0 (no conda needed)
cargo test --manifest-path lasrc_cref/Cargo.toml
```

For `lasrc_cref` stage 1+ (pixi on Linux, or Docker on macOS), see
[`lasrc_cref/README.md`](lasrc_cref/README.md).

### Lint, format, and type check

```bash
scripts/format     # apply cargo fmt + ruff format, and ruff auto-fixes, in place
scripts/lint       # check-only: cargo fmt --check, clippy -D warnings, ruff (use in CI)
scripts/typecheck  # mypy on lasrc_py/python
```

## References

Vermote, E., Roger, J. C., Franch, B., & Skakun, S. (2018). LaSRC (Land Surface Reflectance Code):
Overview, application and validation using MODIS, VIIRS, LANDSAT and Sentinel 2 data's. In
*IGARSS 2018 - 2018 IEEE International Geoscience and Remote Sensing Symposium* (pp. 8173-8176).
Valencia, Spain. https://doi.org/10.1109/IGARSS.2018.8517622 (NASA NTRS Document ID: 20190001670,
https://ntrs.nasa.gov/citations/20190001670)

[espa-sr]: https://github.com/NASA-IMPACT/espa-surface-reflectance/
