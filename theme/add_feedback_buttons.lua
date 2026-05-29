-- SPDX-FileCopyrightText: <text>Copyright 2025-2026 Arm Limited and/or its
-- affiliates <open-source-office@arm.com></text>
-- SPDX-License-Identifier: MIT

-- This lua script adds feedback buttons next to every section header
-- in both HTML and LaTeX output formats.
-- The buttons link to a an email address.
-- local logging = require 'theme/html/logging'

local title = ""
local contact_email = ""
local version = ""

-- URL-encode a string
function urlencode(str)
    if (str) then
        -- Convert line breaks
        str = str:gsub("\n", "\r\n")
        -- Encode non-alphanumeric characters
        str = str:gsub("([^%w%-_%.%~])",
            function(c) return string.format("%%%02X", string.byte(c)) end)
    end
    return str
end

function latex_escape(str)
    if (str) then
        str = str:gsub("([%%&$#_{}])", "\\%1") -- Escape special LaTeX characters
        str = str:gsub("\n", " ") -- Replace newlines with spaces
    end
    return str
end

function construct_email_url(contact_email, title, version, section)
    local subject = urlencode(string.format(
        "[Feedback] %s v%s - Section: %s", title, version, section))
    local body = urlencode(string.format(
        "Hi,\n\nI have some feedback regarding the section '%s' in '%s' v%s.\n\n",
        section, title, version))
    return string.format("mailto:%s?subject=%s&body=%s",
        contact_email, subject, body)
end

function Header(el)
    -- only add the button to level 1 or level 2 headers
    if el.level > 2 then
        return el
    end
    local email_url = construct_email_url(contact_email, title, version,
        pandoc.utils.stringify(el.content))
    local link = pandoc.Link("[give feedback]", email_url)
    if FORMAT:match 'latex' then
        link = pandoc.RawInline('latex',
            string.format("\\href{%s}{\\scriptsize\\texttt{[Give Feedback]}}", latex_escape(email_url)))
    end
    table.insert(el.content,
        pandoc.Span({pandoc.Space(), link}, { class = "feedback-button" }));
    return el;
end

local function warn_missing_metadata(field)
    io.stderr:write(string.format(
        "Warning: '%s' metadata field is missing.\n",
        field))
end

return {
    { Meta = function(meta)
            if not meta["contact-email"] then
                warn_missing_metadata("contact-email")
            end
            contact_email = pandoc.utils.stringify(meta["contact-email"])
            if not meta["title"] then
                warn_missing_metadata("title")
            end
            title = pandoc.utils.stringify(meta["title"])
            if not meta["VERSION"] then
                warn_missing_metadata("VERSION")
            end
            version = pandoc.utils.stringify(meta["VERSION"])
    end },
    { Header = Header }
}