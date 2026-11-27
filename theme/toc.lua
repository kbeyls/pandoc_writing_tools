-- SPDX-FileCopyrightText: <text>Copyright 2025-2026 Arm Limited and/or its
-- affiliates <open-source-office@arm.com></text>
-- SPDX-License-Identifier: MIT


-- This lua script enables adding a mini table of contents in arbitrary
-- locations in the document, based on header levels.
-- It looks for a div with attributes toc-list-top-level and toc-list-entry-levels.
-- toc-list-top-level specifies the specific header to start from.
-- toc-list-entry-levels specifies the range of header levels to include.
-- Example usage:
-- ::: {#key-insights-list toc-list-top-level=#insights toc-list-entry-levels=2-2 }
-- :::
-- This will create a list of all level 2 headers under the header with id "insights".
-- The list will be placed where the div is located.
-- The div will be removed from the final output.
-- The list will be formatted as a simple nested list in HTML and LaTeX output formats.
-- Each list item will link to the corresponding section in the document.
-- Missing heading levels are allowed: entries nest under the nearest included
-- ancestor, or at the top level when there is none. Heading levels and section
-- numbers in the document are not changed.
local function add_tools_root_to_package_path()
  local script = PANDOC_SCRIPT_FILE
  if not script then
    return
  end
  local script_dir = script:match("(.*/)")
  if not script_dir then
    return
  end
  local tools_root = script_dir .. ".."
  package.path = table.concat({
    tools_root .. "/?.lua",
    tools_root .. "/?/init.lua",
    package.path,
  }, ";")
end

add_tools_root_to_package_path()

local logging = require 'theme/logging/logging'

local function parse_level_range(level_range)
    local min_level, max_level = level_range:match("^(%d+)%-(%d+)$")
    if min_level and max_level then
        return tonumber(min_level), tonumber(max_level)
    else
        return nil, nil
    end
end

-- Collect all headers in the document for reference
local all_headers = {}
function record_headers(el)
    table.insert(all_headers, el)
    return el
end

local function add_header_to_toc(header, min_level, max_level, collected, ancestors)
    -- Every heading ends sections at its own level or deeper, even when that
    -- heading is outside the requested TOC entry levels.
    while #ancestors > 0 and ancestors[#ancestors].level >= header.level do
        table.remove(ancestors)
    end
    if header.level < min_level or header.level > max_level then
        return
    end

    local entry = { level = header.level, header = header, children = {} }
    local parent = ancestors[#ancestors]
    -- Skipped levels need no placeholder entries. Without an included
    -- ancestor, this heading starts a top-level entry.
    if parent then
        table.insert(parent.children, entry)
    else
        table.insert(collected, entry)
    end
    table.insert(ancestors, entry)
end

-- Walk headers in document order, selecting descendants of start_id (or all
-- headers for an empty start_id). Stop at the selected section's boundary;
-- add_header_to_toc applies min_level/max_level and builds the nested entries.
local function collect_headers(start_id, min_level, max_level, headers)
    -- Root TOC entries, each containing level, header, and children.
    local collected = {}
    -- Whether the scan has reached the requested section.
    local collecting = false
    -- Selected root's heading level; 0 means the whole document.
    local start_level = nil
    -- Stack of included headings whose sections are still open.
    local ancestors = {}
    if start_id == "" then
        -- an empty start_id means start from the beginning of the document
        collecting = true
        start_level = 0
    end
    for _, header in ipairs(headers) do
        if header.identifier == start_id then
            collecting = true
            start_level = header.level
        elseif collecting then
            if header.level <= start_level then
                -- A heading at the same or a shallower level ends this section.
                break
            end
            add_header_to_toc(header, min_level, max_level, collected, ancestors)
        end
    end
    return collected
end

local function create_sublist(header_infos)
    local items = pandoc.List()
    for _, header_info in ipairs(header_infos) do
        local header = header_info.header
        local text = pandoc.utils.stringify(header.content)
        if true then
            local section_number = header.attr.attributes['section-number']
            text = (section_number and section_number .. " " or "") .. text
        end
        local link = pandoc.Plain({pandoc.Link(text, "#" .. header.identifier),
            pandoc.LineBreak() })
        if FORMAT:match("latex") then
            link = pandoc.Plain({pandoc.Link(text, "#" .. header.identifier)})
        end
        items:insert(link)
        if #header_info.children > 0 then
            if FORMAT:match("latex") then
                items:insert(pandoc.RawBlock("latex", "\\begin{adjustwidth}{2em}{0pt}"))
            end
            items:insert(create_sublist(header_info.children))
            if FORMAT:match("latex") then
                items:insert(pandoc.RawBlock("latex", "\\end{adjustwidth}"))
            end
        end
    end
    return pandoc.Div(items, {class = "toc-list"})
end

function Div(el)
    local attrs = el.attributes
    if attrs["toc-list-top-level"] and attrs["toc-list-entry-levels"] then
        -- check if there's a toc-list-only-format attribute
        --io.stderr:write("Processing toc-list div with attributes:\n")
        --for k,v in pairs(attrs) do
        --    io.stderr:write("  " .. k .. " = " .. v .. "\n")
        --end
        if attrs["toc-list-only-formats"] then
            --io.stderr:write("toc-list-only-formats attribute found: " .. attrs["toc-list-only-formats"] .. "\n")
            local only_formats = attrs["toc-list-only-formats"]
            local format_found = false
            -- split by comma and check if current format is in the lists
            for fmt in string.gmatch(only_formats, '([^,]+)') do
                fmt = fmt:match("^%s*(.-)%s*$") -- trim whitespace
                --io.stderr:write("Checking format: " .. fmt .. "\n")
                --io.stderr:write("Current FORMAT: " .. FORMAT .. "\n")
                if FORMAT:match(fmt) then
                    format_found = true
                    --io.stderr:write("Found matching format: " .. fmt .. "\n")
                    break
                end
            end
            if not format_found then
                return el
            end
        end
        local start_id = attrs["toc-list-top-level"]:gsub("^#", "")
        local min_level, max_level = parse_level_range(attrs["toc-list-entry-levels"])
        if not (min_level and max_level) then
            io.stderr:write("Error: Invalid toc-list-entry-levels format. Use min-max (e.g., 2-3).\n")
            return el
        end
        if min_level < 1 or max_level > 6 or min_level > max_level then
            io.stderr:write("Error: toc-list-entry-levels must be between 1 and 6, and min must be <= max.\n")
            return el
        end
        -- Collect all headers in the document
        local collected_headers = collect_headers(start_id, min_level, max_level, all_headers)
        --logging.error("Collected headers for TOC: ", collected_headers)
        if #collected_headers == 0 then
            io.stderr:write(string.format("Warning: No headers found under id '%s' with levels %d to %d.\n", start_id, min_level, max_level))
            return {}
        end
        return create_sublist(collected_headers)
    end
    return el
end

return {
  { traverse = 'topdown',
    Header = record_headers,
  },
  { Div = Div } };
