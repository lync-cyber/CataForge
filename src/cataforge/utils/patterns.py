"""Shared regex patterns for Markdown document parsing.

Used by doc tools (``cataforge docs load`` / ``cataforge docs index`` /
doc-review checker) and skill scripts. Single source of truth — avoids
pattern duplication across modules.
"""

from __future__ import annotations

import re

# Matches any Markdown heading: group(1) = '#' characters, group(2) = title text
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)

# Matches structured item IDs like F-001, API-002, M-003, T-010, AC-005
ITEM_ID_RE = re.compile(r"^[A-Z]+-\d+$")

# Matches a valid doc_id / alias: word characters and hyphens only.
# Single source of truth for identifier validation in the indexer and the
# REF_RE doc_id capture group below — keep them aligned. Dots are rejected
# because they would collide with the section path separator in REF_RE.
DOC_ID_RE = re.compile(r"^[\w-]+$")

# Matches a doc reference: doc_id#§section[.item]
#   e.g. prd#§2, arch#§3.API-001, prd#§1.1
REF_RE = re.compile(r"^(?P<doc_id>[\w-]+)#§(?P<section>[\w.-]+)$")

# Matches a pure numeric section path: 1, 1.1, 1.1.1
SECTION_PATH_RE = re.compile(r"^\d+(?:\.\d+)*$")

# Matches a top-level section number at the start of a heading title: "1. Overview"
SECTION_NUM_RE = re.compile(r"^(\d+)")

# Matches a sub-section number at the start: "1.1 Background"
SUBSECTION_NUM_RE = re.compile(r"^(\d+\.\d+)")
