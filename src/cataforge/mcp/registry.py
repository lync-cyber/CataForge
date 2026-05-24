"""MCP unified registry — declarative registration and discovery.

Supports three registration methods (priority descending):
1. Declarative: .cataforge/mcp/*.yaml spec files
2. Convention: pyproject.toml entry_points "cataforge.mcp"
3. Programmatic: registry.register(MCPServerSpec(...))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.schema.mcp_spec import TRUSTED_COMMAND_PREFIXES, MCPServerSpec, MCPServerState

logger = logging.getLogger("cataforge.mcp")


class MCPRegistry:
    """Central MCP server registry."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._servers: dict[str, MCPServerSpec] = {}
        self._states: dict[str, MCPServerState] = {}
        self._scan_declarative()
        self._scan_entry_points()

    def _scan_declarative(self) -> None:
        """Scan .cataforge/mcp/ for YAML server specs."""
        mcp_dir = self._paths.mcp_dir
        if not mcp_dir.is_dir():
            return

        for yaml_file in sorted(mcp_dir.glob("*.yaml")):
            try:
                spec = self._parse_spec_file(yaml_file)
                self._servers[spec.id] = spec
                self._states[spec.id] = MCPServerState(spec_id=spec.id)
            except Exception as e:
                logger.warning("Skipping invalid MCP spec %s: %s", yaml_file.name, e)

    def _scan_entry_points(self) -> None:
        """Scan pip-installed packages for cataforge.mcp entry points."""
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group="cataforge.mcp")
            for ep in eps:
                try:
                    factory = ep.load()
                    if callable(factory):
                        spec = factory()
                        if isinstance(spec, MCPServerSpec):
                            if not self._is_trusted_command(spec):
                                logger.warning(
                                    "Skipping MCP entry_point %s: untrusted command %r"
                                    " — first element must be in %s or a relative path",
                                    ep.name,
                                    spec.command,
                                    sorted(TRUSTED_COMMAND_PREFIXES),
                                )
                                continue
                            self._servers.setdefault(spec.id, spec)
                            self._states.setdefault(
                                spec.id, MCPServerState(spec_id=spec.id)
                            )
                except Exception as e:
                    logger.warning("Skipping MCP entry_point %s: %s", ep.name, e)
        except Exception as e:
            logger.debug("entry_points scan unavailable: %s", e)

    @staticmethod
    def _is_trusted_command(spec: MCPServerSpec) -> bool:
        """Return True if spec.command is safe to execute.

        Bare executable names must appear in TRUSTED_COMMAND_PREFIXES.
        Relative paths (containing a path separator, e.g. ``./scripts/run``)
        are accepted as project-local binaries. Absolute paths are rejected.
        """
        cmd = spec.command.strip()
        if not cmd:
            return True  # empty command will fail at start() — not a trust concern
        executable = cmd.split()[0] if " " in cmd else cmd
        if executable in TRUSTED_COMMAND_PREFIXES:
            return True
        from pathlib import PurePosixPath, PureWindowsPath
        if PurePosixPath(executable).is_absolute() or PureWindowsPath(executable).is_absolute():
            return False
        # Allow relative paths that contain a separator (e.g. ./bin/tool).
        return "/" in executable or "\\" in executable

    def _parse_spec_file(self, path: Path) -> MCPServerSpec:
        """Parse a YAML spec file into MCPServerSpec."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict) or "id" not in data:
            raise ValueError(f"Invalid MCP spec: missing 'id' in {path.name}")

        return MCPServerSpec.model_validate(data)

    def register(self, spec: MCPServerSpec) -> None:
        """Programmatically register an MCP server (in-memory only)."""
        self._servers[spec.id] = spec
        if spec.id not in self._states:
            self._states[spec.id] = MCPServerState(spec_id=spec.id)

    def register_from_file(
        self, path: str | Path, *, overwrite: bool = False
    ) -> MCPServerSpec:
        """Register a server from a YAML spec, persisting it to ``.cataforge/mcp/``.

        Without persistence the registration would only live in the current
        Python process; the next ``cataforge mcp start`` invocation (a
        separate process) would not see it. We therefore copy / normalize
        the spec into ``.cataforge/mcp/<id>.yaml`` so subsequent CLI runs
        discover it via :meth:`_scan_declarative`.

        If the source file is already at the canonical location, no copy
        happens. If a different file already lives at the target and
        ``overwrite=False``, raises ``FileExistsError``.
        """
        source = Path(path).resolve()
        spec = self._parse_spec_file(source)

        target_dir = self._paths.mcp_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = (target_dir / f"{spec.id}.yaml").resolve()

        if source != target:
            if target.exists() and not overwrite:
                raise FileExistsError(
                    f"MCP spec already registered at {target}; "
                    "pass overwrite=True (CLI: --force) to replace it."
                )
            target.write_bytes(source.read_bytes())

        self.register(spec)
        return spec

    def list_servers(self) -> list[MCPServerSpec]:
        return list(self._servers.values())

    def get_server(self, server_id: str) -> MCPServerSpec | None:
        return self._servers.get(server_id)

    def get_state(self, server_id: str) -> MCPServerState | None:
        return self._states.get(server_id)

    def get_platform_config(self, server_id: str, platform_id: str) -> dict[str, Any]:
        """Get the MCP config payload for a specific platform."""
        spec = self._servers.get(server_id)
        if spec is None:
            return {}

        base: dict[str, Any] = {
            "command": spec.command,
            "args": spec.args,
        }
        if spec.env:
            base["env"] = spec.env

        platform_override = spec.platform_config.get(platform_id, {})
        base.update(platform_override)
        return base
