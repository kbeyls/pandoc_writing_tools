# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


pytestmark = pytest.mark.regression
DOCKER_IMAGE = "pandoc_writing_tools_build"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    result = subprocess.run(
        ["docker", "version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def run_checked(
    command: list[str],
    *,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        pytest.fail(
            "Command failed with exit code "
            f"{result.returncode}: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


@pytest.fixture(scope="session")
def docker_pandoc_image() -> str:
    if not docker_available():
        pytest.skip("Docker is required for Confluence writer tests")

    root = repo_root()
    run_checked(
        [
            "docker",
            "build",
            "-f",
            str(root / "docker/Dockerfile"),
            "-t",
            DOCKER_IMAGE,
            str(root),
        ]
    )
    return DOCKER_IMAGE


def render_confluence(
    markdown: str,
    docker_pandoc_image: str,
    *,
    lua_filters: tuple[str, ...] = (),
) -> str:
    result = run_confluence(
        markdown,
        docker_pandoc_image,
        lua_filters=lua_filters,
    )
    if result.returncode != 0:
        pytest.fail(
            "Pandoc failed with exit code "
            f"{result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def run_confluence(
    markdown: str,
    docker_pandoc_image: str,
    *,
    lua_filters: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    root = repo_root()
    command = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--mount",
        f"type=bind,source={root},target=/src",
        "--workdir",
        "/src",
        "--entrypoint",
        "pandoc",
        docker_pandoc_image,
        "--from",
        "markdown-example_lists",
        "--to",
        "/src/theme/confluence.lua",
    ]
    for lua_filter in lua_filters:
        command.extend(["--lua-filter", f"/src/{lua_filter}"])
    return subprocess.run(
        command,
        input=markdown,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_confluence_writer_renders_inline_math(docker_pandoc_image):
    output = render_confluence("Inline $a < b & c > d$ here.\n", docker_pandoc_image)

    assert '<span class="math inline">a &lt; b &amp; c &gt; d</span>' in output
    assert "<p>Inline " in output


def test_confluence_writer_renders_display_math_as_block(docker_pandoc_image):
    output = render_confluence("$$\nx < y & y > z\n$$\n", docker_pandoc_image)

    assert '<div class="math display">\nx &lt; y &amp; y &gt; z\n</div>' in output
    assert '<p><div class="math display">' not in output
    assert '</div></p>' not in output


def test_confluence_writer_automatically_renders_linked_sidecar_as_macro(
    docker_pandoc_image,
):
    fixture = "scripts/python/tests/fixtures/confluence_drawio_server/example-diagram"
    output = render_confluence(
        f"![Linked graph]({fixture}){{confluence-width=880px}}\n",
        docker_pandoc_image,
    )

    assert '<ac:structured-macro ac:name="drawio"' in output
    assert (
        f'<ac:parameter ac:name="diagramName">{fixture}.drawio</ac:parameter>'
        in output
    )
    assert '<ac:parameter ac:name="width">880</ac:parameter>' in output
    assert '<ac:image' not in output


def test_confluence_writer_honors_no_drawio_opt_out(docker_pandoc_image):
    fixture = "scripts/python/tests/fixtures/confluence_drawio_server/example-diagram"
    output = render_confluence(
        f"![Linked graph]({fixture}){{.no-drawio}}\n",
        docker_pandoc_image,
    )

    assert 'ac:name="drawio"' not in output
    assert f'ri:filename="{fixture}"' in output


def test_confluence_writer_keeps_unlinked_sidecar_as_ordinary_image(
    docker_pandoc_image,
):
    fixture = "scripts/python/tests/fixtures/confluence_drawio_server/unlinked-diagram"
    output = render_confluence(
        f"![Unlinked graph]({fixture})\n",
        docker_pandoc_image,
    )

    assert 'ac:name="drawio"' not in output
    assert f'ri:filename="{fixture}"' in output


def test_confluence_writer_keeps_ordinary_image_output(docker_pandoc_image):
    output = render_confluence(
        "Before ![Ordinary](build/img/ordinary.png) after.\n",
        docker_pandoc_image,
    )

    assert (
        '<ac:image ac:width="440"><ri:attachment '
        'ri:filename="build/img/ordinary.png"/></ac:image>'
    ) in output
    assert 'ac:name="drawio"' not in output


def test_confluence_writer_honors_custom_ordinary_image_width(
    docker_pandoc_image,
):
    output = render_confluence(
        "![Compact](build/img/compact.png){confluence-width=220px}\n",
        docker_pandoc_image,
    )

    assert (
        '<ac:image ac:width="220"><ri:attachment '
        'ri:filename="build/img/compact.png"/></ac:image>'
    ) in output


def test_confluence_writer_rejects_invalid_image_width(
    docker_pandoc_image,
):
    for invalid_width in ["0px", "800", "50%", "1.5px", "-1px", "wide"]:
        result = run_confluence(
            "![Invalid](build/img/invalid.png)"
            f"{{confluence-width={invalid_width}}}\n",
            docker_pandoc_image,
        )

        assert result.returncode != 0
        assert "invalid confluence-width value" in result.stderr
        assert "confluence-width=880px" in result.stderr


def test_confluence_writer_indents_each_toc_header_level(
    docker_pandoc_image,
):
    output = render_confluence(
        """::: {toc-list-top-level=#root toc-list-entry-levels=2-4}
:::

# Root {#root}

## Parent {#parent}

### Child {#child}

#### Grandchild {#grandchild}

## Sibling {#sibling}

### Sibling child {#sibling-child}
""",
        docker_pandoc_image,
        lua_filters=("theme/toc.lua",),
    )

    toc_output = output.split('<h1 id="root">', maxsplit=1)[0]
    indentation_marker = '<div style="margin-left: 40px;">'

    def indentation_at(anchor: str) -> int:
        preceding_output = toc_output.split(
            f'<ac:link ac:anchor="{anchor}">',
            maxsplit=1,
        )[0]
        return preceding_output.count(indentation_marker) - preceding_output.count(
            "</div>"
        )

    assert indentation_at("parent") == 1
    assert indentation_at("child") == 2
    assert indentation_at("grandchild") == 3
    assert indentation_at("sibling") == 1
    assert indentation_at("sibling-child") == 2


@pytest.mark.parametrize(
    ("start_id", "entry_levels", "headings", "expected_links"),
    [
        pytest.param(
            "", "1-4",
            "## Intro {#intro}\n\n#### Details {#details}\n\n"
            "## Next {#next}\n\n# References {#references}\n",
            [("intro", 1), ("details", 2), ("next", 1), ("references", 1)],
            id="document-starts-below-minimum-level",
        ),
        pytest.param(
            "#root", "2-4",
            "# Root {#root}\n\n### First {#first}\n\n"
            "#### Child {#child}\n\n## Sibling {#sibling}\n\n"
            "# Outside {#outside}\n\n## After {#after}\n",
            [("first", 1), ("child", 2), ("sibling", 1)],
            id="subtree-starts-below-minimum-level",
        ),
        pytest.param(
            "", "1-4",
            "# Root {#root}\n\n### Child {#child}\n\n"
            "#### Grandchild {#grandchild}\n\n## Sibling {#sibling}\n",
            [("root", 1), ("child", 2), ("grandchild", 3), ("sibling", 2)],
            id="skipped-intermediate-level",
        ),
        pytest.param(
            "", "1-3",
            "# First {#first}\n\n## Old child {#old-child}\n\n"
            "# Second {#second}\n\n### New child {#new-child}\n",
            [("first", 1), ("old-child", 2), ("second", 1), ("new-child", 2)],
            id="previous-section-is-not-a-parent",
        ),
        pytest.param(
            "", "1-4",
            "# Root {#root}\n\n## First {#first}\n\n"
            "### Old child {#old-child}\n\n## Second {#second}\n\n"
            "#### New child {#new-child}\n",
            [("root", 1), ("first", 2), ("old-child", 3),
             ("second", 2), ("new-child", 3)],
            id="previous-subsection-is-not-a-parent",
        ),
        pytest.param(
            "", "2-4",
            "# Excluded first {#excluded-first}\n\n## First {#first}\n\n"
            "### Old child {#old-child}\n\n# Excluded second {#excluded-second}\n\n"
            "### Second {#second}\n\n#### New child {#new-child}\n",
            [("first", 1), ("old-child", 2), ("second", 1), ("new-child", 2)],
            id="excluded-headings-end-previous-sections",
        ),
        pytest.param(
            "", "1-3",
            "### First {#first}\n\n### Second {#second}\n\n### Third {#third}\n",
            [("first", 1), ("second", 1), ("third", 1)],
            id="parentless-peers-remain-siblings",
        ),
    ],
)
def test_confluence_toc_handles_skipped_heading_levels(
    docker_pandoc_image, start_id, entry_levels, headings, expected_links,
):
    output = render_confluence(
        f'::: {{toc-list-top-level="{start_id}" '
        f'toc-list-entry-levels={entry_levels}}}\n:::\n\n{headings}',
        docker_pandoc_image,
        lua_filters=("theme/toc.lua",),
    )

    # Read the rendered nesting and link order, not just the presence of links.
    document = ET.fromstring(f'<document xmlns:ac="urn:confluence">{output}</document>')
    links = []

    def collect_links(element, depth=0):
        if element.tag == "div" and element.get("style") == "margin-left: 40px;":
            depth += 1
        if element.tag == "{urn:confluence}link":
            links.append((element.get("{urn:confluence}anchor"), depth))
        for child in element:
            collect_links(child, depth)

    collect_links(document)
    assert links == expected_links


def test_confluence_toc_preserves_skipped_heading_levels_and_numbering(docker_pandoc_image):
    output = render_confluence(
        '::: {toc-list-top-level="" toc-list-entry-levels=1-4}\n:::\n\n'
        "## Intro {#intro}\n\n#### Details {#details}\n",
        docker_pandoc_image,
        lua_filters=("theme/fignos.lua", "theme/toc.lua"),
    )

    assert '<h2 id="intro">0.1 Intro</h2>' in output
    assert '<h4 id="details">0.1.0.1 Details</h4>' in output
    assert '<ac:link-body>0.1 Intro</ac:link-body>' in output
    assert '<ac:link-body>0.1.0.1 Details</ac:link-body>' in output
