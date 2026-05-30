"""Public dataclasses returned by `compile_to_markdown()`.

Kept deliberately small: only what the round-trip test and CLI table
renderer need.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class FileExportRecord:
    """One Markdown file written by the exporter."""

    entity_id: str
    entity_type: str
    output_path: Path
    sha256: str


@dataclass
class CompileResult:
    """Return value of `compile_to_markdown()`.

    `exported_at` exists for operational logging only and is NEVER
    written into any output file. `discovered_count` is every entity
    surfaced by the source scan; `len(file_records)` is the rendered
    subset — anything filtered or errored stays in `errors` and is not
    counted as rendered.
    """

    exported_at: datetime
    discovered_count: int
    output_dir: Path
    file_records: list[FileExportRecord] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)
    errors: list[tuple[str, str]] = field(default_factory=list)
