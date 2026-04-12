"""upgrade.py 公共工具函数测试"""

import json
import os
import sys
import warnings

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts"))
from upgrade import (
    load_json_lenient,
    parse_semver,
    phase_index,
    read_version,
    validate_branch_name,
)


# ── parse_semver ─────────────────────────────────────────────────────────


class TestParseSemver:
    def test_normal(self):
        assert parse_semver("1.2.3") == (1, 2, 3)

    def test_with_v_prefix(self):
        assert parse_semver("v1.2.3") == (1, 2, 3)

    def test_with_extra(self):
        assert parse_semver("1.2.3-beta.1") == (1, 2, 3)

    def test_zero(self):
        assert parse_semver("0.0.0") == (0, 0, 0)

    def test_large(self):
        assert parse_semver("99.88.77") == (99, 88, 77)

    def test_invalid(self):
        with pytest.warns(UserWarning, match="无法解析版本号"):
            assert parse_semver("not-a-version") == (0, 0, 0)

    def test_empty(self):
        with pytest.warns(UserWarning, match="无法解析版本号"):
            assert parse_semver("") == (0, 0, 0)

    def test_whitespace(self):
        assert parse_semver("  1.2.3  ") == (1, 2, 3)

    def test_comparison(self):
        assert parse_semver("0.2.0") > parse_semver("0.1.0")
        assert parse_semver("1.0.0") > parse_semver("0.99.99")


# ── read_version ─────────────────────────────────────────────────────────


class TestReadVersion:
    def test_normal(self, tmp_path):
        toml = tmp_path / "pyproject.toml"
        toml.write_text('[project]\nname = "test"\nversion = "1.2.3"\n')
        assert read_version(str(tmp_path)) == "1.2.3"

    def test_missing_file(self, tmp_path):
        assert read_version(str(tmp_path)) == "0.0.0"

    def test_no_version_field(self, tmp_path):
        toml = tmp_path / "pyproject.toml"
        toml.write_text('[project]\nname = "test"\n')
        assert read_version(str(tmp_path)) == "0.0.0"


# ── load_json_lenient ────────────────────────────────────────────────────


class TestLoadJsonLenient:
    def test_normal(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text('{"a": 1, "b": 2}')
        assert load_json_lenient(str(f)) == {"a": 1, "b": 2}

    def test_trailing_comma_object(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text('{"a": 1, "b": 2,}')
        assert load_json_lenient(str(f)) == {"a": 1, "b": 2}

    def test_trailing_comma_array(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text('{"list": [1, 2, 3,]}')
        result = load_json_lenient(str(f))
        assert result["list"] == [1, 2, 3]

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            load_json_lenient(str(f))


# ── phase_index ──────────────────────────────────────────────────────────


class TestPhaseIndex:
    @pytest.mark.parametrize(
        "phase,expected",
        [
            ("requirements", 0),
            ("architecture", 1),
            ("development", 4),
            ("completed", 7),
        ],
    )
    def test_known_phases(self, phase, expected):
        assert phase_index(phase) == expected

    def test_unknown_phase(self):
        assert phase_index("unknown") == -1


# ── validate_branch_name ────────────────────────────────────────────────


class TestValidateBranchName:
    @pytest.mark.parametrize(
        "name",
        ["main", "develop", "feature/my-branch", "release/v1.0", "fix_123"],
    )
    def test_valid(self, name):
        assert validate_branch_name(name) is True

    @pytest.mark.parametrize(
        "name",
        ["branch with space", "branch;injection", "branch&&cmd", ""],
    )
    def test_invalid(self, name):
        assert validate_branch_name(name) is False
