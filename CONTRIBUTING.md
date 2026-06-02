# Contributing to pandoc_writing_tools

Thanks for helping improve pandoc_writing_tools. This guide covers the developer
workflow and regression testing.

## Setup

Clone with submodules (or initialize them later):

```shell
git clone --recursive https://github.com/kbeyls/pandoc_writing_tools.git
```

If you already cloned the repo, run:

```shell
git submodule update --init --recursive
```

The build scripts use Docker by default to keep the Pandoc toolchain pinned.

## Pull request CI

Pull requests run two GitHub Actions checks:

- `python-tests`: fast Python tests that exclude the regression suite.
- `regression-tests`: the Docker-backed feature-demo regression suite.

The regression check rebuilds the feature demo and compares normalized outputs
against the checked-in golden files. If a change intentionally affects generated
HTML, XHTML, TeX, PDF, native, DOCX, PPTX, or EML output, update the golden files
in the same PR.

## Regression tests

Regression tests rebuild the feature demo and compare normalized outputs against
checked-in golden files:

```shell
uv run --project . -m pytest -k regression
```

The tests build via Docker unless you set `PANDOC_REGRESSION_USE_DOCKER=0`.

## Updating goldens

After intentional output changes, update the golden files:

```shell
uv run --project . scripts/python/update_regression_goldens.py --accept
```

Useful options:

- `--no-docker`: build locally instead of Docker.
- `PANDOC_REGRESSION_SKIP_BUILD=1`: reuse existing build outputs.
- `PANDOC_REGRESSION_USE_DOCKER=0`: build locally for the test run.

## Making changes

If you modify Lua filters or templates, rebuild the feature demo and update the
goldens so regressions stay visible.

If you add a new feature:

- make sure that the feature demo shows it, and
- make sure it is documented in the README.md

## Logging submodule

The lua logging helpers, mostly used for debugging the lua scripts, are provided
via the upstream `pandoc-ext/logging` repository, included as a git submodule at
`theme/logging`. After cloning this repo, run:

```shell
git submodule update --init --recursive
```
