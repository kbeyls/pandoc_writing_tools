# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

import os
import sys
import subprocess
import shutil
from pathlib import Path
import difflib
import pytest

# Add scripts/python to sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from regression.build_outputs import build_outputs
from regression.normalize_outputs import (
    OUTPUT_SPECS,
    normalize_html,
    normalize_native,
    normalize_outputs,
    normalize_tex,
)


def _env_flag(name: str, default: str = "0") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value not in {"0", "false", "no", ""}


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    result = subprocess.run(["docker", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_normalize_tex_replaces_escaped_feedback_versions(tmp_path):
    source = (
        "Version 12-with-local-changes\n"
        r"\href{mailto:docs@example.com?subject=Feature\%20Demo\%20v12-with-local-changes\%20-&body=Feature\%20Demo\%27\%20v12-with-local-changes.\%0D}{feedback}"
        "\n"
        "abcv12.\n"
    )
    path = tmp_path / "sample.tex"
    path.write_text(source, encoding="utf-8")

    assert normalize_tex(path) == (
        "Version <VER>\n"
        r"\href{mailto:docs@example.com?subject=Feature\%20Demo\%20v<VER>\%20-&body=Feature\%20Demo\%27\%20v<VER>.\%0D}{feedback}"
        "\n"
        "abcv12.\n"
    )


def test_normalize_outputs_canonicalizes_last_updated_metadata(tmp_path):
    html_path = tmp_path / "sample.html"
    html_path.write_text(
        "<p>Last updated: Wed Jun 3 13:58:38 2026 +0100</p>\n"
        "<p>Last updated: </p>\n",
        encoding="utf-8",
    )

    assert normalize_html(html_path) == (
        "<p>Last updated: <DATE></p>\n"
        "<p>Last updated: <DATE></p>\n"
    )

    native_path = tmp_path / "sample.native"
    native_path.write_text(
        '( "LAST_UPDATED" , MetaString "" )\n'
        '( "LAST_UPDATED"\n'
        '  , MetaString "Wed Jun 3 13:58:38 2026 +0100"\n'
        '  )\n'
        'Str "LAST_UPDATED="\n'
        'Str "LAST_UPDATED:Wed Jun 3 13:58:38 2026 +0100"\n'
        '[ Para\n'
        '    [ Str "VERSION=1"\n'
        '    , SoftBreak\n'
        '    , Str "LAST_UPDATED=Wed"\n'
        '    , Space\n'
        '    , Str "Jun"\n'
        '    ]\n'
        ']\n',
        encoding="utf-8",
    )

    assert normalize_native(native_path) == (
        '( "LAST_UPDATED" , MetaString "<DATE>" )\n'
        '( "LAST_UPDATED" , MetaString "<DATE>" )\n'
        'Str "LAST_UPDATED:<DATE>"\n'
        'Str "LAST_UPDATED:<DATE>"\n'
        '[ Para [ Str "VERSION:<VER>" , SoftBreak , Str "LAST_UPDATED:<DATE>" ]\n'
        '  ]\n'
    )


def test_regression_outputs(tmp_path):
    use_docker = _env_flag("PANDOC_REGRESSION_USE_DOCKER", "1")
    skip_build = _env_flag("PANDOC_REGRESSION_SKIP_BUILD", "0")
    fixture_override = os.getenv("PANDOC_REGRESSION_FIXTURE")

    repo_root = Path(__file__).resolve().parents[3]
    fixture_root = Path(fixture_override).resolve() if fixture_override else repo_root / "examples/feature-demo"

    if use_docker and not _docker_available():
        pytest.skip("Docker unavailable; set PANDOC_REGRESSION_USE_DOCKER=0 to run locally.")

    build_dir = fixture_root / "build"
    if not skip_build:
        build_dir = build_outputs(fixture_root=fixture_root, use_docker=use_docker, targets=["all"])

    normalized_dir = tmp_path / "normalized"
    normalize_outputs(build_dir, normalized_dir)

    golden_dir = repo_root / "scripts/python/tests/fixtures/regression/feature-demo"
    missing = [spec.golden_name for spec in OUTPUT_SPECS if not (golden_dir / spec.golden_name).exists()]
    if missing:
        raise AssertionError(
            "Missing golden outputs: " + ", ".join(missing) + ". Run update_regression_goldens.py --accept."
        )

    for spec in OUTPUT_SPECS:
        golden_path = golden_dir / spec.golden_name
        current_path = normalized_dir / spec.golden_name
        golden_text = _read_text(golden_path)
        current_text = _read_text(current_path)
        if golden_text != current_text:
            diff_lines = list(
                difflib.unified_diff(
                    golden_text.splitlines(),
                    current_text.splitlines(),
                    fromfile=str(golden_path),
                    tofile=str(current_path),
                    lineterm="",
                )
            )
            diff = "\n".join(diff_lines)
            diff_path = tmp_path / f"{spec.golden_name}.diff"
            diff_path.write_text(diff, encoding="utf-8")
            preview_lines = 25
            preview = "\n".join(diff_lines[:preview_lines])
            print(
                f"\nRegression output mismatch for {spec.golden_name}. "
                f"Diff saved to {diff_path}. "
                f"First {preview_lines} lines:\n{preview}"
            )
            pytest.fail(f"Regression output mismatch for {spec.golden_name}; diff saved to {diff_path}")
