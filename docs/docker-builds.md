<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
<open-source-office@arm.com>
SPDX-License-Identifier: MIT
-->

# Docker builds and customization

The [README quick start](../README.md#quick-start) is sufficient for ordinary
content repositories. This guide explains how
`pandoc_writing_tools/docker/build_content_with_docker.sh` (the Docker helper)
handles Python dependencies, how to customize the image with a standard
Dockerfile, what Docker caches, and how to diagnose failures.

## Content repository states

The helper examines `pyproject.toml` and `uv.lock` at the content repository
root before invoking Docker:

- If neither exists, it runs the `pandoc_writing_tools` image directly. Do not
  add empty files merely to use Docker.
- If both exist, it adds their locked Python dependencies to a content-specific
  image layer automatically. The content repository needs no Dockerfile.
- If exactly one exists, it stops before invoking Docker and names the missing
  file. Generate or restore the matching file rather than bypassing the check.

## Add or update Python dependencies

Initialize Python metadata once when a content repository first needs its own
packages, then use uv to update it:

```shell
uv init --bare
uv add <package>
git add pyproject.toml uv.lock
```

For an existing project, omit `uv init`. Use `uv add`, `uv remove`, or
`uv lock --upgrade` as appropriate, review both files, and commit them together.
The next Docker-backed build notices their changed bytes and rebuilds only the
content dependency layer and layers above it.

The tools and content dependencies share one image-owned Python environment.
Packages present in both lockfiles must have compatible requirements. If uv
cannot satisfy the content lock without breaking the environment, align the
declared constraints rather than deleting a lockfile or weakening the locked
build.

## Invoke the helper

A standalone content repository normally exposes a small local wrapper:

```shell
#!/bin/sh
set -e

CONTENT_ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "${CONTENT_ROOT}/pandoc_writing_tools/docker/build_content_with_docker.sh" \
  --content-root "${CONTENT_ROOT}" -- "$@"
```

The Docker helper provided by the tools repository has this command-line
interface:

```text
build_content_with_docker.sh --content-root PATH \
  [--base-dockerfile PATH] -- [MAKE_ARGUMENTS...]
```

"`--content-root` identifies the root of the content repository that the
helper mounts at `/src`."
-->
`--content-root` identifies the root of the content repository that the helper
mounts at `/src`. The `--` separator is required and distinguishes helper
options from arguments passed to
Make. With no make arguments, the helper runs `make all`.

The optional `--base-dockerfile` path may be absolute or relative to the content
root. It provides the advanced customization described next.

## Customize the container with a Dockerfile

Most content repositories should not have a Dockerfile. When a project needs
native packages, fonts, external package repositories, compilers, copied
assets, or other arbitrary image changes, use an ordinary Dockerfile as a
custom base:

```dockerfile
# syntax=docker/dockerfile:1
ARG BASE_IMAGE=pandoc_writing_tools_build
FROM ${BASE_IMAGE}

RUN dnf install -y libreoffice && dnf clean all
```

Point the content repository's `build_with_docker.sh` wrapper at the custom
Dockerfile:

```shell
exec "${CONTENT_ROOT}/pandoc_writing_tools/docker/build_content_with_docker.sh" \
  --content-root "${CONTENT_ROOT}" \
  --base-dockerfile docker/Dockerfile \
  -- "$@"
```

The default keeps the `FROM` instruction valid during Docker's static
validation. The helper still passes the selected tools image as `BASE_IMAGE`,
builds the custom base, and then adds content Python dependencies when the two
metadata files exist. Native libraries or compilers required to build Python
packages are therefore present before uv runs.

The custom Dockerfile uses the entire content repository as its build context.
Its author is responsible for an appropriate `.dockerignore`, for any files it
copies, and for preserving a make-capable inherited entrypoint. This is a
standard Docker extension point; `pandoc_writing_tools` does not define a
separate system-package list or installation-hook language.

## Cache behavior

Docker caches the build in independent layers:

- The tools layer changes when `pandoc_writing_tools/docker/Dockerfile`, its
  native package installation, or the tools `pyproject.toml` or `uv.lock`
  changes.
- The optional custom-base layer changes according to its Dockerfile and build
  context. Use a `.dockerignore` in the content repository to exclude unrelated
  files.
- The content Python layer changes when the content `pyproject.toml` or
  `uv.lock` changes, or when its selected base image changes. Ordinary Markdown
  and source edits are excluded from this layer's build context.

The helper always asks Docker to build the required layers before launching the
container. Unchanged layers are cache hits. If a tools layer changes, all layers
above it are rebuilt; if only the content lock changes, the tools and custom
base layers remain reusable.

During a dependency-layer rebuild, a BuildKit cache lets uv reuse previously
downloaded artifacts. The runtime container does not mount a uv cache and does
not synchronize dependencies. A completely fresh Docker builder, including a
new hosted CI runner without exported Docker cache data, must download each
required artifact once.

Internally, the image disables runtime synchronization with `UV_NO_SYNC` and
uses an inexact locked sync for the content layer. These are helper-owned
implementation details: content-repository wrappers should not set them or copy
the internal content Dockerfile.

## Troubleshooting

### One Python metadata file is missing

Commit both `pyproject.toml` and `uv.lock`, or remove both if the repository does
not have content-specific Python dependencies. Do not create an empty lockfile.

### The lockfile is stale

The image build deliberately refuses to rewrite a stale lock. Run `uv lock` in
the content repository, review the result, commit it, and rebuild.

### Tools and content requirements overlap incompatibly

Align the version constraints in the two projects. Both dependency sets share
one environment, so two incompatible locked versions of the same distribution
cannot coexist.

### Docker cannot resolve or download an image

Registry authentication, DNS, socket, and Dockerfile-frontend failures occur
before the content helper can build anything. Preserve the error and retry the
unchanged command after registry or network access recovers.

### A dependency version should be refreshed

Update the lock deliberately with `uv add`, `uv remove`, or `uv lock --upgrade`.
The changed lockfile invalidates the content dependency layer. Do not delete
broad Docker state merely to request a package upgrade.

### A custom Dockerfile rebuilds too often

Its context is the content repository. Add a `.dockerignore` to the content
repository that retains only files used by that Dockerfile. Repositories
without a custom-base Dockerfile do not need this file for dependency-layer
caching.
