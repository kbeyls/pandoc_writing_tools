# SPDX-FileCopyrightText: <text>Copyright 2025-2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

# This python script uploads the generated XHTML files to Confluence.
# It requires the 'atlassian-python-api' package, which can be installed via pip:
# pip install atlassian-python-api
import argparse
import html
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests
from atlassian import Confluence

from generate_drawio_overlay import read_png_size

confluence_token = None

DRAWIO_MEDIA_TYPE = "application/vnd.jgraph.mxfile"
DRAWIO_MACRO_RE = re.compile(
    r'<ac:structured-macro\b(?=[^>]*ac:name="drawio")[\s\S]*?</ac:structured-macro>'
)


@dataclass(frozen=True)
class AttachmentSpec:
    source_path: str
    attachment_name: str
    content_type: str
    role: str = "ordinary"


@dataclass(frozen=True)
class DrawioDiagram:
    source_path: str
    preview_path: str
    attachment_name: str
    preview_attachment_name: str
    macro_id: str
    revision_token: str


# Upload XHTML files to Confluence
def upload_xhtml_to_confluence(confluence, page_id, page_title, content):

    confluence.update_page(
        page_id=page_id,
        title=page_title,
        body=content,
        representation="storage",  # 'storage' is the format for XHTML content
    )


def get_confluence_connection(confluence_url, api_token):
    # use user PAT token for authentication
    confluence = Confluence(url=confluence_url, token=api_token)
    return confluence


def get_xhtml_content(file_path):
    with open(file_path, "r") as file:
        content = file.read()
    return content


def rewrite_attachment_paths(content, base_path):
    # Find all image references in the xhtml content and rewrite their paths
    # to be just the filename, as Confluence will handle the attachment paths
    imgpath2attachment_name = {}

    def replace_img_path(match):
        full_path = match.group(1)
        filename = os.path.basename(full_path)
        imgpath2attachment_name[full_path] = filename
        return f'ri:filename="{filename}"'

    content = re.sub(r'ri:filename="([^"]+)"', replace_img_path, content)
    return content, imgpath2attachment_name


def _replace_macro_parameter(macro, name, value):
    pattern = re.compile(
        rf'(<ac:parameter ac:name="{re.escape(name)}">)[\s\S]*?(</ac:parameter>)'
    )
    updated, count = pattern.subn(
        lambda match: (
            match.group(1)
            + html.escape(str(value), quote=False)
            + match.group(2)
        ),
        macro,
        count=1,
    )
    if count != 1:
        raise ValueError(f"draw.io macro is missing parameter {name!r}")
    return updated


def prepare_drawio_macros(content):
    """Resolve generated draw.io paths and static macro placeholders."""

    diagrams = []
    attachment_sources = {}

    def replace_macro(match):
        macro = match.group(0)
        if "__DRAWIO_MACRO_ID__" not in macro:
            return macro
        name_match = re.search(
            r'<ac:parameter ac:name="diagramName">([\s\S]*?)</ac:parameter>',
            macro,
        )
        if not name_match:
            raise ValueError("draw.io macro is missing parameter 'diagramName'")
        source_path = html.unescape(name_match.group(1))
        if not source_path.endswith(".drawio"):
            return macro

        source = Path(source_path)
        preview = source.with_suffix(".png")
        if not source.is_file():
            raise FileNotFoundError(f"draw.io source attachment does not exist: {source}")
        if not preview.is_file():
            raise FileNotFoundError(f"draw.io preview attachment does not exist: {preview}")

        attachment_name = source.stem
        preview_attachment_name = attachment_name + ".png"
        previous = attachment_sources.setdefault(attachment_name, str(source))
        if previous != str(source):
            raise ValueError(
                f"draw.io attachment name collision for {attachment_name!r}: "
                f"{previous} and {source}"
            )

        occurrence = len(diagrams) + 1
        macro_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"drawio:{source.as_posix()}:{occurrence}")
        )
        revision_token = f"__DRAWIO_REVISION_{macro_id}__"
        width, height = read_png_size(preview)

        macro = macro.replace("__DRAWIO_MACRO_ID__", macro_id)
        macro = _replace_macro_parameter(macro, "diagramName", attachment_name)
        macro = _replace_macro_parameter(macro, "diagramWidth", width)
        macro = _replace_macro_parameter(macro, "height", height)
        macro = _replace_macro_parameter(macro, "revision", revision_token)
        diagrams.append(
            DrawioDiagram(
                source_path=str(source),
                preview_path=str(preview),
                attachment_name=attachment_name,
                preview_attachment_name=preview_attachment_name,
                macro_id=macro_id,
                revision_token=revision_token,
            )
        )
        return macro

    return DRAWIO_MACRO_RE.sub(replace_macro, content), diagrams


def finalize_drawio_revisions(content, diagrams, attachment_versions, *, dry_run=False):
    for diagram in diagrams:
        if dry_run:
            revision = "DRY_RUN_REVISION"
        else:
            revision = attachment_versions.get(diagram.attachment_name)
            if revision is None:
                raise RuntimeError(
                    f"Confluence did not report a revision for draw.io attachment "
                    f"{diagram.attachment_name!r}"
                )
        content = content.replace(diagram.revision_token, str(revision))
    return content


def content_type_for_attachment(attachment_name):
    suffix = Path(attachment_name).suffix.lower()
    return {
        ".html": "text/html",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".txt": "text/plain",
    }.get(suffix, "application/octet-stream")


def attachment_specs(image_paths, diagrams=()):
    specs = [
        AttachmentSpec(
            source_path=source_path,
            attachment_name=attachment_name,
            content_type=content_type_for_attachment(attachment_name),
        )
        for source_path, attachment_name in image_paths.items()
    ]
    for diagram in diagrams:
        specs.extend(
            [
                AttachmentSpec(
                    source_path=diagram.source_path,
                    attachment_name=diagram.attachment_name,
                    content_type=DRAWIO_MEDIA_TYPE,
                    role="drawio-source",
                ),
                AttachmentSpec(
                    source_path=diagram.preview_path,
                    attachment_name=diagram.preview_attachment_name,
                    content_type="image/png",
                    role="drawio-preview",
                ),
            ]
        )

    unique_by_name = {}
    for spec in specs:
        previous = unique_by_name.get(spec.attachment_name)
        if previous is not None and previous.source_path != spec.source_path:
            raise ValueError(
                f"attachment name collision for {spec.attachment_name!r}: "
                f"{previous.source_path} and {spec.source_path}"
            )
        if previous is None or spec.role != "ordinary":
            unique_by_name[spec.attachment_name] = spec
    return list(unique_by_name.values())


def fetch_attachment_metadata(confluence, page_id):
    """Fetch enough attachment metadata to compare files and resolve versions."""

    return confluence.get_attachments_from_content(
        page_id, limit=500, expand="version"
    )


def upload_attachment_specs_if_different(
    confluence, page_id, specs, dry_run=False
):
    if dry_run:
        for spec in specs:
            print(
                f"[dry-run] Would upload {spec.role} attachment "
                f"{spec.attachment_name} from {spec.source_path} to page {page_id}"
            )
        return {}

    existing_response = fetch_attachment_metadata(confluence, page_id)
    existing = {
        attachment["title"]: attachment
        for attachment in existing_response.get("results", [])
    }
    versions = {}
    uploaded = False
    for spec in specs:
        source = Path(spec.source_path)
        if not source.is_file():
            raise FileNotFoundError(f"attachment source does not exist: {source}")
        attachment = existing.get(spec.attachment_name)
        if attachment:
            download_url = attachment["_links"]["download"]
            existing_content = requests.get(
                confluence.url + download_url,
                headers={"Authorization": "Bearer " + confluence_token},
            ).content
            if existing_content == source.read_bytes():
                print(
                    f"Attachment {spec.attachment_name} already exists on page "
                    f"{page_id} with identical content, skipping upload."
                )
                version = attachment.get("version", {}).get("number")
                if version is not None:
                    versions[spec.attachment_name] = version
                continue
        confluence.attach_file(
            filename=str(source),
            page_id=page_id,
            name=spec.attachment_name,
            content_type=spec.content_type,
        )
        uploaded = True
        print(f"Uploaded attachment {spec.attachment_name} to page {page_id}")

    if uploaded or any(spec.attachment_name not in versions for spec in specs):
        refreshed = fetch_attachment_metadata(confluence, page_id)
        for attachment in refreshed.get("results", []):
            version = attachment.get("version", {}).get("number")
            if version is not None:
                versions[attachment["title"]] = version
    return versions

def upload_files_if_different(confluence, page_id, file_paths2attachment_names, dry_run: bool = False):
    """
    Upload files to Confluence if they are different from existing attachments.
    :param confluence: Confluence instance
    :param page_id: ID of the Confluence page
    :param file_paths2attachment_names: dict mapping full file paths to attachment names
    """
    specs = attachment_specs(file_paths2attachment_names)
    return upload_attachment_specs_if_different(
        confluence, page_id, specs, dry_run=dry_run
    )

def fetch_page_content(confluence, page_id):
    # page = confluence.get_page_by_id(page_id, expand="body.storage")
    # return page["body"]["storage"]["value"]
    # fetch the page content using the REST API directly to avoid issues with atlassian-python-api
    # This is a workaround for a bug where it seems atlassian-python-api doesn't include
    # inline comment markers in the fetched content.
    url = f"{confluence.url}/rest/api/content/{page_id}?expand=body.storage"
    headers = {"Authorization": "Bearer " + confluence_token,
               "Accept": "application/json"}
    # Don't use the confluence session method to avoid the bug. Instead use requests directly.
    response = requests.get(url, headers=headers)
    #print(f"Fetched page content for page {page_id} via REST API:\n{response.json()}\n")
    # sys.exit(0)
    return response.json()["body"]["storage"]["value"]

def fetch_existing_inline_comments(confluence, page_id):
    url = f"{confluence.url}/rest/inlinecomments/1.0/comments?containerId={page_id}"
    headers = {"Authorization": "Bearer " + confluence_token,
               "Accept": "application/json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch inline comments for page {page_id}: {response.status_code}, {response.text}")
        return []

def adjust_position_to_safe_insertion(content, pos):
    """
    Adjust positions to put comments in so that they are not inside HTML tags or Confluence ac macros.
    There are a few exceptions for the confluence ac macros: comments are allowed inside tags
    that allow general content, such as <ac:rich-text-body>, but not inside tags that define structure,
    such as <ac:structured-macro>.
    """
    # Move pos backwards until we are not inside a tag or macro
    original_pos = pos
    while pos > 0:
        # Fast check: if the last '<' is after the last '>', we are inside a tag.
        last_lt = content.rfind("<", 0, pos)
        last_gt = content.rfind(">", 0, pos)
        if last_lt > last_gt:
            after = content.find(">", last_lt)
            if after == -1:
                break
            # If we're inside a closing tag, move before it; otherwise move after it.
            if content.startswith("</", last_lt):
                pos = last_lt
            else:
                pos = after + 1
            continue
        # Check if we are inside an ac macro
        before_macro = content.rfind("<ac:", 0, pos)
        after_macro = content.find("</ac:", before_macro)
        if before_macro != -1 and after_macro != -1 and before_macro < pos < after_macro:
            # if the closest tag is <ac:rich-text-body>, it's allowed
            tag_match = re.match(r"<ac:([a-zA-Z0-9_-]+)", content[before_macro:after_macro])
            if tag_match and tag_match.group(1) == "rich-text-body":
                break
            pos = before_macro
            continue
        break
    return pos, pos != original_pos


def reattach_comments(confluence, content, page_id):
    # Fetch the content that is already on the Confluence page.
    # Then extract all comment markers and reattach them to the new content.
    # For now use a very simple algorithm:
    # 1. if the text inside the comment marker is found exactly once in the new content,
    #    reattach the comment marker there.
    # 2. if not found or found multiple times, put the comment on an empty space roughly
    #    where it was before.
    # existing_content = confluence.get_page_by_id(page_id, expand="body.storage")
    existing_content = fetch_page_content(confluence, page_id)
    #print(f"Fetched existing content for page {page_id}:\n{existing_content}\n")
    print("Reattaching comments...")
    existing_comments = fetch_existing_inline_comments(confluence, page_id)
    #print(f"Existing body:\n{existing_content}\n")

    # We use the following rules to reattach comments:
    # 1. If the commented text is found exactly once in the new content,
    #    reattach it there.
    # 2. If not found or found multiple times, find a rough position based on
    #    the original position, following these rules:
    #    a. If the commented text is present multiple times, and it is present
    #       the same number of times in the original content,
    #       use the occurrence that matches the original position best.
    #    b. If the commented text is not present in the new content, use the
    #       original position as a rough guide.
    #    c. If the commented text is present multiple times, but not the same
    #       number of times as in the original content,
    #       use the original position as a rough guide.
    # 3. If the comment is marked as resolved, do not reattach it if there is
    #    no exact match (rule 1).

    # Start by scanning all comments, and categorize them according to the
    # above rules.

    # stripped_pos will refer to the position of where the start of a marker
    # is found, after removing all markers from the original content.
    stripped_pos2comment_info = {}
    offset_after_stripping_markers = 0
    comment_marker_regex = r'<ac:inline-comment-marker ac:ref="([^"]+)">([^<]*)</ac:inline-comment-marker>'

    for match in re.finditer(
        comment_marker_regex,
        existing_content,
    ):
        comment_id = match.group(1)
        commented_text = match.group(2)
        # after removing the marker, only the commented_text remains
        #print(f"Found comment: id={comment_id}, text='{commented_text}'")
        stripped_pos = match.start() - offset_after_stripping_markers
        stripped_pos2comment_info[stripped_pos] = (
            stripped_pos,
            comment_id,
            commented_text,
        )
        offset_after_stripping_markers += (match.end() - match.start()) - len(commented_text)

    # strip the comment markers from existing_content:
    stripped_existing_content = re.sub(
        comment_marker_regex,
        r"\2",
        existing_content,
    )

    comment2insertion_info = {}
    for stripped_pos, (stripped_pos, comment_id, commented_text) in stripped_pos2comment_info.items():
        #print(f"Found comment: id={comment_id}, text='{commented_text}'")
        print(f"Trying to match comment on {commented_text}")
        # Try to find the commented text in the new content
        occurrences = [
            m.start() for m in re.finditer(re.escape(commented_text), content)
        ]
        if len(occurrences) == 1:
            # Found exactly one occurrence, reattach the comment here
            comment2insertion_info[comment_id] = (
                True,
                occurrences[0],
                commented_text,
            )
        elif len(occurrences) > 1:
            # Found multiple occurrences in the NEW content. We must decide which
            # occurrence to reattach to by mapping from the ORIGINAL stripped content.
            # Strategy:
            # 1) Compute which occurrence index the original comment referred to in the
            #    stripped existing content (using exact position if possible, otherwise closest).
            # 2) If the new content has the same number of occurrences, reattach to the
            #    same occurrence index to maintain intent.
            # 3) If multiplicity changed, fall back to a rough placement at the original
            #    stripped position (non-destructive insertion).
            def find_occurrence_index_and_count(stripped_existing_content, stripped_pos, commented_text):
                """
                Determine which occurrence of commented_text in the stripped existing content
                corresponds to stripped_pos, and how many total occurrences exist.

                Returns (occurrence_index, total_occurrences).
                """
                assert commented_text is not None and commented_text != ""
                positions = [m.start() for m in re.finditer(re.escape(commented_text), stripped_existing_content)]
                total = len(positions)
                assert total > 1
                for idx, pos in enumerate(positions):
                    if pos == stripped_pos:
                        return idx, total
                # Fallback: choose closest occurrence to original stripped_pos
                closest_idx = min(range(len(positions)), key=lambda i: abs(positions[i] - stripped_pos))
                return closest_idx, total

            occ_index_in_existing, count_in_existing = find_occurrence_index_and_count(
                stripped_existing_content, stripped_pos, commented_text
            )
            if count_in_existing == len(occurrences):
                # Same multiplicity: map the occurrence index from existing to new content.
                # This avoids overlapping or reattaching both comments to the same span.
                mapped_pos = occurrences[min(occ_index_in_existing, len(occurrences) - 1)]
                comment2insertion_info[comment_id] = (
                    True,
                    mapped_pos,
                    commented_text,
                )
                print(
                    f"Multiple occurrences of '{commented_text}', reattaching to occurrence {occ_index_in_existing+1} of {len(occurrences)}."
                )
            else:
                # Different multiplicity: fall back to rough reattachment at original stripped_pos.
                # We insert the marker without deleting any content, and use a placeholder
                # text to indicate loss of an exact anchor.
                comment2insertion_info[comment_id] = (
                    False,
                    stripped_pos,
                    commented_text,
                )
                print(
                    f"Multiple occurrences of '{commented_text}', but different count ({count_in_existing} vs {len(occurrences)}), using rough position."
                )
        else:
            # Not found or multiple occurrences, find a rough position
            # For simplicity, just put it at the same offset as before, derived from the match
            comment2insertion_info[comment_id] = (
                False,
                stripped_pos,
                "[comment]",
            )

    # Now insert the comments back into the content
    # But first, readjust the comment positions to be inserted, so that they are not inserted
    # in the middle of HTML tags or confluence ac macros.
    for comment_id, (exact, pos, commented_text) in comment2insertion_info.items():
        safe_pos, adjusted = adjust_position_to_safe_insertion(content, pos)
        if adjusted:
            print(
                f"Adjusted insertion position for comment {comment_id} (exact: {exact}) "
                f"from {pos} to {safe_pos} to avoid HTML tags/macros."
            )
        comment2insertion_info[comment_id] = (
            exact,
            safe_pos,
            commented_text,
            adjusted,
        )
    # Sort comments by their original position to avoid messing up offsets
    sorted_comments = sorted(
        comment2insertion_info.items(), key=lambda x: x[1][1], reverse=True
    )
    for comment_id, (exact, pos, commented_text, adjusted) in sorted_comments:
        marker = (
            f'<ac:inline-comment-marker ac:ref="{comment_id}">{commented_text}</ac:inline-comment-marker>'
        )
        if exact:
            # Replace exact spans unless adjusted; adjusted inserts marker without deleting.
            if adjusted:
                content = content[:pos] + marker + content[pos:]
            else:
                content = content[:pos] + marker + content[pos + len(commented_text) :]
        else:
            # Rough match: insert the marker at the computed position without deleting content
            content = content[:pos] + marker + content[pos:]
        print(
            f"Reattached comment {comment_id} on '{commented_text}' at ",
            "exact" if exact else "rough", " match."
        )
    #print(f"Content after reattaching comments:\n{content}\n")
    #sys.exit(0)

    return content

def add_other_formats(confluence, content, page_id, xhtml_file, dry_run: bool = False):
    # Check if there are attachments with other formats (e.g. .pdf, .docx) for the same base name as the xhtml file
    base_name = os.path.splitext(os.path.basename(xhtml_file))[0]
    dir_name = os.path.dirname(xhtml_file)
    other_formats = ["pdf", "html"]
    filepath2attachment_name = {}
    fmt2attachment_name = {}
    for fmt in other_formats:
        other_file = os.path.join(dir_name, base_name + "." + fmt)
        if os.path.exists(other_file):
            filepath2attachment_name[other_file] = os.path.basename(other_file)
            fmt2attachment_name[fmt] = os.path.basename(other_file)
    upload_files_if_different(confluence, page_id, filepath2attachment_name, dry_run=dry_run)
    # Now add links to these attachments in the content, right after the version info
    insertion_point = None
    for match in re.finditer(r"\nVersion: .*<\/p>", content):
        insertion_point = match.start()
        break
    if insertion_point is None:
        print("Warning: Could not find version info paragraph to insert other format links after.")
        return content
    links_html = "\nOther formats: "
    for fmt in sorted(fmt2attachment_name.keys()):
        # add link in confluence storage format
        attachment_name = fmt2attachment_name[fmt]
        links_html += (f'<ac:link><ri:attachment ri:filename="{attachment_name}" />'
            + f'<ac:plain-text-link-body><![CDATA[[{fmt}]]]></ac:plain-text-link-body></ac:link> ')
    links_html += "<br />"
    content = content[:insertion_point] + links_html + content[insertion_point:]
    return content

def extract_title_from_content(content):
    # Title will be in a comment: <!-- Title: ... -->
    title_match = re.search(r'<!-- Title: (.*?) -->', content)
    if title_match:
        return title_match.group(1)
    return None

def get_page_title(content, xhtml_file):
    title = extract_title_from_content(content)
    if title:
        return title
    return os.path.splitext(os.path.basename(xhtml_file))[0]

def main():
    # get the name of the xhtml file and the confluence page id from command line arguments
    # parse arguments
    parser = argparse.ArgumentParser(description="Upload XHTML files to Confluence.")
    parser.add_argument("--url", required=True, help="Confluence base URL")
    parser.add_argument(
        "--env_token",
        required=True,
        help="Environment variable containing Confluence API token",
    )
    parser.add_argument("--pageid", required=True, help="Confluence page ID")
    parser.add_argument("--file", required=True, help="XHTML file to upload")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Prepare new page content and write it to a local file without "
            "uploading to Confluence. Skips all remote updates."
        ),
    )
    parser.add_argument(
        "--dry-run-output",
        default=None,
        help=(
            "Optional path to write prepared content when --dry-run is set. "
            "Defaults to <input_basename>.dryrun.confluence.xhtml in the same directory."
        ),
    )
    args = parser.parse_args()

    page_id = args.pageid
    xhtml_file = args.file

    global confluence_token
    confluence_token = os.getenv(args.env_token)
    if confluence_token is None:
        print(f"Environment variable {args.env_token} is not set.")
        return
    confluence = get_confluence_connection(args.url, confluence_token)
    if confluence is None:
        print("Failed to connect to Confluence. Check your URL and API token.")
        return

    content = get_xhtml_content(xhtml_file)
    page_title = get_page_title(content, xhtml_file)
    content, imgpath2attachment_name = rewrite_attachment_paths(
        content, os.path.dirname(xhtml_file)
    )
    content, drawio_diagrams = prepare_drawio_macros(content)
    content = reattach_comments(confluence, content, page_id)
    content = add_other_formats(confluence, content, page_id, xhtml_file, dry_run=args.dry_run)
    specs = attachment_specs(imgpath2attachment_name, drawio_diagrams)

    if args.dry_run:
        content = finalize_drawio_revisions(
            content, drawio_diagrams, {}, dry_run=True
        )
        # Determine output path
        if args.dry_run_output:
            out_path = args.dry_run_output
        else:
            base, _ = os.path.splitext(xhtml_file)
            out_path = base + ".dryrun.confluence.xhtml"
        # Write prepared content for inspection
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[dry-run] Prepared content written to {out_path}")
        print(f"[dry-run] Skipping upload of page {page_id} titled '{page_title}'")
        upload_attachment_specs_if_different(
            confluence, page_id, specs, dry_run=True
        )
        print(f"[dry-run] Would target URL: {args.url}/pages/viewpage.action?pageId={page_id}")
        return

    attachment_versions = upload_attachment_specs_if_different(
        confluence, page_id, specs
    )
    content = finalize_drawio_revisions(
        content, drawio_diagrams, attachment_versions
    )
    upload_xhtml_to_confluence(confluence, page_id, page_title, content)
    print(f"Uploaded {xhtml_file} to Confluence page {page_id} as {page_title}")
    print(f"URL: {args.url}/pages/viewpage.action?pageId={page_id}")


if __name__ == "__main__":
    main()
