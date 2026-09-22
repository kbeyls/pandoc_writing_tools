# Add title-aware section reference styles

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This plan follows `agent/PLANS.md` in the consuming repository that contains this `pandoc_writing_tools` checkout. It is stored at `agent/tasks/section-reference-styles.execplan.md` relative to the `pandoc_writing_tools` repository root. A future contributor must maintain this document in accordance with `agent/PLANS.md` and must be able to resume the work using this file alone.

## Purpose / Big Picture

After this change, an author can choose whether a reference to a labelled section displays the section number, the section title, or both. Existing Markdown such as `section @sec:overview` remains backward compatible and continues to render as, for example, `section 1.2`. An author can opt into a title for one reference with `section [@sec:overview]{ref-style=title}`, or into a combined reference with `section [@sec:overview]{ref-style=number-title}`. A document can choose one of these styles as its default in YAML metadata and can still override that default at an individual reference.

A section may also declare a concise reference title when its visible heading is too long:

    ### GraphCompiler and framework inputs {#sec:graph-inputs ref-title="framework inputs"}

    See section [@sec:graph-inputs]{ref-style=title}.

The result is a link whose visible text is `“framework inputs”`. Without `ref-title`, the filter uses the complete visible heading text. The combined style renders `1.2.3 (“framework inputs”)`. The feature must work through the same ordinary Pandoc link representation already used by numbered references, so HTML, Confluence XHTML, LaTeX/PDF, DOCX, PPTX, native and email outputs all receive equivalent visible text and the same `#sec:graph-inputs` target.

## Progress

- [x] (2026-09-22 09:23Z) Inspected the existing section-numbering and reference implementation in `theme/fignos.lua`, the feature-demo documentation, the Confluence link writer and the regression-output test framework.
- [x] (2026-09-22 09:23Z) Chose the author-facing syntax, precedence rules, validation behavior and exact visible forms recorded in the Decision Log.
- [x] (2026-09-22 09:23Z) Created this implementation-ready ExecPlan; no production code or generated golden output has been changed yet.
- [x] (2026-09-22 09:28Z) Added focused filter tests; the pre-implementation baseline was 13 failures and 2 compatibility passes.
- [x] (2026-09-22 09:31Z) Refactored `theme/fignos.lua` to retain plain titles, validate styles, honor YAML defaults and local overrides, and preserve non-control link attributes. The focused filter and index suites pass all 17 tests.
- [x] (2026-09-22 09:33Z) Extended the feature demo and README with the new section-reference API, precedence and manual-link escape hatch.
- [x] (2026-09-22 09:35Z) Fixed a pre-existing split pattern rule that fed the version stamp, rather than Markdown, to transformed-native builds; added an integration test proving transformed native contains the source document.
- [x] (2026-09-22 09:36Z) Regenerated and reviewed all seven affected regression goldens. The large native diff replaces the erroneous version-stamp AST with the complete transformed feature-demo AST.
- [x] (2026-09-22 09:37Z) Ran focused, REUSE, non-regression, regression and full-suite validation; all checks pass.
- [x] (2026-09-22 09:37Z) Completed `Outcomes & Retrospective`; implementation is ready to commit.

## Surprises & Discoveries

- Observation: The section filter already sees each complete `Header`, but it saves only the hierarchical number for later references.
  Evidence: `theme/fignos.lua` stores the counter in `headerlabel2counter` in `process_headers`, and `process_sec_cite` later constructs link text only from `get_section_reference_text(label)`.
- Observation: Pandoc parses `[@sec:overview]{ref-style=title}` as a `Span` whose only child is the section `Cite`, rather than adding attributes directly to the `Cite`.
  Evidence: `pandoc --from markdown -t native` shows `Span ("", [], [("ref-style","title")]) [Cite ...]` for that source form. The implementation therefore needs a `Span` pass before the ordinary `Cite` pass.
- Observation: Adding a citation prefix inside the same attributed brackets changes the AST shape unless the citation itself is nested in a second bracket pair.
  Evidence: `[see @sec:overview]{ref-style=title}` becomes a Span containing plain `Str`, `Space`, and a bare Cite, while `[[see @sec:overview]]{ref-style=title}` becomes a Span containing one Cite whose `citationPrefix` is `see`. The documented prefixed form therefore uses doubled brackets.
- Observation: The custom Confluence writer already renders arbitrary inline link content inside an `<ac:link-body>` for same-document anchors.
  Evidence: `theme/confluence.lua` implements `Writer.Inline.Link` by calling `Writer.Inlines(link.content)` and uses the resulting content for links whose target starts with `#`. No Confluence-specific section-reference implementation is needed.
- Observation: The feature demo is the cross-format regression fixture and already demonstrates numbered section references.
  Evidence: `examples/feature-demo/src/feature-demo.md` labels `# Overview` as `sec:overview`, and `scripts/python/tests/test_regression_outputs.py` compares normalized HTML, XHTML, TeX, PDF, native, DOCX, PPTX and EML outputs with checked-in goldens.
- Observation: The transformed-native rule was split into two declarations of the same pattern target, which GNU Make does not merge like explicit rules.
  Evidence: `make -B -n build/feature-demo.transformed.native` showed Pandoc reading `build/.version-feature-demo.stamp` through `$<`; `make -pn` omitted the Markdown and filter prerequisites. Combining the prerequisites onto the recipe-bearing rule restores `src/feature-demo.md` as `$<` and is required for meaningful native goldens.
- Observation: The sandboxed Homebrew `uv` executable panicked while initializing macOS system configuration, although the repository virtual environment was already synchronized.
  Evidence: `uv run --project . ...` failed in `system-configuration-0.6.1`, while the equivalent `.venv/bin/python -m pytest` and `.venv/bin/reuse` commands completed normally. Validation used the existing project environment without changing dependencies.

## Decision Log

- Decision: Preserve `number` as the default style when a document has no `section-reference-style` metadata.
  Rationale: Existing documents must not change merely because they update the tools submodule. Current `@sec:` references display numbers, and this remains the compatibility baseline.
  Date/Author: 2026-09-22 / Codex
- Decision: Support exactly three initial styles named `number`, `title` and `number-title`.
  Rationale: These cover the current behavior, a descriptive alternative and the useful combined form without introducing ambiguous synonyms. More styles can be added later without changing the syntax.
  Date/Author: 2026-09-22 / Codex
- Decision: Use `section-reference-style` in document YAML metadata and `ref-style` on an individual reference span.
  Rationale: The metadata name is explicit at document scope. The shorter local attribute is readable in `[@sec:id]{ref-style=title}` and leaves room for the same general concept to be extended to figures or definitions later.
  Date/Author: 2026-09-22 / Codex
- Decision: Apply precedence in this order: a valid local `ref-style`, then a valid document `section-reference-style`, then `number`.
  Rationale: Local exceptions must be possible even in a document that chooses title-aware references globally, while documents with no new metadata stay unchanged.
  Date/Author: 2026-09-22 / Codex
- Decision: Use the target header's `ref-title` attribute when non-empty, otherwise use the plain text of the complete header content.
  Rationale: Automatically shortening prose is editorially unreliable. `ref-title` lets the author provide a stable summary once at the target, while falling back to the visible heading keeps the common case automatic.
  Date/Author: 2026-09-22 / Codex
- Decision: Render title-only references as `“Title”` and combined references as `1.2.3 (“Title”)`, with all of that text inside the link.
  Rationale: Quotation marks make prose such as `see section “Framework inputs”` grammatical and visibly distinguish a section title. Putting the complete form inside the link gives every output format one coherent clickable reference.
  Date/Author: 2026-09-22 / Codex
- Decision: Convert header titles to plain text before inserting them into a reference link.
  Rationale: A header may contain emphasis, code, an existing link or a note. Reusing nested inline links inside the new outer link would produce invalid output. Plain text obtained with `pandoc.utils.stringify` is stable across all writers. A helper must turn that string into normal `Str` and `Space` inlines instead of relying on a `Str` containing embedded whitespace.
  Date/Author: 2026-09-22 / Codex
- Decision: Fail the Pandoc invocation with a clear error for an unknown style, an empty explicit `ref-title`, or a styled reference that cannot produce a non-empty title.
  Rationale: A silent fallback can leave a document looking correct while ignoring an author's requested presentation. Build-time validation makes typographical errors discoverable. Existing missing-target behavior is outside this feature and remains unchanged.
  Date/Author: 2026-09-22 / Codex
- Decision: Do not use citation prefixes or suffixes as style controls, and do not introduce aliases such as `@sec-title:id`.
  Rationale: Citation prefixes are already treated as visible prose and suffixes may become useful as visible prose later. Separate pseudo-namespaces would make identifiers harder to search and maintain. A Pandoc span attribute is explicit and structurally unambiguous.
  Date/Author: 2026-09-22 / Codex
- Decision: Document ordinary Markdown links such as `[framework inputs](#sec:graph-inputs)` as the zero-automation escape hatch for one-off contextual wording.
  Rationale: Authors sometimes need wording that should not become the target's reusable title. Standard links already work in all supported formats, though they do not provide target validation or automatic updates.
  Date/Author: 2026-09-22 / Codex
- Decision: Repair the transformed-native pattern rule as part of this implementation and cover it with an integration test.
  Rationale: The ExecPlan requires native AST regression evidence, but the existing rule rendered the version stamp and could neither rebuild when Markdown or the filter changed nor produce the intended document. Manually forcing an output would conceal a clean-build failure.
  Date/Author: 2026-09-22 / Codex

## Outcomes & Retrospective

Implemented. Authors can retain numeric section references, request quoted titles, request combined number-and-title links, choose a document-wide YAML default and override that default on individual references. Target headings accept an optional `ref-title`; otherwise the filter uses normalized plain heading text. Invalid styles, malformed styled spans and unusable titles now fail with actionable messages. The control attributes are consumed by the filter rather than leaking into generated output.

The existing Pandoc Link representation was sufficient for every writer; no Confluence-specific branch was needed. The feature demo proves `1 (“feature overview”)`, `“feature overview”`, and `1` in HTML, Confluence XHTML, TeX/PDF, DOCX, PPTX, email and transformed native output. PDF text extraction with `mutool draw -F txt` showed all three forms.

Implementation also repaired the transformed-native Make rule discovered during validation. The old split pattern declarations caused Pandoc to transform the version stamp rather than the Markdown source. The corrected rule and integration test make the native golden meaningful; this explains why that golden changes from a tiny stamp AST to the complete feature-demo AST.

Validation completed with 17 focused filter/index tests, 23 focused tests including Make integration, REUSE 3.3 compliance, 91 non-regression tests, 13 regression tests and 104 tests in the complete suite. No dependency was added. The only syntax subtlety is that a styled reference with a citation prefix uses doubled brackets, for example `[[see @sec:overview]]{ref-style=title}`, and this is documented in the README.

## Context and Orientation

This repository is `pandoc_writing_tools`, a reusable collection of Pandoc filters, writers, templates and build rules. Pandoc reads Markdown into an abstract syntax tree, abbreviated AST. An AST represents a heading as a `Header`, a citation-like `@sec:id` reference as a `Cite`, and `[@sec:id]{ref-style=title}` as a `Span` containing a `Cite`. A Lua filter walks that tree and can replace those elements before a writer produces HTML, LaTeX, Confluence storage XHTML or another format.

The main implementation is `theme/fignos.lua`. Despite its historical name, it handles numbered figures, examples, definitions and sections. It currently makes several full-document passes. The header pass computes hierarchical section numbers such as `1.2.3` and saves a labelled header's number in `headerlabel2counter`. A later cite pass recognizes a single citation whose identifier starts with `sec:`, turns the saved number into link text, and returns a `pandoc.Link` targeting the header identifier. The same filter runs before cite processing in `COMMONFILTERS` in `Makefile`.

The relevant files are:

- `theme/fignos.lua`, which must retain title information, read the document-wide setting, recognize local style spans and construct title-aware links.
- `scripts/python/tests/test_fignos_filter.py`, which does not yet exist and should provide focused behavioral tests by invoking the installed `pandoc` executable with `theme/fignos.lua`.
- `README.md`, whose “Figures, examples, definitions, and section references” section documents only numbered references today.
- `examples/feature-demo/src/feature-demo.md`, the end-to-end example used to build all supported output formats.
- `scripts/python/tests/test_regression_outputs.py` and `scripts/python/tests/fixtures/regression/feature-demo/`, which compare normalized feature-demo outputs with checked-in golden text files.
- `theme/confluence.lua`, whose existing `Writer.Inline.Link` implementation should work unchanged but whose output must be covered by the XHTML golden.
- `scripts/python/update_regression_goldens.py`, which deliberately requires `--accept` before replacing golden outputs.

In this plan, a “target style” means the style chosen for one rendered section reference. A “document default” means the YAML key `section-reference-style`. A “reference title” means the plain-text `ref-title` header attribute when present, or otherwise the plain text of the complete visible heading. A “golden” is a checked-in normalized representation of generated output used to detect regression changes.

The complete author-facing contract is:

    ---
    section-reference-style: number-title
    ---

    # A detailed overview of the system {#sec:overview ref-title="system overview"}

    Default for this document: [@sec:overview].
    Title only here: [@sec:overview]{ref-style=title}.
    Number only here: [@sec:overview]{ref-style=number}.

This renders the three link bodies as `1 (“system overview”)`, `“system overview”`, and `1`. When the YAML key is absent, an unadorned `@sec:overview` or `[@sec:overview]` remains `1`. Citation prefix behavior remains as it is now: a prefix supplied inside citation brackets is visible before the generated reference text. Citation suffix behavior is not expanded as part of this feature.

## Milestones

### Milestone 1: Specify the filter behavior with focused tests

At the end of this milestone, `scripts/python/tests/test_fignos_filter.py` exists and exercises the filter through Pandoc rather than testing Lua implementation details. Most new behavior tests should fail against the old filter, proving that they expose the requested feature, while the backward-compatibility test should pass from the start.

The tests must cover an absent document setting preserving a numbered reference, each of the three local styles, a document default for each valid style, local precedence over the document default, `ref-title` taking precedence over the visible heading, full-heading fallback, a forward reference that occurs before its target header, preservation of the `#sec:id` link target, and a visible citation prefix. Add negative tests for an unknown YAML style, an unknown local style, an empty explicit `ref-title`, and a title request whose header has no usable plain text. The negative tests should assert a non-zero Pandoc exit code and a concise diagnostic containing the invalid value or section identifier.

Use a helper that writes supplied Markdown to `tmp_path`, runs `pandoc -t native` or `pandoc -t html --lua-filter <tools-root>/theme/fignos.lua`, and returns standard output. Skip only when `pandoc` is not installed, matching the style of `test_index_filter.py`. Prefer HTML assertions for exact link bodies and targets, and use Pandoc native output when it makes the Span/Cite structure easier to distinguish.

Run from the `pandoc_writing_tools` root:

    uv run --project . -m pytest scripts/python/tests/test_fignos_filter.py -q

Before implementation, expect the new title-style assertions or commands to fail because the old Cite pass always generates the number. Record the concise failure evidence in `Surprises & Discoveries`; do not weaken the tests to match old behavior.

### Milestone 2: Implement title-aware reference resolution in `fignos.lua`

At the end of this milestone, the focused suite passes and existing unstyled section references remain byte-for-byte equivalent at the Pandoc AST level except for incidental internal refactoring.

Refactor global section state in `theme/fignos.lua` so every labelled section can provide its number and its reference title. A simple representation is a table keyed by section identifier whose value contains `number`, `title`, and whether an explicit `ref-title` was supplied. Keep the existing `section-number` header attribute because `theme/index.lua` relies on it. Do not change figure, example or definition numbering.

Add a small style-validation helper with the accepted set `number`, `title`, and `number-title`. Add a metadata handler that reads `meta['section-reference-style']` through `pandoc.utils.stringify`. Treat an absent key as `number`; trim surrounding whitespace; reject an empty or unknown supplied value with an error naming `section-reference-style` and the accepted values.

In `process_headers`, continue computing the number for every heading. For each `sec:` identifier, use `pandoc.utils.stringify(header.content)` to obtain the full plain heading title. Trim surrounding whitespace and collapse runs of whitespace for stable output. If `ref-title` is present, trim it and reject it when empty. Save the explicit value as the reference title; otherwise save the normalized full title. Number-only references must continue to work even if the title is empty. A title-bearing style must fail clearly if no usable title exists.

Add a helper that converts normalized plain text into a `pandoc.Inlines` list of `pandoc.Str` and `pandoc.Space` elements. Add a reference-body helper with behavior equivalent to:

    number       -> 1.2.3
    title        -> “Reference title”
    number-title -> 1.2.3 (“Reference title”)

Construct the punctuation as normal Pandoc inline elements. Continue to prepend `citation.prefix` exactly as the current `get_link_text` helper does. Do not reinterpret `citation.suffix` in this change.

Add a `Span` handler in a separate pass before the ordinary `Cite` handler. It should recognize a Span with a `ref-style` attribute whose content is exactly one Cite containing exactly one `sec:` citation. Validate the local style and call the same section-reference constructor used by ordinary cites. The local style overrides the stored document default. Remove the control attribute from output; if the source Span has any other identifier, classes or attributes, transfer those remaining attributes to the returned Link so unrelated author markup is not silently discarded. A `ref-style` Span that is not a single section reference should fail with a diagnostic showing the accepted source form rather than being ignored.

Update the ordinary Cite handler to use the document default. Keep the existing missing-section diagnostic and link target behavior. Arrange the returned filter passes so metadata is captured first, all headers are collected before any reference is resolved, styled Spans are resolved before ordinary Cites, and later cite processing does not process a link already returned by the Span pass. One intended ordering is a metadata pass, the existing header/figure/div collection passes, a styled Span pass, and finally the Cite pass; confirm the exact behavior with the focused forward-reference test.

Run the focused tests again and expect every test to pass. Also run the existing index filter tests because they consume the `section-number` attribute written by `fignos.lua`:

    uv run --project . -m pytest \
      scripts/python/tests/test_fignos_filter.py \
      scripts/python/tests/test_index_filter.py -q

### Milestone 3: Document and demonstrate all precedence levels

At the end of this milestone, a new author can discover the feature from `README.md` and can inspect `examples/feature-demo/src/feature-demo.md` to see a working document-wide default and all local styles.

Expand the existing section-reference subsection in `README.md`. Preserve the basic numbered example, then document `title` and `number-title`, the target-side `ref-title`, the YAML `section-reference-style` key, the three accepted values and the precedence order. State that `ref-title` is optional and that the visible header title is used when it is absent. Show the exact rendered forms including curly quotation marks. Also mention ordinary `[custom wording](#sec:id)` links for deliberately one-off phrasing and explain that those links do not receive the filter's validation or automatic title updates.

Update `examples/feature-demo/src/feature-demo.md` so its YAML selects `section-reference-style: number-title`. Give `# Overview` an explicit concise `ref-title`, then demonstrate the document default plus local `title` and `number` overrides in the “Citations and section references” subsection. Keep the examples natural enough to be useful documentation rather than a list of synthetic tokens. The default reference should prove the YAML path, and local examples should prove that local attributes override it.

Build the feature demo before accepting golden changes:

    cd examples/feature-demo
    ./build_with_docker.sh all
    cd ../..

Inspect at least `examples/feature-demo/build/feature-demo.html`, `examples/feature-demo/build/feature-demo.xhtml`, `examples/feature-demo/build/feature-demo.tex`, and `examples/feature-demo/build/feature-demo.transformed.native`. Confirm that all generated links target `sec:overview`; HTML contains ordinary anchor link bodies, Confluence XHTML contains `<ac:link ac:anchor="sec:overview">`, TeX contains hyperlinked visible text, and native output contains Link nodes with the expected inline bodies.

### Milestone 4: Update cross-format goldens and complete validation

At the end of this milestone, all documented output formats are covered by reviewed golden changes, the full repository checks pass, and the plan records exact evidence.

Generate normalized outputs and deliberately accept the expected changes:

    uv run --project . scripts/python/update_regression_goldens.py --accept

Review every changed file under `scripts/python/tests/fixtures/regression/feature-demo/`. The expected changes are limited to the feature-demo source material and visible section-reference text or link structure. PDF normalization records only `PDF_OK`, so it proves the PDF built successfully but not its extracted text; manually inspect the generated PDF or use an available PDF-to-text command to confirm the three visible forms before declaring acceptance. DOCX, PPTX and EML normalizers extract text and should show the expected reference text in their goldens. Do not accept unrelated layout, metadata, image or bibliography drift.

Run the repository-required checks from the `pandoc_writing_tools` root:

    uv run --project . reuse lint
    uv run --project . -m pytest -q -k "not regression"
    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp

Then run the complete suite as a final convenience check:

    uv run --project . -m pytest -q

Record the observed pass counts and relevant build evidence in `Progress`, `Surprises & Discoveries`, and `Outcomes & Retrospective`. Before each commit, rerun at least the three checks required by `AGENTS.md`. Keep commits logically scoped and use an imperative subject with a detailed body explaining the author-visible behavior, compatibility guarantee and validation.

## Plan of Work

Begin with a focused Python test module so the desired syntax and output are executable specifications. Use real Pandoc invocations because Lua filter traversal order and Markdown parsing are central to this feature. Make the initial failures explicit, then edit only `theme/fignos.lua` until focused tests pass.

Within `fignos.lua`, preserve the current two-phase principle: collect every target before resolving any reference. Extend the collected section record with normalized title text, and make a single link-building function accept an explicit style. Feed it either the document default from ordinary Cite processing or the local override from Span processing. This avoids maintaining separate rendering implementations for default and local references.

After the filter behavior is stable, update documentation and the feature demo. Build all output formats, inspect representative raw outputs, regenerate normalized goldens with the explicit acceptance tool and review the diff. Finish by running the required lint and test commands and updating this living plan with results and any implementation-driven decisions.

Do not modify the consuming `kristof_thinking_writing` repository's documents as part of this work. The implementation, tests, documentation, example and plan all belong in `pandoc_writing_tools`. Existing unrelated changes in the consuming repository must remain untouched.

## Concrete Steps

Run all commands from the `pandoc_writing_tools` repository root unless a step explicitly changes directory:

    cd /Users/kribey01/dev/kristof_thinking_writing/pandoc_writing_tools
    git status --short --branch

Confirm that only intended work is present. Create the focused test file:

    $EDITOR scripts/python/tests/test_fignos_filter.py
    uv run --project . -m pytest scripts/python/tests/test_fignos_filter.py -q

Edit the filter and iterate with both focused suites:

    $EDITOR theme/fignos.lua
    uv run --project . -m pytest \
      scripts/python/tests/test_fignos_filter.py \
      scripts/python/tests/test_index_filter.py -q

Update the documentation and demo:

    $EDITOR README.md
    $EDITOR examples/feature-demo/src/feature-demo.md
    cd examples/feature-demo
    ./build_with_docker.sh all
    cd ../..

Regenerate and review goldens only after inspecting the built outputs:

    uv run --project . scripts/python/update_regression_goldens.py --accept
    git diff -- scripts/python/tests/fixtures/regression/feature-demo

Run the required final checks:

    uv run --project . reuse lint
    uv run --project . -m pytest -q -k "not regression"
    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp
    uv run --project . -m pytest -q
    git diff --check
    git status --short

The expected focused HTML evidence should include forms equivalent to:

    <a href="#sec:overview">1</a>
    <a href="#sec:overview">“system overview”</a>
    <a href="#sec:overview">1 (“system overview”)</a>

The expected Confluence storage-format evidence should include the same visible bodies inside anchor links equivalent to:

    <ac:link ac:anchor="sec:overview"><ac:link-body>1 (“system overview”)</ac:link-body></ac:link>

Exact whitespace or escaping may vary by writer; tests should assert semantic link target and visible content rather than brittle surrounding document formatting.

## Validation and Acceptance

Acceptance requires all of the following observable behavior.

With no new YAML metadata, `@sec:overview` still produces a clickable numeric reference. With `section-reference-style: title`, an ordinary section reference produces a quoted title link. With `section-reference-style: number-title`, it produces a number plus quoted title. A local `ref-style` produces its requested form and wins over the document setting.

When the target header has `ref-title="system overview"`, title-bearing references display `system overview`, not the full heading. When `ref-title` is absent, they display the full plain heading. All forms link to the original `#sec:overview` anchor, including forward references appearing before the heading.

Invalid style names and invalid target summaries stop the build with actionable messages. A malformed `ref-style` Span does not silently fall through to citeproc. Existing figure, example, definition and number-only section references still render as before, and existing index tests continue to see the header `section-number` attribute.

The feature demo visibly contains the default combined reference and both local overrides in HTML, Confluence XHTML, PDF, DOCX, PPTX and EML output. The relevant normalized goldens contain only intentional changes. The REUSE lint, non-regression tests, regression tests and complete pytest suite all pass.

## Idempotence and Recovery

The implementation steps are safe to repeat. Focused tests write only under pytest temporary directories. The feature-demo build and golden-update tool overwrite generated or normalized outputs deterministically. The golden-update tool refuses to write unless `--accept` is supplied.

If golden generation shows unrelated changes, do not accept or hand-edit them into plausibility. Restore only the newly generated golden changes after first verifying that they were clean before this work, rebuild with the repository's documented Docker path, and investigate the difference. Never reset or remove unrelated work in the consuming repository. If traversal order prevents the Span handler from seeing unresolved Cites, add a separate filter pass rather than combining handlers in a way that makes forward references order-dependent, and record the discovery and revised ordering in this plan.

If the implementation partially succeeds, update `Progress` with what is done and what remains before stopping. Keep failing tests that accurately specify the desired behavior; do not delete them merely to obtain a green suite.

## Artifacts and Notes

The canonical examples to preserve in README and tests are:

    # Long descriptive heading {#sec:target ref-title="short heading"}

    Number: [@sec:target]{ref-style=number}
    Title: [@sec:target]{ref-style=title}
    Both: [@sec:target]{ref-style=number-title}

with visible link bodies:

    1
    “short heading”
    1 (“short heading”)

The document-level example is:

    ---
    section-reference-style: number-title
    ---

An unstyled `[@sec:target]` then uses `number-title`. A local `{ref-style=number}` still produces only `1`.

## Interfaces and Dependencies

Do not add a third-party dependency. Use the Pandoc Lua API already available to `theme/fignos.lua`, especially `pandoc.utils.stringify`, `pandoc.Str`, `pandoc.Space`, `pandoc.List`, `pandoc.Inlines` and `pandoc.Link`.

At completion, `theme/fignos.lua` must conceptually expose these internal responsibilities, although exact private function names may be adjusted for clarity:

    validate_reference_style(value, source_description) -> one of number, title, number-title or an error
    process_metadata(meta) -> records the document default
    normalize_reference_title(text) -> trimmed, whitespace-normalized plain text
    text_to_inlines(text) -> Pandoc inline list using Str and Space
    get_section_reference_inlines(label, style, citation) -> visible prefix plus styled body
    process_section_reference(cite, label, style, optional_link_attr) -> pandoc.Link
    process_reference_span(span) -> styled Link or nil for an unrelated Span

The stored record for each `sec:` header must contain enough information to produce its hierarchical number and normalized title after all headers have been collected. The existing `section-number` header attribute is a compatibility interface with `theme/index.lua` and must remain.

`scripts/python/tests/test_fignos_filter.py` depends only on pytest, Python's standard library and the external `pandoc` executable already required by this repository. Cross-format acceptance uses the existing feature-demo build, custom Confluence writer and regression normalization infrastructure; no new fixture framework is required.

Revision note (2026-09-22): Initial ExecPlan created after inspecting the current filter, Markdown AST shape, custom Confluence writer and feature-demo regression system. The plan resolves the authoring syntax and precedence up front so implementation can proceed without further product decisions.

Revision note (2026-09-22): Updated through completed implementation. Recorded the doubled-bracket prefix syntax, the transformed-native Make defect and repair, reviewed golden changes, sandbox-specific command substitution, final validation evidence and retrospective.
