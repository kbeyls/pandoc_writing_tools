# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

import shutil
import subprocess
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
    run_checked(["docker", "build", "-t", DOCKER_IMAGE, str(root / "docker")])
    return DOCKER_IMAGE


def render_confluence(markdown: str, docker_pandoc_image: str) -> str:
    result = run_confluence(markdown, docker_pandoc_image)
    if result.returncode != 0:
        pytest.fail(
            "Pandoc failed with exit code "
            f"{result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def run_confluence(
    markdown: str,
    docker_pandoc_image: str,
) -> subprocess.CompletedProcess[str]:
    root = repo_root()
    return subprocess.run(
        [
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
        ],
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
