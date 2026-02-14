from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REQUIRED_ASSERT_HELPER = "assert_contract"
_REQUIRED_INPUT_HELPERS = {"load_input"}
_REQUIRED_EXPECTED_HELPERS = {"load_expected", "load_expected_text"}


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list[pytest.Item]) -> None:
    del session, config
    parsed_files: dict[Path, ast.Module] = {}
    violations: list[str] = []

    for item in items:
        if item.get_closest_marker("contract") is None:
            continue

        path = Path(str(item.fspath))
        tree = parsed_files.get(path)
        if tree is None:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            parsed_files[path] = tree

        test_name = getattr(item, "originalname", None) or item.name.split("[", maxsplit=1)[0]
        test_fn = _find_test_function(tree, test_name)
        if test_fn is None:
            violations.append(
                f"{path}::{item.name} - unable to inspect function body; ensure it calls "
                "fixture helpers and assert_contract."
            )
            continue

        calls = _collect_call_names(test_fn)
        missing = _missing_helpers(calls)
        if missing:
            violations.append(
                f"{path}::{test_name} - missing required helper calls: {', '.join(missing)}. "
                "Contract tests must load fixtures via load_input/load_expected (or load_expected_text) "
                "and compare via assert_contract."
            )

    if violations:
        raise pytest.UsageError("Contract format validation failed:\n- " + "\n- ".join(violations))


def _find_test_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _collect_call_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            names.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            names.add(child.func.attr)
    return names


def _missing_helpers(calls: set[str]) -> list[str]:
    missing: list[str] = []
    if _REQUIRED_ASSERT_HELPER not in calls:
        missing.append(_REQUIRED_ASSERT_HELPER)
    if not (_REQUIRED_INPUT_HELPERS & calls):
        missing.append("load_input")
    if not (_REQUIRED_EXPECTED_HELPERS & calls):
        missing.append("load_expected|load_expected_text")
    return missing
