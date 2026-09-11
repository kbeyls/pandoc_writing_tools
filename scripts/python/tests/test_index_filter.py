# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


TOOLS_ROOT = Path(__file__).resolve().parents[3]


def render_with_index_filter(tmp_path: Path, markdown: str) -> str:
    if not shutil.which("pandoc"):
        pytest.skip("pandoc is required to exercise the Lua filters")

    source = tmp_path / "document.md"
    source.write_text(markdown, encoding="utf-8")
    result = subprocess.run(
        [
            "pandoc",
            str(source),
            "-t",
            "html",
            "--lua-filter",
            str(TOOLS_ROOT / "theme/markup_todo.lua"),
            "--lua-filter",
            str(TOOLS_ROOT / "theme/fignos.lua"),
            "--lua-filter",
            str(TOOLS_ROOT / "theme/index.lua"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_index_filter_ignores_todo_spans_before_first_header(tmp_path):
    rendered = render_with_index_filter(
        tmp_path,
        """\
::: TODO
This warning appears before the first heading.
:::

# Section

The indexed [term]{.index} appears after the heading.

::: {#index}
:::
""",
    )

    assert 'class="todo_ref"' in rendered
    assert 'href="#__index_entry_1"' in rendered
    assert 'id="index-header"' in rendered


def test_index_filter_allows_index_entry_before_first_header(tmp_path):
    rendered = render_with_index_filter(
        tmp_path,
        """\
An indexed [preface term]{.index} appears before the first heading.

# Section

::: {#index}
:::
""",
    )

    assert 'href="#__index_entry_1"' in rendered
    assert "(1)" in rendered
