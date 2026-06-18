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
    root = repo_root()
    result = run_checked(
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
        input_text=markdown,
    )
    return result.stdout


def test_confluence_writer_renders_inline_math(docker_pandoc_image):
    output = render_confluence("Inline $a < b & c > d$ here.\n", docker_pandoc_image)

    assert '<span class="math inline">a &lt; b &amp; c &gt; d</span>' in output
    assert "<p>Inline " in output


def test_confluence_writer_renders_display_math_as_block(docker_pandoc_image):
    output = render_confluence("$$\nx < y & y > z\n$$\n", docker_pandoc_image)

    assert '<div class="math display">\nx &lt; y &amp; y &gt; z\n</div>' in output
    assert '<p><div class="math display">' not in output
    assert '</div></p>' not in output
