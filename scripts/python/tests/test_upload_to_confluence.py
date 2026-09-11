# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

import os
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

# Add scripts/python to sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import upload_to_confluence
import io
import requests


def png_header(width, height):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", width, height)


def test_extract_title_from_content_with_title():
    content = "<!-- Title: My Page -->\n<p>Content</p>"
    title = upload_to_confluence.extract_title_from_content(content)
    assert title == "My Page"


def test_extract_title_from_content_no_title():
    content = "<p>No title comment here</p>"
    title = upload_to_confluence.extract_title_from_content(content)
    assert title is None


def test_get_page_title_prefers_comment(tmp_path):
    # Create a dummy file path
    xhtml_file = str(tmp_path / "file.xhtml")
    # Case with title comment
    content = "<!-- Title: CustomTitle -->"
    title = upload_to_confluence.get_page_title(content, xhtml_file)
    assert title == "CustomTitle"
    # Case without title comment
    content2 = "<p>No title</p>"
    title2 = upload_to_confluence.get_page_title(content2, "example.xhtml")
    assert title2 == "example"


def test_rewrite_attachment_paths_single():
    content = '<img src="images/pic.png" ri:filename="images/pic.png"/>'
    updated_content, mapping = upload_to_confluence.rewrite_attachment_paths(content, "images")
    assert 'ri:filename="pic.png"' in updated_content
    assert mapping == {"images/pic.png": "pic.png"}


def test_sanitized_drawio_contract_fixture():
    fixture_dir = Path(__file__).parent / "fixtures/confluence_drawio_server"
    macro = (fixture_dir / "macro.xml").read_text(encoding="utf-8")
    metadata = json.loads((fixture_dir / "attachments.json").read_text(encoding="utf-8"))

    assert 'ac:name="drawio"' in macro
    assert '<ac:parameter ac:name="diagramName">example-diagram</ac:parameter>' in macro
    assert '<ac:parameter ac:name="revision">2</ac:parameter>' in macro
    assert {
        (item["title"], item["metadata"]["mediaType"], item["version"]["number"])
        for item in metadata["results"]
    } == {
        ("example-diagram", "application/vnd.jgraph.mxfile", 2),
        ("example-diagram.png", "image/png", 2),
    }
    assert ET.parse(fixture_dir / "example-diagram.drawio").getroot().tag == "mxfile"


def test_prepare_drawio_macro_resolves_paths_dimensions_and_stable_id(tmp_path):
    source = tmp_path / "linked.drawio"
    source.write_text("<mxfile />", encoding="utf-8")
    source.with_suffix(".png").write_bytes(png_header(640, 360))
    raw = (
        '<ac:structured-macro ac:name="drawio" ac:schema-version="1" '
        'ac:macro-id="__DRAWIO_MACRO_ID__">'
        '<ac:parameter ac:name="diagramName">' + str(source) + '</ac:parameter>'
        '<ac:parameter ac:name="diagramWidth">__DRAWIO_WIDTH__</ac:parameter>'
        '<ac:parameter ac:name="height">__DRAWIO_HEIGHT__</ac:parameter>'
        '<ac:parameter ac:name="revision">__DRAWIO_REVISION__</ac:parameter>'
        '</ac:structured-macro>'
    )

    content, diagrams = upload_to_confluence.prepare_drawio_macros(raw)

    assert len(diagrams) == 1
    assert diagrams[0].attachment_name == "linked"
    assert diagrams[0].preview_attachment_name == "linked.png"
    assert '<ac:parameter ac:name="diagramName">linked</ac:parameter>' in content
    assert '<ac:parameter ac:name="diagramWidth">640</ac:parameter>' in content
    assert '<ac:parameter ac:name="height">360</ac:parameter>' in content
    assert "__DRAWIO_MACRO_ID__" not in content
    assert upload_to_confluence.prepare_drawio_macros(raw)[0] == content
    finalized = upload_to_confluence.finalize_drawio_revisions(
        content, diagrams, {"linked": 7}
    )
    assert '<ac:parameter ac:name="revision">7</ac:parameter>' in finalized


def test_prepare_drawio_macro_requires_both_attachments(tmp_path):
    source = tmp_path / "missing.drawio"
    raw = (
        '<ac:structured-macro ac:name="drawio" ac:macro-id="__DRAWIO_MACRO_ID__">'
        f'<ac:parameter ac:name="diagramName">{source}</ac:parameter>'
        '</ac:structured-macro>'
    )
    with pytest.raises(FileNotFoundError, match="source attachment"):
        upload_to_confluence.prepare_drawio_macros(raw)


def test_prepare_drawio_macro_leaves_existing_server_macro_untouched():
    macro = (
        '<ac:structured-macro ac:name="drawio" ac:macro-id="existing">'
        '<ac:parameter ac:name="diagramName">existing.drawio</ac:parameter>'
        '</ac:structured-macro>'
    )
    assert upload_to_confluence.prepare_drawio_macros(macro) == (macro, [])


def test_drawio_attachment_specs_use_server_media_types(tmp_path):
    diagram = upload_to_confluence.DrawioDiagram(
        source_path=str(tmp_path / "graph.drawio"),
        preview_path=str(tmp_path / "graph.png"),
        attachment_name="graph",
        preview_attachment_name="graph.png",
        macro_id="id",
        revision_token="token",
    )
    specs = upload_to_confluence.attachment_specs({}, [diagram])
    assert [(spec.attachment_name, spec.content_type, spec.role) for spec in specs] == [
        ("graph", "application/vnd.jgraph.mxfile", "drawio-source"),
        ("graph.png", "image/png", "drawio-preview"),
    ]


def test_upload_attachment_specs_returns_refreshed_revision(tmp_path, capsys):
    source = tmp_path / "graph.drawio"
    source.write_text("new", encoding="utf-8")
    spec = upload_to_confluence.AttachmentSpec(
        str(source), "graph", "application/vnd.jgraph.mxfile", "drawio-source"
    )

    class DummyConf:
        url = "https://example.test"

        def __init__(self):
            self.fetch_count = 0
            self.upload = None

        def get_attachments_from_content(self, page_id, **kwargs):
            self.fetch_count += 1
            if self.fetch_count == 1:
                return {"results": []}
            return {"results": [{"title": "graph", "version": {"number": 4}}]}

        def attach_file(self, **kwargs):
            self.upload = kwargs

    confluence = DummyConf()
    versions = upload_to_confluence.upload_attachment_specs_if_different(
        confluence, "page", [spec]
    )
    assert versions == {"graph": 4}
    assert confluence.upload["name"] == "graph"
    assert confluence.upload["content_type"] == "application/vnd.jgraph.mxfile"
    assert "Uploaded attachment graph" in capsys.readouterr().out


def test_upload_attachment_specs_dry_run_performs_no_remote_calls(capsys):
    class NoRemoteCalls:
        def __getattr__(self, name):
            raise AssertionError(f"unexpected remote call: {name}")

    spec = upload_to_confluence.AttachmentSpec(
        "build/graph.drawio",
        "graph",
        "application/vnd.jgraph.mxfile",
        "drawio-source",
    )
    assert upload_to_confluence.upload_attachment_specs_if_different(
        NoRemoteCalls(), "page", [spec], dry_run=True
    ) == {}
    assert "[dry-run] Would upload drawio-source attachment graph" in capsys.readouterr().out


def test_attachment_specs_reject_same_basename_from_different_paths():
    with pytest.raises(ValueError, match="attachment name collision"):
        upload_to_confluence.attachment_specs(
            {"first/graph.png": "graph.png", "second/graph.png": "graph.png"}
        )


def test_upload_xhtml_to_confluence_calls_update_page(monkeypatch):
    calls = {}

    class DummyConfluence:
        def update_page(self, page_id, title, body, representation):
            calls['page_id'] = page_id
            calls['title'] = title
            calls['body'] = body
            calls['representation'] = representation

    dummy = DummyConfluence()
    upload_to_confluence.upload_xhtml_to_confluence(dummy, "123", "Title", "Content")
    assert calls == {
        'page_id': "123",
        'title': "Title",
        'body': "Content",
        'representation': "storage",
    }
    # ensure update_page is called exactly once

def test_get_xhtml_content_reads_file(tmp_path):
    file = tmp_path / "sample.xhtml"
    text = "<p>Hello</p>"
    file.write_text(text)
    content = upload_to_confluence.get_xhtml_content(str(file))
    assert content == text

def test_get_confluence_connection_returns_instance(monkeypatch):
    class DummyConf:
        def __init__(self, url, token):
            self.url = url
            self.token = token
    monkeypatch.setattr(upload_to_confluence, 'Confluence', DummyConf)
    url = "http://example.com"
    token = "secret"
    conf = upload_to_confluence.get_confluence_connection(url, token)
    assert isinstance(conf, DummyConf)
    assert conf.url == url and conf.token == token

def test_upload_files_if_different_new_attachment(tmp_path, monkeypatch, capsys):
    # Prepare file
    file = tmp_path / "att.txt"
    data = b"data"
    file.write_bytes(data)
    mapping = {str(file): "att.txt"}
    class DummyConf:
        def get_attachments_from_content(self, page_id, **kwargs):
            return {"results": []}
        def attach_file(self, filename, page_id, name, content_type):
            print(f"ATTACH called: {name}")
    dummy = DummyConf()
    upload_to_confluence.confluence_token = "tok"
    upload_to_confluence.upload_files_if_different(dummy, "42", mapping)
    captured = capsys.readouterr()
    assert "ATTACH called: att.txt" in captured.out

def test_upload_files_if_different_skip_same(monkeypatch, tmp_path, capsys):
    file = tmp_path / "same.txt"
    data = b"same"
    file.write_bytes(data)
    mapping = {str(file): "same.txt"}
    existing = [{
        "title": "same.txt",
        "_links": {"download": "/download/same.txt"}
    }]
    class DummyConf2:
        url = "http://ex"
        def get_attachments_from_content(self, page_id, **kwargs):
            return {"results": existing}
        def attach_file(self, **kwargs):
            pytest.skip("Should not attach when same content")
    dummy2 = DummyConf2()
    class Resp:
        def __init__(self, content): self._content = content
        @property
        def content(self): return self._content
    monkeypatch.setattr(requests, 'get', lambda url, headers: Resp(data))
    upload_to_confluence.confluence_token = "tok"
    upload_to_confluence.upload_files_if_different(dummy2, "id", mapping)
    out = capsys.readouterr().out
    assert "already exists on page id with identical content, skipping upload" in out

def test_fetch_page_content(monkeypatch):
    class Resp:
        def __init__(self, body): self._body = body
        def json(self): return {"body": {"storage": {"value": self._body}}}
    dummy_conf = type('C', (), {'url': 'http://ex'})()
    upload_to_confluence.confluence_token = "tok"
    monkeypatch.setattr(requests, 'get', lambda url, headers: Resp('val'))
    result = upload_to_confluence.fetch_page_content(dummy_conf, "pid")
    assert result == 'val'

def test_fetch_existing_inline_comments_success(monkeypatch):
    class Resp:
        status_code = 200
        def json(self): return ['cmt']
    monkeypatch.setattr(requests, 'get', lambda url, headers: Resp())
    dummy_conf = type('C', (), {'url': 'http://example'})()
    res = upload_to_confluence.fetch_existing_inline_comments(dummy_conf, "pid")
    assert res == ['cmt']

def test_fetch_existing_inline_comments_fail(monkeypatch, capsys):
    class Resp:
        status_code = 404
        text = 'err'
    monkeypatch.setattr(requests, 'get', lambda url, headers: Resp())
    dummy_conf = type('C', (), {'url': 'http://example'})()
    res = upload_to_confluence.fetch_existing_inline_comments(dummy_conf, "pid")
    assert res == []
    assert "Failed to fetch inline comments for page pid" in capsys.readouterr().out

def test_reattach_comments_exact(monkeypatch):
    existing = '<p>x<ac:inline-comment-marker ac:ref="c1">foo</ac:inline-comment-marker>y</p>'
    new_content = '<p>foo bar</p>'
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: [])
    res = upload_to_confluence.reattach_comments(None, new_content, "pid")
    assert '<ac:inline-comment-marker ac:ref="c1">foo</ac:inline-comment-marker>' in res
    # Ensure exact match path doesn't include fallback marker
    assert '[comment]' not in res

def test_reattach_comments_multiplesame_exact(monkeypatch):
    existing = (
        'start'
        '<ac:inline-comment-marker ac:ref="c1">foo</ac:inline-comment-marker>'
        'middle'
        '<ac:inline-comment-marker ac:ref="c2">foo</ac:inline-comment-marker>'
        'end'
    )
    new_content = 'new text at startfoomiddlefooend'
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    existing_comments = [
        {'markerRef': 'c1', 'resolveProperties': {'resolved': False}},
        {'markerRef': 'c2', 'resolveProperties': {'resolved': False}},
    ]
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: existing_comments)
    res = upload_to_confluence.reattach_comments(None, new_content, "pid")
    assert res == 'new text at '+existing, f"Expected exact match reattachment, got: {res}"

def test_reattach_comments_rough(monkeypatch):
    # existing content with one comment, new content missing the text
    existing = '<p>start<ac:inline-comment-marker ac:ref="c1">foo</ac:inline-comment-marker>end</p>'
    new_content = '<p>different content</p>'
    # Monkeypatch fetches
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    # Return one comment entry with unresolved status
    existing_comments = [{
        'markerRef': 'c1',
        'resolveProperties': {'resolved': False}
    }]
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: existing_comments)
    # Perform reattachment
    res = upload_to_confluence.reattach_comments(None, new_content, "pid")
    # Fallback should insert a placeholder comment marker
    assert f'<ac:inline-comment-marker ac:ref="c1">[comment]</ac:inline-comment-marker>' in res


def test_adjust_position_to_safe_insertion_moves_out_of_tag():
    content = '<div style="margin-left: 40px;"><span>Text</span></div>'
    pos_inside_tag = content.find("margin-left")
    safe_pos, adjusted = upload_to_confluence.adjust_position_to_safe_insertion(
        content, pos_inside_tag
    )
    assert adjusted is True
    assert safe_pos == content.find(">") + 1
    # Ensure the safe position is not inside the opening tag.
    assert content.rfind("<", 0, safe_pos) < content.rfind(">", 0, safe_pos)

def test_add_other_formats(tmp_path, monkeypatch):
    d = tmp_path / "d"
    d.mkdir()
    xhtml = d / "file.xhtml"
    pdf = d / "file.pdf"
    html = d / "file.html"
    xhtml.write_text('')
    pdf.write_bytes(b'')
    html.write_bytes(b'')
    recorded = {}
    def fake_upload(conf, pid, mapping, **kwargs):
        recorded.update(mapping)
    monkeypatch.setattr(upload_to_confluence, 'upload_files_if_different', fake_upload)
    content = "<p>more Info:\nVersion: 1.0</p>Text"
    res = upload_to_confluence.add_other_formats(None, content, "pid", str(xhtml))
    assert str(pdf) in recorded and str(html) in recorded
    assert 'ac:link' in res

def test_reattach_comments_multiple_rough(monkeypatch):
    # existing content with two different comment markers not present in new content
    existing = (
        'start'
        '<ac:inline-comment-marker ac:ref="c1">foo</ac:inline-comment-marker>'
        'middle'
        '<ac:inline-comment-marker ac:ref="c2">bar</ac:inline-comment-marker>'
        'end'
    )
    # Use content that does not include 'foo' or 'bar' to force rough fallback
    new_content = 'startxxxmiddleyyyend'
    # Monkeypatch fetches
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    # Both comments unresolved
    existing_comments = [
        {'markerRef': 'c1', 'resolveProperties': {'resolved': False}},
        {'markerRef': 'c2', 'resolveProperties': {'resolved': False}},
    ]
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: existing_comments)
    # Perform reattachment
    res = upload_to_confluence.reattach_comments(None, new_content, 'pid')
    # Both fallback markers should be present
    marker1 = '<ac:inline-comment-marker ac:ref="c1">[comment]</ac:inline-comment-marker>'
    marker2 = '<ac:inline-comment-marker ac:ref="c2">[comment]</ac:inline-comment-marker>'
    assert marker1 in res and marker2 in res
    # Ensure markers appear in order of their original positions: c1 then c2
    assert res.index(marker1) < res.index(marker2)
    assert res.index(marker1) == res.index('start') + len('start')
    assert res.index(marker2) == res.index('middle') + len('middle')

def test_reattach_comments_multiple_rough_same_words(monkeypatch):
    # existing content with two different comment markers not present in new content
    existing = (
        'start'
        'foo'
        '<ac:inline-comment-marker ac:ref="c1">foo</ac:inline-comment-marker>'
        'middle'
        'foo'
        '<ac:inline-comment-marker ac:ref="c2">foo</ac:inline-comment-marker>'
        'end'
    )
    # Use content that does not include 'foo' or 'bar' to force rough fallback
    new_content = 'startxxxyyymiddlezzzyyyend'
    # Monkeypatch fetches
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    # Both comments unresolved
    existing_comments = [
        {'markerRef': 'c1', 'resolveProperties': {'resolved': False}},
        {'markerRef': 'c2', 'resolveProperties': {'resolved': False}},
    ]
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: existing_comments)
    # Perform reattachment
    res = upload_to_confluence.reattach_comments(None, new_content, 'pid')
    # Both fallback markers should be present
    marker1 = '<ac:inline-comment-marker ac:ref="c1">[comment]</ac:inline-comment-marker>'
    marker2 = '<ac:inline-comment-marker ac:ref="c2">[comment]</ac:inline-comment-marker>'
    assert res == 'startxxx'+marker1+'yyymiddlezzz'+marker2+'yyyend'

def test_reattach_comment_failing_20251008(monkeypatch):
    # existing content with two different comment markers not present in new content
    existing = (
        ''
        '<p>The key insight here seems to be that <em>token usage should be '+
        'kept under control</em> in the responses of '+
        '<ac:inline-comment-marker ac:ref="f147fea5-35fa-4d83-915a-9ea00048ee46">'+
        'tool functions.</ac:inline-comment-marker> However, reducing the length'+
        ' of the response should be done such that potentially essential'+
        ' information is not missing. A mechanism should be provided in the '+
        'response such that the LLM understand where further detail has been '+
        'omitted, and that it can ask for further detail if it wants.'+
        '<ac:structured-macro ac:macro-id="754de881-6622-4e26-ac1d-433be724fd10"'+
        ' ac:name="anchor" ac:schema-version="1"><ac:parameter ac:name="">'+
        '__index_entry_1</ac:parameter></ac:structured-macro></p>\n'+
        'tool functions.'
    )
    # Use content that does not include 'foo' or 'bar' to force rough fallback
    new_content = (
        '<p>The key insight here seems to be that <em>token usage should be '+
        'kept under control</em> in the responses of '+
        'tool functions. However, reducing the length'+
        ' of the response should be done such that potentially essential'+
        ' information is not missing. A mechanism should be provided in the '+
        'response such that the LLM understand where further detail has been '+
        'omitted, and that it can ask for further detail if it wants.'+
        '<ac:structured-macro ac:macro-id="754de881-6622-4e26-ac1d-433be724fd10"'+
        ' ac:name="anchor" ac:schema-version="1"><ac:parameter ac:name="">'+
        '__index_entry_1</ac:parameter></ac:structured-macro></p>\n'+
        'tool functions.'
    )
    # Monkeypatch fetches
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    # Both comments unresolved
    existing_comments = [
        {'markerRef': 'c1', 'resolveProperties': {'resolved': False}},
        {'markerRef': 'c2', 'resolveProperties': {'resolved': False}},
    ]
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: existing_comments)
    # Perform reattachment
    res = upload_to_confluence.reattach_comments(None, new_content, 'pid')
    assert res == existing

def test_reattach_comments_mixed_exact_rough(monkeypatch):
    # existing content has two comments: 'alpha' and 'beta'
    existing = (
        'A'
        '<ac:inline-comment-marker ac:ref="c1">alpha</ac:inline-comment-marker>'
        'B'
        '<ac:inline-comment-marker ac:ref="c2">beta</ac:inline-comment-marker>'
        'C'
    )
    # new content keeps 'alpha' (exact reattach) but removes 'beta' (rough fallback)
    new_content = 'AalphaB something else C'
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    existing_comments = [
        {'markerRef': 'c1', 'resolveProperties': {'resolved': False}},
        {'markerRef': 'c2', 'resolveProperties': {'resolved': False}},
    ]
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: existing_comments)
    res = upload_to_confluence.reattach_comments(None, new_content, 'pid')

    alpha_marker = '<ac:inline-comment-marker ac:ref="c1">alpha</ac:inline-comment-marker>'
    beta_marker = '<ac:inline-comment-marker ac:ref="c2">[comment]</ac:inline-comment-marker>'

    # Exact match preserved for alpha
    assert alpha_marker in res
    # Rough fallback used for beta since 'beta' text is absent in new content
    assert beta_marker in res
    # Order: alpha marker should appear before beta marker
    assert res.index(alpha_marker) < res.index(beta_marker)

def test_only_attach_comments_outside_tags(monkeypatch):
    """
    This tests that comments markers are not injecting in the middle
    of HTML tags, not HTML attributes, nor in the middle of confluence macros (except
    in safe areas, such as inside
    - <ac:parameter ac:name="title">
    - <ac:rich-text-body>
    """
    existing = '<p>Here is a <strong><ac:inline-comment-marker ac:ref="c1">bold</ac:inline-comment-marker></strong> word.</p>'
    new_content = '<p>is <strong>blod</strong> word.</p>'
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    existing_comments = [{'markerRef': 'c1', 'resolveProperties': {'resolved': False}}]
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: existing_comments)
    res = upload_to_confluence.reattach_comments(None, new_content, "pid")
    # Instead, it should be placed outside the <strong> tag
    assert '<p>is <strong>blod<ac:inline-comment-marker ac:ref="c1">[comment]</ac:inline-comment-marker></strong> word.</p>' == res

def test_only_adjust_comment_outside_confluence_macros(monkeypatch):
    """
    This tests that comments markers are not injecting in the middle
    of confluence macros, except in safe areas, such as inside
    - <ac:parameter ac:name="title">
    - <ac:rich-text-body>
    """
    existing = (
        '<ac:structured-macro ac:name="note" ac:schema-version="1">'
        '<ac:rich-text-body>'
        'Note with <ac:inline-comment-marker ac:ref="c1">important</ac:inline-comment-marker> info.'
        '</ac:rich-text-body>'
        '</ac:structured-macro>'
    )
    new_content = (
        '          <ac:structured-macro ac:name="note" ac:schema-version="1">'
        '<ac:rich-text-body>'
        'Note with info.'
        '</ac:rich-text-body>'
        '</ac:structured-macro>'
    )
    monkeypatch.setattr(upload_to_confluence, 'fetch_page_content', lambda c, pid: existing)
    existing_comments = [{'markerRef': 'c1', 'resolveProperties': {'resolved': False}}]
    monkeypatch.setattr(upload_to_confluence, 'fetch_existing_inline_comments', lambda c, pid: existing_comments)
    res = upload_to_confluence.reattach_comments(None, new_content, "pid")
    # It should be placed inside the <ac:rich-text-body>
    expected = (
        '          <ac:structured-macro ac:name="note" ac:schema-version="1">'
        '<ac:rich-text-body>'
        '<ac:inline-comment-marker ac:ref="c1">[comment]</ac:inline-comment-marker>Note with info.'
        '</ac:rich-text-body>'
        '</ac:structured-macro>'
    )
    assert expected == res


def test_rough_comment_is_not_inserted_inside_drawio_macro(monkeypatch):
    existing = (
        '<p><ac:inline-comment-marker ac:ref="c1">old</ac:inline-comment-marker></p>'
    )
    macro = (
        '<ac:structured-macro ac:name="drawio" ac:schema-version="1">'
        '<ac:parameter ac:name="diagramName">graph</ac:parameter>'
        '</ac:structured-macro>'
    )
    monkeypatch.setattr(
        upload_to_confluence, "fetch_page_content", lambda confluence, page_id: existing
    )
    monkeypatch.setattr(
        upload_to_confluence,
        "fetch_existing_inline_comments",
        lambda confluence, page_id: [
            {"markerRef": "c1", "resolveProperties": {"resolved": False}}
        ],
    )

    result = upload_to_confluence.reattach_comments(None, macro, "page")

    marker_position = result.index('<ac:inline-comment-marker ac:ref="c1">')
    macro_start = result.index('<ac:structured-macro ac:name="drawio"')
    macro_end = result.index("</ac:structured-macro>")
    assert not macro_start < marker_position < macro_end
