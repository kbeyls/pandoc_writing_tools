#!/bin/sh
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

cd /src
ls -al
echo pandoc version:
pandoc --version
sh -c "make $*"
#bash
