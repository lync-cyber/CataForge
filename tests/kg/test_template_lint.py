"""Per-rule pass/fail coverage for the template-lint static checker.

The CLI smoke test in :mod:`tests/kg/test_cli.py` only exercises the
clean-templates happy path; this module pins each rule's positive and
negative cases."""

from __future__ import annotations

from pathlib import Path

from cataforge.kg.template_lint import (
    RULE_DEPRECATED_PLACEHOLDER,
    RULE_JINJA_SYNTAX_VALID,
    RULE_SPARQL_REQUIRES_ORDER_BY,
    Finding,
    lint_template,
    lint_template_roots,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ---------- JINJA01 ----------

def test_jinja_syntax_error_caught(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "bad.md.j2",
        "{% for x in xs %}{# missing endfor",
    )
    findings = lint_template(p)
    assert any(f.rule_id == RULE_JINJA_SYNTAX_VALID for f in findings)


def test_jinja_syntax_clean_passes_to_downstream(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "clean.md.j2",
        "{{ kg.query('SELECT ?x WHERE { ?x ?p ?o } ORDER BY ?x') | length }}",
    )
    findings = lint_template(p)
    # Clean JINJA → downstream rules also fire (and pass).
    assert not any(f.rule_id == RULE_JINJA_SYNTAX_VALID for f in findings)
    assert findings == []


def test_jinja_failure_short_circuits_downstream(tmp_path: Path) -> None:
    """If Jinja syntax fails we shouldn't surface noisy SPARQL findings on
    text the parser couldn't make sense of."""
    p = _write(
        tmp_path / "bad.md.j2",
        "{% for x in xs %}\n{{ kg.query('SELECT ?x WHERE { ?x ?p ?o }') }}",
        # no endfor, no ORDER BY — only the syntax error should appear
    )
    findings = lint_template(p)
    assert len(findings) == 1
    assert findings[0].rule_id == RULE_JINJA_SYNTAX_VALID


# ---------- SPARQL01 ----------

def test_sparql_missing_order_by_flagged(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "noorder.md.j2",
        "{{ kg.query('SELECT ?id WHERE { ?x cfk:hasId ?id }') }}",
    )
    findings = lint_template(p)
    rule_ids = [f.rule_id for f in findings]
    assert RULE_SPARQL_REQUIRES_ORDER_BY in rule_ids


def test_sparql_with_order_by_clean(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "ordered.md.j2",
        "{{ kg.query('SELECT ?id WHERE { ?x cfk:hasId ?id } ORDER BY ?id') }}",
    )
    findings = lint_template(p)
    assert all(
        f.rule_id != RULE_SPARQL_REQUIRES_ORDER_BY for f in findings
    )


def test_sparql_ask_query_exempt_from_order_by(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "ask.md.j2",
        "{{ kg.query('ASK { ?x ?p ?o }') }}",
    )
    findings = lint_template(p)
    assert all(
        f.rule_id != RULE_SPARQL_REQUIRES_ORDER_BY for f in findings
    )


def test_sparql_function_alias_also_checked(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "sparql_alias.md.j2",
        "{{ sparql('SELECT ?x WHERE { ?x ?p ?o }') }}",
    )
    findings = lint_template(p)
    assert any(
        f.rule_id == RULE_SPARQL_REQUIRES_ORDER_BY for f in findings
    )


# ---------- TPL01 ----------

def test_deprecated_project_placeholder_flagged(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "old.md.j2",
        "# PRD: {project}\n",
    )
    findings = lint_template(p)
    assert any(
        f.rule_id == RULE_DEPRECATED_PLACEHOLDER for f in findings
    )


def test_deprecated_ver_placeholder_flagged(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "old2.md.j2",
        "version: {ver}\n",
    )
    findings = lint_template(p)
    assert any(
        f.rule_id == RULE_DEPRECATED_PLACEHOLDER for f in findings
    )


def test_jinja_curly_curly_not_flagged_as_deprecated(tmp_path: Path) -> None:
    # Jinja's own {{ var }} must NOT trigger TPL01.
    p = _write(
        tmp_path / "jinja.md.j2",
        "id: {{ project }}\nversion: {{ ver }}\n",
    )
    findings = lint_template(p)
    assert all(
        f.rule_id != RULE_DEPRECATED_PLACEHOLDER for f in findings
    )


# ---------- multi-root lint sweep ----------

def test_lint_template_roots_aggregates_findings(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    _write(root_a / "x.md.j2", "{{ '{project}' }}")  # deprecated placeholder
    _write(
        root_b / "y.md.j2",
        "{{ kg.query('SELECT ?x WHERE { ?x ?p ?o }') }}",  # no ORDER BY
    )
    findings = lint_template_roots([root_a, root_b])
    rules = [f.rule_id for f in findings]
    assert RULE_DEPRECATED_PLACEHOLDER in rules
    assert RULE_SPARQL_REQUIRES_ORDER_BY in rules


def test_lint_finding_carries_file_and_line(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "noorder.md.j2",
        "# header\n\n{{ kg.query('SELECT ?id WHERE { ?x cfk:hasId ?id }') }}",
    )
    findings = lint_template(p)
    f: Finding = next(
        f for f in findings if f.rule_id == RULE_SPARQL_REQUIRES_ORDER_BY
    )
    assert f.path == p
    assert f.line == 3  # third line of the file
