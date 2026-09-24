#!/bin/sh
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT
set -eu
# Build the runtime image in up to three stages:
# 1. Build the tools image from the pandoc_writing_tools repository. It
#    contains the native tools and the tools repository's Python packages.
# 2. If requested, extend it with a custom Dockerfile whose build context is
#    the content repository.
# 3. If the content repository has pyproject.toml and uv.lock, extend the
#    selected base with those Python packages. This stage uses a temporary
#    context containing only those two metadata files so unrelated content
#    changes do not invalidate the dependency layer.
# Run the final image with the content repository mounted at /src.

usage() {
  cat >&2 <<'EOF'
Usage: build_content_with_docker.sh --content-root PATH \
       [--base-dockerfile PATH] -- [MAKE_ARGUMENTS...]
EOF
}

fail() {
  echo "build_content_with_docker.sh: $*" >&2
  exit 2
}

content_root=""
base_dockerfile=""
found_separator=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --content-root)
      [ "$#" -ge 2 ] || fail "--content-root requires a path"
      content_root=$2
      shift 2
      ;;
    --base-dockerfile)
      [ "$#" -ge 2 ] || fail "--base-dockerfile requires a path"
      base_dockerfile=$2
      shift 2
      ;;
    --)
      found_separator=1
      shift
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      fail "unknown option: $1"
      ;;
  esac
done

[ "${found_separator}" -eq 1 ] || {
  usage
  fail "missing -- before make arguments"
}
[ -n "${content_root}" ] || fail "--content-root is required"
[ -d "${content_root}" ] || fail "content root is not a directory: ${content_root}"
content_root=$(cd "${content_root}" && pwd)

if [ -n "${base_dockerfile}" ]; then
  case "${base_dockerfile}" in
    /*) ;;
    *) base_dockerfile="${content_root}/${base_dockerfile}" ;;
  esac
  [ -f "${base_dockerfile}" ] || \
    fail "base Dockerfile does not exist: ${base_dockerfile}"
  base_dockerfile_directory=$(dirname "${base_dockerfile}")
  base_dockerfile_name=$(basename "${base_dockerfile}")
  base_dockerfile_directory=$(cd "${base_dockerfile_directory}" && pwd)
  base_dockerfile="${base_dockerfile_directory}/${base_dockerfile_name}"
fi

pyproject="${content_root}/pyproject.toml"
lockfile="${content_root}/uv.lock"
if [ -f "${pyproject}" ] && [ ! -f "${lockfile}" ]; then
  fail "${content_root} contains pyproject.toml but is missing uv.lock"
fi
if [ -f "${lockfile}" ] && [ ! -f "${pyproject}" ]; then
  fail "${content_root} contains uv.lock but is missing pyproject.toml"
fi

if [ "$#" -eq 0 ]; then
  set -- all
fi

script_directory=$(cd "$(dirname "$0")" && pwd)
tools_root=$(cd "${script_directory}/.." && pwd)
uid=$(id -u)
gid=$(id -g)
content_key=$(printf '%s' "${content_root}" | cksum | awk '{print $1}')

tools_image="pandoc_writing_tools_build"
runtime_image="${tools_image}"

docker build -f "${tools_root}/docker/Dockerfile" \
  -t "${tools_image}" "${tools_root}"

# Apply optional docker image customizations before adding the
# content repository's Python dependency layer.
if [ -n "${base_dockerfile}" ]; then
  custom_image="pandoc_writing_tools_custom_${content_key}"
  docker build --build-arg "BASE_IMAGE=${tools_image}" \
    -f "${base_dockerfile}" -t "${custom_image}" "${content_root}"
  runtime_image="${custom_image}"
fi

# The content-dependency build uses a temporary directory containing copies
# of pyproject.toml and uv.lock. Remove it after Docker has consumed it,
# including on failure or interruption, so builds do not leave stale metadata
# under the temporary directory.
metadata_context=""
cleanup_metadata_context() {
  if [ -n "${metadata_context}" ] && \
      [ -d "${metadata_context}" ] && \
      [ "${metadata_context}" != "/" ]; then
    rm -f -- \
      "${metadata_context}/pyproject.toml" \
      "${metadata_context}/uv.lock"
    rmdir -- "${metadata_context}"
  fi
  metadata_context=""
}
trap cleanup_metadata_context EXIT
trap 'cleanup_metadata_context; exit 1' HUP INT TERM

if [ -f "${pyproject}" ]; then
  metadata_context=$(mktemp -d \
    "${TMPDIR:-/tmp}/pandoc-writing-tools-content.XXXXXX")
  cp "${pyproject}" "${metadata_context}/pyproject.toml"
  cp "${lockfile}" "${metadata_context}/uv.lock"

  content_image="pandoc_writing_tools_content_${content_key}"
  docker build --build-arg "BASE_IMAGE=${runtime_image}" \
    -f "${tools_root}/docker/content.Dockerfile" \
    -t "${content_image}" "${metadata_context}"
  runtime_image="${content_image}"

  cleanup_metadata_context
fi

echo "Running Docker image: ${runtime_image}"
docker run --rm --user="${uid}:${gid}" \
  --env HOME=/tmp \
  --mount type=bind,source="${content_root}",target=/src \
  "${runtime_image}" "$@"
