# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 6: Checker - Validate Monty Compatibility

**Purpose**: Detect Python features that Monty doesn't support BEFORE runtime.

### Work to be done

Create `src/grail/checker.py`:

```python
"""Validation checker for Monty compatibility."""
import ast
from typing import Any

from grail._types import CheckMessage, CheckResult, ParseResult


class MontyCompatibilityChecker(ast.NodeVisitor):
    """
    AST visitor that detects Monty-incompatible Python features.

    Errors detected:
    - E001: Class definitions
    - E002: Generators (yield/yield from)
    - E003: with statements
    - E004: match statements
    - E005: Forbidden imports
    """

    def __init__(self, source_lines: list[str]):
        self.errors: list[CheckMessage] = []
        self.warnings: list[CheckMessage] = []
        self.source_lines = source_lines

        # Track what features are used (for info)
        self.features_used: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Detect class definitions (not supported in Monty)."""
        self.errors.append(CheckMessage(
            code="E001",
            lineno=node.lineno,
            col_offset=node.col_offset,
            end_lineno=node.end_lineno,
            end_col_offset=node.end_col_offset,
            severity="error",
            message="Class definitions are not supported in Monty",
            suggestion="Remove the class or refactor to use functions and dicts"
        ))
        self.generic_visit(node)

    def visit_Yield(self, node: ast.Yield) -> None:
        """Detect yield expressions (generators not supported)."""
        self.errors.append(CheckMessage(
            code="E002",
            lineno=node.lineno,
            col_offset=node.col_offset,
            end_lineno=node.end_lineno,
            end_col_offset=node.end_col_offset,
            severity="error",
            message="Generator functions (yield) are not supported in Monty",
            suggestion="Refactor to return a list or use async iteration"
        ))
        self.generic_visit(node)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        """Detect yield from expressions."""
        self.errors.append(CheckMessage(
            code="E002",
            lineno=node.lineno,
            col_offset=node.col_offset,
            end_lineno=node.end_lineno,
            end_col_offset=node.end_col_offset,
            severity="error",
            message="Generator functions (yield from) are not supported in Monty",
            suggestion="Refactor to return a list"
        ))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Detect with statements (not supported)."""
        self.errors.append(CheckMessage(
            code="E003",
            lineno=node.lineno,
            col_offset=node.col_offset,
            end_lineno=node.end_lineno,
            end_col_offset=node.end_col_offset,
            severity="error",
            message="'with' statements are not supported in Monty",
            suggestion="Use try/finally instead, or make file operations external functions"
        ))
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        """Detect match statements (not supported yet)."""
        self.errors.append(CheckMessage(
            code="E004",
            lineno=node.lineno,
            col_offset=node.col_offset,
            end_lineno=node.end_lineno,
            end_col_offset=node.end_col_offset,
            severity="error",
            message="'match' statements are not supported in Monty yet",
            suggestion="Use if/elif/else instead"
        ))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Detect import statements (only grail and typing allowed)."""
        for alias in node.names:
            if alias.name not in ["typing"]:
                self.errors.append(CheckMessage(
                    code="E005",
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                    end_lineno=node.end_lineno,
                    end_col_offset=node.end_col_offset,
                    severity="error",
                    message=f"Import '{alias.name}' is not allowed in Monty",
                    suggestion="Only 'from grail import ...' and 'from typing import ...' are allowed"
                ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Detect from...import statements."""
        if node.module not in ["grail", "typing"]:
            self.errors.append(CheckMessage(
                code="E005",
                lineno=node.lineno,
                col_offset=node.col_offset,
                end_lineno=node.end_lineno,
                end_col_offset=node.end_col_offset,
                severity="error",
                message=f"Import from '{node.module}' is not allowed in Monty",
                suggestion="Only 'from grail import ...' and 'from typing import ...' are allowed"
            ))
        self.generic_visit(node)

    # Track features used (for info)
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # Skip if it's an @external function (those don't execute)
        is_external = any(
            (isinstance(d, ast.Name) and d.id == 'external') or
            (isinstance(d, ast.Attribute) and d.attr == 'external')
            for d in node.decorator_list
        )
        if not is_external:
            self.features_used.add("async_await")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.features_used.add("for_loop")
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.features_used.add("list_comprehension")
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self.features_used.add("dict_comprehension")
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        """F-strings."""
        self.features_used.add("f_string")
        self.generic_visit(node)


def check_for_warnings(parse_result: ParseResult) -> list[CheckMessage]:
    """
    Check for warning conditions (non-blocking issues).

    Warnings:
    - W001: Bare dict/list as return value
    - W002: Unused @external function
    - W003: Unused Input() variable
    - W004: Very long script (>200 lines)
    """
    warnings = []
    module = parse_result.ast_module

    # W001: Check if final expression is bare dict/list
    if module.body:
        last_stmt = module.body[-1]
        if isinstance(last_stmt, ast.Expr):
            if isinstance(last_stmt.value, (ast.Dict, ast.List)):
                warnings.append(CheckMessage(
                    code="W001",
                    lineno=last_stmt.lineno,
                    col_offset=last_stmt.col_offset,
                    end_lineno=last_stmt.end_lineno,
                    end_col_offset=last_stmt.end_col_offset,
                    severity="warning",
                    message="Bare dict/list as return value — consider assigning to a variable for clarity",
                    suggestion="result = {...}; result"
                ))

    # W002 & W003: Check for unused declarations
    # (Would need more sophisticated analysis - skip for now or implement later)

    # W004: Very long script
    if len(parse_result.source_lines) > 200:
        warnings.append(CheckMessage(
            code="W004",
            lineno=1,
            col_offset=0,
            end_lineno=None,
            end_col_offset=None,
            severity="warning",
            message=f"Script is {len(parse_result.source_lines)} lines long (>200) — may indicate too much logic in sandbox",
            suggestion="Consider breaking into smaller scripts or moving logic to external functions"
        ))

    return warnings


def check_pym(parse_result: ParseResult) -> CheckResult:
    """
    Run all validation checks on parsed .pym file.

    Args:
        parse_result: Result from parse_pym_file()

    Returns:
        CheckResult with errors, warnings, and info
    """
    # Run compatibility checker
    checker = MontyCompatibilityChecker(parse_result.source_lines)
    checker.visit(parse_result.ast_module)

    # Collect warnings
    warnings = check_for_warnings(parse_result)
    warnings.extend(checker.warnings)

    # Build info dict
    info = {
        "externals_count": len(parse_result.externals),
        "inputs_count": len(parse_result.inputs),
        "lines_of_code": len(parse_result.source_lines),
        "monty_features_used": sorted(list(checker.features_used))
    }

    # Determine if valid
    valid = len(checker.errors) == 0

    return CheckResult(
        file="<unknown>",  # Caller should set this
        valid=valid,
        errors=checker.errors,
        warnings=warnings,
        info=info
    )
```

### Testing/Validation

Create `tests/unit/test_checker.py`:

```python
"""Test Monty compatibility checker."""
import pytest
from pathlib import Path

from grail.parser import parse_pym_file, parse_pym_content
from grail.checker import check_pym

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_valid_pym_passes():
    """Valid .pym files should pass all checks."""
    result = parse_pym_file(FIXTURES_DIR / "simple.pym")
    check_result = check_pym(result)

    assert check_result.valid is True
    assert len(check_result.errors) == 0


def test_class_definition_detected():
    """Class definitions should be detected as E001."""
    result = parse_pym_file(FIXTURES_DIR / "invalid_class.pym")
    check_result = check_pym(result)

    assert check_result.valid is False
    assert any(e.code == "E001" for e in check_result.errors)
    assert any("Class definitions" in e.message for e in check_result.errors)


def test_with_statement_detected():
    """'with' statements should be detected as E003."""
    result = parse_pym_file(FIXTURES_DIR / "invalid_with.pym")
    check_result = check_pym(result)

    assert check_result.valid is False
    assert any(e.code == "E003" for e in check_result.errors)


def test_generator_detected():
    """Generators should be detected as E002."""
    result = parse_pym_file(FIXTURES_DIR / "invalid_generator.pym")
    check_result = check_pym(result)

    assert check_result.valid is False
    assert any(e.code == "E002" for e in check_result.errors)


def test_forbidden_import_detected():
    """Forbidden imports should be detected as E005."""
    content = """
import json

data = json.loads('{}')
"""
    result = parse_pym_content(content)
    check_result = check_pym(result)

    assert check_result.valid is False
    assert any(e.code == "E005" for e in check_result.errors)
    assert any("json" in e.message for e in check_result.errors)


def test_typing_import_allowed():
    """Imports from typing should be allowed."""
    content = """
from typing import Any, Dict

x: Dict[str, Any] = {}
"""
    result = parse_pym_content(content)
    check_result = check_pym(result)

    # Should not have import errors
    assert not any(e.code == "E005" for e in check_result.errors)


def test_info_collection():
    """Should collect info about the script."""
    result = parse_pym_file(FIXTURES_DIR / "with_multiple_externals.pym")
    check_result = check_pym(result)

    assert check_result.info["externals_count"] == 2
    assert check_result.info["inputs_count"] == 2
    assert check_result.info["lines_of_code"] > 0
    assert "for_loop" in check_result.info["monty_features_used"]


def test_bare_dict_warning():
    """Bare dict as final expression should warn."""
    content = """
from grail import external, Input

x: int = Input("x")

{"result": x * 2}
"""
    result = parse_pym_content(content)
    check_result = check_pym(result)

    assert any(w.code == "W001" for w in check_result.warnings)
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_checker.py` passes
- [ ] All Monty-incompatible features are detected
- [ ] Valid files pass without errors
- [ ] Info is collected correctly
