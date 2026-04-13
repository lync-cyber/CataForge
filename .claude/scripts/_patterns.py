#!/usr/bin/env python3
"""CataForge Shared Regex Patterns for document and reference parsing.

Single source of truth for patterns used across:
- load_section.py (section extraction)
- build_doc_index.py (index construction)

Avoids defining identical regex in multiple modules.
"""

import re

# Markdown heading: "## 1. Title" -> (level_hashes, title_text)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# Item ID: F-001, API-001, M-003, E-012, T-042, C-007, P-001, AC-015
ITEM_ID_RE = re.compile(r"^[A-Z]+-\d+$")

# Section path: pure numeric or dot-separated (1, 1.1, 2.3.4)
SECTION_PATH_RE = re.compile(r"^\d+(?:\.\d+)*$")

# Document reference: doc_id#§<section>[.<item>]
REF_RE = re.compile(r"^(?P<doc_id>[a-z][a-z0-9\-]*)#§(?P<section>.+)$")

# Section number extraction
SECTION_NUM_RE = re.compile(r"^(\d+)(?:\.|\s|$)")
SUBSECTION_NUM_RE = re.compile(r"^(\d+\.\d+)(?:\.|\s|$)")
