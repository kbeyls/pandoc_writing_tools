# ExecPlan: PR CI for Balanced Python and Regression Tests

## Goal

Add GitHub Actions CI for pull requests using Option 2: a balanced PR gate with
fast Python tests and the existing Docker-backed Pandoc regression test suite.

The CI should make regressions visible before merge while keeping the initial
implementation simple and aligned with the repository's documented development
workflow.

## Current State

- The repository has no `.github/workflows/` directory.
- Python project metadata lives in `pyproject.toml` and requires Python
  `>=3.13`.
- Developer dependencies include `pytest` and `pytest-cov`.
- `CONTRIBUTING.md` documents regression testing with:

  ```shell
  uv run --project pandoc_writing_tools -m pytest -k regression
  ```

- The regression test rebuilds `examples/feature-demo` and compares normalized
  generated outputs against checked-in golden files.
- The regression test uses Docker by default unless
  `PANDOC_REGRESSION_USE_DOCKER=0` is set.
- The feature demo Docker wrapper builds the image from `docker/Dockerfile` and
  runs `make -C examples/feature-demo all`.
- The repo has a `theme/logging` submodule, so CI checkout must initialize
  submodules recursively.

## Desired End State

A pull request to this repository runs a workflow with two required jobs:

1. `python-tests`
   - Checks out the repository with submodules.
   - Installs Python 3.13.
   - Installs `uv`.
   - Runs the fast non-regression Python tests:

     ```shell
     uv run --project . -m pytest -q -k "not regression"
     ```

2. `regression-tests`
   - Checks out the repository with submodules.
   - Installs Python 3.13.
   - Installs `uv`.
   - Uses the GitHub-hosted Linux runner's Docker support.
   - Runs the existing Docker-backed regression suite:

     ```shell
     uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp
     ```

   - Uploads useful failure artifacts, including `examples/feature-demo/build`
     and `.pytest-tmp`, when the job fails.

## Implementation Steps

1. Create `.github/workflows/pr-ci.yml`.

2. Configure workflow triggers:

   ```yaml
   on:
     pull_request:
     push:
       branches: [main]
   ```

   `pull_request` is the primary target. Running the same checks on `main` keeps
   branch protection and post-merge visibility straightforward.

3. Set conservative workflow permissions:

   ```yaml
   permissions:
     contents: read
   ```

4. Add the `python-tests` job.

   Planned job shape:

   ```yaml
   python-tests:
     runs-on: ubuntu-latest
     env:
       UV_CACHE_DIR: .uv-cache
     steps:
       - uses: actions/checkout@v4
         with:
           submodules: recursive
       - uses: actions/setup-python@v5
         with:
           python-version: "3.13"
       - uses: astral-sh/setup-uv@v5
         with:
           enable-cache: true
       - run: uv run --project . -m pytest -q -k "not regression"
   ```

   Use current stable action versions at implementation time if newer major
   versions have replaced these.

5. Add the `regression-tests` job.

   Planned job shape:

   ```yaml
   regression-tests:
     runs-on: ubuntu-latest
     env:
       UV_CACHE_DIR: .uv-cache
       DOCKER_BUILDKIT: "1"
     steps:
       - uses: actions/checkout@v4
         with:
           submodules: recursive
       - uses: actions/setup-python@v5
         with:
           python-version: "3.13"
       - uses: astral-sh/setup-uv@v5
         with:
           enable-cache: true
       - run: uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp
       - name: Upload regression artifacts
         if: failure()
         uses: actions/upload-artifact@v4
         with:
           name: regression-artifacts
           path: |
             examples/feature-demo/build
             .pytest-tmp
           if-no-files-found: ignore
   ```

6. Keep Confluence upload behavior out of CI credentials.

   The existing unit tests monkeypatch Confluence and `requests` behavior. The
   PR CI workflow should not require Atlassian credentials or perform real
   Confluence uploads.

7. Update `CONTRIBUTING.md` if needed.

   Add a short section describing:

   - PRs run fast Python tests and full regression tests.
   - Intentional output changes should be accompanied by updated golden files.
   - Golden files are updated with:

     ```shell
     uv run --project . scripts/python/update_regression_goldens.py --accept
     ```

8. Open a PR and verify that both jobs run and report clear failures.

9. In GitHub branch protection, mark both workflow jobs as required before merge:

   - `python-tests`
   - `regression-tests`

## Validation

Before merging the CI change:

1. Run fast tests locally:

   ```shell
   uv run --project . -m pytest -q -k "not regression"
   ```

2. Run regression tests locally if Docker is available:

   ```shell
   uv run --project . -m pytest -q -k regression
   ```

3. Confirm the GitHub Actions workflow runs on a test pull request.

4. Confirm a regression mismatch produces actionable output:

   - pytest failure log contains the first diff lines,
   - `.pytest-tmp` is uploaded,
   - `examples/feature-demo/build` is uploaded if generated.

5. Confirm the workflow does not need repository secrets.

## Risks and Mitigations

- Docker regression tests may be slow because the image installs Fedora,
  Pandoc, Inkscape, and `texlive-scheme-full`.
  - Mitigation: start with this simple, reproducible setup and measure runtime.

- The first CI run may be slower than later runs because dependency and Docker
  layers are cold.
  - Mitigation: enable `uv` caching immediately and consider Docker caching or a
    prebuilt image later.

- GitHub-hosted runners may change installed Docker behavior over time.
  - Mitigation: keep the workflow explicit and fail fast if Docker is
    unavailable.

- Full regression tests may produce intentional golden mismatches after Lua
  filter, template, Makefile, or feature-demo changes.
  - Mitigation: require contributors to update and review golden files in the
    same PR.

## Later Optimization: Option 7

If the `regression-tests` job proves too slow, implement Option 7 as a follow-up:
publish a prebuilt Docker image to GitHub Container Registry and have the
regression job pull that image instead of rebuilding it on every PR.

That follow-up should:

- Build and publish the image when `docker/Dockerfile` or `docker/entrypoint.sh`
  changes.
- Tag the image by commit SHA and optionally by a stable branch tag.
- Update the regression job to pull the prebuilt image.
- Keep a fallback path that rebuilds locally if the image is unavailable.
- Reassess whether Docker layer caching is enough before adding extra image
  publishing complexity.
