#!/bin/sh
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly uid="$(id -u)"
readonly gid="$(id -g)"

if [ "$#" -eq 0 ]; then
  set -- all
fi

docker build -t pandoc_writing_tools_build "${TOOLS_ROOT}/docker" && \
  docker run --rm --user="${uid}":"${gid}" \
  --mount type=bind,source="${TOOLS_ROOT}",target=/src \
  pandoc_writing_tools_build -C examples/feature-demo "$@"
