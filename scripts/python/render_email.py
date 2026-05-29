#!/usr/bin/env python3
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import mimetypes
import re
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path


IMG_SRC_RE = re.compile(r'<img\s+[^>]*src="([^"]+)"', re.IGNORECASE)


def load_html(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def collect_image_sources(html: str) -> list[str]:
    return IMG_SRC_RE.findall(html)


def replace_sources(html: str, src_to_cid: dict[str, str]) -> str:
    for src, cid in src_to_cid.items():
        html = html.replace(f'src="{src}"', f'src="cid:{cid}"')
    return html


def read_image(path: Path) -> tuple[bytes, str, str]:
    data = path.read_bytes()
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        raise ValueError(f"Unknown MIME type for image: {path}")
    maintype, subtype = mime_type.split("/", 1)
    return data, maintype, subtype


def build_email(html: str, images: list[tuple[str, Path]]) -> EmailMessage:
    msg = EmailMessage(policy=SMTP)
    msg["From"] = ""
    msg["To"] = ""
    msg["Subject"] = ""
    msg.set_content("This email requires an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    html_part = msg.get_payload()[1]
    for cid, path in images:
        data, maintype, subtype = read_image(path)
        html_part.add_related(data, maintype=maintype, subtype=subtype, cid=cid, filename=path.name)
    return msg


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an HTML file to an EML with inline images.")
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    html = load_html(args.html)
    sources = collect_image_sources(html)
    html_dir = args.html.parent.resolve()
    src_to_cid: dict[str, str] = {}
    images: list[tuple[str, Path]] = []
    for index, src in enumerate(sources, start=1):
        if src in src_to_cid:
            continue
        cid = f"img-{index}@"
        src_to_cid[src] = cid
        src_path = Path(src)
        if not src_path.is_absolute():
            candidate = (html_dir / src_path).resolve()
            if not candidate.exists():
                fallback = (html_dir.parent / src_path).resolve()
                if fallback.exists():
                    candidate = fallback
            src_path = candidate
        images.append((cid, src_path))

    html = replace_sources(html, src_to_cid)
    email = build_email(html, images)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(email.as_bytes())


if __name__ == "__main__":
    main()
