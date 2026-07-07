"""Vendored viz asset provenance: pinned versions, URLs, and content hashes.

Default run verifies every pinned asset under
``src/cataforge/application/viz/assets/`` matches its recorded sha256, and —
when a ``node`` executable is available — syntax-checks the first-party
``dashboard.js``. ``--refresh`` re-downloads the pinned versions and verifies
them against the same hashes; bumping a library means editing its ``Pin``
(version / url / sha256) first, so every vendored byte stays traceable to a
public release.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ASSETS_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "cataforge" / "application" / "viz" / "assets"
)


@dataclass(frozen=True)
class Pin:
    name: str
    version: str
    url: str
    sha256: str


PINS: tuple[Pin, ...] = (
    Pin(
        name="cytoscape.min.js",
        version="3.30.2",
        url="https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js",
        sha256="83e8c54a6bec655bfd81df07df605649c268af69aeca67a5ea2da54ea42dac81",
    ),
    Pin(
        name="echarts.min.js",
        version="5.6.0",
        url="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js",
        sha256="e84270bd0cd5bdf60fefc26d00c2a391cb2e81f4d26a7a9ee16185a54773a3cf",
    ),
)

# First-party assets: not hash-pinned (they evolve with the repo), but syntax-
# smoked so a broken edit fails here instead of inside every rendered page.
FIRST_PARTY_JS: tuple[str, ...] = ("dashboard.js",)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_pins() -> list[str]:
    errors: list[str] = []
    for pin in PINS:
        path = ASSETS_DIR / pin.name
        if not path.is_file():
            errors.append(f"{pin.name}: missing from {ASSETS_DIR}")
            continue
        actual = _sha256(path)
        if actual != pin.sha256:
            errors.append(
                f"{pin.name}: sha256 mismatch — pinned {pin.sha256[:12]}…, actual {actual[:12]}…"
            )
    return errors


def _check_first_party_syntax() -> list[str]:
    node = shutil.which("node")
    if node is None:
        print("node not found — skipping dashboard.js syntax check", file=sys.stderr)
        return []
    errors: list[str] = []
    for name in FIRST_PARTY_JS:
        path = ASSETS_DIR / name
        if not path.is_file():
            errors.append(f"{name}: missing from {ASSETS_DIR}")
            continue
        proc = subprocess.run(
            [node, "--check", str(path)], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            errors.append(f"{name}: node --check failed\n{proc.stderr.strip()}")
    return errors


def _refresh() -> list[str]:
    errors: list[str] = []
    for pin in PINS:
        print(f"downloading {pin.name} {pin.version} …")
        with urllib.request.urlopen(pin.url, timeout=60) as resp:  # noqa: S310 — pinned https URL
            content = resp.read()
        actual = hashlib.sha256(content).hexdigest()
        if actual != pin.sha256:
            errors.append(
                f"{pin.name}: downloaded sha256 {actual[:12]}… does not match pin "
                f"{pin.sha256[:12]}… — refusing to write"
            )
            continue
        (ASSETS_DIR / pin.name).write_bytes(content)
        print(f"wrote {pin.name} ({len(content)} bytes)")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-download the pinned versions (hash-verified) instead of only checking",
    )
    args = parser.parse_args(argv)

    errors = _refresh() if args.refresh else _check_pins()
    errors.extend(_check_first_party_syntax())
    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    if not errors:
        mode = "refreshed" if args.refresh else "verified"
        print(f"viz assets {mode}: {', '.join(p.name for p in PINS)} + {', '.join(FIRST_PARTY_JS)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
