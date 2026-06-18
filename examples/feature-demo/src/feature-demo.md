---
title: "pandoc_writing_tools Feature Demo"
contact-email: docs@example.com
github-repo: https://github.com/kbeyls/pandoc_writing_tools
edit-source-file: src/feature-demo.md
edit-url-base: https://github.com/kbeyls/pandoc_writing_tools/edit/main/examples/feature-demo/src/feature-demo.md
bibliography: src/feature-demo.bib
---

<!--
SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com></text>
SPDX-License-Identifier: MIT
-->

# Overview {#sec:overview}

This document demonstrates the functionality of the Lua filters in
pandoc_writing_tools.

## Citations and section references {#sec:citations-and-refs}

This is what a citation looks like: [@doe2020]. The list of all cited references
appears in the bibliography section at the end of the document.

The pandoc_writing_tools lua filters enable referring to a section by number,
for example, this references section [@sec:overview].

## Table of contents {#table-of-contents}

The table of contents is generated from the section headers. The
`toc-list-top-level` and `toc-list-entry-levels` attributes control which
headers are included and how they are nested. For example, the mini-TOC below
includes level 2 and level 3 headers under the "Overview" section:

::: {toc-list-top-level=#sec:overview toc-list-entry-levels=2-3}
:::

## Figures and references {#sec:figures}

![A demo figure](img/demo-figure){#fig:demo}

See Figure [@fig:demo] for the numbered figure reference.

## Examples and definitions {#sec:examples}

We have custom environments for examples and definitions, which are numbered and
can be referenced from the text:

::: {#ex:demo .example caption="Demo example"}
This block is tagged as an example.
:::

::: {#def:demo .definition caption="Demo definition"}
This block is tagged as a definition.
:::

Refer back to Example [@ex:demo] and Definition [@def:demo].

## Index entries {#sec:index-entries}

The index filter allows you to mark index entries in the text, which are then
collected and emitted in an index div, see at the end of this document. The
simplest usage is to just add `.index` spans around the relevant text and add an
index div somewhere in the document. The filter will collect all `.index` spans
and emit them as entries in the index div. You can also specify an `entry`
attribute on the span to customize the index entry text, and use `!` to create
nested entries.

For example, in this sentence the word [color]{.index} is indexed, and a
we index the word "[concept]{.index entry="idea"}" as "idea". We can also create
nested entries like [color!blue]{.index}, and multiple entries like
[alpha;beta]{.index}.

## Sidenotes {#sec:sidenotes}

This sentence has a footnote.[^1]

[^1]: Footnote content that becomes a sidenote in HTML.

## TODOs {#sec:todos}

It is often useful to be able to mark TODO items in the text. It helps you to
avoid writer's block on something you can't quite put into words just yet. The
`markup_todo.lua` filter allows you to do this with a `.todo` class. You can use
this class on inline spans for inline TODOs, or on divs for block TODOs.
For example, please [fix this]{.todo} inline.

::: {.TODO}
Block TODO content.
:::

## Linking to github issues and edit links {#sec:github-links}

Github issue link when enabled: Github issue [1]{.issue}.

Edit links appear as little pencil icons at the end of headers when
`add_edit_to_headers.lua` is enabled.

::: {#index}
:::

# Standard Pandoc Regression Coverage {#sec:standard-pandoc-regression}

The features in this final section are standard Pandoc features. They are not
features added or enabled by the pandoc_writing_tools Lua filters.

This section exists to regression-test whether selected Pandoc features keep
working across output formats. In particular, it helps catch accidentally
missing dependencies that are needed for LaTeX/PDF output when standard Pandoc
constructs trigger extra TeX packages.

## Tables {#sec:standard-pandoc-tables}

This table exercises Pandoc's standard Markdown table support. For LaTeX/PDF
output, Pandoc renders this construct through longtable-compatible LaTeX.

| Standard Pandoc feature | Regression coverage |
| --- | --- |
| Markdown tables | Longtable-compatible LaTeX/PDF output |
| LaTeX package selection | Required TeX packages are installed |

The grid table below includes a row span. For LaTeX/PDF output, Pandoc renders
this standard table construct with the `multirow` package.

+-------------------------+-------------------------------+
| Standard Pandoc feature | Regression coverage           |
+=========================+===============================+
| Grid table row span     | First row covered by span     |
|                         +-------------------------------+
|                         | Second row covered by span    |
+-------------------------+-------------------------------+
