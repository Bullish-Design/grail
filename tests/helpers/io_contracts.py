"""Helpers for visible fixture-driven contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INPUTS_DIR = ROOT / "fixtures" / "inputs"
EXPECTED_DIR = ROOT / "fixtures" / "expected"
ACTUAL_DIR = ROOT / ".artifacts" / "actual"


def load_input(name: str) -> dict[str, Any]:
    return _load_json(INPUTS_DIR / f"{name}.json")


def load_expected(name: str) -> dict[str, Any]:
    return _load_json(EXPECTED_DIR / f"{name}.json")


def assert_contract(name: str, *, expected: Any, actual: Any, context: dict[str, Any]) -> None:
    if expected == actual:
        return

    ACTUAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = ACTUAL_DIR / f"{name}.json"
    actual_path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    raise AssertionError(
        "\n".join(
            [
                f"Contract mismatch for '{name}'",
                f"Context: {json.dumps(context, indent=2, sort_keys=True)}",
                (
                    f"Expected ({EXPECTED_DIR / f'{name}.json'}): "
                    f"{json.dumps(expected, indent=2, sort_keys=True)}"
                ),
                f"Actual ({actual_path}): {json.dumps(actual, indent=2, sort_keys=True)}",
            ]
        )
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
