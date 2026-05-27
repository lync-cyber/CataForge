"""Build the Jinja2 Environment used by the exporter.

`StrictUndefined` is the idempotency safety net: referencing an undefined
variable in any template — including a phantom `{{ generated_at }}` —
raises immediately rather than silently rendering as an empty string.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_BUILTIN_TEMPLATE_DIR = Path(__file__).parent / "templates"


def build_jinja_env(builtin_dir: Path = _BUILTIN_TEMPLATE_DIR) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(builtin_dir)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return env
