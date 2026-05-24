"""``cataforge kg adapter-migrate`` — batch frontmatter rewrite contract.

Covers:
* idempotency (re-run is a no-op)
* dry-run never writes
* schemas land at the right path, only once (force does not overwrite)
* malformed frontmatter raises AdapterMigrationError
* unknown adapter name in plan raises at validation time
* CLI surface produces the expected report text
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.kg.adapter_migrate import (
    AdapterMigrationError,
    TargetAssignment,
    _split_frontmatter,
    default_plan,
    migrate_adapters,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_with_pm_agent(tmp_path: Path) -> Path:
    target = tmp_path / ".cataforge" / "agents" / "product-manager" / "AGENT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent("""\
        ---
        name: product-manager
        description: 产品经理
        skills: [doc-gen, req-analysis]
        ---

        # Role
        Body content.
        """), encoding="utf-8")
    return tmp_path


# ---------- happy path ----------

def test_first_run_writes_block_and_schema(
    project_with_pm_agent: Path,
) -> None:
    report = migrate_adapters(project_with_pm_agent)
    # The PM agent's frontmatter got a kg_adapter block.
    fm_path = (
        project_with_pm_agent
        / ".cataforge/agents/product-manager/AGENT.md"
    )
    assert fm_path in report.frontmatter_written
    raw = fm_path.read_text(encoding="utf-8")
    assert "kg_adapter:" in raw
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["kg_adapter"]["name"] == "feature_authoring"
    assert (
        "write_back_schema"
        in fm["kg_adapter"]["config"]
    )

    # The schema landed on disk.
    schema_path = (
        project_with_pm_agent
        / ".cataforge/skills/doc-gen/schemas/feature.schema.json"
    )
    assert schema_path in report.schemas_written
    assert schema_path.is_file()
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    assert payload["items"][0]["type"] == "cfa:Feature"


# ---------- idempotency ----------

def test_second_run_is_a_no_op(project_with_pm_agent: Path) -> None:
    migrate_adapters(project_with_pm_agent)
    second = migrate_adapters(project_with_pm_agent)
    # Frontmatter should be marked as skipped (block already matches).
    fm_path = (
        project_with_pm_agent
        / ".cataforge/agents/product-manager/AGENT.md"
    )
    assert fm_path in second.frontmatter_skipped
    assert fm_path not in second.frontmatter_written


# ---------- dry-run ----------

def test_dry_run_does_not_touch_files(project_with_pm_agent: Path) -> None:
    fm_path = (
        project_with_pm_agent
        / ".cataforge/agents/product-manager/AGENT.md"
    )
    original = fm_path.read_text(encoding="utf-8")
    report = migrate_adapters(project_with_pm_agent, dry_run=True)
    # Report still flags the would-write entries.
    assert fm_path in report.frontmatter_written
    # File contents unchanged.
    assert fm_path.read_text(encoding="utf-8") == original


# ---------- skip user-customised block ----------

def test_existing_block_is_preserved_without_force(
    project_with_pm_agent: Path,
) -> None:
    fm_path = (
        project_with_pm_agent
        / ".cataforge/agents/product-manager/AGENT.md"
    )
    # Inject a hand-tweaked block first.
    fm_path.write_text(textwrap.dedent("""\
        ---
        name: product-manager
        kg_adapter:
          name: doc_read
          config:
            pre_dispatch_queries:
              user_specific: "SELECT ?x WHERE { ?x ?p ?o } ORDER BY ?x"
        ---
        Body.
        """), encoding="utf-8")
    report = migrate_adapters(project_with_pm_agent)
    assert fm_path in report.frontmatter_skipped
    raw = fm_path.read_text(encoding="utf-8")
    assert "user_specific" in raw  # preserved


def test_force_overwrites_existing_block(
    project_with_pm_agent: Path,
) -> None:
    fm_path = (
        project_with_pm_agent
        / ".cataforge/agents/product-manager/AGENT.md"
    )
    fm_path.write_text(textwrap.dedent("""\
        ---
        name: product-manager
        kg_adapter:
          name: doc_read
          config: {}
        ---
        Body.
        """), encoding="utf-8")
    report = migrate_adapters(project_with_pm_agent, force=True)
    assert fm_path in report.frontmatter_written
    raw = fm_path.read_text(encoding="utf-8")
    assert "feature_authoring" in raw


# ---------- schema preservation ----------

def test_schema_not_overwritten_on_rerun(project_with_pm_agent: Path) -> None:
    migrate_adapters(project_with_pm_agent)
    schema_path = (
        project_with_pm_agent
        / ".cataforge/skills/doc-gen/schemas/feature.schema.json"
    )
    schema_path.write_text(
        json.dumps({"custom": "user-edit"}), encoding="utf-8",
    )
    report = migrate_adapters(project_with_pm_agent)
    assert schema_path in report.schemas_skipped
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    assert payload == {"custom": "user-edit"}


# ---------- missing targets ----------

def test_missing_targets_reported_not_fatal(tmp_path: Path) -> None:
    # No agents / skills under tmp_path → every target missing, no crash.
    report = migrate_adapters(tmp_path)
    assert report.frontmatter_written == []
    assert len(report.targets_missing) == len(default_plan())


# ---------- CRLF frontmatter ----------

def test_split_frontmatter_crlf_body_intact() -> None:
    crlf_doc = "---\r\ntitle: test\r\n---\r\nbody content here"
    _, _, body = _split_frontmatter(crlf_doc)
    assert body == "body content here", (
        "body must not include a leading \\r from the CRLF closing delimiter"
    )


def test_split_frontmatter_lf_body_intact() -> None:
    lf_doc = "---\ntitle: test\n---\nbody content here"
    _, _, body = _split_frontmatter(lf_doc)
    assert body == "body content here"


# ---------- bad input ----------

def test_malformed_frontmatter_raises(tmp_path: Path) -> None:
    fm_path = tmp_path / ".cataforge/agents/product-manager/AGENT.md"
    fm_path.parent.mkdir(parents=True, exist_ok=True)
    fm_path.write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(AdapterMigrationError):
        migrate_adapters(tmp_path)


def test_unknown_adapter_in_custom_plan_raises(tmp_path: Path) -> None:
    fm_path = tmp_path / ".cataforge/agents/dummy/AGENT.md"
    fm_path.parent.mkdir(parents=True, exist_ok=True)
    fm_path.write_text("---\nname: dummy\n---\nBody.\n", encoding="utf-8")
    bad_plan = [TargetAssignment(
        target=".cataforge/agents/dummy/AGENT.md",
        adapter="does-not-exist",
        config={},
    )]
    from cataforge.kg.adapters import AdapterError

    with pytest.raises(AdapterError):  # raised by adapters.get(...)
        migrate_adapters(tmp_path, plan=bad_plan)


# ---------- CLI surface ----------

def test_cli_adapter_migrate_dry_run(
    runner: CliRunner, project_with_pm_agent: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "adapter-migrate",
        "--project-root", str(project_with_pm_agent),
        "--dry-run",
    ])
    assert result.exit_code == 0, result.output
    assert "frontmatter written" in result.output
    # File untouched after dry-run.
    fm = (
        project_with_pm_agent
        / ".cataforge/agents/product-manager/AGENT.md"
    ).read_text(encoding="utf-8")
    assert "kg_adapter:" not in fm


def test_cli_adapter_migrate_applies_changes(
    runner: CliRunner, project_with_pm_agent: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "adapter-migrate",
        "--project-root", str(project_with_pm_agent),
    ])
    assert result.exit_code == 0, result.output
    fm = (
        project_with_pm_agent
        / ".cataforge/agents/product-manager/AGENT.md"
    ).read_text(encoding="utf-8")
    assert "kg_adapter:" in fm
    assert "feature_authoring" in fm
