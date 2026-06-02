# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree


HTML_BASE64_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")
CID_RE = re.compile(r"cid:img-\d+@[^\"'>]+")
FEATURE_VERSION_RE = re.compile(r"(Feature(?:%20|\s)Demo(?:%20|\s)v)\d+(?:-with-local-changes)?")
VERSION_TOKEN_RE = re.compile(r"\bv\d+(?:-with-local-changes)?(?=(?:[.%&]|%0D|%20|$))")
LAST_UPDATED_DISPLAY_RE = re.compile(r"(Last updated:\s*)[^<\n]+")
VERSION_DISPLAY_RE = re.compile(r"(Version:\s*)\d+(?:-with-local-changes)?")
LAST_UPDATED_INLINE_RE = re.compile(r'LAST_UPDATED[:=]\s*("[^"]+"|[^\s\n"]+)')
VERSION_INLINE_RE = re.compile(r'VERSION[:=]\s*("[^"]+"|[^\s\n"]+)')
LAST_UPDATED_META_RE = re.compile(r'(LAST_UPDATED"\s*,\s*MetaString\s*")[^"]+(")')
VERSION_META_RE = re.compile(r'(VERSION"\s*,\s*MetaString\s*")[^"]+(")')
LAST_UPDATED_NATIVE_BLOCK_RE = re.compile(
    r'Str "LAST_UPDATED:<DATE>"(?:\n\s*,\s*Space\n\s*,\s*Str "[^"]+")+'
)


@dataclass(frozen=True)
class OutputSpec:
    key: str
    suffix: str
    normalizer: Callable[[Path], str]
    golden_name: str


def _strip_trailing_whitespace(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def _normalize_common(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = FEATURE_VERSION_RE.sub(r"\1<VER>", text)
    text = VERSION_TOKEN_RE.sub("v<VER>", text)
    text = LAST_UPDATED_DISPLAY_RE.sub(r"\1<DATE>", text)
    text = VERSION_DISPLAY_RE.sub(r"\1<VER>", text)
    text = VERSION_INLINE_RE.sub("VERSION:<VER>", text)
    text = LAST_UPDATED_INLINE_RE.sub("LAST_UPDATED:<DATE>", text)
    text = VERSION_META_RE.sub(r"\1<VER>\2", text)
    text = LAST_UPDATED_META_RE.sub(r"\1<DATE>\2", text)
    return _strip_trailing_whitespace(text)


def normalize_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = HTML_BASE64_RE.sub("data:image/<BASE64>", text)
    text = CID_RE.sub("cid:IMG", text)
    return _normalize_common(text)


def normalize_xhtml(path: Path) -> str:
    return normalize_html(path)


def normalize_tex(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return _normalize_common(text)


def normalize_native(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = _normalize_common(text)
    text = LAST_UPDATED_NATIVE_BLOCK_RE.sub('Str "LAST_UPDATED:<DATE>"', text)
    return text


def normalize_pdf(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"PDF output is empty: {path}")
    return _strip_trailing_whitespace("PDF_OK")


def _extract_docx_text(xml_bytes: bytes) -> str:
    root = ElementTree.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", ns):
        parts: list[str] = []
        for node in para.iter():
            if node.tag == f"{{{ns['w']}}}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{{{ns['w']}}}tab":
                parts.append("\t")
            elif node.tag in (f"{{{ns['w']}}}br", f"{{{ns['w']}}}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def normalize_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml_bytes = zf.read("word/document.xml")
    text = _extract_docx_text(xml_bytes)
    return _normalize_common(text)


def _extract_pptx_text(xml_bytes: bytes) -> str:
    root = ElementTree.fromstring(xml_bytes)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    texts: list[str] = []
    for node in root.findall(".//a:t", ns):
        if node.text:
            texts.append(node.text)
    return " ".join(texts)


def normalize_pptx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        slide_names = sorted(
            (name for name in zf.namelist() if name.startswith("ppt/slides/slide")),
            key=lambda name: int(re.findall(r"slide(\d+)", name)[0]),
        )
        slides: list[str] = []
        for name in slide_names:
            slides.append(_extract_pptx_text(zf.read(name)))
    text = "\n\n---\n\n".join(slides)
    return _normalize_common(text)


def normalize_eml(path: Path) -> str:
    msg = BytesParser(policy=policy.default).parse(path.open("rb"))
    html = ""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            html = part.get_content()
            break
    if not html:
        html = msg.get_content()
    text = HTML_BASE64_RE.sub("data:image/<BASE64>", html)
    text = CID_RE.sub("cid:IMG", text)
    return _normalize_common(text)


OUTPUT_SPECS = [
    OutputSpec("html", ".html", normalize_html, "feature-demo.html.txt"),
    OutputSpec("xhtml", ".xhtml", normalize_xhtml, "feature-demo.xhtml.txt"),
    OutputSpec("tex", ".tex", normalize_tex, "feature-demo.tex.txt"),
    OutputSpec("pdf", ".pdf", normalize_pdf, "feature-demo.pdf.txt"),
    OutputSpec("native", ".transformed.native", normalize_native, "feature-demo.native.txt"),
    OutputSpec("docx", ".docx", normalize_docx, "feature-demo.docx.txt"),
    OutputSpec("pptx", ".pptx", normalize_pptx, "feature-demo.pptx.txt"),
    OutputSpec("eml", ".eml", normalize_eml, "feature-demo.eml.txt"),
]


def normalize_outputs(build_dir: Path, output_dir: Path, stem: str = "feature-demo") -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for spec in OUTPUT_SPECS:
        input_path = build_dir / f"{stem}{spec.suffix}"
        if not input_path.exists():
            raise FileNotFoundError(f"Missing output: {input_path}")
        normalized = spec.normalizer(input_path)
        output_path = output_dir / spec.golden_name
        output_path.write_text(normalized, encoding="utf-8")
        written[spec.key] = output_path
    return written
