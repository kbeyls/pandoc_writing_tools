-- SPDX-FileCopyrightText: <text>Copyright 2024 Arm Limited and/or its
-- affiliates <open-source-office@arm.com></text>
-- SPDX-License-Identifier: MIT

-- This script adds an "edit" button after every header that, when clicked,
-- brings the reader to a github interface to edit the source code of the
-- relevant section, and create a pull request.

-- pandoc has poor support for getting source line information. It is
-- currently (as of 2024) only supported if the input is commonmark.
-- In content projects using this filter, we use the pandoc dialect of Markdown, not commonmark,
-- so we cannot use that.
-- To get line information, we use the following hack in this script:
-- We first read the book.md source file and store the line number for
-- each header we find. We find headers by parsing against a regular
-- expression (^#+ .*$).
-- Then we iterate over all headers in the pandoc AST and annotate a
-- header with line number information and a link to the github "edit"
-- interface.

-- local logging = require 'theme/html/logging'

local edit_source_file = nil
local edit_url_base = nil

local headernr2depth_linenr = {}
function mdheaders_linenrs_in_file(file)
  local linenr = 1
  local header_count = 0
  local header_pattern = "^(#+) +(.*)$"
  for line in io.lines(file) do
    if string.find(line, header_pattern) then
      _, _, header_hashes, header_text = string.find(line, header_pattern)
      depth = string.len(header_hashes)
      headernr2depth_linenr[header_count] = {depth=depth, text=header_text, linenr=linenr};
      header_count = header_count + 1;
    end
    linenr = linenr + 1;
  end
  return headernr2depth_linenr
end

function Pandoc(p)
  if not p.meta then
    io.stderr:write("Error: 'edit-source-file' and 'edit-url-base' metadata fields are required for add_edit_to_headers.lua.\n")
    os.exit(1)
  end
  if p.meta["edit-source-file"] then
    local value = pandoc.utils.stringify(p.meta["edit-source-file"])
    if value ~= "" then
      edit_source_file = value
    end
  end
  if p.meta["edit-url-base"] then
    local value = pandoc.utils.stringify(p.meta["edit-url-base"])
    if value ~= "" then
      edit_url_base = value
    end
  end
  if not edit_source_file or edit_source_file == "" then
    io.stderr:write("Error: 'edit-source-file' metadata field is required for add_edit_to_headers.lua.\n")
    os.exit(1)
  end
  if not edit_url_base or edit_url_base == "" then
    io.stderr:write("Error: 'edit-url-base' metadata field is required for add_edit_to_headers.lua.\n")
    os.exit(1)
  end
  mdheaders_linenrs_in_file(edit_source_file)
end

local header_nr=0
function Header (h)
  parsed_header_info = headernr2depth_linenr[header_nr]
  linenr = parsed_header_info.linenr
  if h.level ~= parsed_header_info.depth then
    print("In filter add_edit_to_headers.lua:")
    print("Expected a header at level "..parsed_header_info.depth,
          " at source linenr "..parsed_header_info.linenr,
          ": "..parsed_header_info.text);
    print("  instead saw ",h);
    os.exit(-1);
  end
  header_nr = header_nr + 1
  link_url = edit_url_base .. "#L" .. linenr;
  local edit_link = pandoc.Link({pandoc.Str ''}, link_url, "Suggest an edit",
                                {});
  edit_link.classes = {"suggestedit"}

  h.content = h.content .. {edit_link}
  return h
end



return {
  { Pandoc = Pandoc },
  { Header = Header }
}
