# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _run(
    args: list[str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _write_content_makefile(content_root: Path, tools_root: Path) -> None:
    (content_root / "Makefile").write_text(
        f"TOOLS_ROOT := {tools_root}\n"
        "CONTENT_ROOT := $(CURDIR)\n"
        "include $(TOOLS_ROOT)/Makefile\n",
        encoding="utf-8",
    )


def _commit_fixture_repo(content_root: Path) -> None:
    _run(["git", "init"], cwd=content_root)
    _run(["git", "add", "."], cwd=content_root)
    _run(
        [
            "git",
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--no-gpg-sign",
            "-m",
            "init",
        ],
        cwd=content_root,
    )


def _make(
    content_root: Path,
    *targets: str,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    args = ["make", "-C", str(content_root), "PYTHON_RUNNER=python3"]
    if dry_run:
        args.append("-n")
    args.extend(targets)
    return _run(args, cwd=content_root)


def test_newer_bib_checked_stamp_does_not_rebuild_document(tmp_path: Path) -> None:
    missing_tools = [tool for tool in ("git", "make", "pandoc") if not shutil.which(tool)]
    if missing_tools:
        pytest.skip("missing tools: " + ", ".join(missing_tools))

    tools_root = Path(__file__).resolve().parents[3]
    content_root = tmp_path / "content"
    src_dir = content_root / "src"
    src_dir.mkdir(parents=True)
    _write_content_makefile(content_root, tools_root)
    (src_dir / "doc.md").write_text(
        "---\n"
        "title: Doc\n"
        "contact-email: docs@example.com\n"
        "bibliography: src/refs.bib\n"
        "---\n\n"
        "# Doc\n\n"
        "Alpha citation [@alpha].\n",
        encoding="utf-8",
    )
    (src_dir / "refs.bib").write_text(
        "@article{alpha,\n"
        "  title = {Alpha},\n"
        "  author = {Author, Alice},\n"
        "  year = {2020}\n"
        "}\n",
        encoding="utf-8",
    )
    _commit_fixture_repo(content_root)

    _make(content_root, "html")

    refs_json = content_root / "build/bib-deps/doc.refs.json"
    refs_checked = content_root / "build/bib-deps/doc.refs.checked"
    future = max(refs_json.stat().st_mtime, refs_checked.stat().st_mtime) + 10
    os.utime(refs_checked, (future, future))

    # The checked stamp only means "the scanner examined the current inputs".
    # It must not make document outputs rebuild when the JSON fingerprint, the
    # file that represents citation content, is unchanged.
    result = _make(content_root, "html", dry_run=True)

    assert "doc.md -t html" not in result.stdout


def test_unchanged_metadata_check_does_not_rebuild_document(tmp_path: Path) -> None:
    missing_tools = [tool for tool in ("git", "make", "pandoc") if not shutil.which(tool)]
    if missing_tools:
        pytest.skip("missing tools: " + ", ".join(missing_tools))

    tools_root = Path(__file__).resolve().parents[3]
    content_root = tmp_path / "content"
    src_dir = content_root / "src"
    src_dir.mkdir(parents=True)
    _write_content_makefile(content_root, tools_root)
    (src_dir / "doc.md").write_text(
        "---\n"
        "title: Doc\n"
        "contact-email: docs@example.com\n"
        "---\n\n"
        "# Doc\n",
        encoding="utf-8",
    )
    _commit_fixture_repo(content_root)

    _make(content_root, "html")

    old_mtime = (tools_root / "Makefile").stat().st_mtime - 10
    for path in [
        content_root / "build/.githash-doc.stamp",
        content_root / "build/.version-doc.stamp",
        content_root / "build/.githash-doc.checked",
        content_root / "build/.version-doc.checked",
    ]:
        if path.exists():
            os.utime(path, (old_mtime, old_mtime))

    # The checked files may need to run because the tools Makefile is newer.
    # If the recomputed metadata bytes match the existing content stamps, the
    # document output must remain up to date.
    result = _make(content_root, "html")

    assert (content_root / "build/.githash-doc.stamp").stat().st_mtime == old_mtime
    assert (content_root / "build/.version-doc.stamp").stat().st_mtime == old_mtime
    assert (content_root / "build/.githash-doc.checked").stat().st_mtime > old_mtime
    assert (content_root / "build/.version-doc.checked").stat().st_mtime > old_mtime
    assert "doc.md -t html" not in result.stdout


def test_email_html_intermediate_survives_eml_build(tmp_path: Path) -> None:
    missing_tools = [tool for tool in ("git", "make", "pandoc") if not shutil.which(tool)]
    if missing_tools:
        pytest.skip("missing tools: " + ", ".join(missing_tools))

    tools_root = Path(__file__).resolve().parents[3]
    content_root = tmp_path / "content"
    src_dir = content_root / "src"
    src_dir.mkdir(parents=True)
    _write_content_makefile(content_root, tools_root)
    (src_dir / "doc.md").write_text(
        "---\n"
        "title: Doc\n"
        "contact-email: docs@example.com\n"
        "---\n\n"
        "# Doc\n",
        encoding="utf-8",
    )
    _commit_fixture_repo(content_root)

    _make(content_root, "eml")

    email_html = content_root / "build/doc.email.html"
    assert email_html.exists()

    # The email HTML file is a generated prerequisite for the EML target. If
    # Make deletes it as an intermediate, a second no-change EML build has to
    # rerun Pandoc and render_email.py instead of proving the EML is current.
    result = _make(content_root, "eml", dry_run=True)

    assert "doc.md -t html" not in result.stdout
    assert "render_email.py" not in result.stdout
