"""Helpers for visible fixture-driven contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "fixtures"
INPUTS_DIR = FIXTURES_DIR / "inputs"
EXPECTED_DIR = FIXTURES_DIR / "expected"
ACTUAL_DIR = ROOT / ".artifacts" / "actual"


def load_input(name: str) -> dict[str, Any]:
    return _load_json(INPUTS_DIR / f"{name}.json")


def load_expected(name: str, *, section: str | None = None) -> dict[str, Any]:
    base = EXPECTED_DIR if section is None else EXPECTED_DIR / section
    return _load_json(base / f"{name}.json")


def load_expected_text(name: str, *, section: str, suffix: str = ".pyi") -> str:
    path = EXPECTED_DIR / section / f"{name}{suffix}"
    return path.read_text(encoding="utf-8")


def assert_contract(
    fixture_id: str,
    *,
    expected: Any,
    actual: Any,
    input_payload: dict[str, Any],
) -> None:
    print(
        json.dumps(
            {
                "fixture_id": fixture_id,
                "input_payload": input_payload,
                "resolved_payload": actual,
            },
            indent=2,
            sort_keys=True,
        )
    )

    if expected == actual:
        return

    ACTUAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = ACTUAL_DIR / f"{fixture_id}.json"
    actual_path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    raise AssertionError(
        "\n".join(
            [
                f"Contract mismatch for '{fixture_id}'",
                f"Input payload: {json.dumps(input_payload, indent=2, sort_keys=True)}",
                (
                    f"Expected ({EXPECTED_DIR / f'{fixture_id}.json'}): "
                    f"{json.dumps(expected, indent=2, sort_keys=True)}"
                ),
                f"Actual ({actual_path}): {json.dumps(actual, indent=2, sort_keys=True)}",
            ]
        )
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
