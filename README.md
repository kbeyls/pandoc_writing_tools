# pandoc_writing_tools

This repository provides tools to write markdown documents, which are then built
to various output formats with Pandoc. It extends standard markdown by using
Pandoc's Lua filter system to add features like figure numbering,
cross-references, index entries, mini-TOCs, tracking TODOs, and more.

This repository evolved from the tools that were built to create
[llsoftsecbook](https://llsoftsec.github.io/llsoftsecbook/), but is designed to
be reusable for other content projects.

<!--TOC-->

- [pandoc_writing_tools](#pandoc_writing_tools)
  - [Quick start](#quick-start)
  - [Features, implemented as Lua filters](#features-implemented-as-lua-filters)
    - [Figures, examples, definitions, and section references (fignos.lua)](#figures-examples-definitions-and-section-references-fignoslua)
    - [Index entries (index.lua)](#index-entries-indexlua)
    - [Mini table of contents (toc.lua)](#mini-table-of-contents-toclua)
    - [Feedback buttons (add_feedback_buttons.lua)](#feedback-buttons-add_feedback_buttonslua)
    - [Markup TODOs (markup_todo.lua)](#markup-todos-markup_todolua)
    - [Features only for HTML output](#features-only-for-html-output)
      - [Clickable headers (clickable_headers.lua)](#clickable-headers-clickable_headerslua)
      - [Convert to sidenote (convert_to_sidenote.lua)](#convert-to-sidenote-convert_to_sidenotelua)
      - [Optional: markup_issue.lua](#optional-markup_issuelua)
      - [Optional: add_edit_to_headers.lua](#optional-add_edit_to_headerslua)
    - [Generate Confluence content (confluence.lua)](#generate-confluence-content-confluencelua)
    - [Confluence uploads (upload_to_confluence.py)](#confluence-uploads-upload_to_confluencepy)
  - [Using this repository for your own content projects](#using-this-repository-for-your-own-content-projects)
    - [Use it as a submodule inside your content repository](#use-it-as-a-submodule-inside-your-content-repository)
    - [Preferred build workflow (Docker)](#preferred-build-workflow-docker)
    - [Output formats](#output-formats)
  - [Contributing](#contributing)
  - [AI-assisted contribution policy](#ai-assisted-contribution-policy)

<!--TOC-->

## Quick start

0. Make sure you have Docker installed and running.
1. Clone this repository and its submodules:

   ```shell
   git clone --recursive https://github.com/kbeyls/pandoc_writing_tools.git
   ```

2. Build the feature demo:

   ```shell
   cd pandoc_writing_tools/examples/feature-demo
   ./build_with_docker.sh all
   ```

3. Open the generated HTML, PDF, and other files in
   `examples/feature-demo/build/` to see the various features in action.

## Features, implemented as Lua filters

This section describes the Lua filters provided in `theme/`, what features
they provide, and how to use those features in your markdown source.

All of these features are present in
`examples/feature-demo/src/feature-demo.md`, which you can refer to for a
complete demo of the syntax.

### Figures, examples, definitions, and section references (fignos.lua)

This script provides the ability to create numbered figures, examples and
definition environments, and to reference them from the text. It also provides
referring to sections by section number.

```markdown
![A demo figure](img/demo-figure.svg){#fig:demo}
See Figure [@fig:demo] for details.
```

Examples and definitions:

```markdown
::: {#ex:demo .example caption="Demo example"}
Example content.
:::

::: {#def:demo .definition caption="Demo definition"}
Definition content.
:::

See Example [@ex:demo] and Definition [@def:demo].
```

Section references:

```markdown
# Overview {#sec:overview}
See section [@sec:overview].
```

### Index entries (index.lua)

This lua filter allows you to mark index entries in the text, which are then
collected and emitted in an index div. The simplest usage is to just add
`.index` spans around the relevant text and add an index div somewhere in the
document. The filter will collect all `.index` spans and emit them as entries in
the index div. You can also specify an `entry` attribute on the span to
customize the index entry text, and use `!` to create nested entries.

```markdown
The [widget]{.index} is useful.
A [concept]{.index entry="idea"} can be renamed.
Nested entries: [widget!blue]{.index}.
Multiple entries: [alpha;beta]{.index}.

::: {#index}
:::
```

### Mini table of contents (toc.lua)

Insert a div that will contain a full or partial table of contents, requested
with the `toc-list-top-level` and `toc-list-entry-levels` attributes. The filter
will populate the div with a nested list of links to the headers in the document
that match the specified levels. For example, to insert a mini-TOC that includes
H2 and H3 headers under the "Overview" section:

```markdown
::: {toc-list-top-level=#sec:overview toc-list-entry-levels=2-3}
:::
```

To insert a full table of contents for the entire document, use:

```markdown
::: {toc-list-entry-levels=1-3}
:::
```

### Feedback buttons (add_feedback_buttons.lua)

Adds feedback buttons to H1/H2 headers. Requires metadata:

```yaml
contact-email: docs@example.com
```

`VERSION` is provided by the build tooling, and `title` is taken from the
front matter.

### Markup TODOs (markup_todo.lua)

Often while writing a document you want to mark TODO items in the text. Using
TODOs often helps you with overcoming writer's block. If there is just one thing
you can't put into words yet, just leave a TODO, which unblocks you and helps
you to continue writing.

This filter provides a way to do that, and to have them rendered in a consistent
way across output formats.

Inline and block TODOs:

```markdown
Please [fix this]{.todo}.

::: {.TODO}
Block TODO content.
:::
```

### Features only for HTML output

#### Clickable headers (clickable_headers.lua)

Adds a self-link anchor to headers in HTML. No extra syntax required.

#### Convert to sidenote (convert_to_sidenote.lua)

Footnotes become HTML sidenotes:

```markdown
This sentence has a note.[^1]

[^1]: Footnote content.
```

#### Optional: markup_issue.lua

Enables GitHub issue links for `.issue` spans. Requires metadata:

```yaml
github-repo: https://github.com/example/repo
```

Enable by setting `HTML_ISSUE_LINKS=1` before including the tools Makefile, or
on the command line:

```shell
make html HTML_ISSUE_LINKS=1
```

#### Optional: add_edit_to_headers.lua

Adds an edit link to each header. Required metadata (build fails if missing):

```yaml
edit-source-file: src/feature-demo.md
edit-url-base: https://github.com/example/repo/edit/main/src/feature-demo.md
```

Enable by setting `HTML_EDIT_LINKS=1` before including the tools Makefile, or
on the command line:

```shell
make html HTML_EDIT_LINKS=1
```

### Generate Confluence content (confluence.lua)

Used by the `xhtml` build target to emit Confluence storage format. This xhtml
output can be uploaded via the Confluence REST API and rendered properly on
Confluence pages. The `scripts/python/upload_to_confluence.py` script provides
an example of how to do that.

### Confluence uploads (upload_to_confluence.py)

Build the Confluence XHTML output, which can then be uploaded to Confluence
using the upload script with a Confluence PAT stored in an environment variable:

```shell
./build_with_docker.sh xhtml
uv run --project pandoc_writing_tools scripts/python/upload_to_confluence.py \
  --url https://<space>.atlassian.net/wiki \
  --env_token CONFLUENCE_TOKEN \
  --pageid 12345 \
  --file build/feature-demo.xhtml \
  --dry-run
```

Notes:

- `--dry-run` writes a prepared `.dryrun.confluence.xhtml` file and skips all
  remote updates. Use `--dry-run-output` to override the output path.
- Images referenced in the XHTML are uploaded as attachments and rewritten to
  Confluence attachment links.
- If `build/<name>.pdf` or `build/<name>.html` exists next to the XHTML file,
  those formats are uploaded as attachments and linked in the page.
- Inline comments are reattached on a best-effort basis (exact match first,
  then a position-based fallback).

## Using this repository for your own content projects

### Use it as a submodule inside your content repository

This repository is designed to be included as a git submodule inside your
"content repository". The content repository contains the markdown source files.
This repository is called the "tools repository" and contains the build tooling
and Lua filters.

Add the tools repo as a submodule and include its Makefile from a thin wrapper
Makefile in your content repo. The tools Makefile requires `CONTENT_ROOT` to be
set to the content repo root.

```Makefile
# In your content repo root
TOOLS_ROOT ?= $(CURDIR)/pandoc_writing_tools
CONTENT_ROOT := $(CURDIR)

include $(TOOLS_ROOT)/Makefile
```

Git-derived metadata (`VERSION`/`LAST_UPDATED`) is computed from the closest
`.git` directory when walking up from `CONTENT_ROOT`.

### Preferred build workflow (Docker)

Use the `examples/feature-demo/build_with_docker.sh` script whenever possible.
The Docker image pins Pandoc and all related dependencies, which avoids
breakage caused by local toolchain drift.

When you set up your own content repo, copy this script as a starting point and
adjust the content path and targets to match your project.

If you pass no arguments to the script, it runs `all`. From the demo folder,
run:

```shell
./build_with_docker.sh all
./build_with_docker.sh html
./build_with_docker.sh pdf
./build_with_docker.sh xhtml
```

### Output formats

Outputs are written under `build/` in the content repo:

- HTML: `build/*.html`
- PDF: `build/*.pdf`
- Confluence XHTML: `build/*.xhtml`
- DOCX: `build/*.docx`
- PPTX: `build/*.pptx`
- EML (HTML email with inline images): `build/*.eml`
- Pandoc native AST: `build/*.native`
- LaTeX: `build/*.tex`

## Contributing

Developer notes, regression testing, and golden update guidance live in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## AI-assisted contribution policy

The AI tool use policy for this project is inspired by the [LLVM AI Tool Use
Policy](https://llvm.org/docs/AIToolPolicy.html). Basically: contributors can
use whatever tools they would like to craft their contributions, but there must
be a human in the loop. Contributors must read and review all LLM-generated
code or text before they ask other project members to review it. The
contributor is always the author and is fully accountable for their
contributions. Contributors should be sufficiently confident that the
contribution is high enough quality that asking for a review is a good use of
scarce maintainer time, and they should be able to answer questions about their
work during review.

