"""共享 fixtures 和导入辅助"""

import os
import sys

import pytest

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 将脚本子目录加入 sys.path，使 import 可用
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, ".claude", "scripts")
SCRIPTS_LIB = os.path.join(SCRIPTS_DIR, "lib")
SCRIPTS_DOCS = os.path.join(SCRIPTS_DIR, "docs")
SCRIPTS_FRAMEWORK = os.path.join(SCRIPTS_DIR, "framework")
HOOKS_DIR = os.path.join(PROJECT_ROOT, ".claude", "hooks")
AGENTS_DIR = os.path.join(PROJECT_ROOT, ".claude", "agents")
SKILLS_DIR = os.path.join(PROJECT_ROOT, ".claude", "skills")

for d in (SCRIPTS_LIB, SCRIPTS_DOCS, SCRIPTS_FRAMEWORK, HOOKS_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)


@pytest.fixture
def project_root():
    """返回项目根目录路径"""
    return PROJECT_ROOT


@pytest.fixture
def agents_dir():
    return AGENTS_DIR


@pytest.fixture
def skills_dir():
    return SKILLS_DIR
