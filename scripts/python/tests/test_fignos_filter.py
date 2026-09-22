# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


TOOLS_ROOT = Path(__file__).resolve().parents[3]


def render_with_fignos(tmp_path: Path, markdown: str) -> subprocess.CompletedProcess[str]:
    if not shutil.which("pandoc"):
        pytest.skip("pandoc is required to exercise the Lua filters")

    source = tmp_path / "document.md"
    source.write_text(markdown, encoding="utf-8")
    return subprocess.run(
        [
            "pandoc",
            str(source),
            "--from",
            "markdown",
            "--to",
            "html",
            "--lua-filter",
            str(TOOLS_ROOT / "theme/fignos.lua"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def assert_rendered(tmp_path: Path, markdown: str) -> str:
    result = render_with_fignos(tmp_path, markdown)
    assert result.returncode == 0, result.stderr
    return " ".join(result.stdout.split())


def test_number_is_the_backward_compatible_default_and_forward_refs_work(tmp_path: Path) -> None:
    rendered = assert_rendered(
        tmp_path,
        """\
See section [@sec:overview].

# Overview {#sec:overview}
""",
    )

    assert '<a href="#sec:overview">1</a>' in rendered


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("number", "1"),
        ("title", "“system overview”"),
        ("number-title", "1 (“system overview”)"),
    ],
)
def test_local_reference_styles(tmp_path: Path, style: str, expected: str) -> None:
    rendered = assert_rendered(
        tmp_path,
        f"""\
See section [@sec:overview]{{ref-style={style}}}.

# A detailed overview of the system {{#sec:overview ref-title="system overview"}}
""",
    )

    assert f'<a href="#sec:overview">{expected}</a>' in rendered


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("number", "1"),
        ("title", "“system overview”"),
        ("number-title", "1 (“system overview”)"),
    ],
)
def test_document_default_styles(tmp_path: Path, style: str, expected: str) -> None:
    rendered = assert_rendered(
        tmp_path,
        f"""\
---
section-reference-style: {style}
---

See section [@sec:overview].

# Overview {{#sec:overview ref-title="system overview"}}
""",
    )

    assert f'<a href="#sec:overview">{expected}</a>' in rendered


def test_local_style_overrides_document_default(tmp_path: Path) -> None:
    rendered = assert_rendered(
        tmp_path,
        """\
---
section-reference-style: number-title
---

Default [@sec:overview]. Local [@sec:overview]{ref-style=number}.

# Overview {#sec:overview ref-title="system overview"}
""",
    )

    assert '<a href="#sec:overview">1 (“system overview”)</a>' in rendered
    assert '<a href="#sec:overview">1</a>' in rendered


def test_title_falls_back_to_plain_full_header_text(tmp_path: Path) -> None:
    rendered = assert_rendered(
        tmp_path,
        """\
See [@sec:overview]{ref-style=title}.

# A *detailed* [system](https://example.com) overview {#sec:overview}
""",
    )

    assert '<a href="#sec:overview">“A detailed system overview”</a>' in rendered
    assert rendered.count("<a ") == 2  # The reference plus the link in the heading.


def test_citation_prefix_and_non_control_span_attributes_are_preserved(tmp_path: Path) -> None:
    rendered = assert_rendered(
        tmp_path,
        """\
[[see @sec:overview]]{#overview-ref .important ref-style=title data-kind=section}.

# Overview {#sec:overview}
""",
    )

    assert (
        '<a href="#sec:overview" id="overview-ref" class="important" '
        'data-kind="section">see “Overview”</a>'
    ) in rendered
    assert "ref-style" not in rendered


@pytest.mark.parametrize(
    ("markdown", "expected_error"),
    [
        (
            """\
---
section-reference-style: verbose
---

# Overview {#sec:overview}
""",
            "section-reference-style",
        ),
        (
            """\
See [@sec:overview]{ref-style=verbose}.

# Overview {#sec:overview}
""",
            "verbose",
        ),
        (
            """\
See [@sec:overview]{ref-style=title}.

# Overview {#sec:overview ref-title=""}
""",
            "ref-title",
        ),
        (
            """\
See [@sec:empty]{ref-style=title}.

# {#sec:empty}
""",
            "sec:empty",
        ),
        (
            """\
[ordinary text]{ref-style=title}
""",
            "single section reference",
        ),
    ],
)
def test_invalid_reference_configuration_fails(
    tmp_path: Path, markdown: str, expected_error: str
) -> None:
    result = render_with_fignos(tmp_path, markdown)

    assert result.returncode != 0
    assert expected_error in result.stderr
