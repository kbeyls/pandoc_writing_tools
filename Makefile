# SPDX-FileCopyrightText: <text>Copyright 2021-2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

TOOLS_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ifeq ($(origin CONTENT_ROOT), undefined)
$(error CONTENT_ROOT is not set; set it to the content repo root before including this Makefile)
endif
ifeq ($(strip $(CONTENT_ROOT)),)
$(error CONTENT_ROOT is empty; set it to the content repo root before including this Makefile)
endif
find_git_root = $(shell \
  dir="$(abspath $(1))"; \
  while [ -n "$$dir" ] && [ "$$dir" != "/" ]; do \
    if [ -e "$$dir/.git" ]; then echo "$$dir"; exit 0; fi; \
    dir=$$(dirname "$$dir"); \
  done; \
  if [ -e "/.git" ]; then echo "/"; fi \
)

CONTENT_GIT_ROOT := $(call find_git_root,$(CONTENT_ROOT))
ifeq ($(strip $(CONTENT_GIT_ROOT)),)
$(error Could not locate .git directory starting from CONTENT_ROOT=$(CONTENT_ROOT))
endif

SRC_DIR := $(CONTENT_ROOT)/src
BUILD_DIR := $(CONTENT_ROOT)/build
SRC_IMG_DIR := $(SRC_DIR)/img
BUILD_IMG_DIR := $(BUILD_DIR)/img
DEFAULT_HTML_TEMPLATE := $(TOOLS_ROOT)/default_pandoc_html_template
DEFAULT_LATEX_TEMPLATE := $(TOOLS_ROOT)/default_pandoc_latex_template
DEFAULT_DOCX_TEMPLATE := $(TOOLS_ROOT)/default_pandoc_docx_template

GIT = git -C $(CONTENT_GIT_ROOT)
GIT_HEAD_REL := $(shell $(GIT) rev-parse --git-path HEAD 2>/dev/null)
GIT_HEAD_PATH := $(if $(strip $(GIT_HEAD_REL)),$(abspath $(CONTENT_GIT_ROOT)/$(GIT_HEAD_REL)),)
GIT_HEAD_DEP := $(if $(strip $(GIT_HEAD_PATH)),$(GIT_HEAD_PATH),)

last_updated = $(shell $(GIT) log --format=%ad HEAD -- $(1) $(2) | head -1)

is_dirty = $(shell test -n "`$(GIT) status --porcelain -- $(1) $(2)`" && echo "-with-local-changes")
compute_version = $(strip $(shell $(GIT) log --oneline --follow -- $(1) $(2) | wc -l))$(call is_dirty,$(1),$(2))
short_commit_log = $(shell $(GIT) log --oneline --follow -- $(1) $(2))

# --self-contained ensures images are embedded in the generated HTML.
# --resource-path indicates where pandoc can find external resources, such as
# images.
PANDOCFLAGS = \
	      --table-of-contents \
	      --number-sections \
	      --resource-path=$(CONTENT_ROOT):$(SRC_DIR):$(BUILD_DIR) \
	      --standalone \
	      --embed-resources \
		  --metadata=LAST_UPDATED:"$(call last_updated,$(SRC_DIR)/$*.md)" \
		  --metadata=VERSION:$(call compute_version,$(SRC_DIR)/$*.md) \
		  --from markdown-example_lists
#		  --metadata=SHORT_COMMIT_LOG:"$(call short_commit_log,$*.md,$*.bib)"

# Email outputs should not inline resources because images are attached via MIME.
EMAILPANDOCFLAGS = \
	      --table-of-contents \
	      --number-sections \
	      --resource-path=$(CONTENT_ROOT):$(SRC_DIR):$(BUILD_DIR) \
	      --standalone \
		  --metadata=LAST_UPDATED:"$(call last_updated,$(SRC_DIR)/$*.md)" \
		  --metadata=VERSION:$(call compute_version,$(SRC_DIR)/$*.md) \
		  --from markdown-example_lists

PYTHON_RUNNER = $(shell command -v uv >/dev/null 2>&1 && echo "uv run --project $(TOOLS_ROOT)" || echo "python3")

COMMONFILTERS = \
          --lua-filter $(TOOLS_ROOT)/theme/fignos.lua \
          --lua-filter $(TOOLS_ROOT)/theme/index.lua \
		  --lua-filter $(TOOLS_ROOT)/theme/toc.lua \
          --citeproc

HTML_ISSUE_LINKS ?= 0
HTML_EDIT_LINKS ?= 0

HTML_EXTRA_FILTERS =
HTML_EXTRA_DEPS =

ifeq ($(strip $(HTML_ISSUE_LINKS)),1)
HTML_EXTRA_FILTERS += --lua-filter $(TOOLS_ROOT)/theme/html/markup_issue.lua
HTML_EXTRA_DEPS += $(TOOLS_ROOT)/theme/html/markup_issue.lua
endif

ifeq ($(strip $(HTML_EDIT_LINKS)),1)
HTML_EXTRA_FILTERS += --lua-filter $(TOOLS_ROOT)/theme/html/add_edit_to_headers.lua
HTML_EXTRA_DEPS += $(TOOLS_ROOT)/theme/html/add_edit_to_headers.lua
endif

DOCS = $(filter-out AGENTS,$(patsubst $(SRC_DIR)/%.md,%,$(wildcard $(SRC_DIR)/*.md)))
# Bibliography files are content-specific; default to the source .bib files
# instead of requiring every content repo to provide a file named thinking.bib.
BIB_DEPS ?= $(wildcard $(SRC_DIR)/*.bib)
PDFTARGETS = $(patsubst %,$(BUILD_DIR)/%.pdf,$(DOCS))
TEXTARGETS = $(patsubst %,$(BUILD_DIR)/%.tex,$(DOCS))
HTMLTARGETS = $(patsubst %,$(BUILD_DIR)/%.html,$(DOCS))
XHTMLTARGETS = $(patsubst %,$(BUILD_DIR)/%.xhtml,$(DOCS))
DOCXTARGETS = $(patsubst %,$(BUILD_DIR)/%.docx,$(DOCS))
PPTXTARGETS = $(patsubst %,$(BUILD_DIR)/%.pptx,$(DOCS))
NATIVETARGETS = $(patsubst %,$(BUILD_DIR)/%.native,$(DOCS))
NATIVE_TRANSFORMED_TARGETS = $(patsubst %,$(BUILD_DIR)/%.transformed.native,$(DOCS))
NATIVETARGETS += $(NATIVE_TRANSFORMED_TARGETS)
DOWNLOADSTARGETS = $(PDFTARGETS) $(HTMLTARGETS)
VERSIONSTAMPS = $(patsubst %,$(BUILD_DIR)/.version-%.stamp,$(DOCS))
GITHASHSTAMPS = $(patsubst %,$(BUILD_DIR)/.githash-%.stamp,$(DOCS))
VERSIONCHECKS = $(patsubst %,$(BUILD_DIR)/.version-%.checked,$(DOCS))
GITHASHCHECKS = $(patsubst %,$(BUILD_DIR)/.githash-%.checked,$(DOCS))
EMLHTMLTARGETS = $(patsubst %,$(BUILD_DIR)/%.email.html,$(DOCS))
EMLTARGETS = $(patsubst %,$(BUILD_DIR)/%.eml,$(DOCS))
IMAGE_DEPS_MK := $(BUILD_DIR)/.image-deps.mk
BUILD_BIB_DEPS_DIR := $(BUILD_DIR)/bib-deps
# Bibliography dependency tracking uses two per-document files with different
# mtime contracts. The JSON fingerprint changes only when the document's
# selected citation data changes, and document outputs depend on that file so
# unrelated .bib edits do not rebuild them. The checked stamp records that the
# scanner has already examined the current Markdown and .bib inputs, even when
# the JSON did not change, so later no-change builds do not rerun the scanner.
BIB_REF_TARGETS = $(patsubst %,$(BUILD_BIB_DEPS_DIR)/%.refs.json,$(DOCS))
BIB_CHECK_TARGETS = $(patsubst %,$(BUILD_BIB_DEPS_DIR)/%.refs.checked,$(DOCS))
BIB_CHECKED_PATTERN = $(BUILD_BIB_DEPS_DIR)/%.refs.checked
BIB_FILE_ARGS = $(foreach bib,$(BIB_DEPS),--bib-file $(bib))

# Version stamps track git-derived metadata so outputs rebuild when VERSION or
# LAST_UPDATED changes (e.g., after commits) without forcing full rebuilds.

.PHONY: all clean pdf html eml pptx
# These generated prerequisites carry incremental state in their mtimes.
# `.SECONDARY` would prevent Make from deleting them, but it would also let
# Make ignore a missing generated prerequisite if a final output already
# exists. `.PRECIOUS` only disables the automatic deletion, so missing state is
# rebuilt and no-change builds can still inspect the preserved files.
.PRECIOUS: $(VERSIONSTAMPS) $(GITHASHSTAMPS) $(VERSIONCHECKS) \
	$(GITHASHCHECKS) $(BIB_REF_TARGETS) $(BIB_CHECK_TARGETS) \
	$(EMLHTMLTARGETS)
all: pdf html native downloads xhtml tex docx pptx eml
pdf: $(PDFTARGETS)
html: $(HTMLTARGETS) $(BUILD_DIR)/default.css
native: $(NATIVETARGETS)
downloads: $(DOWNLOADSTARGETS)
xhtml: $(XHTMLTARGETS)
tex: $(TEXTARGETS)
docx: $(DOCXTARGETS)
pptx: $(PPTXTARGETS)
eml: $(EMLTARGETS)

# A pure `make clean` must not remake generated dependency files before
# removing build artifacts. Combined goals such as `make clean all` still
# include image dependencies so the build goal has an accurate graph.
ifneq ($(MAKECMDGOALS),clean)
-include $(IMAGE_DEPS_MK)
# Empty refs.checked files are included as generated makefiles so Make updates
# bibliography fingerprints before it decides whether document outputs are
# stale. The files intentionally contain no rules; their mtimes only record
# that generate_bib_deps.py has checked the current Markdown and .bib inputs.
-include $(BIB_CHECK_TARGETS)
# Metadata checked files follow the same pattern. They are empty generated
# makefiles that update the content stamps before Make compares document
# outputs against VERSION and LAST_UPDATED metadata files.
-include $(GITHASHCHECKS) $(VERSIONCHECKS)
endif

# Image sources can be SVG, Graphviz DOT, PNG, or JPEG files.
# The below lines define to convert the SVG source images to PDF images such
# that they can be included in the LaTeX/PDF build.
# The source images live in src/img, the produced images live in build/img.
# The pandoc markdown source files need to include the images living in build/img.
# Derive Inkscape's export type from the target suffix so the normal SVG and
# Excalidraw SVG rules share one command for both PDF and PNG outputs.
INKSCAPE_EXPORT_IMAGE = inkscape $< --export-type=$(patsubst .%,%,$(suffix $@)) --export-filename=$@
GRAPHVIZ_DOT ?= dot

$(BUILD_IMG_DIR)/%.pdf: $(SRC_IMG_DIR)/%.svg | $(BUILD_IMG_DIR)
	$(INKSCAPE_EXPORT_IMAGE)
# Excalidraw exports keep editable scene metadata in files named
# `name.excalidraw.svg`. Markdown should still refer to the logical image stem,
# e.g. `build/img/name`, so Pandoc can select `.svg`, `.pdf`, or `.png` per
# output format. These fallback rules strip the editor marker from build
# artifact names while preserving the source filename on disk.
$(BUILD_IMG_DIR)/%.pdf: $(SRC_IMG_DIR)/%.excalidraw.svg | $(BUILD_IMG_DIR)
	$(INKSCAPE_EXPORT_IMAGE)
$(BUILD_IMG_DIR)/%.png: $(SRC_IMG_DIR)/%.svg | $(BUILD_IMG_DIR)
	$(INKSCAPE_EXPORT_IMAGE)
$(BUILD_IMG_DIR)/%.png: $(SRC_IMG_DIR)/%.excalidraw.svg | $(BUILD_IMG_DIR)
	$(INKSCAPE_EXPORT_IMAGE)
$(BUILD_IMG_DIR)/%.png: $(SRC_IMG_DIR)/%.png | $(BUILD_IMG_DIR)
	cp $< $@
$(BUILD_IMG_DIR)/%.jpg: $(SRC_IMG_DIR)/%.jpg | $(BUILD_IMG_DIR)
	cp $< $@
$(BUILD_IMG_DIR)/%.jpeg: $(SRC_IMG_DIR)/%.jpeg | $(BUILD_IMG_DIR)
	cp $< $@
$(BUILD_IMG_DIR)/%.svg: $(SRC_IMG_DIR)/%.svg | $(BUILD_IMG_DIR)
	cp $< $@
$(BUILD_IMG_DIR)/%.svg: $(SRC_IMG_DIR)/%.excalidraw.svg | $(BUILD_IMG_DIR)
	cp $< $@
$(BUILD_IMG_DIR)/%.svg: $(SRC_IMG_DIR)/%.dot | $(BUILD_IMG_DIR)
	$(GRAPHVIZ_DOT) -Tsvg $< -o $@
$(BUILD_IMG_DIR)/%.pdf: $(SRC_IMG_DIR)/%.dot | $(BUILD_IMG_DIR)
	$(GRAPHVIZ_DOT) -Tpdf $< -o $@
$(BUILD_IMG_DIR)/%.png: $(SRC_IMG_DIR)/%.dot | $(BUILD_IMG_DIR)
	$(GRAPHVIZ_DOT) -Tpng $< -o $@
$(BUILD_IMG_DIR)/%.cmapx: $(SRC_IMG_DIR)/%.dot | $(BUILD_IMG_DIR)
	$(GRAPHVIZ_DOT) -Tcmapx $< -o $@
$(BUILD_IMG_DIR)/%.drawio: $(BUILD_IMG_DIR)/%.svg $(BUILD_IMG_DIR)/%.png \
					$(BUILD_IMG_DIR)/%.cmapx $(TOOLS_ROOT)/scripts/python/generate_drawio_overlay.py | $(BUILD_IMG_DIR)
	$(PYTHON_RUNNER) $(TOOLS_ROOT)/scripts/python/generate_drawio_overlay.py \
		--svg $(BUILD_IMG_DIR)/$*.svg \
		--png $(BUILD_IMG_DIR)/$*.png \
		--map $(BUILD_IMG_DIR)/$*.cmapx \
		--output $@
	touch $@
$(BUILD_IMG_DIR): | $(BUILD_DIR)
	mkdir -p $(BUILD_IMG_DIR)
srcsvgimages := $(wildcard $(SRC_IMG_DIR)/*.svg)
srcdotimages := $(wildcard $(SRC_IMG_DIR)/*.dot)
srcpngimages := $(wildcard $(SRC_IMG_DIR)/*.png)
srcjpgimages := $(wildcard $(SRC_IMG_DIR)/*.jpg)
srcjpegimages := $(wildcard $(SRC_IMG_DIR)/*.jpeg)
bldsvgimages := $(patsubst $(SRC_IMG_DIR)/%.svg,$(BUILD_IMG_DIR)/%.svg,$(srcsvgimages))
bldpdfimages := $(patsubst $(SRC_IMG_DIR)/%.svg,$(BUILD_IMG_DIR)/%.pdf,$(srcsvgimages))
bldsvgpngimages := $(patsubst $(SRC_IMG_DIR)/%.svg,$(BUILD_IMG_DIR)/%.png,$(srcsvgimages))
blddotsvgimages := $(patsubst $(SRC_IMG_DIR)/%.dot,$(BUILD_IMG_DIR)/%.svg,$(srcdotimages))
blddotpdfimages := $(patsubst $(SRC_IMG_DIR)/%.dot,$(BUILD_IMG_DIR)/%.pdf,$(srcdotimages))
blddotpngimages := $(patsubst $(SRC_IMG_DIR)/%.dot,$(BUILD_IMG_DIR)/%.png,$(srcdotimages))
blddotmapimages := $(patsubst $(SRC_IMG_DIR)/%.dot,$(BUILD_IMG_DIR)/%.cmapx,$(srcdotimages))
blddotdrawioimages := $(patsubst $(SRC_IMG_DIR)/%.dot,$(BUILD_IMG_DIR)/%.drawio,$(srcdotimages))
bldpngpngimages := $(patsubst $(SRC_IMG_DIR)/%.png,$(BUILD_IMG_DIR)/%.png,$(srcpngimages))
bldjpgjpgimages := $(patsubst $(SRC_IMG_DIR)/%.jpg,$(BUILD_IMG_DIR)/%.jpg,$(srcjpgimages))
bldjpegjpegimages := $(patsubst $(SRC_IMG_DIR)/%.jpeg,$(BUILD_IMG_DIR)/%.jpeg,$(srcjpegimages))
bldimages := $(bldsvgimages) $(bldpngpngimages) $(bldsvgpngimages) $(bldpdfimages) \
	$(blddotsvgimages) $(blddotpdfimages) $(blddotpngimages) \
	$(blddotmapimages) $(blddotdrawioimages) \
	$(bldjpgjpgimages) $(bldjpegjpegimages)
.PRECIOUS: $(blddotsvgimages) $(blddotpngimages) $(blddotmapimages)
commonfilters := $(TOOLS_ROOT)/theme/fignos.lua $(TOOLS_ROOT)/theme/index.lua $(TOOLS_ROOT)/theme/toc.lua


clean:
	rm -rf $(BUILD_DIR) $(bldimages)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_BIB_DEPS_DIR): | $(BUILD_DIR)
	mkdir -p $(BUILD_BIB_DEPS_DIR)

$(IMAGE_DEPS_MK): $(wildcard $(SRC_DIR)/*.md) $(TOOLS_ROOT)/scripts/python/generate_image_deps.py $(TOOLS_ROOT)/Makefile | $(BUILD_DIR)
	$(PYTHON_RUNNER) $(TOOLS_ROOT)/scripts/python/generate_image_deps.py --content-root $(CONTENT_ROOT) --output $@

# Updating the stamp runs the scanner and validates the fingerprint against
# current inputs. The scanner itself preserves refs.json's mtime when the
# selected bibliography data is unchanged; touch the stamp only after that
# successful check completes.
$(BUILD_BIB_DEPS_DIR)/%.refs.checked: $(SRC_DIR)/%.md $(BIB_DEPS) $(TOOLS_ROOT)/scripts/python/generate_bib_deps.py $(TOOLS_ROOT)/Makefile | $(BUILD_BIB_DEPS_DIR)
	$(PYTHON_RUNNER) $(TOOLS_ROOT)/scripts/python/generate_bib_deps.py --content-root $(CONTENT_ROOT) --document $< --output $(BUILD_BIB_DEPS_DIR)/$*.refs.json $(BIB_FILE_ARGS)
	touch $@

# Fingerprints are produced or validated as a side effect of updating the
# checked stamp. refs.json is the content file that document outputs compare
# against; refs.checked only records that the scanner examined the current
# Markdown and .bib inputs. Keep refs.checked order-only here so a scanner run
# that leaves refs.json unchanged does not make document outputs rebuild.
$(BUILD_BIB_DEPS_DIR)/%.refs.json: | $(BUILD_BIB_DEPS_DIR)/%.refs.checked
	@set -e; \
	if [ ! -f $@ ]; then \
	  $(PYTHON_RUNNER) $(TOOLS_ROOT)/scripts/python/generate_bib_deps.py \
	    --content-root $(CONTENT_ROOT) --document $(SRC_DIR)/$*.md \
	    --output $@ $(BIB_FILE_ARGS); \
	  touch $(BUILD_BIB_DEPS_DIR)/$*.refs.checked; \
	fi
	@test -f $@

$(BUILD_DIR)/default.css: $(TOOLS_ROOT)/theme/html/default.css $(TOOLS_ROOT)/Makefile | $(BUILD_DIR)
	mkdir -p $(dir $@)
	cp $(TOOLS_ROOT)/theme/html/default.css $(BUILD_DIR)/default.css

$(BUILD_DIR)/%.html: $(SRC_DIR)/%.md $(BUILD_BIB_DEPS_DIR)/%.refs.json $(TOOLS_ROOT)/Makefile $(TOOLS_ROOT)/theme/html/pandoc_template.html \
                 $(TOOLS_ROOT)/theme/html/clickable_headers.lua \
				 $(TOOLS_ROOT)/theme/html/convert_to_sidenote.lua \
				 $(TOOLS_ROOT)/theme/markup_todo.lua \
				 $(HTML_EXTRA_DEPS) \
				 $(commonfilters) \
				 $(BUILD_DIR)/default.css $(BUILD_DIR)/.version-%.stamp | $(BUILD_DIR) $(BIB_CHECKED_PATTERN)
	mkdir -p $(dir $@)
	pandoc $< -t html \
		--template $(TOOLS_ROOT)/theme/html/pandoc_template.html \
		--lua-filter $(TOOLS_ROOT)/theme/html/clickable_headers.lua \
		--lua-filter $(TOOLS_ROOT)/theme/markup_todo.lua \
		--lua-filter $(TOOLS_ROOT)/theme/html/convert_to_sidenote.lua \
		--lua-filter $(TOOLS_ROOT)/theme/add_feedback_buttons.lua \
		$(HTML_EXTRA_FILTERS) \
		-M css=$(BUILD_DIR)/default.css \
		--default-image-extension=svg \
		-o $@ $(PANDOCFLAGS) $(COMMONFILTERS)

$(BUILD_DIR)/%.email.html: $(SRC_DIR)/%.md $(BUILD_BIB_DEPS_DIR)/%.refs.json $(TOOLS_ROOT)/Makefile $(TOOLS_ROOT)/theme/html/pandoc_template.html \
                 $(TOOLS_ROOT)/theme/html/clickable_headers.lua \
				 $(TOOLS_ROOT)/theme/html/convert_to_sidenote.lua \
				 $(TOOLS_ROOT)/theme/markup_todo.lua \
				 $(commonfilters) \
				 $(BUILD_DIR)/default.css $(BUILD_DIR)/.version-%.stamp | $(BUILD_DIR) $(BIB_CHECKED_PATTERN)
	mkdir -p $(dir $@)
	pandoc $< -t html \
		--template $(TOOLS_ROOT)/theme/html/pandoc_template.html \
		--lua-filter $(TOOLS_ROOT)/theme/html/clickable_headers.lua \
		--lua-filter $(TOOLS_ROOT)/theme/markup_todo.lua \
		--lua-filter $(TOOLS_ROOT)/theme/html/convert_to_sidenote.lua \
		--lua-filter $(TOOLS_ROOT)/theme/add_feedback_buttons.lua \
		-M css=$(BUILD_DIR)/default.css \
		--default-image-extension=png \
		-o $@ $(EMAILPANDOCFLAGS) $(COMMONFILTERS)

$(BUILD_DIR)/%.native: $(SRC_DIR)/%.md $(BUILD_BIB_DEPS_DIR)/%.refs.json $(TOOLS_ROOT)/Makefile $(BUILD_DIR)/.version-%.stamp | $(BUILD_DIR) $(BIB_CHECKED_PATTERN)
	mkdir -p $(dir $@)
	pandoc $< -t native -o $@ $(PANDOCFLAGS)

$(BUILD_DIR)/%.transformed.native: $(SRC_DIR)/%.md $(BUILD_BIB_DEPS_DIR)/%.refs.json $(TOOLS_ROOT)/Makefile \
				 $(commonfilters) $(BUILD_DIR)/.version-%.stamp | $(BUILD_DIR) $(BIB_CHECKED_PATTERN)
	mkdir -p $(dir $@)
	pandoc $< -t native -o $@ $(PANDOCFLAGS) $(COMMONFILTERS)

$(BUILD_DIR)/%.tex: $(SRC_DIR)/%.md $(BUILD_BIB_DEPS_DIR)/%.refs.json $(TOOLS_ROOT)/Makefile $(TOOLS_ROOT)/theme/tex/pandoc_template.tex \
				$(TOOLS_ROOT)/theme/markup_todo.lua \
				$(commonfilters) \
				$(BUILD_DIR)/.version-%.stamp | $(BUILD_DIR) $(BIB_CHECKED_PATTERN)
	mkdir -p $(dir $@)
	pandoc $< -t latex \
		--template $(TOOLS_ROOT)/theme/tex/pandoc_template.tex \
		--default-image-extension=pdf \
		--lua-filter $(TOOLS_ROOT)/theme/markup_todo.lua \
		--lua-filter $(TOOLS_ROOT)/theme/tex/text_size.lua \
		--lua-filter $(TOOLS_ROOT)/theme/add_feedback_buttons.lua \
		-o $@ $(PANDOCFLAGS) $(COMMONFILTERS)

$(BUILD_DIR)/%.xhtml: $(SRC_DIR)/%.md $(BUILD_BIB_DEPS_DIR)/%.refs.json $(TOOLS_ROOT)/Makefile \
				$(TOOLS_ROOT)/theme/markup_todo.lua \
				$(commonfilters) \
				$(TOOLS_ROOT)/theme/confluence.lua $(BUILD_DIR)/.version-%.stamp | $(BUILD_DIR) $(BIB_CHECKED_PATTERN)
	mkdir -p $(dir $@)
	pandoc $< -t $(TOOLS_ROOT)/theme/confluence.lua \
	    --default-image-extension=png \
		-o $@ $(PANDOCFLAGS) $(COMMONFILTERS)

$(BUILD_DIR)/%.docx: $(SRC_DIR)/%.md $(BUILD_BIB_DEPS_DIR)/%.refs.json $(TOOLS_ROOT)/Makefile \
				$(TOOLS_ROOT)/theme/markup_todo.lua \
				$(commonfilters) \
				$(TOOLS_ROOT)/theme/confluence.lua $(BUILD_DIR)/.version-%.stamp | $(BUILD_DIR) $(BIB_CHECKED_PATTERN)
	mkdir -p $(dir $@)
	pandoc $< -t docx \
	    --default-image-extension=png \
		-o $@ $(PANDOCFLAGS) $(COMMONFILTERS)

$(BUILD_DIR)/%.pptx: $(SRC_DIR)/%.md $(BUILD_BIB_DEPS_DIR)/%.refs.json $(TOOLS_ROOT)/Makefile \
				$(TOOLS_ROOT)/theme/markup_todo.lua \
				$(commonfilters) \
				$(BUILD_DIR)/.version-%.stamp | $(BUILD_DIR) $(BIB_CHECKED_PATTERN)
	mkdir -p $(dir $@)
	pandoc $< -t pptx \
	    --default-image-extension=png \
		-o $@ $(PANDOCFLAGS) $(COMMONFILTERS)

$(BUILD_DIR)/%.eml: $(BUILD_DIR)/%.email.html $(TOOLS_ROOT)/scripts/python/render_email.py | $(BUILD_DIR)
	$(PYTHON_RUNNER) $(TOOLS_ROOT)/scripts/python/render_email.py --html $< --output $@


$(BUILD_DIR)/%.pdf: $(BUILD_DIR)/%.tex $(TOOLS_ROOT)/Makefile | $(BUILD_DIR)
	mkdir -p $(dir $@)
	latexmk -xelatex $< -output-directory=$(BUILD_DIR)
	touch $@

$(BUILD_DIR)/.version-%.checked: $(SRC_DIR)/%.md $(TOOLS_ROOT)/Makefile \
		$(BUILD_DIR)/.githash-%.stamp | $(BUILD_DIR) \
		$(BUILD_DIR)/.githash-%.checked
	# Update the content stamp only if visible metadata changes.
	mkdir -p $(dir $@)
	@stamp="$(BUILD_DIR)/.version-$*.stamp"; \
	tmpfile="$$stamp.tmp"; \
	{ \
	  printf "VERSION=%s\n" "$(call compute_version,$(SRC_DIR)/$*.md)"; \
	  printf "LAST_UPDATED=%s\n" "$(call last_updated,$(SRC_DIR)/$*.md)"; \
	} > $$tmpfile; \
	if [ -f $$stamp ] && cmp -s $$tmpfile $$stamp; then \
	  rm $$tmpfile; \
	else \
	  mv $$tmpfile $$stamp; \
	fi; \
	touch $@

$(BUILD_DIR)/.version-%.stamp: | $(BUILD_DIR)/.version-%.checked
	@set -e; \
	if [ ! -f $@ ]; then \
	  mkdir -p $(dir $@); \
	  tmpfile="$@.tmp"; \
	  { \
	    printf "VERSION=%s\n" "$(call compute_version,$(SRC_DIR)/$*.md)"; \
	    printf "LAST_UPDATED=%s\n" "$(call last_updated,$(SRC_DIR)/$*.md)"; \
	  } > $$tmpfile; \
	  mv $$tmpfile $@; \
	  touch $(BUILD_DIR)/.version-$*.checked; \
	fi
	@test -f $@

# Per-document git hashes prevent unrelated commits from triggering rebuilds.
$(BUILD_DIR)/.githash-%.checked: $(SRC_DIR)/%.md $(TOOLS_ROOT)/Makefile | $(GIT_HEAD_DEP) $(BUILD_DIR)
	mkdir -p $(dir $@)
	@stamp="$(BUILD_DIR)/.githash-$*.stamp"; \
	tmpfile="$$stamp.tmp"; \
	last_commit="$$( $(GIT) log -1 --format=%H -- $(SRC_DIR)/$*.md )"; \
	commit_count="$$( $(GIT) log --oneline --follow -- $(SRC_DIR)/$*.md | wc -l )"; \
	dirty_suffix="$$( $(GIT) status --porcelain -- $(SRC_DIR)/$*.md )"; \
	{ \
	  printf "LAST_COMMIT=%s\n" "$$last_commit"; \
	  printf "COMMIT_COUNT=%s\n" "$$commit_count"; \
	  printf "DIRTY=%s\n" "$$dirty_suffix"; \
	} > $$tmpfile; \
	if [ -f $$stamp ] && cmp -s $$tmpfile $$stamp; then \
	  rm $$tmpfile; \
	else \
	  mv $$tmpfile $$stamp; \
	fi; \
	touch $@

$(BUILD_DIR)/.githash-%.stamp: | $(BUILD_DIR)/.githash-%.checked
	@set -e; \
	if [ ! -f $@ ]; then \
	  mkdir -p $(dir $@); \
	  tmpfile="$@.tmp"; \
	  last_commit="$$( $(GIT) log -1 --format=%H -- $(SRC_DIR)/$*.md )"; \
	  commit_count="$$( $(GIT) log --oneline --follow -- $(SRC_DIR)/$*.md | wc -l )"; \
	  dirty_suffix="$$( $(GIT) status --porcelain -- $(SRC_DIR)/$*.md )"; \
	  { \
	    printf "LAST_COMMIT=%s\n" "$$last_commit"; \
	    printf "COMMIT_COUNT=%s\n" "$$commit_count"; \
	    printf "DIRTY=%s\n" "$$dirty_suffix"; \
	  } > $$tmpfile; \
	  mv $$tmpfile $@; \
	  touch $(BUILD_DIR)/.githash-$*.checked; \
	fi
	@test -f $@
