"""Static contract: suite-performance discipline reaches every test-writing context."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / ".cataforge" / "references" / "test-suite-performance.md"
TDD_ENGINE = ROOT / ".cataforge" / "skills" / "tdd-engine" / "SKILL.md"
TEST_WRITER = ROOT / ".cataforge" / "agents" / "test-writer" / "AGENT.md"
TESTING_SKILL = ROOT / ".cataforge" / "skills" / "testing" / "SKILL.md"
ARCH_TEMPLATE = ROOT / ".cataforge" / "skills" / "context" / "templates" / "standard" / "arch.md"
QA_ENGINEER = ROOT / ".cataforge" / "agents" / "qa-engineer" / "AGENT.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_terms(text: str, *terms: str) -> None:
    missing = [term for term in terms if term not in text]
    assert not missing, f"suite-performance contract missing: {missing}"


def test_shared_reference_carries_four_disciplines() -> None:
    text = _read(REFERENCE)
    _assert_terms(
        text,
        "## 1. 慢测标签分层",
        "## 2. 昂贵确定 setup 跨用例复用",
        "## 3. 进程内优先",
        "## 4. 并行就绪",
    )


def test_discipline_reaches_all_test_writing_contexts() -> None:
    tdd = _read(TDD_ENGINE)
    # RED dispatch + light-dispatch prompts each inject the discipline section;
    # light-inline loads the reference in its context list.
    assert tdd.count("## suite_discipline") == 2
    assert tdd.count("test-suite-performance.md") >= 3

    writer = _read(TEST_WRITER)
    _assert_terms(writer, "五维度自检", "### 5. 套件性能", "test-suite-performance.md")

    testing = _read(TESTING_SKILL)
    _assert_terms(testing, "test-suite-performance.md")
    assert "分层标签隔离慢测" not in testing, "纪律正文应收敛到共享 reference，不留双份"


def test_two_tier_test_command_contract() -> None:
    arch = _read(ARCH_TEMPLATE)
    _assert_terms(
        arch, "### 7.4 测试执行口径", "慢测标签约定", "test_command_fast", "test_command_full"
    )

    tdd = _read(TDD_ENGINE)
    _assert_terms(tdd, "test_command_fast", "test_command_full", "收敛点门禁")
    assert tdd.count("test_command_full") >= 3, "三处收敛点验证均应用 full 档"

    _assert_terms(_read(QA_ENGINEER), "test_command_full")


def test_scan_carries_test_hygiene_probe() -> None:
    skill = _read(ROOT / ".cataforge" / "skills" / "code-review" / "SKILL.md")
    _assert_terms(skill, "test_hygiene", "无标签慢测候选", "test-hygiene-{lang}.yaml")

    from cataforge.runtime.skill.builtins.code_review import CHECKS_MANIFEST

    entry = next(e for e in CHECKS_MANIFEST if e["id"] == "code_review.test_hygiene")
    assert entry["severity"] == "informational"
    assert entry["modes"] == "scan"
