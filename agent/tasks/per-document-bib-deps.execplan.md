# Add per-document bibliography dependencies to pandoc_writing_tools

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to
date as work proceeds.

This repository stores execution plans under `agent/tasks/`. The plan must
remain self-contained: a future contributor should be able to read only this
file, inspect the current repository, and implement the feature end to end.

## Purpose / Big Picture

After this change, editing a shared BibTeX file will rebuild only the documents
whose rendered output can actually be affected by the changed bibliography
entries. Today, every document output rule lists `$(BIB_DEPS)` as a normal
prerequisite. Since `$(BIB_DEPS)` normally expands to every `src/*.bib` file,
touching one bibliography file makes every document that uses the shared
Makefile look out of date, even if only one uncited entry changed.

The desired behavior is automatic and precise. Authors should keep writing
normal Pandoc citations such as `[@doe2020]` and normal bibliography metadata
such as `bibliography: src/refs.bib`. They should not manually edit
Makefiles or dependency lists when a citation is added, removed, or when a
BibTeX entry changes.

The visible proof is an incremental build scenario with two documents and one
shared bibliography. `doc-a.md` cites `@alpha`, `doc-b.md` cites `@beta`, and
both documents use `src/refs.bib`. After a clean build, changing only the
`@alpha` entry should rebuild outputs for `doc-a` and should not rebuild
outputs for `doc-b`. Changing an uncited entry should refresh only generated
dependency fingerprints and should not rebuild either document.

## Progress

- [x] (2026-06-16) Drafted this ExecPlan from the current `Makefile`
  dependency graph and the image dependency design already implemented in this
  repository.
- [x] (2026-06-16 10:24Z) Implemented `scripts/python/generate_bib_deps.py` to extract citation keys
  with Pandoc JSON, parse `$(BIB_DEPS)` with Pandoc, and write per-document
  citation fingerprint files.
- [x] (2026-06-16 10:24Z) Wired `Makefile` so document outputs depend on generated per-document
  bibliography fingerprints instead of depending directly on every source
  `.bib` file.
- [x] (2026-06-16 10:24Z) Added focused unit and Make integration tests for citation extraction,
  fingerprint stability, and incremental rebuild behavior.
- [x] (2026-06-16 10:24Z) Ran the required local checks, the focused
  bibliography and image dependency tests, and the feature-demo Docker wrapper.
- [x] (2026-06-16 12:54Z) Updated duplicate BibTeX id handling to match Pandoc
  citeproc's last-entry-wins behavior after a content repository build reported
  a duplicate BibTeX key.
- [x] (2026-06-16 12:54Z) Verified duplicate-key handling with repository-local
  tests and reran the required local checks.
- [x] (2026-06-17) Removed local content-repository details from this ExecPlan
  and recorded the review follow-up plan.
- [x] (2026-06-17) Removed the generated README table-of-contents entry for the
  document's own top-level title.
- [x] (2026-06-17) Documented the image and bibliography dependency generators
  that keep unrelated document outputs up to date.
- [x] (2026-06-17) Explained why generated version, git hash, and bibliography
  fingerprint files are marked as `.SECONDARY`.
- [x] (2026-06-17) Replaced explicit `agent/tasks` REUSE annotations with a glob
  that covers ExecPlan files.

## Surprises & Discoveries

- Observation: The current document rules over-depend on shared bibliography
  files.
  Evidence: `Makefile` defines `BIB_DEPS ?= $(wildcard $(SRC_DIR)/*.bib)`, and
  the `.html`, `.email.html`, `.native`, `.transformed.native`, `.tex`,
  `.xhtml`, `.docx`, and `.pptx` rules list `$(BIB_DEPS)` as normal
  prerequisites.
- Observation: This problem cannot be solved by making document outputs depend
  directly on individual BibTeX entries, because Make tracks files, not ranges
  or entries inside one file.
  Evidence: a BibTeX entry such as `@article{doe2020, ...}` is a fragment inside
  `src/feature-demo.bib`; it has no separate path or timestamp that Make can
  compare against a document output.
- Observation: Pandoc JSON is still the right source of truth for finding
  document references, as it was for image dependencies.
  Evidence: citations can appear in nested Markdown constructs and metadata;
  Pandoc already parses the Markdown dialect used by this repository into
  structured `Citation` nodes.
- Observation: The repository also uses Pandoc-style references such as
  `[@fig:demo]` and `[@sec:overview]`.
  Evidence: `examples/feature-demo/src/feature-demo.md` contains references to
  figures, examples, definitions, and sections using the same bracketed syntax
  as bibliography citations. The generator must not fail simply because a
  citation-like key is not present in a bibliography file.
- Observation: Generated pattern prerequisites can be treated as intermediate
  files by Make and removed after the build.
  Evidence: the first Make integration test run printed `rm` commands for
  generated `.version-*.stamp`, `.githash-*.stamp`, and
  `bib-deps/*.refs.json` files. The fix marks version stamps, git hash stamps,
  and bibliography fingerprints as `.SECONDARY`.
- Observation: Pandoc represents `nocite: "@*"` as a citation id of `*`.
  Evidence: a small Markdown fixture parsed with `pandoc -t json` produced a
  `Citation` object with `"citationId":"*"`.
- Observation: Pandoc citeproc tolerates duplicate BibTeX ids and uses the last
  entry for rendering.
  Evidence: a fixture with two entries using the same id
  rendered the second entry's author and title when cited with
  that duplicated id.

## Decision Log

- Decision: Use the same Make-based dependency model as the image dependency
  fix: generate files under `build/`, use normal prerequisites, and avoid any
  separate cache, daemon, database, or manual per-document Makefile edits.
  Rationale: The user explicitly wants no unnecessary different solution from
  the image dependency work. The build should remain understandable as ordinary
  Make rules plus generated build artifacts.
  Date/Author: 2026-06-16 / Codex
- Decision: Add one generated citation fingerprint file per source document,
  for example `$(BUILD_BIB_DEPS_DIR)/doc-a.refs.json`.
  Rationale: This is the necessary difference from image dependencies. Images
  already have separate source and built files with separate timestamps; BibTeX
  entries do not. A per-document fingerprint file gives Make a file-level
  representation of the entries that matter to one document.
  Date/Author: 2026-06-16 / Codex
- Decision: Do not pass the generated fingerprint file to Pandoc as the
  bibliography input in the first implementation.
  Rationale: The fingerprint is a dependency artifact, not a rendering change.
  Keeping Pandoc's existing bibliography metadata and command behavior avoids
  output regressions while still rebuilding when cited entries change.
  Date/Author: 2026-06-16 / Codex
- Decision: Use Pandoc to parse both Markdown citations and BibTeX data rather
  than writing an ad hoc BibTeX parser.
  Rationale: Pandoc is already required for the build. It understands this
  repository's Markdown syntax and can normalize bibliography entries into CSL
  JSON, avoiding brittle parsing of BibTeX strings, braces, macros, and
  cross-reference-like constructs.
  Date/Author: 2026-06-16 / Codex
- Decision: Preserve `BIB_DEPS` as the source bibliography list, but move it
  from every document output rule to the generated fingerprint rule.
  Rationale: Content repositories can still override `BIB_DEPS`, and any source
  `.bib` change still causes Make to re-check fingerprints. Unchanged
  fingerprints must keep their mtimes, so unchanged documents remain up to
  date.
  Date/Author: 2026-06-16 / Codex
- Decision: Match Pandoc citeproc's duplicate-id behavior by using the last
  bibliography entry for a repeated id.
  Rationale: Content repositories may already contain duplicate BibTeX ids that
  Pandoc renders without failing. The dependency scanner should not reject
  content that the actual build accepts, and the fingerprint should track the
  same effective entry as rendering.
  Date/Author: 2026-06-16 / Codex
- Decision: Mark generated state files as `.SECONDARY`.
  Rationale: The build relies on mtimes for version stamps, git hash stamps,
  and bibliography fingerprints. If Make deletes those generated prerequisites
  as intermediate files after a build, subsequent invocations cannot make
  precise incremental decisions.
  Date/Author: 2026-06-16 / Codex

## Outcomes & Retrospective

Implemented. The tools repo now generates one bibliography fingerprint per
document under `build/bib-deps/`. Document output rules depend on their own
fingerprint instead of depending directly on every source `.bib` file. The
fingerprint generator parses Markdown with Pandoc JSON, parses BibTeX through
Pandoc's CSL JSON writer, records missing citation-like keys, and rewrites the
fingerprint only when the normalized entries used by that document change.

The Makefile still keeps `BIB_DEPS` as the overridable source bibliography
list. Raw `.bib` files are prerequisites of the fingerprint rule, not direct
prerequisites of document output rules. This means a changed shared `.bib` file
causes Make to re-check the fingerprints, while unaffected document outputs
remain up to date when their fingerprint content and mtime do not change.

Generated version stamps, git hash stamps, and bibliography fingerprints are
marked as `.SECONDARY` so Make does not delete them as intermediate files after
using them as generated prerequisites.

Validation passed:

    uv run --project . -m pytest scripts/python/tests/test_bib_dependencies.py -q
    8 passed in 5.67s

    uv run --project . -m pytest scripts/python/tests/test_image_dependencies.py -q
    11 passed in 3.79s

    uv run --project . reuse lint
    Congratulations! Your project is compliant with version 3.3 of the REUSE Specification :-)

    uv run --project . -m pytest -q -k "not regression"
    42 passed, 4 deselected in 9.39s

    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp
    4 passed, 42 deselected in 3.01s

    cd examples/feature-demo
    ./build_with_docker.sh
    make: Nothing to be done for 'all'.

## Context and Orientation

This repository is the reusable `pandoc_writing_tools` repository. It is often
consumed as a Git submodule by content repositories. Its `Makefile` is included
by content repositories and is responsible for building Markdown files from
`src/*.md` into outputs under `build/`.

The relevant existing files are:

- `Makefile`, which defines `SRC_DIR`, `BUILD_DIR`, `DOCS`, `BIB_DEPS`,
  document output targets, and the document build rules.
- `scripts/python/generate_image_deps.py`, which is the closest implemented
  pattern: a Python generator driven by Pandoc JSON and Make prerequisites.
- `scripts/python/tests/test_image_dependencies.py`, which has useful patterns
  for temporary content repositories and Make dry-run assertions.
- `examples/feature-demo/`, which has one Markdown document with bibliography
  metadata and a small BibTeX file.

Make uses file timestamps to decide whether to rebuild a target. A normal
prerequisite means "if this input is newer than the target, rebuild the target."
The raw shared `.bib` file is too coarse for this purpose. The generated
per-document fingerprint file must therefore have this timestamp contract:

- If a source `.bib` file changes but the normalized bibliography entries used
  by a document are unchanged, leave that document's fingerprint bytes and mtime
  unchanged.
- If a source `.bib` file change alters an entry cited or included by a
  document, rewrite that document's fingerprint atomically so its mtime becomes
  newer than the document outputs.

This differs from `build/.image-deps.mk`, which may be touched after a check so
GNU Make knows the included makefile was considered. Bibliography fingerprint
files must not be touched when unchanged, because their mtimes are the precise
rebuild trigger for document outputs.

## Milestones

### Milestone 1: Add a citation fingerprint generator

At the end of this milestone, the tools repo will have
`scripts/python/generate_bib_deps.py`. Given one Markdown document and the
source bibliography files from `BIB_DEPS`, it writes a deterministic JSON
fingerprint file containing the document's citation keys, any missing keys, the
selected normalized bibliography entries, and enough metadata to inspect what
was tracked.

### Milestone 2: Integrate fingerprints into the Makefile

At the end of this milestone, document build rules no longer depend directly on
`$(BIB_DEPS)`. They instead depend on `$(BUILD_BIB_DEPS_DIR)/%.refs.json`, and
that fingerprint target depends on the corresponding Markdown source, the
source bibliography files, the generator script, and the Makefile.

### Milestone 3: Test entry-level rebuild behavior

At the end of this milestone, pytest tests prove that changing a cited entry
rewrites only the fingerprint for documents that cite it, while changing an
uncited entry leaves existing document fingerprints unchanged. A Make
integration test proves that the document build recipes follow that behavior.

### Milestone 4: Validate the existing rendered outputs

At the end of this milestone, the existing regression tests and feature-demo
outputs still pass. Since the generated fingerprint is only a dependency
artifact and not a Pandoc input, rendered output changes are not expected.

## Plan of Work

Create `scripts/python/generate_bib_deps.py`. Follow the style of
`scripts/python/generate_image_deps.py`: top-level summary comment, small
testable functions with docstrings, standard-library code where practical, and
Pandoc as the parser for Markdown and bibliography data.

The script should support at least this command shape:

    scripts/python/generate_bib_deps.py \
      --content-root PATH \
      --document PATH \
      --output PATH \
      --bib-file PATH [--bib-file PATH ...] \
      --from FORMAT

Defaults should match the existing Makefile where possible:

- `--content-root` is the content repository root.
- `--document` is one `src/*.md` file.
- `--output` is one generated fingerprint file under
  `$(BUILD_BIB_DEPS_DIR)`.
- `--bib-file` values come from `$(BIB_DEPS)`. If no `--bib-file` is supplied,
  default to `src/*.bib` under the content root.
- `--from` defaults to `markdown-example_lists`, matching `PANDOCFLAGS`.

Use Pandoc JSON to collect citation ids from the document:

    pandoc src/doc-a.md --from markdown-example_lists -t json

Walk the decoded JSON tree recursively and collect every `Citation` element's
`citationId`. This should find citations in paragraphs, tables, footnotes, and
metadata. Preserve a deterministic order for output, but de-duplicate ids for
matching against bibliography entries.

Handle `nocite` metadata explicitly:

- If `nocite` contains `@*`, the fingerprint includes all normalized entries
  from `BIB_DEPS`, because the document explicitly includes the whole
  bibliography.
- If `nocite` contains specific citation ids, treat those ids like normal
  citation ids.
- If implementation discovers that Pandoc's JSON representation already exposes
  `nocite` as normal `Citation` nodes, still add a focused test so this remains
  documented.

Use Pandoc to parse the bibliography files into normalized CSL JSON. The exact
command can be adjusted during implementation, but the plan is to rely on
Pandoc rather than an ad hoc BibTeX parser. One workable shape to verify is:

    pandoc --from bibtex --to csljson src/refs.bib

If multiple `--bib-file` values are supplied, parse them together and merge by
id using Pandoc citeproc's observed last-entry-wins behavior for duplicate ids.
This keeps the dependency fingerprint aligned with rendered output for content
repositories that already contain duplicate BibTeX keys.

The fingerprint file should be deterministic and inspectable. A reasonable JSON
shape is:

    {
      "schema": "pandoc_writing_tools.bib_refs.v1",
      "document": "$(SRC_DIR)/doc-a.md",
      "bib_files": ["$(SRC_DIR)/refs.bib"],
      "citation_keys": ["alpha"],
      "missing_keys": [],
      "entries": [
        { "id": "alpha", "...": "normalized CSL JSON fields" }
      ]
    }

The paths inside the JSON may be content-root-relative paths rather than
absolute paths so the file stays portable between host and Docker builds. The
document output rules will not depend on the path strings inside the JSON, but
portable diagnostics make the artifact easier to inspect.

Write the fingerprint atomically:

1. Render the deterministic JSON bytes.
2. If the output file already has identical bytes, do nothing and leave its
   mtime unchanged.
3. If the bytes differ or the file is missing, write to a temporary file next
   to the output and rename it into place.

This "do nothing when unchanged" behavior is required for correctness. Do not
reuse the image dependency helper behavior that refreshes mtimes for generated
Make include files.

Modify `Makefile` to define the generated bibliography dependency directory:

    BUILD_BIB_DEPS_DIR := $(BUILD_DIR)/bib-deps

Add a directory rule:

    $(BUILD_BIB_DEPS_DIR): | $(BUILD_DIR)
        mkdir -p $(BUILD_BIB_DEPS_DIR)

Add a pattern rule for per-document fingerprints:

    $(BUILD_BIB_DEPS_DIR)/%.refs.json: $(SRC_DIR)/%.md $(BIB_DEPS) \
        $(TOOLS_ROOT)/scripts/python/generate_bib_deps.py \
        $(TOOLS_ROOT)/Makefile | $(BUILD_BIB_DEPS_DIR)
        $(PYTHON_RUNNER) $(TOOLS_ROOT)/scripts/python/generate_bib_deps.py \
          --content-root $(CONTENT_ROOT) \
          --document $< \
          --output $@ \
          $(addprefix --bib-file ,$(BIB_DEPS))

The Make syntax may need line-continuation tuning. Keep it readable and close
to the existing `$(IMAGE_DEPS_MK)` generator rule.

Replace direct `$(BIB_DEPS)` prerequisites on document output pattern rules
with the matching fingerprint prerequisite:

    $(BUILD_BIB_DEPS_DIR)/%.refs.json

Apply that replacement to every output rule currently depending on
`$(BIB_DEPS)`: `.html`, `.email.html`, `.native`, `.transformed.native`,
`.tex`, `.xhtml`, `.docx`, and `.pptx`. The `.pdf` and `.eml` targets already
depend on `.tex` and `.email.html` respectively, so they do not need separate
bibliography fingerprint prerequisites unless implementation finds a concrete
reason to add them.

Keep `BIB_DEPS` defined and overridable. It remains the source bibliography
list for the fingerprint generator and should not be removed.

Add tests in `scripts/python/tests/test_bib_dependencies.py`:

- Unit-test citation extraction from a small Pandoc JSON object with nested
  `Citation` nodes.
- Unit-test `nocite` handling, including `@*`.
- Unit-test fingerprint rendering so output is deterministic and contains
  cited entries, missing keys, and no uncited entries.
- Unit-test the write behavior so unchanged fingerprints keep their mtimes and
  changed fingerprints get rewritten.
- Add a generator-level integration test with `doc-a.md`, `doc-b.md`, and one
  shared `refs.bib`; changing `@alpha` should rewrite only
  `doc-a.refs.json`.
- Add a Make integration test using a temporary content repository and wrapper
  Makefile. Build `html`, change an uncited BibTeX entry, run `make html`, and
  assert that document Pandoc recipes do not run. Then change `@alpha`, run
  `make html`, and assert that `doc-a.md -t html` appears while
  `doc-b.md -t html` does not.

Do not rely only on `make -n` immediately after changing a `.bib` file. Unlike
image files, Make cannot know whether a changed shared `.bib` file affects a
document until the fingerprint generator has run. The integration test should
run real `make html` commands and inspect the recipes that Make prints.

## Concrete Steps

Run commands from the tools repository root:

    cd /path/to/pandoc_writing_tools

Start by checking the branch and status:

    git status --short --branch

Create the generator:

    $EDITOR scripts/python/generate_bib_deps.py

Add focused tests:

    $EDITOR scripts/python/tests/test_bib_dependencies.py

Modify the Makefile:

    $EDITOR Makefile

Run focused tests:

    uv run --project . -m pytest scripts/python/tests/test_bib_dependencies.py -q

Run the existing image dependency tests too, because the Makefile integration
will touch the same document rules:

    uv run --project . -m pytest scripts/python/tests/test_image_dependencies.py -q

Run the required checks before committing:

    uv run --project . reuse lint
    uv run --project . -m pytest -q -k "not regression"
    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp

If Docker is available, run the feature demo build:

    cd /path/to/pandoc_writing_tools/examples/feature-demo
    ./build_with_docker.sh

Return to the tools repo root and inspect the status:

    cd /path/to/pandoc_writing_tools
    git status --short

## Validation and Acceptance

Acceptance requires automated tests and an observable incremental-build
scenario.

The generator unit tests pass:

    uv run --project . -m pytest scripts/python/tests/test_bib_dependencies.py -q

Expected result: all tests pass. At least one test should fail before the
implementation because `scripts/python/generate_bib_deps.py` does not exist.

The Make behavior is observable. Use a tiny content root with `src/doc-a.md`,
`src/doc-b.md`, and `src/refs.bib`. After an initial build:

1. Change an uncited entry in `src/refs.bib`.
2. Run `make html`.
3. Confirm that neither `doc-a.md -t html` nor `doc-b.md -t html` appears in
   the Make output.
4. Change the cited `@alpha` entry.
5. Run `make html`.
6. Confirm that `doc-a.md -t html` appears and `doc-b.md -t html` does not.

The full local checks pass:

    uv run --project . reuse lint
    uv run --project . -m pytest -q -k "not regression"
    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp

Expected result: all commands exit successfully.

Rendered regression outputs remain unchanged unless implementation intentionally
changes Pandoc inputs. Since this plan does not feed generated fingerprints to
Pandoc, rendered output changes are not expected. If a regression fixture
changes, stop and investigate rather than updating goldens by default.

## Idempotence and Recovery

The generator must be idempotent. Running it twice with the same Markdown and
BibTeX inputs should produce identical JSON bytes and should not update the
fingerprint mtime on the second run.

Generated fingerprint files live under `build/` and must not be committed. If a
fingerprint becomes stale or corrupt, delete `build/` or the specific
`build/bib-deps/*.refs.json` file and rerun Make; the pattern rule should
regenerate it.

If Pandoc cannot parse a bibliography file, fail clearly. A parse failure means
the generator cannot know which documents are affected by the bibliography
change.

If a citation key is not present in the parsed bibliography entries, record it
in `missing_keys` and continue. This preserves useful behavior for local
cross-reference-like keys such as `fig:demo` and `sec:overview`, and it lets
Pandoc's normal build path continue to report missing real bibliography keys.

## Notes and Artifacts

The implementation should create:

- `scripts/python/generate_bib_deps.py`
- `scripts/python/tests/test_bib_dependencies.py`

The implementation should modify:

- `Makefile`
- This ExecPlan

Plan update note: 2026-06-16. Created the ExecPlan for automatic
per-document bibliography dependency tracking in `pandoc_writing_tools`, using
the same Make and Pandoc JSON dependency model as the image dependency fix and
adding per-document citation fingerprints as the file-level representation
needed for shared BibTeX entries.
Plan update note: 2026-06-16. Implemented the bibliography fingerprint
generator, Makefile integration, focused tests, and validation. Marked generated
state files as `.SECONDARY` after Make integration testing showed they could
otherwise be removed as intermediate files.
Plan update note: 2026-06-16. Changed duplicate BibTeX id handling from failure
to Pandoc-compatible last-entry-wins behavior after a content repository build
hit a duplicate BibTeX key.
Plan update note: 2026-06-17. Removed local content-repository file names and
duplicate-key details from this ExecPlan. Added a review follow-up checklist for
README TOC cleanup, dependency-tracking documentation, `.SECONDARY`
documentation, and REUSE glob simplification.
Plan update note: 2026-06-17. Removed the top-level README title from the
manual table of contents so the TOC starts at the first real section.
Plan update note: 2026-06-17. Documented the generated image dependency
include and per-document bibliography fingerprints in the README.
Plan update note: 2026-06-17. Replaced the `.SECONDARY` review comment in the
Makefile with an explanation of why generated state files must be preserved.
Plan update note: 2026-06-17. Replaced explicit REUSE annotations for
individual ExecPlans with an `agent/tasks/*.execplan.md` glob.
