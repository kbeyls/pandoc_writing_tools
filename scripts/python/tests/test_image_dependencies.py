# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from generate_image_deps import (  # noqa: E402
    collect_make_dependencies,
    iter_image_targets,
    make_variable_path,
    render_makefile,
    resolve_image_target,
)


def test_iter_image_targets_finds_nested_images():
    pandoc_json = {
        "blocks": [
            {"t": "Para", "c": [{"t": "Str", "c": "text"}]},
            {
                "t": "Table",
                "c": [
                    {
                        "body": [
                            {
                                "t": "Image",
                                "c": [
                                    ["", [], []],
                                    [],
                                    ["build/img/table-figure", ""],
                                ],
                            }
                        ]
                    }
                ],
            },
            {
                "t": "Div",
                "c": [
                    ["", [], []],
                    [
                        {
                            "t": "Plain",
                            "c": [
                                {
                                    "t": "Image",
                                    "c": [
                                        ["", [], []],
                                        [],
                                        ["build/img/div-figure.png", ""],
                                    ],
                                }
                            ],
                        }
                    ],
                ],
            },
        ]
    }

    assert iter_image_targets(pandoc_json) == [
        "build/img/table-figure",
        "build/img/div-figure.png",
    ]


def test_resolve_image_target_maps_supported_prefixes(tmp_path):
    content_root = tmp_path / "content"
    build_dir = content_root / "build"

    assert resolve_image_target(
        "build/img/figure",
        content_root=content_root,
        build_dir=build_dir,
        default_extension="pdf",
    ) == build_dir / "img/figure.pdf"
    assert resolve_image_target(
        "build/img/figure.png",
        content_root=content_root,
        build_dir=build_dir,
        default_extension="pdf",
    ) == build_dir / "img/figure.png"
    assert resolve_image_target(
        "src/img/figure",
        content_root=content_root,
        build_dir=build_dir,
        default_extension="svg",
    ) == build_dir / "img/figure.svg"
    assert resolve_image_target(
        "img/nested/figure",
        content_root=content_root,
        build_dir=build_dir,
        default_extension="png",
    ) == build_dir / "img/nested/figure.png"


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com/image.png",
        "http://example.com/image.png",
        "mailto:docs@example.com",
        "data:image/png;base64,AAAA",
        "//example.com/image.png",
    ],
)
def test_resolve_image_target_ignores_remote_targets(tmp_path, target):
    content_root = tmp_path / "content"

    assert resolve_image_target(
        target,
        content_root=content_root,
        build_dir=content_root / "build",
        default_extension="png",
    ) is None


def test_make_variable_path_uses_make_variables(tmp_path):
    content_root = tmp_path / "content"
    build_dir = content_root / "build"

    assert (
        make_variable_path(build_dir / "img/figure.svg", content_root, build_dir)
        == "$(BUILD_IMG_DIR)/figure.svg"
    )
    assert (
        make_variable_path(build_dir / "doc.html", content_root, build_dir)
        == "$(BUILD_DIR)/doc.html"
    )
    assert (
        make_variable_path(content_root / "src/doc.md", content_root, build_dir)
        == "$(SRC_DIR)/doc.md"
    )
    assert (
        make_variable_path(content_root / "notes/file.txt", content_root, build_dir)
        == "$(CONTENT_ROOT)/notes/file.txt"
    )


def test_render_makefile_groups_targets_with_same_prerequisites():
    rendered = render_makefile(
        {
            "$(BUILD_DIR)/doc.tex": {"$(BUILD_IMG_DIR)/figure.pdf"},
            "$(BUILD_DIR)/doc.pdf": {"$(BUILD_IMG_DIR)/figure.pdf"},
            "$(BUILD_DIR)/doc.html": {"$(BUILD_IMG_DIR)/figure.svg"},
        }
    )

    assert "$(BUILD_DIR)/doc.html: $(BUILD_IMG_DIR)/figure.svg\n" in rendered
    assert (
        "$(BUILD_DIR)/doc.pdf $(BUILD_DIR)/doc.tex: $(BUILD_IMG_DIR)/figure.pdf\n"
        in rendered
    )
    assert "/tmp/" not in rendered


def test_collect_make_dependencies_is_per_document(tmp_path):
    if not shutil.which("pandoc"):
        pytest.skip("pandoc is required to parse Markdown into JSON")

    content_root = tmp_path / "content"
    src_dir = content_root / "src"
    (src_dir / "img").mkdir(parents=True)
    (src_dir / "doc-a.md").write_text("![A](build/img/a)\n", encoding="utf-8")
    (src_dir / "doc-b.md").write_text("![B](build/img/b.png)\n", encoding="utf-8")

    dependencies = collect_make_dependencies(
        content_root=content_root,
        src_dir=src_dir,
        build_dir=content_root / "build",
    )
    rendered = render_makefile(dependencies)

    assert "$(BUILD_DIR)/doc-a.html: $(BUILD_IMG_DIR)/a.svg\n" in rendered
    assert "$(BUILD_DIR)/doc-a.pdf $(BUILD_DIR)/doc-a.tex: $(BUILD_IMG_DIR)/a.pdf\n" in rendered
    assert "$(BUILD_DIR)/doc-b.html" in rendered
    assert "$(BUILD_IMG_DIR)/b.png" in rendered
    assert "$(BUILD_DIR)/doc-a.html: $(BUILD_IMG_DIR)/b.png" not in rendered
    assert "$(BUILD_DIR)/doc-b.html: $(BUILD_IMG_DIR)/a.svg" not in rendered


def test_make_dry_run_rebuilds_only_document_for_touched_image(tmp_path):
    missing_tools = [tool for tool in ("git", "make", "pandoc") if not shutil.which(tool)]
    if missing_tools:
        pytest.skip("missing tools: " + ", ".join(missing_tools))

    repo_root = Path(__file__).resolve().parents[3]
    content_root = tmp_path / "content"
    src_dir = content_root / "src"
    img_dir = src_dir / "img"
    img_dir.mkdir(parents=True)
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
        "---\n\n"
        "# Doc A\n\n"
        "![A](build/img/a)\n",
        encoding="utf-8",
    )
    (src_dir / "doc-b.md").write_text(
        "---\n"
        "title: Doc B\n"
        "contact-email: docs@example.com\n"
        "---\n\n"
        "# Doc B\n\n"
        "![B](build/img/b)\n",
        encoding="utf-8",
    )
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>\n'
    (img_dir / "a.svg").write_text(svg, encoding="utf-8")
    (img_dir / "b.svg").write_text(svg, encoding="utf-8")

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
    (src_dir / "doc-c.md").write_text(
        "---\n"
        "title: Doc C\n"
        "contact-email: docs@example.com\n"
        "---\n\n"
        "# Doc C\n\n"
        "![C](build/img/c)\n",
        encoding="utf-8",
    )
    (img_dir / "c.svg").write_text(svg, encoding="utf-8")
    subprocess.run(["make", "-C", str(content_root), "html"], check=True)
    result = subprocess.run(
        ["make", "-C", str(content_root), "-n", "html"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )

    assert "doc-a.md -t html" not in result.stdout
    assert "doc-b.md -t html" not in result.stdout

    future = time.time() + 5
    os.utime(img_dir / "a.svg", (future, future))
    result = subprocess.run(
        ["make", "-C", str(content_root), "-n", "html"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )

    assert "doc-a.md -t html" in result.stdout
    assert "doc-b.md -t html" not in result.stdout
