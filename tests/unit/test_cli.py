"""Test CLI commands."""

import pytest
from pathlib import Path
import tempfile
import os
import json
import subprocess
import sys

from grail.cli import cmd_init, cmd_check, cmd_clean, cmd_run
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


def test_run_parses_input_flag(tmp_path):
    """The --input flag should parse key=value pairs into a dict."""
    pym_file = tmp_path / "analysis.pym"
    pym_file.write_text("result = 1")

    output_file = tmp_path / "inputs.json"
    host_file = tmp_path / "host.py"
    host_file.write_text(
        """
import json
from pathlib import Path


def main(inputs=None):
    Path(r"{output_path}").write_text(json.dumps(inputs or {{}}))
""".format(output_path=str(output_file))
    )

    args = argparse.Namespace(
        file=str(pym_file),
        host=str(host_file),
        input=["budget=5000", "dept=engineering"],
    )

    result = cmd_run(args)

    assert result == 0
    assert json.loads(output_file.read_text()) == {
        "budget": "5000",
        "dept": "engineering",
    }


def test_run_rejects_invalid_input_format(tmp_path, capsys):
    """An --input value without '=' should produce an error."""
    pym_file = tmp_path / "analysis.pym"
    pym_file.write_text("result = 1")

    args = argparse.Namespace(
        file=str(pym_file),
        host=str(tmp_path / "host.py"),
        input=["invalid_no_equals"],
    )

    result = cmd_run(args)
    captured = capsys.readouterr()

    assert result == 1
    assert "Invalid input format" in captured.out


def test_run_input_flag_appears_in_help():
    """The --input flag should appear in the grail run help text."""
    result = subprocess.run(
        [sys.executable, "-m", "grail", "run", "--help"],
        capture_output=True,
        text=True,
    )

    assert "--input" in result.stdout
