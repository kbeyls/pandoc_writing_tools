# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import base64
import json
import struct
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_drawio_overlay import (  # noqa: E402
    DrawioOverlayError,
    Hotspot,
    build_drawio_document,
    hotspot_bounds,
    parse_graphviz_map,
    read_png_size,
    write_if_changed,
)


def png_header(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", width, height)


def test_parse_graphviz_map_and_calculate_bounds():
    hotspots = parse_graphviz_map(
        '<map id="G"><area shape="poly" id="node1" '
        'href="https://example.com/?a=1&amp;b=2" title="A &amp; B" '
        'coords="10,20,30,15,40,50"/>'
        '<area shape="circle" title="Circle" coords="20,30,5"/>'
        '<area shape="rect" href="https://example.com/rect" '
        'coords="30,40,10,20"/></map>'
    )

    assert hotspots[0] == Hotspot(
        shape="poly",
        coordinates=(10.0, 20.0, 30.0, 15.0, 40.0, 50.0),
        href="https://example.com/?a=1&b=2",
        tooltip="A & B",
        source_id="node1",
    )
    assert hotspot_bounds(hotspots[0]) == (10.0, 15.0, 30.0, 35.0)
    assert hotspot_bounds(hotspots[1]) == (15.0, 25.0, 10.0, 10.0)
    assert hotspot_bounds(hotspots[2]) == (10.0, 20.0, 20.0, 20.0)


@pytest.mark.parametrize(
    "map_text, message",
    [
        ("<html />", "root must be <map>"),
        ('<map><area shape="default" href="x" coords="1,2,3,4"/></map>', "unsupported shape"),
        ('<map><area shape="rect" href="x" coords="1,2,3"/></map>', "requires 4"),
        ('<map><area shape="poly" href="x" coords="1,2,3,4"/></map>', "at least three"),
        ('<map><area shape="circle" href="x" coords="2,2,0"/></map>', "radius"),
        ('<map><area shape="rect" coords="1,2,3,4"/></map>', "neither a link nor a tooltip"),
    ],
)
def test_parse_graphviz_map_rejects_malformed_areas(map_text, message):
    with pytest.raises(DrawioOverlayError, match=message):
        parse_graphviz_map(map_text)


def test_read_png_size(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(png_header(1427, 1262))
    assert read_png_size(image) == (1427, 1262)

    image.write_bytes(b"not a png")
    with pytest.raises(DrawioOverlayError, match="not a valid PNG"):
        read_png_size(image)


def test_build_drawio_document_embeds_svg_and_linked_objects():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10"/></svg>'
    hotspots = [
        Hotspot("rect", (1, 2, 9, 8), "https://example.com/?a=1&b=2", "Caf\u00e9 & docs", "n1"),
        Hotspot("rect", (0, 0, 100, 100), "https://example.com/broad", None, "n2"),
    ]

    content = build_drawio_document(svg, (100, 100), hotspots)
    root = ET.fromstring(content)
    model = root.find("./diagram/mxGraphModel")
    assert model is not None
    background = json.loads(model.get("backgroundImage"))
    assert background["width"] == 100
    assert base64.b64decode(background["src"].split(",", 1)[1]) == svg

    objects = model.findall("./root/object")
    assert [item.get("link") for item in objects] == [
        "https://example.com/broad",
        "https://example.com/?a=1&b=2",
    ]
    assert objects[1].get("tooltip") == "Caf\u00e9 & docs"
    geometry = objects[1].find("./mxCell/mxGeometry")
    assert geometry is not None
    assert geometry.attrib == {
        "x": "1",
        "y": "2",
        "width": "8",
        "height": "6",
        "as": "geometry",
    }
    assert build_drawio_document(svg, (100, 100), hotspots) == content


def test_build_drawio_document_rejects_non_svg():
    with pytest.raises(DrawioOverlayError, match="<svg> root"):
        build_drawio_document(b"<html />", (10, 10), [])


def test_write_if_changed_preserves_unchanged_mtime(tmp_path):
    output = tmp_path / "diagram.drawio"
    assert write_if_changed(output, b"first") is True
    original_mtime = output.stat().st_mtime_ns
    time.sleep(0.01)
    assert write_if_changed(output, b"first") is False
    assert output.stat().st_mtime_ns == original_mtime
    assert write_if_changed(output, b"second") is True
    assert output.read_bytes() == b"second"
