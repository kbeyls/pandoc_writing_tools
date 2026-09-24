# Bake the locked uv environment into the Docker image

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to
date as work proceeds.

This plan is maintained in accordance with the ExecPlan requirements in the
consuming repository's `agent/PLANS.md`.

## Purpose / Big Picture

The Docker-backed document build currently runs `uv run` against a bind-mounted
checkout whose Python environment starts empty in every new container. As a
result, repeated builds can download and install the same Python packages again.
After this change, the Docker image itself contains the exact default and
development dependencies locked by `uv.lock`. A repeat invocation of
`examples/feature-demo/build_with_docker.sh` reuses Docker's dependency layer,
and the short-lived build container uses the already-created environment
without synchronizing or downloading packages at runtime.

This is deliberately an alternative to mounting a persistent uv cache into
each container. It lives on the `docker-baked-uv-environment` branch, forked
directly from `main`, so that the two approaches can be compared independently.
A user can observe the result by running the feature-demo Docker build twice:
the second Docker build reports the `uv sync` layer as cached, and neither
runtime container creates a virtual environment or downloads Python packages.

## Progress

- [x] (2026-09-24 13:30Z) Create `docker-baked-uv-environment` directly from
  `pandoc_writing_tools/main`, preserving the unrelated untracked patch file.
- [x] (2026-09-24 13:30Z) Inspect the Dockerfile, feature-demo wrapper, project
  dependency metadata, documentation, and repository contribution rules.
- [x] (2026-09-24 13:32Z) Add focused tests that describe the root build context, baked locked
  environment, cache mount, and runtime command forwarding.
- [x] (2026-09-24 13:32Z) Refactor the Docker build so dependency metadata is copied and synchronized
  into an image-owned environment before the source checkout is mounted.
- [x] (2026-09-24 13:33Z) Document the behavior, invalidation rules, standalone-project command,
  benefits, and limitations of the image-baked approach.
- [x] (2026-09-24 13:35Z) Prove the behavior with two Docker-backed builds and inspect the second
  build log for a cached dependency layer and absence of runtime installation.
- [x] (2026-09-24 13:36Z) Run REUSE, non-regression, and regression validation required by
  `AGENTS.md`.
- [x] (2026-09-24 13:36Z) Commit the completed plan and implementation on the
  comparison branch with the unrelated patch excluded.

## Surprises & Discoveries

- Observation: The first full regression run found a second direct Docker image
  builder in `scripts/python/tests/test_confluence_writer.py`; it still supplied
  `docker/` as the context and therefore could not copy `uv.lock` or the
  root-relative entrypoint.
  Evidence: All nine Confluence writer setups failed with `"/uv.lock": not
  found`; after changing the fixture to use `-f docker/Dockerfile` with the
  repository root, the regression suite reported `13 passed, 95 deselected`.

- Observation: The image-owned environment remains usable when the runtime
  container runs as the host user's numeric UID even though root created the
  environment during image construction.
  Evidence: Both feature-demo wrapper invocations exited zero, and a direct
  `/opt/pandoc_writing_tools_venv/bin/python -c 'import drawsvg, jinja2, yaml'`
  command exited zero without output.

## Decision Log

- Decision: Build with the repository root as the Docker build context and
  select `docker/Dockerfile` using `docker build -f`.
  Rationale: Docker can only `COPY` files from its build context. Baking the
  locked environment requires `pyproject.toml` and `uv.lock`, which live at the
  repository root rather than under `docker/`.
  Date/Author: 2026-09-24 / Codex

- Decision: Install the locked dependencies into
  `/opt/pandoc_writing_tools_venv` using `uv sync --locked
  --no-install-project` and set `UV_NO_SYNC=1` for runtime commands.
  Rationale: `/opt` belongs to the image rather than the bind-mounted checkout.
  The repository is a collection of build tools, not an installable Python
  package, so only its dependencies need installation. Disabling runtime sync
  makes the container consume the immutable, readable environment and avoids
  an attempted write by the host user's numeric UID.
  Date/Author: 2026-09-24 / Codex

- Decision: Use a BuildKit cache mount for uv's download cache while building
  the dependency layer, but do not mount any uv cache into runtime containers.
  Rationale: Docker's normal layer cache makes an unchanged lockfile a complete
  cache hit. The BuildKit cache still avoids redownloading unchanged artifacts
  when dependency metadata changes and the layer must be rebuilt, without
  creating host-owned project cache directories.
  Date/Author: 2026-09-24 / Codex

- Decision: Do not add a GitHub Actions Buildx cache in this focused change.
  Rationale: Local Docker builders retain layers and BuildKit caches, which is
  the behavior under comparison. A fresh hosted CI runner has no persistent
  Docker cache and remains a documented limitation; solving that separately
  avoids coupling this design to image publishing or CI-specific cache export.
  Date/Author: 2026-09-24 / Codex

## Outcomes & Retrospective

The alternative implementation is complete on
`docker-baked-uv-environment`. The first Docker build created the image-owned
environment and installed 33 locked packages. The second reported the locked
`uv sync` instruction as `CACHED`; its runtime portion invoked the Python helper
scripts without environment creation, resolution, download, or installation.
Direct imports from the baked environment succeeded.

The focused Docker-wrapper suite passed 4 tests, the non-regression suite passed
95 tests with 13 deselected, and the regression suite passed 13 tests with 95
deselected. REUSE reported all 73 considered files compliant. The implementation
also updated the Confluence writer's image fixture after the first regression
run exposed its obsolete build context.

This approach deliberately leaves one limitation for comparison: its cache is
local to the Docker builder. A new CI runner downloads dependencies unless a
future change exports Docker's cache or pulls a prebuilt image. It also bakes
only this tools repository's locked dependencies; content-specific Python
dependencies require an extending layer. Neither limitation affects the
ordinary feature-demo build.

## Context and Orientation

`pandoc_writing_tools/docker/Dockerfile` defines a Fedora-based image containing
Pandoc, TeX, Inkscape, Graphviz, Python, uv, and the other native tools used by
document builds. `pandoc_writing_tools/docker/entrypoint.sh` starts `make` in
the `/src` directory. A Docker bind mount makes a host checkout visible at
`/src`; changes made there are immediately visible in the container and build
outputs retain the host user's ownership.

`pandoc_writing_tools/examples/feature-demo/build_with_docker.sh` builds that
image and runs the feature demo. Before this work it passes
`pandoc_writing_tools/docker/` as the Docker build context. A build context is
the directory tree Docker is allowed to read for `COPY` instructions. Because
`pyproject.toml` and `uv.lock` are one level above that directory, the wrapper
must instead pass the repository root and identify the Dockerfile explicitly.

`pandoc_writing_tools/pyproject.toml` declares normal Python dependencies and a
default `dev` dependency group. `pandoc_writing_tools/uv.lock` pins their full
dependency graph. `uv sync --locked` creates an environment exactly from those
files and fails rather than silently changing the lockfile. The
`--no-install-project` option skips installing this repository itself; there is
no package module to install, and helper scripts are run directly from the
bind-mounted checkout.

A Docker layer is the cached result of one Dockerfile instruction. Copying only
`pyproject.toml` and `uv.lock` immediately before `uv sync` means ordinary
source, documentation, and content changes do not invalidate the dependency
layer. A BuildKit cache mount is a temporary directory whose contents Docker
retains outside the image layer and makes available to later builds. It lets uv
reuse downloaded wheels when a changed lockfile legitimately invalidates the
dependency layer. `UV_LINK_MODE=copy` is required because files cannot safely
be hard-linked from that cache mount into the image environment.

The comparison branch must not include the unrelated untracked
`0001-docker-persist-uv-downloads-across-builds.patch`. It must also remain
independent of the runtime-cache implementation on the
`docker-persistent-uv-cache` branch.

## Plan of Work

First add `scripts/python/tests/test_build_with_docker.py`. The tests will place
a fake `docker` executable first on `PATH`, invoke the real feature-demo wrapper,
and assert that the wrapper uses the repository root as its context, selects
`docker/Dockerfile`, retains the host UID/GID bind-mounted run, and forwards
both the default and explicit make targets. A second group of assertions will
read the Dockerfile and verify the dependency-layer contract: exact lockfile
input, an image-owned environment, a BuildKit cache mount, locked sync without
installing the project, disabled runtime synchronization, and ordering that
keeps entrypoint edits from invalidating the dependency layer. These focused
tests establish observable command and image-construction behavior without
needing Docker in the ordinary unit-test suite.

Then change `examples/feature-demo/build_with_docker.sh` to call `docker build`
with `-f "${TOOLS_ROOT}/docker/Dockerfile"` and the repository root context.
Change `docker/Dockerfile` to copy `pyproject.toml` and `uv.lock`, synchronize
them into `/opt/pandoc_writing_tools_venv` with uv's cache mounted at
`/root/.cache/uv`, and set `UV_NO_SYNC=1` only after the synchronization layer.
Set `UV_PYTHON=/usr/bin/python3` and `UV_PYTHON_DOWNLOADS=never` so uv uses the
Python supplied by Fedora and does not download another interpreter. Copy
`docker/entrypoint.sh` from its new root-relative path after the dependency
layer. Add `.dockerignore` at the repository root to avoid sending Git state,
host virtual environments, pytest state, and generated feature-demo output in
the build context.

Update `README.md` in the quick-start instructions and standalone wrapper
example. Explain why the image-baked environment speeds repeated builds, how
Docker invalidates and reconstructs it when `pyproject.toml` or `uv.lock`
changes, why the BuildKit download cache remains useful, and that no runtime
cache volume or opt-out switch is required. Also state the limitation: the
image contains the dependencies declared by `pandoc_writing_tools`, so a
consumer with additional repository-specific Python dependencies must extend
the image or use a separate project-specific dependency strategy.

Finally run the focused tests, two Docker builds, and all validation required by
`AGENTS.md`. Update this document with the actual observations, then commit only
the intended files on `docker-baked-uv-environment` with a detailed, wrapped
message.

## Concrete Steps

All commands in this section run from the `pandoc_writing_tools` repository
root, which in the current workspace is
`/Users/kribey01/dev/kristof_thinking_writing/pandoc_writing_tools`.

Confirm the comparison branch and preserve unrelated state:

    git status --short --branch

The first line must name `docker-baked-uv-environment`. The untracked patch may
appear but must never be staged.

After adding the focused tests, run:

    uv run --project . -m pytest -q scripts/python/tests/test_build_with_docker.py

Before implementation, the new contract tests should fail because the wrapper
uses `docker/` as its context and the Dockerfile has no locked sync layer. After
implementation, all tests in that file must pass.

Exercise the real feature demo twice and capture separate evidence:

    ./examples/feature-demo/build_with_docker.sh -B build/.image-deps.mk \
      > /tmp/pandoc-baked-uv-first.log 2>&1
    ./examples/feature-demo/build_with_docker.sh -B build/.image-deps.mk \
      > /tmp/pandoc-baked-uv-second.log 2>&1

Inspect both logs. The first build may download dependencies in the Docker
build step. In the second log, the `uv sync --locked --no-install-project` step
must be reported as cached and the `docker run` phase must not say it is
creating an environment, resolving packages, downloading packages, or
installing packages.

Verify imports directly from the baked environment:

    docker run --rm \
      --entrypoint /opt/pandoc_writing_tools_venv/bin/python \
      pandoc_writing_tools_build \
      -c 'import drawsvg, jinja2, yaml'

The command must exit successfully with no output.

Run the repository-required checks:

    uv run --project . reuse lint
    uv run --project . -m pytest -q -k "not regression"
    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp

All must exit zero. Before committing, inspect `git diff`, stage exact paths so
the unrelated patch remains untracked, commit with a detailed message, and
verify wrapping with:

    git log -1 --format=%B | awk '{ if (length($0) > 80) print length($0), $0 }'

The wrapping command must produce no output.

## Validation and Acceptance

Acceptance requires both structural tests and real Docker behavior. The focused
unit tests must prove the wrapper's exact build and run arguments and the
Dockerfile layer contract. The first real invocation must produce the feature
demo dependency file successfully while using dependencies already present in
the launched container. The second invocation must reuse the Docker dependency
layer and perform no runtime Python dependency setup. The direct image command
must import representative locked packages from
`/opt/pandoc_writing_tools_venv`.

The complete non-regression and regression pytest suites must pass, as must the
REUSE license check. Documentation examples must use the root build context and
must not retain the obsolete `${TOOLS_ROOT}/docker` context command. The final
commit must contain the plan, Dockerfile, root `.dockerignore`, wrapper, README,
and focused tests, and must not contain the unrelated patch file.

## Idempotence and Recovery

The implementation and validation commands are safe to repeat. Docker reuses
unchanged image layers and overwrites the same local image tag. The demo build
regenerates files under its ignored `build/` directory. Logs under `/tmp` may be
overwritten safely.

If a Docker build fails during dependency synchronization, fix the Dockerfile
or locked metadata and rerun the same wrapper; BuildKit retains successfully
downloaded artifacts. If an old local image makes the evidence ambiguous, use
`docker build --no-cache` only for a diagnostic first build, then run the normal
wrapper twice to verify cache reuse. Do not delete broad Docker state because
other projects may rely on it. If the branch must be abandoned, switch back to
`main`; the alternative implementation remains isolated in its branch and does
not require undoing the runtime-cache branch.

## Artifacts and Notes

Keep the concise portions of `/tmp/pandoc-baked-uv-first.log` and
`/tmp/pandoc-baked-uv-second.log` that show the dependency step's first-run
execution and second-run cache hit. Record the final pytest counts and Docker
observation in `Outcomes & Retrospective` rather than checking generated logs
into the repository.

The expected core Dockerfile shape is:

    COPY pyproject.toml uv.lock ./
    RUN --mount=type=cache,target=/root/.cache/uv \
        UV_CACHE_DIR=/root/.cache/uv \
        uv sync --locked --no-install-project

The exact surrounding `ENV`, `WORKDIR`, and entrypoint instructions are part of
the implementation and test contract described above.

## Interfaces and Dependencies

The external interface remains
`examples/feature-demo/build_with_docker.sh [make arguments]`. With no argument,
it supplies `all`; with arguments, it forwards them after `make -C
examples/feature-demo`. No runtime environment variable or cache-directory API
is introduced.

The Docker image interface adds the environment at
`/opt/pandoc_writing_tools_venv` and these uv settings:
`UV_PROJECT_ENVIRONMENT=/opt/pandoc_writing_tools_venv`, `UV_LINK_MODE=copy`,
`UV_PYTHON=/usr/bin/python3`, `UV_PYTHON_DOWNLOADS=never`, and, after the build
sync, `UV_NO_SYNC=1`. The implementation depends only on the existing Fedora
`uv` package and Dockerfile frontend syntax already declared at the top of
`docker/Dockerfile`; it adds no Python project dependency.

Revision note (2026-09-24): Created the initial self-contained plan after the
comparison branch was forked from `main`, recording the image-layer design,
validation evidence, and deliberate exclusion of runtime cache mounts and CI
cache export.

Revision note (2026-09-24): Marked implementation and validation milestones
complete, recorded the additional Confluence test builder found by the full
suite, and captured the observed layer-cache behavior and final test counts.
