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
    ImageReference,
    collect_make_dependencies,
    drawio_dependency,
    iter_image_references,
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


def test_iter_image_references_preserves_classes():
    pandoc_json = {
        "blocks": [
            {
                "t": "Para",
                "c": [
                    {
                        "t": "Image",
                        "c": [
                            ["figure", ["no-drawio", "thumbnail"], []],
                            [],
                            ["build/img/graph", ""],
                        ],
                    }
                ],
            }
        ]
    }

    assert iter_image_references(pandoc_json) == [
        ImageReference("build/img/graph", frozenset({"no-drawio", "thumbnail"}))
    ]


def test_drawio_dependency_finds_only_dot_backed_logical_images(tmp_path):
    content_root = tmp_path / "content"
    image_dir = content_root / "src/img"
    image_dir.mkdir(parents=True)
    reference = ImageReference("build/img/graph", frozenset())

    assert drawio_dependency(
        reference,
        content_root=content_root,
        build_dir=content_root / "build",
    ) is None

    (image_dir / "graph.dot").write_text("digraph G {}\n", encoding="utf-8")
    assert drawio_dependency(
        reference,
        content_root=content_root,
        build_dir=content_root / "build",
    ) == content_root / "build/img/graph.drawio"
    assert drawio_dependency(
        ImageReference("build/img/graph.png", frozenset()),
        content_root=content_root,
        build_dir=content_root / "build",
    ) is None


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


def test_collect_make_dependencies_adds_drawio_candidates_only_to_xhtml(tmp_path):
    if not shutil.which("pandoc"):
        pytest.skip("pandoc is required to parse Markdown into JSON")

    content_root = tmp_path / "content"
    src_dir = content_root / "src"
    image_dir = src_dir / "img"
    image_dir.mkdir(parents=True)
    (src_dir / "doc.md").write_text(
        "![Linked](build/img/linked)\n\n"
        "![Unlinked](build/img/unlinked)\n\n"
        "![Disabled](build/img/disabled){.no-drawio}\n",
        encoding="utf-8",
    )
    (image_dir / "linked.dot").write_text(
        'digraph G { a [URL="https://example.com"]; }\n', encoding="utf-8"
    )
    (image_dir / "unlinked.dot").write_text("digraph G { a; }\n", encoding="utf-8")
    (image_dir / "disabled.dot").write_text(
        'digraph G { a [URL="https://example.com"]; }\n', encoding="utf-8"
    )

    rendered = render_makefile(
        collect_make_dependencies(
            content_root=content_root,
            src_dir=src_dir,
            build_dir=content_root / "build",
        )
    )

    xhtml_rule = next(
        line for line in rendered.splitlines() if "$(BUILD_DIR)/doc.xhtml:" in line
    )
    html_rule = next(
        line for line in rendered.splitlines() if "$(BUILD_DIR)/doc.html:" in line
    )
    assert "$(BUILD_IMG_DIR)/linked.drawio" in xhtml_rule
    assert "$(BUILD_IMG_DIR)/linked.png" in xhtml_rule
    assert "$(BUILD_IMG_DIR)/unlinked.drawio" in xhtml_rule
    assert "disabled.drawio" not in xhtml_rule
    assert "drawio" not in html_rule


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


def test_make_builds_logical_image_from_excalidraw_svg_source(tmp_path):
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
    (src_dir / "doc.md").write_text(
        "---\n"
        "title: Doc\n"
        "contact-email: docs@example.com\n"
        "---\n\n"
        "# Doc\n\n"
        "![Excalidraw export](build/img/diagram)\n",
        encoding="utf-8",
    )
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>\n'
    source_svg = img_dir / "diagram.excalidraw.svg"
    source_svg.write_text(svg, encoding="utf-8")

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

    # The source keeps the Excalidraw-specific suffix for editor tooling, while
    # the built file uses the logical image stem referenced from Markdown.
    built_svg = content_root / "build/img/diagram.svg"
    assert built_svg.read_text(encoding="utf-8") == svg
    assert (content_root / "build/doc.html").exists()


def test_make_builds_graphviz_source_in_all_output_formats(tmp_path):
    missing_tools = [tool for tool in ("git", "make") if not shutil.which(tool)]
    if missing_tools:
        pytest.skip("missing tools: " + ", ".join(missing_tools))

    repo_root = Path(__file__).resolve().parents[3]
    content_root = tmp_path / "content"
    img_dir = content_root / "src/img"
    img_dir.mkdir(parents=True)
    (content_root / "Makefile").write_text(
        f"TOOLS_ROOT := {repo_root}\n"
        "CONTENT_ROOT := $(CURDIR)\n"
        "include $(TOOLS_ROOT)/Makefile\n",
        encoding="utf-8",
    )
    source_dot = img_dir / "diagram.dot"
    source_dot.write_text("digraph G { input -> output; }\n", encoding="utf-8")

    invocation_log = tmp_path / "graphviz-invocations.log"
    fake_dot = tmp_path / "fake-dot"
    fake_dot.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "format=${1#-T}\n"
        "source=$2\n"
        "output=$4\n"
        'printf "%s\\n" "$format" >> "$GRAPHVIZ_TEST_LOG"\n'
        "{\n"
        '  printf "format=%s\\n" "$format"\n'
        '  cat "$source"\n'
        '} > "$output"\n',
        encoding="utf-8",
    )
    fake_dot.chmod(0o755)

    subprocess.run(["git", "init"], cwd=content_root, check=True, stdout=subprocess.PIPE)

    targets = [
        str(content_root / f"build/img/diagram.{extension}")
        for extension in ("svg", "pdf", "png")
    ]
    command = [
        "make",
        "-C",
        str(content_root),
        f"PYTHON_RUNNER={sys.executable}",
        f"GRAPHVIZ_DOT={fake_dot}",
        *targets,
    ]
    environment = os.environ.copy()
    environment["GRAPHVIZ_TEST_LOG"] = str(invocation_log)

    subprocess.run(command, check=True, env=environment)

    for extension in ("svg", "pdf", "png"):
        rendered = content_root / f"build/img/diagram.{extension}"
        assert rendered.read_text(encoding="utf-8").startswith(
            f"format={extension}\n"
        )
    assert invocation_log.read_text(encoding="utf-8").splitlines() == [
        "svg",
        "pdf",
        "png",
    ]

    subprocess.run(command, check=True, env=environment)
    assert invocation_log.read_text(encoding="utf-8").splitlines() == [
        "svg",
        "pdf",
        "png",
    ]

    time.sleep(1.1)
    source_dot.write_text("digraph G { input -> middle -> output; }\n", encoding="utf-8")
    subprocess.run(command, check=True, env=environment)
    assert invocation_log.read_text(encoding="utf-8").splitlines() == [
        "svg",
        "pdf",
        "png",
        "svg",
        "pdf",
        "png",
    ]


def test_make_builds_drawio_sidecar_incrementally(tmp_path):
    missing_tools = [tool for tool in ("git", "make") if not shutil.which(tool)]
    if missing_tools:
        pytest.skip("missing tools: " + ", ".join(missing_tools))

    repo_root = Path(__file__).resolve().parents[3]
    content_root = tmp_path / "content"
    image_dir = content_root / "src/img"
    image_dir.mkdir(parents=True)
    (content_root / "Makefile").write_text(
        f"TOOLS_ROOT := {repo_root}\n"
        "CONTENT_ROOT := $(CURDIR)\n"
        "include $(TOOLS_ROOT)/Makefile\n",
        encoding="utf-8",
    )
    source = image_dir / "linked.dot"
    source.write_text(
        'digraph G { a [URL="https://example.com"]; }\n', encoding="utf-8"
    )

    invocation_log = tmp_path / "drawio-graphviz.log"
    fake_dot = tmp_path / "fake-dot.py"
    fake_dot.write_text(
        f"#!{sys.executable}\n"
        "import os, struct, sys\n"
        "fmt = sys.argv[1][2:]\n"
        "output = sys.argv[4]\n"
        "with open(os.environ['GRAPHVIZ_TEST_LOG'], 'a') as log: log.write(fmt + '\\n')\n"
        "if fmt == 'svg': data = b'<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"100\" height=\"50\" />'\n"
        "elif fmt == 'png': data = b'\\x89PNG\\r\\n\\x1a\\n' + struct.pack('>I4sII', 13, b'IHDR', 100, 50)\n"
        "elif fmt == 'cmapx': data = b'<map><area shape=\"rect\" id=\"node1\" href=\"https://example.com\" title=\"Example\" coords=\"10,10,40,30\"/></map>'\n"
        "else: raise SystemExit('unexpected format: ' + fmt)\n"
        "open(output, 'wb').write(data)\n",
        encoding="utf-8",
    )
    fake_dot.chmod(0o755)
    subprocess.run(["git", "init"], cwd=content_root, check=True, stdout=subprocess.PIPE)

    target = content_root / "build/img/linked.drawio"
    command = [
        "make",
        "-C",
        str(content_root),
        f"PYTHON_RUNNER={sys.executable}",
        f"GRAPHVIZ_DOT={fake_dot}",
        str(target),
    ]
    environment = os.environ.copy()
    environment["GRAPHVIZ_TEST_LOG"] = str(invocation_log)

    subprocess.run(command, check=True, env=environment)
    assert target.exists()
    assert b"https://example.com" in target.read_bytes()
    assert sorted(invocation_log.read_text(encoding="utf-8").splitlines()) == [
        "cmapx",
        "png",
        "svg",
    ]

    original_mtime = target.stat().st_mtime_ns
    subprocess.run(command, check=True, env=environment)
    assert target.stat().st_mtime_ns == original_mtime
    assert sorted(invocation_log.read_text(encoding="utf-8").splitlines()) == [
        "cmapx",
        "png",
        "svg",
    ]

    time.sleep(1.1)
    source.write_text('digraph G { b [URL="https://example.com"]; }\n', encoding="utf-8")
    subprocess.run(command, check=True, env=environment)
    assert sorted(invocation_log.read_text(encoding="utf-8").splitlines()) == [
        "cmapx",
        "cmapx",
        "png",
        "png",
        "svg",
        "svg",
    ]
