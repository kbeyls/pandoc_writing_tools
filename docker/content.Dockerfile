# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

# Keep the FROM instruction valid during Docker's static validation. The
# helper overrides this when a custom base image was requested.
ARG BASE_IMAGE=pandoc_writing_tools_build
FROM ${BASE_IMAGE}

# Add content-specific locked dependencies without removing packages that
# belong only to pandoc_writing_tools.
WORKDIR /opt/pandoc_writing_tools_content_project
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    env -u UV_NO_SYNC \
    UV_CACHE_DIR=/root/.cache/uv \
    uv sync --locked --no-install-project --inexact

WORKDIR /src
