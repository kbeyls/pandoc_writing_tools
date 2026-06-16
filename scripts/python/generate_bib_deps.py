#!/usr/bin/env python3
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

# Generate a per-document bibliography fingerprint. The fingerprint contains
# the normalized bibliography entries referenced by one Markdown source, so Make
# can rebuild only documents whose cited entries changed inside a shared .bib
# file.

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


SCHEMA = "pandoc_writing_tools.bib_refs.v1"


@dataclass(frozen=True)
class CitationSelection:
    """Describe the citation keys requested by one document."""

    keys: tuple[str, ...]
    include_all: bool = False


def read_pandoc_json(markdown_path: Path, markdown_format: str) -> object:
    """Parse one Markdown file with Pandoc and return its decoded JSON tree.

    `markdown_path` points to the source document. `markdown_format` is passed
    to Pandoc's `--from` option. The function raises `CalledProcessError` if
    Pandoc fails and returns the parsed JSON object on success.
    """

    result = subprocess.run(
        ["pandoc", str(markdown_path), "--from", markdown_format, "-t", "json"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return json.loads(result.stdout)


def iter_citation_ids(pandoc_json: object) -> list[str]:
    """Return citation ids found anywhere in a Pandoc JSON tree.

    The input is the decoded JSON object produced by `pandoc -t json`. The
    return value preserves traversal order and includes ids from normal
    citations as well as `nocite` metadata, including the special `*` id.
    """

    citation_ids: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            citation_id = value.get("citationId")
            if isinstance(citation_id, str):
                citation_ids.append(citation_id)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(pandoc_json)
    return citation_ids


def select_citations(citation_ids: Sequence[str]) -> CitationSelection:
    """Return de-duplicated citation ids and whether the document uses `nocite: @*`.

    `citation_ids` should be in document traversal order. The returned keys
    preserve first-use order, while `include_all` is true when the special
    Pandoc nocite id `*` appears.
    """

    include_all = False
    keys: list[str] = []
    seen: set[str] = set()
    for citation_id in citation_ids:
        if citation_id == "*":
            include_all = True
            continue
        if citation_id not in seen:
            seen.add(citation_id)
            keys.append(citation_id)
    return CitationSelection(keys=tuple(keys), include_all=include_all)


def read_bibliography_entries(bib_files: Sequence[Path]) -> dict[str, object]:
    """Parse BibTeX files with Pandoc and return normalized CSL entries by id.

    Duplicate entry ids are resolved with Pandoc citeproc's observed
    last-entry-wins behavior, so the fingerprint tracks the same entry that
    rendering uses.
    """

    if not bib_files:
        return {}

    result = subprocess.run(
        ["pandoc", "--from", "bibtex", "--to", "csljson", *map(str, bib_files)],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    decoded = json.loads(result.stdout)
    if not isinstance(decoded, list):
        raise ValueError("Pandoc did not return a CSL JSON entry list")

    entries: dict[str, object] = {}
    for entry in decoded:
        if not isinstance(entry, dict):
            raise ValueError("Pandoc returned a non-object bibliography entry")
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("Pandoc returned a bibliography entry without an id")
        entries[entry_id] = entry
    return entries


def build_fingerprint(
    document_path: Path,
    bib_files: Sequence[Path],
    selection: CitationSelection,
    entries_by_id: Mapping[str, object],
    content_root: Path,
) -> dict[str, object]:
    """Build the deterministic fingerprint object for one document.

    `selection` contains the document's requested citation ids. When
    `selection.include_all` is true, every parsed bibliography entry is tracked.
    Otherwise only entries whose ids appear in `selection.keys` are included.
    Missing ids are recorded so cross-reference-like keys do not fail the
    dependency scan.
    """

    if selection.include_all:
        selected_ids = tuple(sorted(entries_by_id))
        missing_keys: tuple[str, ...] = ()
    else:
        selected_ids = tuple(key for key in selection.keys if key in entries_by_id)
        missing_keys = tuple(key for key in selection.keys if key not in entries_by_id)

    entries = [entries_by_id[entry_id] for entry_id in selected_ids]
    return {
        "schema": SCHEMA,
        "document": _relative_path(document_path, content_root),
        "bib_files": [_relative_path(path, content_root) for path in bib_files],
        "include_all": selection.include_all,
        "citation_keys": list(selection.keys),
        "selected_entry_ids": list(selected_ids),
        "missing_keys": list(missing_keys),
        "entries": entries,
    }


def render_fingerprint(fingerprint: Mapping[str, object]) -> str:
    """Render a fingerprint as stable, human-readable JSON."""

    return json.dumps(fingerprint, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_if_changed(path: Path, content: str) -> bool:
    """Write `content` atomically only when bytes differ.

    The parent directory is created if necessary. The function returns true when
    it writes a new file. If the file already has the requested content, it is
    left untouched so its mtime remains a precise rebuild signal.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    temp_path.replace(path)
    return True


def generate_fingerprint(
    document_path: Path,
    output_path: Path,
    content_root: Path,
    bib_files: Sequence[Path],
    markdown_format: str = "markdown-example_lists",
) -> bool:
    """Generate and write the fingerprint for one document.

    Returns true if the fingerprint file changed. Unchanged fingerprints are not
    touched.
    """

    pandoc_json = read_pandoc_json(document_path, markdown_format)
    selection = select_citations(iter_citation_ids(pandoc_json))
    entries_by_id = read_bibliography_entries(bib_files)
    fingerprint = build_fingerprint(
        document_path=document_path,
        bib_files=bib_files,
        selection=selection,
        entries_by_id=entries_by_id,
        content_root=content_root,
    )
    return write_if_changed(output_path, render_fingerprint(fingerprint))


def _relative_path(path: Path, content_root: Path) -> str:
    path = path.resolve()
    content_root = content_root.resolve()
    try:
        return path.relative_to(content_root).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line generator and return a process exit code."""

    parser = argparse.ArgumentParser(
        description="Generate per-document bibliography fingerprints for Make builds."
    )
    parser.add_argument("--content-root", required=True, type=Path)
    parser.add_argument("--document", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bib-file", action="append", default=[], type=Path)
    parser.add_argument("--from", dest="markdown_format", default="markdown-example_lists")
    args = parser.parse_args(argv)

    content_root = args.content_root.resolve()
    document_path = args.document.resolve()
    output_path = args.output.resolve()
    bib_files = (
        [path.resolve() for path in args.bib_file]
        if args.bib_file
        else sorted((content_root / "src").glob("*.bib"))
    )

    generate_fingerprint(
        document_path=document_path,
        output_path=output_path,
        content_root=content_root,
        bib_files=bib_files,
        markdown_format=args.markdown_format,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
