"""Shared test fixtures and utilities."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with minimal SKILL.md stubs for testing."""
    skills = {
        "search.md": (
            "# search\n"
            "Description: Search for information on a given topic.\n\n"
            "## Instructions\n"
            "Return factual information about the query.\n"
        ),
        "analyze.md": (
            "# analyze\n"
            "Description: Analyze and interpret a piece of information or data.\n\n"
            "## Instructions\n"
            "Provide a detailed analysis of the input.\n"
        ),
        "synthesize.md": (
            "# synthesize\n"
            "Description: Combine multiple pieces of information into a coherent answer.\n\n"
            "## Instructions\n"
            "Synthesize the provided information into a final answer.\n"
        ),
    }
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    for name, content in skills.items():
        (skill_dir / name).write_text(content, encoding="utf-8")
    return skill_dir


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    """Temporary JSONL log file path."""
    return tmp_path / "session.jsonl"
