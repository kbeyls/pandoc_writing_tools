#!/usr/bin/env python3
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

# Generate a Make include file that maps each document output target to the
# built image files referenced by that document's Markdown source. The scanner
# uses Pandoc JSON as the source of truth so it handles images in nested
# Markdown constructs without relying on regular expressions.

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


REMOTE_SCHEMES = {"data", "ftp", "ftps", "http", "https", "mailto", "tel"}


@dataclass(frozen=True)
class OutputProfile:
    """Describe one generated document suffix and its default image extension."""

    suffix: str
    default_extension: str


@dataclass(frozen=True)
class ImageReference:
    """One Pandoc image target and the classes attached to that image."""

    target: str
    classes: frozenset[str]


OUTPUT_PROFILES: Mapping[str, OutputProfile] = {
    "html": OutputProfile(".html", "svg"),
    "tex": OutputProfile(".tex", "pdf"),
    "pdf": OutputProfile(".pdf", "pdf"),
    "xhtml": OutputProfile(".xhtml", "png"),
    "docx": OutputProfile(".docx", "png"),
    "pptx": OutputProfile(".pptx", "png"),
    "native": OutputProfile(".native", "png"),
    "transformed_native": OutputProfile(".transformed.native", "png"),
    "email_html": OutputProfile(".email.html", "png"),
    "eml": OutputProfile(".eml", "png"),
}


def iter_image_targets(pandoc_json: object) -> list[str]:
    """Return image target strings found anywhere in a Pandoc JSON tree.

    The input is the decoded JSON object produced by `pandoc -t json`. The
    return value preserves traversal order and contains the raw target strings
    from Pandoc `Image` elements, such as `build/img/figure`.
    """

    return [reference.target for reference in iter_image_references(pandoc_json)]


def iter_image_references(pandoc_json: object) -> list[ImageReference]:
    """Return image targets and classes found anywhere in a Pandoc JSON tree."""

    references: list[ImageReference] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if value.get("t") == "Image":
                reference = _image_reference(value.get("c"))
                if reference:
                    references.append(reference)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(pandoc_json)
    return references


def _image_target(content: object) -> str | None:
    reference = _image_reference(content)
    return reference.target if reference else None


def _image_reference(content: object) -> ImageReference | None:
    if not isinstance(content, list) or not content:
        return None
    target = content[-1]
    if (
        isinstance(target, list)
        and target
        and isinstance(target[0], str)
    ):
        classes: frozenset[str] = frozenset()
        attributes = content[0] if content else None
        if (
            isinstance(attributes, list)
            and len(attributes) >= 2
            and isinstance(attributes[1], list)
        ):
            classes = frozenset(
                item for item in attributes[1] if isinstance(item, str)
            )
        return ImageReference(target=target[0], classes=classes)
    return None


def drawio_dependency(
    reference: ImageReference,
    *,
    content_root: Path,
    build_dir: Path,
) -> Path | None:
    """Return a draw.io candidate for an extensionless DOT-backed image."""

    target_path = PurePosixPath(urlparse(reference.target).path)
    if target_path.suffix:
        return None

    rendered = resolve_image_target(
        reference.target,
        content_root=content_root,
        build_dir=build_dir,
        default_extension="png",
    )
    if rendered is None:
        return None
    build_img_dir = (build_dir / "img").resolve()
    try:
        relative = rendered.resolve().relative_to(build_img_dir)
    except ValueError:
        return None
    source_relative = relative.with_suffix("")
    source = content_root.resolve() / "src" / "img" / source_relative.with_suffix(
        ".dot"
    )
    if not source.exists():
        return None
    return rendered.with_suffix(".drawio")


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


def resolve_image_target(
    target: str,
    content_root: Path,
    build_dir: Path,
    default_extension: str,
) -> Path | None:
    """Resolve one Markdown image target to the built image path to track.

    `target` is the raw image target string from Pandoc. `content_root` is the
    consuming repository root, `build_dir` is its build directory, and
    `default_extension` is the output profile's Pandoc default image extension.
    Remote URLs return `None`. Local image paths under `build/img`, `src/img`,
    or `img` return paths under `build/img`; other local paths resolve relative
    to `content_root`.
    """

    parsed = urlparse(target)
    if parsed.scheme in REMOTE_SCHEMES or target.startswith("//"):
        return None

    path_text = parsed.path
    if not path_text:
        return None

    target_path = _with_default_extension(PurePosixPath(path_text), default_extension)
    content_root = content_root.resolve()
    build_dir = build_dir.resolve()
    build_img_dir = build_dir / "img"

    if target_path.is_absolute():
        absolute_path = Path(str(target_path))
        try:
            source_relative = absolute_path.resolve().relative_to(content_root / "src" / "img")
        except ValueError:
            return absolute_path.resolve()
        return build_img_dir / source_relative

    parts = target_path.parts
    if len(parts) >= 2 and parts[:2] == ("build", "img"):
        return build_img_dir.joinpath(*parts[2:])
    if len(parts) >= 2 and parts[:2] == ("src", "img"):
        return build_img_dir.joinpath(*parts[2:])
    if parts and parts[0] == "img":
        return build_img_dir.joinpath(*parts[1:])
    return content_root.joinpath(*parts)


def _with_default_extension(path: PurePosixPath, default_extension: str) -> PurePosixPath:
    extension = default_extension.lstrip(".")
    if path.suffix or not extension:
        return path
    return path.with_name(f"{path.name}.{extension}")


def deps_for_document(
    markdown_path: Path,
    content_root: Path,
    profiles: Mapping[str, str],
    markdown_format: str = "markdown-example_lists",
) -> Mapping[str, set[Path]]:
    """Return resolved image dependencies for one Markdown document.

    `profiles` maps profile names to default image extensions. The return value
    maps each profile name to the set of built image `Path` objects referenced
    by `markdown_path` for that profile.
    """

    build_dir = content_root / "build"
    pandoc_json = read_pandoc_json(markdown_path, markdown_format)
    image_references = iter_image_references(pandoc_json)
    dependencies: dict[str, set[Path]] = {}
    for profile_name, default_extension in profiles.items():
        profile_deps: set[Path] = set()
        for reference in image_references:
            resolved = resolve_image_target(
                reference.target,
                content_root=content_root,
                build_dir=build_dir,
                default_extension=default_extension,
            )
            if resolved is not None:
                profile_deps.add(resolved)
            if profile_name == "xhtml" and "no-drawio" not in reference.classes:
                drawio = drawio_dependency(
                    reference,
                    content_root=content_root,
                    build_dir=build_dir,
                )
                if drawio is not None:
                    profile_deps.add(drawio)
        dependencies[profile_name] = profile_deps
    return dependencies


def collect_make_dependencies(
    content_root: Path,
    src_dir: Path,
    build_dir: Path,
    markdown_format: str = "markdown-example_lists",
) -> dict[str, set[str]]:
    """Collect Make target prerequisites for every Markdown document in `src_dir`.

    The returned dictionary maps Make target strings such as
    `$(BUILD_DIR)/doc.html` to prerequisite strings such as
    `$(BUILD_IMG_DIR)/figure.svg`. Paths are rendered with Make variables so
    the generated include file is portable across host and Docker mount paths.
    """

    default_extensions = {
        profile_name: profile.default_extension
        for profile_name, profile in OUTPUT_PROFILES.items()
    }
    dependencies: dict[str, set[str]] = {}
    for markdown_path in sorted(src_dir.glob("*.md")):
        if markdown_path.stem == "AGENTS":
            continue
        document_deps = deps_for_document(
            markdown_path,
            content_root=content_root,
            profiles=default_extensions,
            markdown_format=markdown_format,
        )
        for profile_name, profile in OUTPUT_PROFILES.items():
            target = f"$(BUILD_DIR)/{_escape_make_path(markdown_path.stem + profile.suffix)}"
            prereqs = {
                make_variable_path(path, content_root=content_root, build_dir=build_dir)
                for path in document_deps[profile_name]
            }
            if prereqs:
                dependencies[target] = prereqs
    return dependencies


def make_variable_path(path: Path, content_root: Path, build_dir: Path) -> str:
    """Render a concrete path using Make variables where possible.

    Paths below the build image directory become `$(BUILD_IMG_DIR)/...`; paths
    below the build, source, or content root use the corresponding Make
    variable. Paths outside those roots fall back to an escaped filesystem path.
    """

    path = path.resolve()
    content_root = content_root.resolve()
    build_dir = build_dir.resolve()
    build_img_dir = build_dir / "img"
    src_dir = content_root / "src"

    for root, variable in (
        (build_img_dir, "$(BUILD_IMG_DIR)"),
        (build_dir, "$(BUILD_DIR)"),
        (src_dir, "$(SRC_DIR)"),
        (content_root, "$(CONTENT_ROOT)"),
    ):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if str(relative) == ".":
            return variable
        return f"{variable}/{_escape_make_path(relative.as_posix())}"
    return _escape_make_path(str(path))


def render_makefile(dependencies: Mapping[object, set[object]]) -> str:
    """Render dependency mappings as a deterministic Makefile fragment.

    `dependencies` maps targets to prerequisite sets. The output groups targets
    that share identical prerequisites and starts with a generated-file warning.
    """

    lines = [
        "# Generated by scripts/python/generate_image_deps.py; do not edit.",
        "",
    ]

    grouped: dict[tuple[str, ...], list[str]] = {}
    for target, prereqs in dependencies.items():
        prereq_tuple = tuple(sorted(str(prereq) for prereq in prereqs))
        grouped.setdefault(prereq_tuple, []).append(str(target))

    for prereqs, targets in sorted(grouped.items(), key=lambda item: (item[1], item[0])):
        if not prereqs:
            continue
        lines.append(f"{' '.join(sorted(targets))}: {' '.join(prereqs)}")

    return "\n".join(lines) + "\n"


def write_if_changed(path: Path, content: str) -> None:
    """Write `content` to `path` atomically, preserving unchanged files.

    The parent directory is created if necessary. If the file already contains
    the requested content, the function leaves the bytes unchanged and only
    refreshes the timestamp so Make knows the include file was considered.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        os.utime(path, None)
        return

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


def _escape_make_path(path: str) -> str:
    return (
        path.replace("\\", "\\\\")
        .replace("$", "$$")
        .replace(" ", "\\ ")
        .replace("#", "\\#")
        .replace(":", "\\:")
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line generator and return a process exit code.

    `argv` may be supplied by tests; when it is `None`, argparse reads
    `sys.argv`. The command writes the generated Make dependency fragment to
    `--output` and returns zero on success.
    """

    parser = argparse.ArgumentParser(
        description="Generate per-document image dependencies for pandoc_writing_tools Make builds."
    )
    parser.add_argument("--content-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--src-dir", type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--from", dest="markdown_format", default="markdown-example_lists")
    args = parser.parse_args(argv)

    content_root = args.content_root.resolve()
    src_dir = (args.src_dir or content_root / "src").resolve()
    build_dir = (args.build_dir or content_root / "build").resolve()

    dependencies = collect_make_dependencies(
        content_root=content_root,
        src_dir=src_dir,
        build_dir=build_dir,
        markdown_format=args.markdown_format,
    )
    write_if_changed(args.output, render_makefile(dependencies))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
