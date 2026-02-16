"""Test CLI commands."""

import pytest
from pathlib import Path
import tempfile
import os

from grail.cli import cmd_init, cmd_check, cmd_clean
import argparse


def test_cmd_init_creates_directory(tmp_path, monkeypatch):
    """Should create .grail/ directory."""
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace()
    cmd_init(args)

    assert (tmp_path / ".grail").exists()
    assert (tmp_path / "example.pym").exists()


def test_cmd_check_valid_file(tmp_path, monkeypatch):
    """Should check valid .pym file."""
    monkeypatch.chdir(tmp_path)

    # Create a valid .pym file
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""
from grail import external, Input

x: int = Input("x")

@external
async def double(n: int) -> int:
    ...

result = await double(x)
result
""")

    args = argparse.Namespace(files=["test.pym"], format="text", strict=False)
    result = cmd_check(args)

    assert result == 0


def test_cmd_clean_removes_directory(tmp_path, monkeypatch):
    """Should remove .grail/ directory."""
    monkeypatch.chdir(tmp_path)

    grail_dir = tmp_path / ".grail"
    grail_dir.mkdir()
    (grail_dir / "test.txt").write_text("test")

    args = argparse.Namespace()
    cmd_clean(args)

    assert not grail_dir.exists()
