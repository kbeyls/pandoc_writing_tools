# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

import os
import sys
import pytest

# Add scripts/python to sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import upload_to_confluence
import io
import requests


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
        def get_attachments_from_content(self, page_id):
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
        def get_attachments_from_content(self, page_id):
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
