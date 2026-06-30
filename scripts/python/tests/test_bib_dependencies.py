# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from generate_bib_deps import (  # noqa: E402
    CitationSelection,
    build_fingerprint,
    generate_fingerprint,
    iter_citation_ids,
    read_bibliography_entries,
    render_fingerprint,
    select_citations,
    write_if_changed,
)


def test_iter_citation_ids_finds_nested_citations():
    pandoc_json = {
        "blocks": [
            {
                "t": "Para",
                "c": [
                    {
                        "t": "Cite",
                        "c": [
                            [
                                {"citationId": "alpha"},
                                {"citationId": "beta"},
                            ],
                            [{"t": "Str", "c": "[@alpha; @beta]"}],
                        ],
                    }
                ],
            },
            {
                "t": "Table",
                "c": [
                    {
                        "body": [
                            {
                                "t": "Cite",
                                "c": [
                                    [{"citationId": "nested"}],
                                    [{"t": "Str", "c": "[@nested]"}],
                                ],
                            }
                        ]
                    }
                ],
            },
        ],
    }

    assert iter_citation_ids(pandoc_json) == ["alpha", "beta", "nested"]


def test_select_citations_handles_nocite_all_and_de_duplicates():
    selection = select_citations(["alpha", "beta", "alpha", "*", "gamma"])

    assert selection == CitationSelection(
        keys=("alpha", "beta", "gamma"),
        include_all=True,
    )


def test_render_fingerprint_tracks_only_selected_entries(tmp_path):
    content_root = tmp_path / "content"
    document_path = content_root / "src/doc-a.md"
    bib_path = content_root / "src/refs.bib"
    entries = {
        "alpha": {"id": "alpha", "title": "Alpha"},
        "beta": {"id": "beta", "title": "Beta"},
    }

    fingerprint = build_fingerprint(
        document_path=document_path,
        bib_files=[bib_path],
        selection=CitationSelection(keys=("alpha", "missing")),
        entries_by_id=entries,
        content_root=content_root,
    )
    rendered = render_fingerprint(fingerprint)
    decoded = json.loads(rendered)

    assert decoded["document"] == "src/doc-a.md"
    assert decoded["bib_files"] == ["src/refs.bib"]
    assert decoded["citation_keys"] == ["alpha", "missing"]
    assert decoded["selected_entry_ids"] == ["alpha"]
    assert decoded["missing_keys"] == ["missing"]
    assert decoded["entries"] == [{"id": "alpha", "title": "Alpha"}]
    assert "Beta" not in rendered


def test_nocite_all_selects_all_entries(tmp_path):
    content_root = tmp_path / "content"
    entries = {
        "beta": {"id": "beta", "title": "Beta"},
        "alpha": {"id": "alpha", "title": "Alpha"},
    }

    fingerprint = build_fingerprint(
        document_path=content_root / "src/doc.md",
        bib_files=[content_root / "src/refs.bib"],
        selection=CitationSelection(keys=(), include_all=True),
        entries_by_id=entries,
        content_root=content_root,
    )

    assert fingerprint["selected_entry_ids"] == ["alpha", "beta"]
    assert fingerprint["entries"] == [
        {"id": "alpha", "title": "Alpha"},
        {"id": "beta", "title": "Beta"},
    ]


def test_write_if_changed_preserves_mtime_for_unchanged_content(tmp_path):
    output = tmp_path / "fingerprint.json"

    assert write_if_changed(output, "same\n") is True
    original_mtime = output.stat().st_mtime_ns
    assert write_if_changed(output, "same\n") is False
    assert output.stat().st_mtime_ns == original_mtime

    time.sleep(0.01)
    assert write_if_changed(output, "different\n") is True
    assert output.stat().st_mtime_ns != original_mtime


def test_read_bibliography_entries_uses_last_duplicate_id_like_pandoc(tmp_path):
    if not shutil.which("pandoc"):
        pytest.skip("pandoc is required to parse BibTeX")

    bib_path = tmp_path / "dupe.bib"
    bib_path.write_text(
        "@article{alpha, title={Alpha}, author={A, Author}, year={2020}}\n"
        "@article{alpha, title={Alpha Two}, author={A, Author}, year={2021}}\n",
        encoding="utf-8",
    )

    entries = read_bibliography_entries([bib_path])

    assert entries["alpha"]["title"] == "Alpha two"


def test_generate_fingerprint_rewrites_only_when_selected_entries_change(tmp_path):
    if not shutil.which("pandoc"):
        pytest.skip("pandoc is required to parse Markdown and BibTeX")

    content_root = tmp_path / "content"
    src_dir = content_root / "src"
    src_dir.mkdir(parents=True)
    doc_a = src_dir / "doc-a.md"
    doc_b = src_dir / "doc-b.md"
    refs = src_dir / "refs.bib"
    out_a = content_root / "build/bib-deps/doc-a.refs.json"
    out_b = content_root / "build/bib-deps/doc-b.refs.json"
    doc_a.write_text("[@alpha]\n", encoding="utf-8")
    doc_b.write_text("[@beta]\n", encoding="utf-8")
    refs.write_text(_bibtex(alpha_title="Alpha", beta_title="Beta"), encoding="utf-8")

    generate_fingerprint(doc_a, out_a, content_root, [refs])
    generate_fingerprint(doc_b, out_b, content_root, [refs])
    original_a_mtime = out_a.stat().st_mtime_ns
    original_b_mtime = out_b.stat().st_mtime_ns

    time.sleep(0.01)
    refs.write_text(
        _bibtex(alpha_title="Alpha changed", beta_title="Beta"),
        encoding="utf-8",
    )
    generate_fingerprint(doc_a, out_a, content_root, [refs])
    generate_fingerprint(doc_b, out_b, content_root, [refs])

    assert out_a.stat().st_mtime_ns != original_a_mtime
    assert out_b.stat().st_mtime_ns == original_b_mtime
    assert "Alpha changed" in out_a.read_text(encoding="utf-8")
    assert "Alpha changed" not in out_b.read_text(encoding="utf-8")


def test_make_rebuilds_only_documents_whose_cited_bib_entries_change(tmp_path):
    missing_tools = [tool for tool in ("git", "make", "pandoc") if not shutil.which(tool)]
    if missing_tools:
        pytest.skip("missing tools: " + ", ".join(missing_tools))

    repo_root = Path(__file__).resolve().parents[3]
    content_root = tmp_path / "content"
    src_dir = content_root / "src"
    src_dir.mkdir(parents=True)
    (content_root / "Makefile").write_text(
        f"TOOLS_ROOT := {repo_root}\n"
        "CONTENT_ROOT := $(CURDIR)\n"
        "include $(TOOLS_ROOT)/Makefile\n",
        encoding="utf-8",
    )
    (src_dir / "doc-a.md").write_text(
        "---\n"
        "title: Doc A\n"
        "contact-email: docs@example.com\n"
        "bibliography: src/refs.bib\n"
        "---\n\n"
        "# Doc A\n\n"
        "Alpha citation [@alpha].\n",
        encoding="utf-8",
    )
    (src_dir / "doc-b.md").write_text(
        "---\n"
        "title: Doc B\n"
        "contact-email: docs@example.com\n"
        "bibliography: src/refs.bib\n"
        "---\n\n"
        "# Doc B\n\n"
        "Beta citation [@beta].\n",
        encoding="utf-8",
    )
    refs = src_dir / "refs.bib"
    refs.write_text(_bibtex(alpha_title="Alpha", beta_title="Beta"), encoding="utf-8")

    subprocess.run(["git", "init"], cwd=content_root, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "add", "."], cwd=content_root, check=True)
    subprocess.run(
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
        check=True,
        stdout=subprocess.PIPE,
    )

    subprocess.run(["make", "-C", str(content_root), "html"], check=True)

    time.sleep(1.1)
    refs.write_text(
        _bibtex(
            alpha_title="Alpha",
            beta_title="Beta",
            gamma_title="Gamma changed",
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["make", "-C", str(content_root), "html"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    # Make echoes recipes by default, so stdout shows whether the scanner or
    # Pandoc recipes ran. An uncited .bib change should rerun the scanner once
    # to refresh refs.checked, but it should not rebuild either HTML output.
    assert "generate_bib_deps.py" in result.stdout
    assert "doc-a.md -t html" not in result.stdout
    assert "doc-b.md -t html" not in result.stdout

    result = subprocess.run(
        ["make", "-C", str(content_root), "html"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    # With no further input changes, the fresh refs.checked stamps should keep
    # Make from rerunning generate_bib_deps.py.
    assert "generate_bib_deps.py" not in result.stdout
    assert "doc-a.md -t html" not in result.stdout
    assert "doc-b.md -t html" not in result.stdout

    time.sleep(1.1)
    refs.write_text(
        _bibtex(
            alpha_title="Alpha changed",
            beta_title="Beta",
            gamma_title="Gamma changed",
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["make", "-C", str(content_root), "html"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )

    assert "doc-a.md -t html" in result.stdout
    assert "doc-b.md -t html" not in result.stdout


def _bibtex(
    *,
    alpha_title: str,
    beta_title: str,
    gamma_title: str = "Gamma",
) -> str:
    return (
        "@article{alpha,\n"
        f"  title = {{{alpha_title}}},\n"
        "  author = {Author, Alice},\n"
        "  year = {2020}\n"
        "}\n\n"
        "@article{beta,\n"
        f"  title = {{{beta_title}}},\n"
        "  author = {Builder, Bob},\n"
        "  year = {2021}\n"
        "}\n\n"
        "@article{gamma,\n"
        f"  title = {{{gamma_title}}},\n"
        "  author = {Garcia, Gloria},\n"
        "  year = {2022}\n"
        "}\n"
    )
