#!/usr/bin/env python3
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
from pathlib import Path

from regression.build_outputs import build_outputs
from regression.normalize_outputs import OUTPUT_SPECS, normalize_outputs


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Update regression golden outputs.")
    parser.add_argument("--accept", action="store_true", help="Overwrite golden outputs.")
    parser.add_argument("--fixture", default="examples/feature-demo", help="Fixture root relative to repo.")
    parser.add_argument("--skip-build", action="store_true", help="Skip rebuilding outputs.")
    parser.add_argument("--no-docker", action="store_true", help="Build without Docker.")
    args = parser.parse_args()

    if not args.accept:
        raise SystemExit("Refusing to overwrite goldens without --accept")

    root = repo_root()
    fixture_root = (root / args.fixture).resolve()
    if not fixture_root.exists():
        raise SystemExit(f"Fixture root not found: {fixture_root}")

    build_dir = fixture_root / "build"
    if not args.skip_build:
        build_dir = build_outputs(fixture_root=fixture_root, use_docker=not args.no_docker, targets=["all"])

    golden_dir = root / "scripts/python/tests/fixtures/regression/feature-demo"
    temp_dir = golden_dir / ".tmp"
    if temp_dir.exists():
        for path in temp_dir.glob("*"):
            path.unlink()
    temp_dir.mkdir(parents=True, exist_ok=True)

    normalize_outputs(build_dir, temp_dir)

    changed: list[str] = []
    for spec in OUTPUT_SPECS:
        temp_path = temp_dir / spec.golden_name
        golden_path = golden_dir / spec.golden_name
        if not golden_path.exists() or golden_path.read_text(encoding="utf-8") != temp_path.read_text(encoding="utf-8"):
            changed.append(spec.golden_name)
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(temp_path.read_text(encoding="utf-8"), encoding="utf-8")

    manifest_path = golden_dir / "manifest.txt"
    manifest_path.write_text("\n".join(spec.golden_name for spec in OUTPUT_SPECS) + "\n", encoding="utf-8")

    for filename in changed:
        print(f"Updated golden: {filename}")

    for path in temp_dir.glob("*"):
        path.unlink()
    temp_dir.rmdir()


if __name__ == "__main__":
    main()
