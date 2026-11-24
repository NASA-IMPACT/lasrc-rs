# Project Instructions

See `README.md` ("Developer getting started") for the full setup.

## Python Environment

The repo root is a uv workspace (`pyproject.toml`, members `lasrc_py` and `lasrc_ancillary`) with a
single `uv.lock` and `.venv` in the root. The Python version comes from `.python-version`.

- Set up or refresh the environment with `uv sync`. It also builds and installs the `lasrc`
  extension (editable).
- Run Python commands with `uv run <cmd>` (e.g. `uv run python ...`, `uv run pytest ...`). No need
  to activate the venv.
- Add dependencies with `uv add <pkg>` (dev tools: `uv add --dev <pkg>`). Never use `pip`,
  `uv pip install`, or conda; they bypass the lockfile and the next `uv sync` removes them.
- Do not use `maturin develop`; the next `uv run` replaces whatever it installed. `uv run`
  rebuilds the extension automatically when Rust sources change
  (`uv sync --reinstall-package lasrc` forces it).

## Build, Test, Lint

Prefer the scripts in `scripts/` (CI runs the same ones):

- `scripts/test [rust|python] [pytest args...]` - `cargo test --workspace` and
  `pytest lasrc_py lasrc_ancillary`
- `scripts/lint [rust|python]` - check-only: cargo fmt, clippy `-D warnings`, ruff
- `scripts/format` - apply cargo fmt, ruff format, ruff auto-fixes
- `scripts/typecheck` - mypy on `lasrc_py/python` and `lasrc_ancillary/src`
- `scripts/check-versions TAG` - TAG matches the `Cargo.toml` version and has a CHANGELOG entry
  (run by the Release workflow, see `VERSIONING.md`)
- `scripts/version` - version for a build of this checkout: the tag on a release, `X.Y.Z+g<sha>`
  otherwise

Running cargo directly: the `lasrc_py` crate builds against Python via PyO3, which uses the first
`python3` on PATH. Set `PYO3_PYTHON="$(uv python find)"` to match the project interpreter (the
scripts do this).

## Rust Toolchain

Pinned in `rust-toolchain.toml` (version + rustfmt/clippy). Clippy allow-list for patterns that
mirror the C port lives in `[workspace.lints.clippy]` in the root `Cargo.toml`.
