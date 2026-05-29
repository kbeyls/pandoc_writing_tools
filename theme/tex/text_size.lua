-- SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
-- affiliates <open-source-office@arm.com></text>
-- SPDX-License-Identifier: MIT

-- This lua pandoc filter converts divs with class "small" to LaTeX \small{}
-- local logging = require 'theme/html/logging'

function Div(div)
  if div.classes[1] == "small" then
    if FORMAT:match 'latex' then
      return {
        pandoc.RawInline('latex', '\\begin{small}'),
        div,
        pandoc.RawInline('latex', '\\end{small}'),
      }
    end
  end
  return div
end