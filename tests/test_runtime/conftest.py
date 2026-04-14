"""Test fixtures for runtime tests."""
import sys
from pathlib import Path

CATAFORGE_DIR = Path(__file__).resolve().parents[2] / ".cataforge"
sys.path.insert(0, str(CATAFORGE_DIR))
