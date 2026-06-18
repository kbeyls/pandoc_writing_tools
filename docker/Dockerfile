# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: <text>Copyright 2021-2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT
FROM fedora:43

# Install a focused Pandoc/TeX toolchain.
# Keep git for version metadata, Inkscape for SVG conversion, Python for helper
# scripts, and uv so container builds follow the developer-oriented Makefile
# path without installing the full TeX Live scheme.
RUN dnf -y --setopt=install_weak_deps=False update && \
    dnf -y --setopt=install_weak_deps=False install \
        pandoc \
        make \
        diffutils \
        git-core \
        python3 \
        uv \
        inkscape \
        libxcrypt-compat \
        latexmk \
        texlive-xetex \
        texlive-makeindex \
        texlive-amsfonts \
        texlive-amsmath \
        texlive-atbegshi \
        texlive-atveryend \
        texlive-auxhook \
        texlive-bclogo \
        texlive-bigintcalc \
        texlive-bitset \
        texlive-bookmark \
        texlive-caption \
        texlive-changepage \
        texlive-etexcmds \
        texlive-etoolbox \
        texlive-fontname \
        texlive-fontspec \
        texlive-footnotehyper \
        texlive-gettitlestring \
        texlive-graphics \
        texlive-graphics-cfg \
        texlive-graphics-def \
        texlive-hycolor \
        texlive-hyperref \
        texlive-iftex \
        texlive-infwarerr \
        texlive-intcalc \
        texlive-kpathsea \
        texlive-kvdefinekeys \
        texlive-kvoptions \
        texlive-kvsetkeys \
        texlive-l3backend \
        texlive-l3kernel \
        texlive-l3packages \
        texlive-latex \
        texlive-letltxmacro \
        texlive-lm \
        texlive-ltxcmds \
        texlive-mdwtools \
        texlive-mdframed \
        texlive-microtype \
        texlive-multirow \
        texlive-needspace \
        texlive-parskip \
        texlive-pdfescape \
        texlive-pdftexcmds \
        texlive-pgf \
        texlive-pst-coil \
        texlive-pst-grad \
        texlive-pst-node \
        texlive-pstricks \
        texlive-refcount \
        texlive-rerunfilecheck \
        texlive-stringenc \
        texlive-todonotes \
        texlive-tools \
        texlive-unicode-math \
        texlive-uniquecounter \
        texlive-upquote \
        texlive-url \
        texlive-xcolor \
        texlive-xetex-pstricks \
        texlive-xkeyval \
        texlive-xurl \
        texlive-zapfding \
        texlive-zref \
    && dnf clean all

# The repo is bind-mounted at /src during Docker-backed builds. Keep uv's
# project environment in /tmp so `uv run` does not replace a developer's host
# .venv with a Linux virtualenv through the bind mount.
ENV UV_PROJECT_ENVIRONMENT=/tmp/pandoc_writing_tools_venv \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_LINK_MODE=copy

COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
