# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable


DEFAULT_FIXTURE_REL = Path("examples/feature-demo")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_outputs(
    fixture_root: Path | None = None,
    use_docker: bool = True,
    targets: Iterable[str] | None = None,
) -> Path:
    root = repo_root()
    fixture_root = fixture_root or (root / DEFAULT_FIXTURE_REL)
    targets = list(targets) if targets is not None else ["all"]

    if use_docker:
        script = fixture_root / "build_with_docker.sh"
        if not script.exists():
            raise FileNotFoundError(f"Missing build script: {script}")
        subprocess.run([str(script), *targets], check=True)
    else:
        env = os.environ.copy()
        subprocess.run(["make", "-C", str(fixture_root), *targets], check=True, env=env)

    return fixture_root / "build"
