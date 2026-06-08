# Add per-document image dependencies to pandoc_writing_tools

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository stores execution plans under `agent/tasks/`. The plan must remain self-contained: a future contributor should be able to read only this file, inspect the current repository, and implement the feature end to end.

## Purpose / Big Picture

After this change, adding or editing an image will rebuild only the documents that actually refer to that image. Today, several document targets in `Makefile` depend on `$(bldimages)`, which is the list of every built image in the content repository. That means one new image can cause all documents to rebuild, even when only one document uses it. The desired behavior is automatic and precise: authors should keep writing image references in Markdown, should not manually edit Makefile dependency lists, and should see Make rebuild only the affected document outputs.

The visible proof is an incremental build scenario with two documents and two images. After a clean build, touching `src/img/a.svg` should rebuild outputs for the document that includes image `a`, and it should not rebuild outputs for a different document that includes only image `b`.

## Progress

- [x] (2026-06-08 08:23Z) Drafted this ExecPlan from the current `Makefile` dependency graph and the agreed design choice to treat image dependencies as normal prerequisites for all generated document formats.
- [x] (2026-06-08 08:43Z) Updated the generated dependency design to emit Make-variable paths such as `$(BUILD_DIR)/doc.html` and `$(BUILD_IMG_DIR)/figure.svg` instead of absolute filesystem paths.
- [x] (2026-06-08 09:12Z) Implemented `scripts/python/generate_image_deps.py` with Pandoc JSON scanning, path resolution, Make-variable rendering, and atomic output writes.
- [x] (2026-06-08 09:16Z) Wired `Makefile` to generate and include `$(BUILD_DIR)/.image-deps.mk`, skipped the include for `clean`, and removed global image prerequisites from document output rules.
- [x] (2026-06-08 09:22Z) Added `scripts/python/tests/test_image_dependencies.py` covering nested image extraction, path resolution, generated Makefile output, per-document dependencies, and a Make dry-run rebuild check.
- [x] (2026-06-08 09:27Z) Ran the local test suite and the feature-demo regression path used by GitHub CI.
- [x] (2026-06-08 09:30Z) Recorded final validation evidence and retrospective notes in this ExecPlan.
- [x] (2026-06-08 12:55Z) Committed the implementation as `07ad6e7 make: track per-document image deps`, including the then-current review feedback comments.
- [x] (2026-06-08 13:20Z) Addressed review feedback by replacing real consuming-repository paths in this ExecPlan with generic fixture and tools-root paths.
- [x] (2026-06-08 13:24Z) Addressed review feedback by adding a top-level summary comment to `scripts/python/generate_image_deps.py` and docstrings to the public helper functions.
- [x] (2026-06-08 13:31Z) Reran the required local checks after addressing review feedback: `uv run --project . reuse lint`, `uv run --project . -m pytest -q -k "not regression"`, and `uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp`.
- [x] (2026-06-08 13:50Z) Committed the review-feedback cleanup as `6d135cf docs: address image deps review feedback`.
- [x] (2026-06-08 13:50Z) Inspected the remaining `Makefile` `REVIEW` comments and recorded the next follow-up steps in this ExecPlan.
- [x] (2026-06-08 14:26Z) Addressed the remaining `Makefile` review feedback by removing the redundant `EMAIL_RUNNER`, documenting the clean/include guard, removing the obsolete `build:` target, and adding order-only directory prerequisites to generated-output rules.
- [x] (2026-06-08 14:26Z) Converted the image conversion rules to use `$(BUILD_IMG_DIR)` as an order-only prerequisite so a directory timestamp change cannot make every built image stale.
- [x] (2026-06-08 14:26Z) Extended the Make dry-run regression test to cover adding and building a new image-backed document without making older documents stale.
- [x] (2026-06-08 14:26Z) Ran focused validation for the Makefile follow-up: `uv run --project . -m pytest scripts/python/tests/test_image_dependencies.py -q` and a temporary `make -n clean` / `make -n clean html` check.
- [x] (2026-06-08 14:28Z) Reran the required local checks before committing the Makefile follow-up: `uv run --project . reuse lint`, `uv run --project . -m pytest -q -k "not regression"`, and `uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp`.

## Surprises & Discoveries

- Observation: Normal HTML builds in this repo embed image bytes into the generated HTML.
  Evidence: `Makefile` puts `--embed-resources` in `PANDOCFLAGS`, and a generated HTML file in a consuming content repository can contain `src="data:image/svg+xml;base64,..."`
- Observation: The current document rules over-depend on all built images.
  Evidence: `Makefile` lists `$(bldimages)` as a prerequisite for `.tex`, `.xhtml`, `.docx`, and `.pptx` targets.
- Observation: The HTML rule currently mentions `$(svgimages)`, but the variable defined nearby is `srcsvgimages`; in the current file, `$(svgimages)` appears to be empty or unused.
  Evidence: `Makefile` defines `srcsvgimages`, `bldsvgimages`, and related variables, but no `svgimages` definition was found.
- Observation: Absolute paths in generated dependency files would not be portable between host and Docker builds.
  Evidence: a consuming repository may live at a host path such as `/tmp/pandoc-image-deps-fixture`, while its Docker wrapper can mount the same checkout at `/src` inside the container. A generated dependency file under `build/` may be reused by both environments, so hard-coded host or container paths could stop matching Make target names.
- Observation: The Make dry-run behavior can be tested without relying on the repository's real content.
  Evidence: `test_make_dry_run_rebuilds_only_document_for_touched_image` creates a temporary content repository, runs a real `make html` build, touches only `src/img/a.svg`, and verifies that `make -n html` prints a `doc-a.md -t html` recipe but not a `doc-b.md -t html` recipe.
- Observation: The generated dependency include should be skipped only for a pure `make clean`.
  Evidence: `Makefile` uses `ifneq ($(MAKECMDGOALS),clean)` so `make clean` avoids regenerating `build/.image-deps.mk`, while combined invocations such as `make clean all` still include image dependencies for the build goal.

## Decision Log

- Decision: Generate per-document image prerequisites automatically from the Markdown source instead of maintaining them manually in the Makefile.
  Rationale: The user specifically wants image dependency tracking without updating Makefiles every time an image is added to a document.
  Date/Author: 2026-06-08 / Codex
- Decision: Use Pandoc's JSON abstract syntax tree as the source of truth for image references.
  Rationale: Pandoc already parses this repository's Markdown dialect, including images in tables and other nested structures. A JSON tree avoids fragile regular expressions.
  Date/Author: 2026-06-08 / Codex
- Decision: Treat images as normal prerequisites for all generated document outputs covered by the scanner, including HTML, TeX, PDF, XHTML, DOCX, PPTX, native, transformed native, email HTML, and EML.
  Rationale: Some formats embed image bytes and some may only reference paths, but using normal prerequisites everywhere is simpler and still fixes the main problem: only documents that refer to the changed image rebuild.
  Date/Author: 2026-06-08 / Codex
- Decision: Keep output-format-aware image extension resolution.
  Rationale: The Makefile passes different `--default-image-extension` values to Pandoc for different formats. Extensionless Markdown image targets must resolve the same way as the real build, otherwise Make will track the wrong files.
  Date/Author: 2026-06-08 / Codex
- Decision: Emit generated dependencies with Make variables such as `$(BUILD_DIR)` and `$(BUILD_IMG_DIR)` instead of absolute paths.
  Rationale: Variableized paths are resolved by the current Make invocation, so the same generated dependency file remains valid when the checkout is built on the host or mounted at a different path inside Docker.
  Date/Author: 2026-06-08 / Codex

## Outcomes & Retrospective

Implemented. The tools repo now generates `build/.image-deps.mk` from Markdown image references and includes it in the Make build so each document output depends only on the images referenced by its own source document. The Makefile no longer uses the global `$(bldimages)` prerequisite on document output rules, although it still keeps the image conversion rules and `clean` support.

The implementation uses Make-variable paths such as `$(BUILD_DIR)/feature-demo.html` and `$(BUILD_IMG_DIR)/demo-figure.svg` in generated dependency files so the same generated file remains valid when a checkout is built on the host or mounted at a different path inside Docker. Validation passed with `uv run --project . reuse lint`, `uv run --project . -m pytest -q -k "not regression"`, `uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp`, and `uv run --project . -m pytest -q`.

Remaining limitation: generating dependency files requires the `pandoc` executable because the scanner uses Pandoc's JSON parser as the source of truth. This is acceptable for Make builds because Pandoc is already required to build any document output.

## Context and Orientation

This repository is the reusable `pandoc_writing_tools` repository. It is often consumed as a Git submodule by content repositories. Its `Makefile` is included by content repositories and is responsible for building Markdown files from `src/*.md` into outputs under `build/`. In this plan, "content repository" means a repository like `/tmp/pandoc-image-deps-fixture` that has `src/`, `src/img/`, and `build/`. "Tools repository" means this repository, which provides the shared Makefile, Docker image, filters, templates, and Python utilities.

The relevant files are:

- `Makefile`, which defines `SRC_DIR`, `BUILD_DIR`, `SRC_IMG_DIR`, `BUILD_IMG_DIR`, `DOCS`, output targets, image conversion rules, and document build rules.
- `scripts/python/`, which already contains Python utilities and tests.
- `scripts/python/tests/`, which contains pytest tests and should receive new tests for the dependency scanner.
- `examples/feature-demo/`, which is the existing regression fixture and a useful end-to-end build target.

Make uses file timestamps to decide whether to rebuild a target. A normal prerequisite means "if this input is newer than the target, rebuild the target." An order-only prerequisite means "this input must exist before the recipe runs, but its timestamp should not cause a rebuild." This plan deliberately uses normal prerequisites for image dependencies on all document outputs. That means changing an image may rebuild an intermediate `.tex` file even though the TeX text only contains an image path, but it keeps the behavior simple and correct for embedded formats.

The current image conversion rules produce built images under `build/img/`. SVG source images in `src/img/*.svg` can become `build/img/*.svg`, `build/img/*.png`, and `build/img/*.pdf`. PNG, JPG, and JPEG source images are copied to matching files under `build/img/`. Document authors generally refer to `build/img/...` paths from Markdown. For extensionless image targets, Pandoc chooses an extension based on the `--default-image-extension` flag used by the output rule.

## Milestones

### Milestone 1: Add a scanner that emits Make dependencies

At the end of this milestone, the tools repo will have a Python script that can read all `src/*.md` files for a content root, find local image references, resolve the built image paths needed for each output profile, and write a generated Makefile fragment such as `build/.image-deps.mk`. A novice can run the script by hand and inspect rules showing that `build/doc-a.html` depends on `build/img/a.svg`, while `build/doc-b.html` depends on `build/img/b.svg`.

### Milestone 2: Integrate generated dependencies into the Makefile

At the end of this milestone, `Makefile` will include `build/.image-deps.mk` and document build rules will no longer depend on the global `$(bldimages)` list. Referenced images will still be built by the existing image conversion pattern rules, but unrelated images will not become prerequisites of unrelated documents.

### Milestone 3: Test the dependency graph and incremental behavior

At the end of this milestone, pytest tests will cover the scanner's path resolution and a small Make-based integration scenario. The integration test should create or use a tiny content tree with two documents and separate images, build or dry-run the relevant targets, touch one image, and prove that only the document depending on that image is considered out of date.

### Milestone 4: Validate with the feature demo and full test suite

At the end of this milestone, the existing regression tests and feature-demo build still pass. The plan's `Outcomes & Retrospective` section must record the exact commands run and the observed results.

## Plan of Work

Create `scripts/python/generate_image_deps.py`. This script should use only the Python standard library plus the `pandoc` executable already required by the build. It should invoke Pandoc with `-t json` and `--from markdown-example_lists` for each Markdown document. It should parse the JSON recursively and collect every element whose Pandoc type is `Image`.

The script should expose small testable functions. Use names like `iter_image_targets`, `resolve_image_target`, `deps_for_document`, and `render_makefile`. The function `iter_image_targets` should walk arbitrary nested dictionaries and lists from the Pandoc JSON tree. The function `resolve_image_target` should ignore remote URLs such as `https://...`, `http://...`, `mailto:...`, and `data:...`. It should treat local image targets as repository-relative paths and map references under `build/img/`, `src/img/`, or `img/` to the corresponding built path under `build/img/`.

The scanner must resolve extensionless image paths using the same defaults as the Makefile recipes:

- `html`: default image extension `svg`.
- `email_html`, `xhtml`, `docx`, and `pptx`: default image extension `png`.
- `tex` and `pdf`: default image extension `pdf`.
- `eml`: use `png`, because the `.eml` target is built from email HTML and image attachments should be PNG-oriented like the email HTML path.
- `native` and `transformed_native`: use `png` as a conservative dependency representation. Native output does not embed image bytes, but this plan intentionally treats all formats as if image bytes could matter so Make behavior is simple and per-document.

For explicit image extensions, keep the extension from Markdown. For example, `build/img/open_evolve_architecture.png` should stay `build/img/open_evolve_architecture.png` for every profile. For extensionless image targets, append the profile's default extension. For example, `build/img/llm_exponential` should become `build/img/llm_exponential.svg` for HTML and `build/img/llm_exponential.pdf` for PDF/TeX.

The generated makefile should contain normal prerequisites for each document output profile. A readable output shape is:

    # Generated by scripts/python/generate_image_deps.py; do not edit.
    $(BUILD_DIR)/doc-a.html: $(BUILD_IMG_DIR)/a.svg
    $(BUILD_DIR)/doc-a.tex $(BUILD_DIR)/doc-a.pdf: $(BUILD_IMG_DIR)/a.pdf
    $(BUILD_DIR)/doc-a.xhtml $(BUILD_DIR)/doc-a.docx $(BUILD_DIR)/doc-a.pptx $(BUILD_DIR)/doc-a.native $(BUILD_DIR)/doc-a.transformed.native $(BUILD_DIR)/doc-a.email.html $(BUILD_DIR)/doc-a.eml: $(BUILD_IMG_DIR)/a.png

Use Make variables in the generated dependency file, not absolute filesystem paths. In normal builds, `CONTENT_ROOT`, `BUILD_DIR`, and `BUILD_IMG_DIR` may expand to absolute paths, but the expansion must happen inside the current Make invocation. This matters because the same checkout can be built at a host path and also inside Docker at a different mounted path. Do not generate plain relative paths like `build/doc-a.html` either, because the existing Makefile target variables expand through `$(BUILD_DIR)`. The generated rules should match that style by spelling targets as `$(BUILD_DIR)/<stem>.<ext>` and image prerequisites as `$(BUILD_IMG_DIR)/<image>.<ext>`.

Modify `Makefile` to define an image dependency include file after `BUILD_DIR` is defined:

    IMAGE_DEPS_MK := $(BUILD_DIR)/.image-deps.mk

Add a rule that regenerates that file from all Markdown sources, the generator script, and the Makefile:

    $(IMAGE_DEPS_MK): $(wildcard $(SRC_DIR)/*.md) $(TOOLS_ROOT)/scripts/python/generate_image_deps.py $(TOOLS_ROOT)/Makefile | $(BUILD_DIR)
        $(PYTHON_RUNNER) $(TOOLS_ROOT)/scripts/python/generate_image_deps.py --content-root $(CONTENT_ROOT) --output $@

Define `PYTHON_RUNNER` in the Makefile in the same spirit as `EMAIL_RUNNER`, preferring `uv run --project $(TOOLS_ROOT)` when `uv` is available and falling back to `python3` otherwise. Reuse `EMAIL_RUNNER` only if it remains semantically clear; otherwise add a separate variable so future Python scripts do not appear email-specific.

Include the generated dependencies with:

    -include $(IMAGE_DEPS_MK)

This include should appear after `DOCS` and target variables are defined, and before or after the document rules as long as GNU Make can remake the included file and restart. If implementation finds restart behavior confusing, put the include after the rule that builds `$(IMAGE_DEPS_MK)` so a novice can read it top to bottom.

Remove `$(bldimages)` from document build rule prerequisites for `.tex`, `.xhtml`, `.docx`, and `.pptx`. Remove or replace the currently unused `$(svgimages)` prerequisite from `.html` and `.email.html`. Do not remove the image conversion pattern rules or the `bldimages` variables entirely unless they are still unused after checking `clean` and any explicit image-related target. It is acceptable for `clean` to continue using `$(bldimages)` so it removes generated image artifacts.

Add tests in `scripts/python/tests/test_image_dependencies.py`. Unit tests should cover explicit PNG references, extensionless SVG-style references, external URLs, references inside nested Markdown constructs such as tables, and path mapping from `build/img/name`, `src/img/name`, and `img/name` to `build/img/name.<ext>`. An integration test should create a temporary content root with two Markdown documents and separate images, run the generator, and assert that the generated makefile contains dependencies only from each document to its own images.

If practical, add a Make dry-run integration test. The test can create a tiny wrapper `Makefile` in the temporary content root that sets `CONTENT_ROOT` and includes the tools `Makefile`. After generating or building once, touch one built image or one source image and run `make -n html` or `make -n pdf`. The observed dry-run output should mention only the target for the document that depends on that image. If this proves brittle because of generated metadata stamps or timestamps, keep the Python integration test and record the reason in `Surprises & Discoveries`.

## Review Feedback Follow-up

Two review comments were intentionally committed with `07ad6e7` so the follow-up work was visible and tracked. This section records how they were addressed in the next change.

First, the manual scanner exercise now uses a generic temporary fixture path, `/tmp/pandoc-image-deps-fixture`, instead of a real local consuming-repository path. The user-specific path fragments from the original review comment must not appear anywhere in this repository.

Second, `scripts/python/generate_image_deps.py` now has a concise summary comment near the top of the file explaining that the script scans Markdown through Pandoc JSON and writes a Make include file that maps document outputs to referenced built images. The public helper functions now have docstrings describing their behavior, inputs, and outputs.

After both changes, run:

    uv run --project . reuse lint
    uv run --project . -m pytest -q -k "not regression"
    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp

Validation after addressing the review feedback:

    uv run --project . reuse lint
    Congratulations! Your project is compliant with version 3.3 of the REUSE Specification :-)

    uv run --project . -m pytest -q -k "not regression"
    34 passed, 4 deselected in 2.36s

    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp
    4 passed, 34 deselected in 2.60s

## Makefile Review Feedback Follow-up

After `6d135cf`, three `REVIEW` comments remained in `Makefile`. They were addressed in a focused follow-up change.

First, `EMAIL_RUNNER` was removed after inspection confirmed that it was only an alias for `PYTHON_RUNNER`. The `.eml` recipe now invokes `$(PYTHON_RUNNER)` directly. Check usage with:

    rg -n "EMAIL_RUNNER|PYTHON_RUNNER" Makefile

Second, the `REVIEW` comment above the `$(IMAGE_DEPS_MK)` include guard was replaced with a normal explanatory comment. The comment explains that a pure `make clean` must not remake generated dependency files before removing build artifacts, while combined goals such as `make clean all` still include image dependencies for the build goal.

Third, the old `build:` target was removed after repository search found no callers. Generated-output rules now name `$(BUILD_DIR)` as an order-only prerequisite where they write directly below the build directory. Image conversion rules also use `$(BUILD_IMG_DIR)` as an order-only prerequisite so creating or updating the image directory does not make unrelated built images stale.

Focused validation after implementing those edits:

    uv run --project . -m pytest scripts/python/tests/test_image_dependencies.py -q
    11 passed in 3.76s

    temporary clean-guard check
    pure_clean_touched_deps=0
    combined_goal_exposed_deps=1

Required validation before committing the follow-up:

    uv run --project . reuse lint
    Congratulations! Your project is compliant with version 3.3 of the REUSE Specification :-)

    uv run --project . -m pytest -q -k "not regression"
    34 passed, 4 deselected in 3.90s

    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp
    4 passed, 34 deselected in 8.00s

## Concrete Steps

Run commands from the tools repository root. In a local checkout, that is the root of this repository:

    cd /path/to/pandoc_writing_tools

Start by checking the branch and status:

    git status --short --branch

Create the scanner:

    $EDITOR scripts/python/generate_image_deps.py

The script should accept these command-line arguments:

    --content-root PATH
    --output PATH
    --src-dir PATH optional, default CONTENT_ROOT/src
    --build-dir PATH optional, default CONTENT_ROOT/build
    --from FORMAT optional, default markdown-example_lists

The script should write the parent directory for `--output` if needed. It should be safe to run repeatedly and should overwrite the dependency file atomically by writing to a temporary file next to the output and then renaming it.

Manually exercise the scanner against a consuming content repository before wiring it into Make. Use a temporary fixture or the feature demo instead of a real private content repository:

    uv run --project . \
      scripts/python/generate_image_deps.py \
      --content-root /tmp/pandoc-image-deps-fixture \
      --output /tmp/image-deps.mk

The output should contain dependencies for documents that include images, such as `how-llms-affect-sw-engineering` depending on `build/img/llm_exponential.svg` for HTML and `build/img/llm_exponential.pdf` for PDF/TeX.

Next, edit `Makefile` to add `PYTHON_RUNNER`, `IMAGE_DEPS_MK`, the generated dependency rule, and the `-include`. Then remove global image prerequisites from document rules as described above.

Add tests:

    $EDITOR scripts/python/tests/test_image_dependencies.py

Run the focused tests:

    uv run --project . -m pytest scripts/python/tests/test_image_dependencies.py -q

Run all tests that are expected to run in GitHub CI:

    uv run --project . -m pytest -q

Run the regression output tests explicitly because they are most likely to catch output or build graph regressions:

    uv run --project . -m pytest scripts/python/tests/test_regression_outputs.py -q

If Docker is available, run the feature demo build:

    cd /path/to/pandoc_writing_tools/examples/feature-demo
    ./build_with_docker.sh

Return to the tools repo root and inspect the status:

    cd /path/to/pandoc_writing_tools
    git status --short

## Validation and Acceptance

Acceptance requires both automated tests and an observable incremental-build scenario.

The scanner unit tests pass:

    uv run --project . -m pytest scripts/python/tests/test_image_dependencies.py -q

Expected result: all tests in `test_image_dependencies.py` pass. At least one test should fail before the implementation because `scripts/python/generate_image_deps.py` does not exist yet.

The full Python test suite passes:

    uv run --project . -m pytest -q

Expected result: all tests pass, including the existing regression output test. If a regression golden changes only because generated dependency files are added or omitted, update the implementation instead; generated `build/.image-deps.mk` should not be part of rendered document output.

The Make behavior is observable. Use a tiny content root with `src/doc-a.md`, `src/doc-b.md`, `src/img/a.svg`, and `src/img/b.svg`, or an equivalent pytest fixture. After an initial build, touching `src/img/a.svg` and running a dry-run build should show a rebuild for `doc-a` outputs and not for `doc-b` outputs. A concise expected transcript looks like:

    $ make -n html
    pandoc /tmp/content/src/doc-a.md -t html ...

The transcript should not include:

    pandoc /tmp/content/src/doc-b.md -t html ...

The feature demo still builds:

    cd /path/to/pandoc_writing_tools/examples/feature-demo
    ./build_with_docker.sh

Expected result: the command exits successfully. Any LaTeX warnings that were already present before this change should be recorded, but new missing image errors or regression mismatches are not acceptable.

## Idempotence and Recovery

The generator must be idempotent: running it twice with the same Markdown inputs should produce the same `build/.image-deps.mk` content. Atomic writes prevent half-written dependency files if the script fails. If a generated dependency file becomes stale or corrupt, delete `build/.image-deps.mk` and rerun Make; the include rule should regenerate it.

If the Makefile integration causes unexpected rebuild loops, temporarily remove the `-include $(IMAGE_DEPS_MK)` line and run the generator manually to inspect whether it writes stable content. A common cause of Makefile rebuild loops is nondeterministic output ordering; sort documents, targets, and prerequisites before writing.

If a path does not resolve, prefer a warning in the generated dependency file comments or on stderr over silently adding a dependency that Make cannot build. For example, an extensionless PNG source used in a PDF build may resolve to `build/img/name.pdf`, but the current Makefile only knows how to produce PDF images from SVG sources. The scanner should not hide that problem; Make or LaTeX should still fail clearly.

Do not commit generated `build/.image-deps.mk`; it belongs under `build/`, which is an artifact directory.

## Artifacts and Notes

Useful snippets to capture after implementation:

    # First lines of generated dependency file
    # Generated by scripts/python/generate_image_deps.py; do not edit.
    $(BUILD_DIR)/how-llms-affect-sw-engineering.html: $(BUILD_IMG_DIR)/llm_exponential.svg
    $(BUILD_DIR)/how-llms-affect-sw-engineering.tex $(BUILD_DIR)/how-llms-affect-sw-engineering.pdf: $(BUILD_IMG_DIR)/llm_exponential.pdf

    # Focused test result
    scripts/python/tests/test_image_dependencies.py::test_extensionless_image_uses_profile_default PASSED
    scripts/python/tests/test_image_dependencies.py::test_generated_deps_are_per_document PASSED

    # Incremental behavior evidence
    touch src/img/a.svg
    make -n html
    # output includes doc-a.html recipe and does not include doc-b.html recipe

Actual validation results:

    uv run --project . -m pytest scripts/python/tests/test_image_dependencies.py -q
    11 passed in 1.97s

    uv run --project . -m pytest -q -k "not regression"
    34 passed, 4 deselected in 2.12s

    uv run --project . reuse lint
    Congratulations! Your project is compliant with version 3.3 of the REUSE Specification :-)

    uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp
    4 passed, 34 deselected in 5.19s

    uv run --project . -m pytest -q
    38 passed in 2.96s

## Interfaces and Dependencies

Add `scripts/python/generate_image_deps.py` with these public functions:

    iter_image_targets(pandoc_json: object) -> list[str]
    resolve_image_target(target: str, content_root: Path, build_dir: Path, default_extension: str) -> Path | None
    deps_for_document(markdown_path: Path, content_root: Path, profiles: Mapping[str, str]) -> Mapping[str, set[Path]]
    render_makefile(dependencies: Mapping[Path, set[Path]]) -> str
    main(argv: Sequence[str] | None = None) -> int

Use Python's `json`, `pathlib`, `subprocess`, `tempfile`, and `urllib.parse` modules. Do not add a new third-party dependency unless implementation proves the standard-library approach inadequate, and if that happens, record the decision in this plan before adding the dependency.

Modify `Makefile` to define:

    PYTHON_RUNNER = $(shell command -v uv >/dev/null 2>&1 && echo "uv run --project $(TOOLS_ROOT)" || echo "python3")
    IMAGE_DEPS_MK := $(BUILD_DIR)/.image-deps.mk

The exact Make syntax may vary, but the final behavior must be that Make can regenerate `$(IMAGE_DEPS_MK)` before deciding document targets, and document targets depend only on the images referenced by their own Markdown source.

Add `scripts/python/tests/test_image_dependencies.py` using pytest. The tests should not require network access. They may require the local `pandoc` executable for AST parsing; if Pandoc is missing, skip only the tests that invoke Pandoc and keep pure path-resolution tests active.

Plan update note: 2026-06-08. Created the ExecPlan for automatic per-document image dependency tracking in `pandoc_writing_tools`, based on the design decision to use normal prerequisites for all generated document formats while still resolving image extensions per output profile.
Plan update note: 2026-06-08. Moved the ExecPlan into the `pandoc_writing_tools` repository and rewrote paths and commands so they are relative to the tools repository root.
Plan update note: 2026-06-08. Replaced absolute generated dependency paths with Make-variable paths to keep the dependency file portable between host and Docker builds.
Plan update note: 2026-06-08. Implemented the scanner, Makefile integration, tests, and validation, and recorded the final evidence.
Plan update note: 2026-06-08. Tightened the Make include guard so only pure `make clean` skips generated dependencies, then refreshed validation evidence.
Plan update note: 2026-06-08. After committing the implementation, added concrete follow-up steps for the committed review feedback comments.
Plan update note: 2026-06-08. Addressed the review feedback by removing real local paths and documenting the generator functions.
Plan update note: 2026-06-08. Recorded successful validation after addressing the review feedback.
Plan update note: 2026-06-08. Committed the review-feedback cleanup as `6d135cf` and recorded follow-up steps for the remaining `Makefile` review comments.
Plan update note: 2026-06-08. Implemented the remaining `Makefile` review follow-up and recorded focused validation for the directory-prerequisite behavior.
Plan update note: 2026-06-08. Recorded the required local validation results for the Makefile review follow-up.
