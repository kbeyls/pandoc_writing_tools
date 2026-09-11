#!/usr/bin/env python3
# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

"""Build a draw.io diagram from a rendered SVG and Graphviz image map."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import struct
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SUPPORTED_SHAPES = {"circle", "poly", "rect"}


class DrawioOverlayError(ValueError):
    """Raised when an input cannot be represented as a draw.io overlay."""


@dataclass(frozen=True)
class Hotspot:
    shape: str
    coordinates: tuple[float, ...]
    href: str | None
    tooltip: str | None
    source_id: str | None


def _optional_attribute(element: ET.Element, name: str) -> str | None:
    value = element.get(name)
    return value if value not in (None, "") else None


def parse_graphviz_map(map_text: str) -> list[Hotspot]:
    """Parse Graphviz cmapx XML into validated hotspot records."""

    try:
        root = ET.fromstring(map_text)
    except ET.ParseError as error:
        raise DrawioOverlayError(f"invalid Graphviz cmapx XML: {error}") from error
    if root.tag != "map":
        raise DrawioOverlayError(
            f"Graphviz cmapx root must be <map>, found <{root.tag}>"
        )

    hotspots: list[Hotspot] = []
    for ordinal, area in enumerate(root.findall("area"), start=1):
        shape = (area.get("shape") or "").lower()
        if shape not in SUPPORTED_SHAPES:
            raise DrawioOverlayError(
                f"area {ordinal} has unsupported shape {shape!r}; "
                f"expected one of {sorted(SUPPORTED_SHAPES)}"
            )
        coordinate_text = area.get("coords")
        if not coordinate_text:
            raise DrawioOverlayError(f"area {ordinal} has no coords attribute")
        try:
            coordinates = tuple(
                float(component.strip()) for component in coordinate_text.split(",")
            )
        except ValueError as error:
            raise DrawioOverlayError(
                f"area {ordinal} has non-numeric coordinates: {coordinate_text!r}"
            ) from error
        if any(not math.isfinite(value) or value < 0 for value in coordinates):
            raise DrawioOverlayError(
                f"area {ordinal} coordinates must be finite and non-negative"
            )

        expected = 3 if shape == "circle" else 4 if shape == "rect" else None
        if expected is not None and len(coordinates) != expected:
            raise DrawioOverlayError(
                f"{shape} area {ordinal} requires {expected} coordinates, "
                f"found {len(coordinates)}"
            )
        if shape == "poly" and (len(coordinates) < 6 or len(coordinates) % 2):
            raise DrawioOverlayError(
                f"poly area {ordinal} requires at least three x,y coordinate pairs"
            )

        href = _optional_attribute(area, "href")
        tooltip = _optional_attribute(area, "title")
        if href is None and tooltip is None:
            raise DrawioOverlayError(
                f"area {ordinal} has neither a link nor a tooltip"
            )
        hotspot = Hotspot(
            shape=shape,
            coordinates=coordinates,
            href=href,
            tooltip=tooltip,
            source_id=_optional_attribute(area, "id"),
        )
        hotspot_bounds(hotspot)
        hotspots.append(hotspot)
    return hotspots


def hotspot_bounds(hotspot: Hotspot) -> tuple[float, float, float, float]:
    """Return a hotspot's positive-width x, y, width, and height bounds."""

    values = hotspot.coordinates
    if hotspot.shape == "circle":
        center_x, center_y, radius = values
        if radius <= 0:
            raise DrawioOverlayError("circle hotspot radius must be greater than zero")
        left, top = center_x - radius, center_y - radius
        right, bottom = center_x + radius, center_y + radius
    elif hotspot.shape == "rect":
        x1, y1, x2, y2 = values
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
    elif hotspot.shape == "poly":
        x_values = values[0::2]
        y_values = values[1::2]
        left, right = min(x_values), max(x_values)
        top, bottom = min(y_values), max(y_values)
    else:
        raise DrawioOverlayError(f"unsupported hotspot shape {hotspot.shape!r}")
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise DrawioOverlayError(
            f"{hotspot.shape} hotspot has invalid bounds "
            f"({left}, {top})-({right}, {bottom})"
        )
    return left, top, right - left, bottom - top


def read_png_size(path: Path) -> tuple[int, int]:
    """Read a PNG's canvas size without decoding its pixel data."""

    with path.open("rb") as png_file:
        header = png_file.read(24)
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise DrawioOverlayError(f"{path} is not a valid PNG with an IHDR header")
    width, height = struct.unpack(">II", header[16:24])
    if width == 0 or height == 0:
        raise DrawioOverlayError(f"{path} has an empty PNG canvas")
    return width, height


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, ".6f").rstrip("0").rstrip(".")


def _validate_svg(svg_bytes: bytes) -> None:
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as error:
        raise DrawioOverlayError(f"invalid SVG XML: {error}") from error
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise DrawioOverlayError("SVG input does not have an <svg> root element")


def build_drawio_document(
    svg_bytes: bytes,
    canvas_size: tuple[int, int],
    hotspots: Sequence[Hotspot],
) -> bytes:
    """Return deterministic uncompressed draw.io XML for the supplied inputs."""

    _validate_svg(svg_bytes)
    width, height = canvas_size
    if width <= 0 or height <= 0:
        raise DrawioOverlayError("draw.io canvas dimensions must be positive")

    digest = hashlib.sha256(svg_bytes).hexdigest()[:16]
    svg_uri = "data:image/svg+xml;base64," + base64.b64encode(svg_bytes).decode("ascii")
    background = json.dumps(
        {"src": svg_uri, "width": width, "height": height},
        ensure_ascii=True,
        separators=(",", ":"),
    )

    mxfile = ET.Element("mxfile", {"host": "confluence", "compressed": "false"})
    diagram = ET.SubElement(
        mxfile,
        "diagram",
        {"id": f"graphviz-{digest}", "name": "Page-1"},
    )
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "dx": "0",
            "dy": "0",
            "grid": "0",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "0",
            "arrows": "0",
            "fold": "0",
            "page": "0",
            "pageScale": "1",
            "pageWidth": str(width),
            "pageHeight": str(height),
            "math": "0",
            "shadow": "0",
            "backgroundImage": background,
        },
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    positioned = [
        (index, hotspot, hotspot_bounds(hotspot))
        for index, hotspot in enumerate(hotspots, start=1)
    ]
    positioned.sort(key=lambda item: (-(item[2][2] * item[2][3]), item[0]))
    for ordinal, hotspot, (x, y, hotspot_width, hotspot_height) in positioned:
        hotspot_digest = hashlib.sha256(
            repr((ordinal, hotspot)).encode("utf-8")
        ).hexdigest()[:10]
        attributes = {
            "id": f"hotspot-{ordinal}-{hotspot_digest}",
            "label": "",
        }
        if hotspot.href is not None:
            attributes["link"] = hotspot.href
        if hotspot.tooltip is not None:
            attributes["tooltip"] = hotspot.tooltip
        wrapper = ET.SubElement(root, "object", attributes)
        cell = ET.SubElement(
            wrapper,
            "mxCell",
            {
                "style": (
                    "rounded=0;whiteSpace=wrap;html=1;fillOpacity=0;"
                    "strokeOpacity=0;pointerEvents=1;connectable=0;"
                ),
                "vertex": "1",
                "parent": "1",
                "connectable": "0",
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": _format_number(x),
                "y": _format_number(y),
                "width": _format_number(hotspot_width),
                "height": _format_number(hotspot_height),
                "as": "geometry",
            },
        )

    ET.indent(mxfile, space="  ")
    return ET.tostring(mxfile, encoding="utf-8", xml_declaration=True) + b"\n"


def write_if_changed(path: Path, content: bytes) -> bool:
    """Atomically write content if it differs; return whether bytes changed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return False
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)
    try:
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a draw.io SVG background with Graphviz link hotspots."
    )
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        hotspots = parse_graphviz_map(args.map.read_text(encoding="utf-8"))
        content = build_drawio_document(
            args.svg.read_bytes(), read_png_size(args.png), hotspots
        )
        write_if_changed(args.output, content)
    except (DrawioOverlayError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
