# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: <text>Copyright 2021-2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT
FROM fedora:43

# 1. install pandoc and texlive dependencies
#    Also install git as we need that for computing version numbers.
#    Also install librsvg2-bin and inkscape to enable pandoc to convert SVG images to PDF.
#    Also install python as the pandoc-fignos filter depends on it.
RUN dnf -y update && \
    dnf -y install \
        wget \
        perl \
        pandoc \
        make \
        git \
        librsvg2-tools \
        python3-pip \
        inkscape \
        libxcrypt-compat \
        texlive-scheme-full xindy \
    && dnf clean all

RUN python3 -m pip install --no-cache-dir uv

COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
