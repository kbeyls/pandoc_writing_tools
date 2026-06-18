# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

import subprocess
import shutil
from pathlib import Path

import pytest


pytestmark = pytest.mark.regression


def render_confluence(markdown: str) -> str:
    if not shutil.which("pandoc"):
        pytest.skip("pandoc executable is required for Confluence writer tests")

    repo_root = Path(__file__).resolve().parents[3]
    writer = repo_root / "theme" / "confluence.lua"
    result = subprocess.run(
        ["pandoc", "--from", "markdown-example_lists", "--to", str(writer)],
        input=markdown,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def test_confluence_writer_renders_inline_math():
    output = render_confluence("Inline $a < b & c > d$ here.\n")

    assert '<span class="math inline">a &lt; b &amp; c &gt; d</span>' in output
    assert "<p>Inline " in output


def test_confluence_writer_renders_display_math_as_block():
    output = render_confluence("$$\nx < y & y > z\n$$\n")

    assert '<div class="math display">\nx &lt; y &amp; y &gt; z\n</div>' in output
    assert '<p><div class="math display">' not in output
    assert '</div></p>' not in output
