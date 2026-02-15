# Grail v2 Development Guide (Revised)

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

## Prerequisites

- Python 3.13+
- pydantic-monty (Monty Python bindings)
- Understanding of Python AST module
- pytest, ruff, mypy for testing/linting

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 0: Grail Declarations (external & Input)

**Why this comes first**: The parser needs these to exist, and `.pym` files won't work in IDEs without them.

### Work to be done

1. **Create `src/grail/_external.py`**:

```python
"""External function decorator for .pym files."""
from typing import Any, Callable, TypeVar

F = TypeVar('F', bound=Callable[..., Any])

def external(func: F) -> F:
    """
    Decorator to mark a function as externally provided.

    This is a no-op at runtime - it exists purely for grail's parser
    to extract function signatures and generate type stubs.

    Usage:
        @external
        async def fetch_data(url: str) -> dict[str, Any]:
            '''Fetch data from URL.'''
            ...

    Requirements:
    - Function must have complete type annotations
    - Function body must be ... (Ellipsis)
    """
    # Store metadata on the function for introspection
    func.__grail_external__ = True
    return func
```

2. **Create `src/grail/_input.py`**:

```python
"""Input declaration for .pym files."""
from typing import TypeVar, overload, Any

T = TypeVar('T')

# Overloads for type checker to understand Input() properly
@overload
def Input(name: str) -> Any: ...

@overload
def Input(name: str, default: T) -> T: ...

def Input(name: str, default: Any = None) -> Any:
    """
    Declare an input variable that will be provided at runtime.

    This is a no-op at runtime - it exists for grail's parser to extract
    input declarations. At Monty runtime, these become actual variable bindings.

    Usage:
        budget_limit: float = Input("budget_limit")
        department: str = Input("department", default="Engineering")

    Requirements:
    - Must have a type annotation

    Args:
        name: The input variable name
        default: Optional default value if not provided at runtime

    Returns:
        The default value if provided, otherwise None (at parse time)
    """
    return default
```

3. **Create `src/grail/_types_stubs.pyi`** (type stubs for IDEs):

```python
"""Type stubs for grail declarations."""
from typing import TypeVar, Callable, Any, overload

F = TypeVar('F', bound=Callable[..., Any])
T = TypeVar('T')

def external(func: F) -> F:
    """Mark a function as externally provided."""
    ...

@overload
def Input(name: str) -> Any: ...

@overload
def Input(name: str, default: T) -> T: ...

def Input(name: str, default: Any = None) -> Any:
    """Declare an input variable."""
    ...
```

4. **Create `src/grail/py.typed`** (empty marker file for PEP 561)

### Testing/Validation

Create `tests/unit/test_declarations.py`:

```python
"""Test grail declarations (external, Input)."""
import pytest
from grail._external import external
from grail._input import Input

def test_external_decorator_is_noop():
    """External decorator should not modify function behavior."""
    @external
    def dummy(x: int) -> int:
        ...

    assert hasattr(dummy, '__grail_external__')
    assert dummy.__grail_external__ is True

def test_input_returns_default():
    """Input should return the default value."""
    result = Input("test_var", default="default_value")
    assert result == "default_value"

def test_input_without_default_returns_none():
    """Input without default should return None."""
    result = Input("test_var")
    assert result is None

def test_can_import_from_grail():
    """Should be able to import from grail package."""
    from grail._external import external
    from grail._input import Input

    assert external is not None
    assert Input is not None
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_declarations.py` passes
- [ ] Can import `from grail._external import external`
- [ ] Can import `from grail._input import Input`
- [ ] IDE recognizes these imports (no red squiggles)

---

## Step 1: Core Type Definitions

### Work to be done

Create `src/grail/_types.py` with all core data structures:

```python
"""Core type definitions for grail."""
from dataclasses import dataclass, field
from typing import Any, Literal
import ast

@dataclass
class ParamSpec:
    """Specification for a function parameter."""
    name: str
    type_annotation: str
    default: Any | None = None

@dataclass
class ExternalSpec:
    """Specification for an external function."""
    name: str
    is_async: bool
    parameters: list[ParamSpec]
    return_type: str
    docstring: str | None
    lineno: int
    col_offset: int

@dataclass
class InputSpec:
    """Specification for an input variable."""
    name: str
    type_annotation: str
    default: Any | None
    required: bool
    lineno: int
    col_offset: int

@dataclass
class ParseResult:
    """Result of parsing a .pym file."""
    externals: dict[str, ExternalSpec]
    inputs: dict[str, InputSpec]
    ast_module: ast.Module
    source_lines: list[str]

@dataclass
class SourceMap:
    """Maps line numbers between .pym and monty_code.py."""
    # monty_line -> pym_line
    monty_to_pym: dict[int, int] = field(default_factory=dict)
    # pym_line -> monty_line
    pym_to_monty: dict[int, int] = field(default_factory=dict)

    def add_mapping(self, pym_line: int, monty_line: int) -> None:
        """Add a bidirectional line mapping."""
        self.monty_to_pym[monty_line] = pym_line
        self.pym_to_monty[pym_line] = monty_line

@dataclass
class CheckMessage:
    """A validation error or warning."""
    code: str  # E001, W001, etc.
    lineno: int
    col_offset: int
    end_lineno: int | None
    end_col_offset: int | None
    severity: Literal['error', 'warning']
    message: str
    suggestion: str | None = None

@dataclass
class CheckResult:
    """Result of validation checks."""
    file: str
    valid: bool
    errors: list[CheckMessage]
    warnings: list[CheckMessage]
    info: dict[str, Any]

# Type alias for resource limits
ResourceLimits = dict[str, Any]
```

### Testing/Validation

Create `tests/unit/test_types.py`:

```python
"""Test core type definitions."""
from grail._types import (
    ExternalSpec, InputSpec, ParamSpec, ParseResult,
    SourceMap, CheckMessage, CheckResult
)

def test_external_spec_creation():
    spec = ExternalSpec(
        name="test_func",
        is_async=True,
        parameters=[ParamSpec("x", "int", None)],
        return_type="str",
        docstring="Test function",
        lineno=1,
        col_offset=0
    )
    assert spec.name == "test_func"
    assert spec.is_async is True

def test_source_map_bidirectional():
    smap = SourceMap()
    smap.add_mapping(pym_line=10, monty_line=5)

    assert smap.pym_to_monty[10] == 5
    assert smap.monty_to_pym[5] == 10

def test_check_message_creation():
    msg = CheckMessage(
        code="E001",
        lineno=10,
        col_offset=4,
        end_lineno=10,
        end_col_offset=10,
        severity="error",
        message="Test error",
        suggestion="Fix it"
    )
    assert msg.code == "E001"
    assert msg.severity == "error"
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_types.py` passes
- [ ] `ruff check src/grail/_types.py` passes
- [ ] Can import all types: `from grail._types import ExternalSpec, InputSpec, ...`

---

## Step 2: Error Hierarchy

### Work to be done

Create `src/grail/errors.py`:

```python
"""Error hierarchy for grail."""
from typing import Any

class GrailError(Exception):
    """Base exception for all grail errors."""
    pass

class ParseError(GrailError):
    """Raised when .pym file has Python syntax errors."""

    def __init__(self, message: str, lineno: int | None = None, col_offset: int | None = None):
        self.message = message
        self.lineno = lineno
        self.col_offset = col_offset
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if self.lineno is not None:
            return f"Syntax error at line {self.lineno}: {self.message}"
        return f"Syntax error: {self.message}"

class CheckError(GrailError):
    """Raised when @external or Input() declarations are malformed."""

    def __init__(self, message: str, lineno: int | None = None):
        self.message = message
        self.lineno = lineno
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if self.lineno is not None:
            return f"Declaration error at line {self.lineno}: {self.message}"
        return f"Declaration error: {self.message}"

class InputError(GrailError):
    """Raised when runtime inputs don't match declared Input() specs."""

    def __init__(self, message: str, input_name: str | None = None):
        self.message = message
        self.input_name = input_name
        super().__init__(message)

class ExternalError(GrailError):
    """Raised when external functions aren't provided or don't match declarations."""

    def __init__(self, message: str, function_name: str | None = None):
        self.message = message
        self.function_name = function_name
        super().__init__(message)

class ExecutionError(GrailError):
    """Raised when Monty runtime error occurs."""

    def __init__(
        self,
        message: str,
        lineno: int | None = None,
        col_offset: int | None = None,
        source_context: str | None = None,
        suggestion: str | None = None
    ):
        self.message = message
        self.lineno = lineno
        self.col_offset = col_offset
        self.source_context = source_context
        self.suggestion = suggestion
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = []
        if self.lineno is not None:
            parts.append(f"Line {self.lineno}")
        parts.append(self.message)

        msg = " — ".join(parts)

        if self.source_context:
            msg += f"\n\n{self.source_context}"

        if self.suggestion:
            msg += f"\n\nSuggestion: {self.suggestion}"

        return msg

class LimitError(ExecutionError):
    """Raised when resource limits are exceeded."""

    def __init__(self, message: str, limit_type: str | None = None):
        self.limit_type = limit_type
        super().__init__(message)

class OutputError(GrailError):
    """Raised when output validation against output_model fails."""

    def __init__(self, message: str, validation_errors: Any = None):
        self.message = message
        self.validation_errors = validation_errors
        super().__init__(message)
```

### Testing/Validation

Create `tests/unit/test_errors.py`:

```python
"""Test error hierarchy."""
import pytest
from grail.errors import (
    GrailError, ParseError, CheckError, InputError,
    ExternalError, ExecutionError, LimitError, OutputError
)

def test_error_hierarchy():
    """All errors should inherit from GrailError."""
    assert issubclass(ParseError, GrailError)
    assert issubclass(CheckError, GrailError)
    assert issubclass(InputError, GrailError)
    assert issubclass(ExternalError, GrailError)
    assert issubclass(ExecutionError, GrailError)
    assert issubclass(LimitError, ExecutionError)
    assert issubclass(OutputError, GrailError)

def test_parse_error_formatting():
    """ParseError should format with line numbers."""
    err = ParseError("unexpected token", lineno=10, col_offset=5)
    assert "line 10" in str(err)
    assert "unexpected token" in str(err)

def test_execution_error_with_context():
    """ExecutionError should include source context."""
    err = ExecutionError(
        "NameError: undefined_var",
        lineno=22,
        source_context="  22 | if total > undefined_var:",
        suggestion="Check if variable is declared"
    )
    msg = str(err)
    assert "Line 22" in msg
    assert "undefined_var" in msg
    assert "Suggestion:" in msg

def test_limit_error_is_execution_error():
    """LimitError should be a subclass of ExecutionError."""
    err = LimitError("Memory limit exceeded", limit_type="memory")
    assert isinstance(err, ExecutionError)
    assert err.limit_type == "memory"
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_errors.py` passes
- [ ] All error types can be imported
- [ ] Error messages format correctly

---

## Step 3: Resource Limits Parser

### Work to be done

Create `src/grail/limits.py`:

```python
"""Resource limits parsing and presets."""
from typing import Any
import re

# Named presets (plain dicts)
STRICT: dict[str, Any] = {
    "max_memory": "8mb",
    "max_duration": "500ms",
    "max_recursion": 120,
}

DEFAULT: dict[str, Any] = {
    "max_memory": "16mb",
    "max_duration": "2s",
    "max_recursion": 200,
}

PERMISSIVE: dict[str, Any] = {
    "max_memory": "64mb",
    "max_duration": "5s",
    "max_recursion": 400,
}

def parse_memory_string(value: str) -> int:
    """
    Parse memory string to bytes.

    Examples:
        "16mb" -> 16777216
        "1gb" -> 1073741824
        "512kb" -> 524288

    Args:
        value: Memory string (e.g., "16mb", "1GB")

    Returns:
        Number of bytes

    Raises:
        ValueError: If format is invalid
    """
    value = value.lower().strip()

    # Match number and unit
    match = re.match(r'^(\d+(?:\.\d+)?)(kb|mb|gb)$', value)
    if not match:
        raise ValueError(f"Invalid memory format: {value}. Use format like '16mb', '1gb'")

    number, unit = match.groups()
    number = float(number)

    multipliers = {
        'kb': 1024,
        'mb': 1024 * 1024,
        'gb': 1024 * 1024 * 1024,
    }

    return int(number * multipliers[unit])

def parse_duration_string(value: str) -> float:
    """
    Parse duration string to seconds.

    Examples:
        "500ms" -> 0.5
        "2s" -> 2.0
        "1.5s" -> 1.5

    Args:
        value: Duration string (e.g., "500ms", "2s")

    Returns:
        Number of seconds

    Raises:
        ValueError: If format is invalid
    """
    value = value.lower().strip()

    # Match number and unit
    match = re.match(r'^(\d+(?:\.\d+)?)(ms|s)$', value)
    if not match:
        raise ValueError(f"Invalid duration format: {value}. Use format like '500ms', '2s'")

    number, unit = match.groups()
    number = float(number)

    if unit == 'ms':
        return number / 1000.0
    else:  # 's'
        return number

def parse_limits(limits: dict[str, Any]) -> dict[str, Any]:
    """
    Parse limits dict, converting string formats to native types.

    Args:
        limits: Raw limits dict (may contain string formats)

    Returns:
        Parsed limits dict with native types

    Examples:
        {"max_memory": "16mb"} -> {"max_memory": 16777216}
        {"max_duration": "2s"} -> {"max_duration": 2.0}
    """
    parsed = {}

    for key, value in limits.items():
        if key == "max_memory" and isinstance(value, str):
            parsed[key] = parse_memory_string(value)
        elif key == "max_duration" and isinstance(value, str):
            parsed[key] = parse_duration_string(value)
        else:
            parsed[key] = value

    return parsed

def merge_limits(base: dict[str, Any] | None, override: dict[str, Any] | None) -> dict[str, Any]:
    """
    Merge two limits dicts, with override taking precedence.

    Args:
        base: Base limits (e.g., from load())
        override: Override limits (e.g., from run())

    Returns:
        Merged limits dict
    """
    if base is None and override is None:
        return parse_limits(DEFAULT.copy())

    if base is None:
        return parse_limits(override.copy())

    if override is None:
        return parse_limits(base.copy())

    # Merge: override takes precedence
    merged = base.copy()
    merged.update(override)
    return parse_limits(merged)
```

### Testing/Validation

Create `tests/unit/test_limits.py`:

```python
"""Test resource limits parsing."""
import pytest
from grail.limits import (
    parse_memory_string, parse_duration_string,
    parse_limits, merge_limits,
    STRICT, DEFAULT, PERMISSIVE
)

def test_parse_memory_string():
    """Test memory string parsing."""
    assert parse_memory_string("16mb") == 16 * 1024 * 1024
    assert parse_memory_string("1gb") == 1 * 1024 * 1024 * 1024
    assert parse_memory_string("512kb") == 512 * 1024
    assert parse_memory_string("1MB") == 1 * 1024 * 1024  # case insensitive

def test_parse_duration_string():
    """Test duration string parsing."""
    assert parse_duration_string("500ms") == 0.5
    assert parse_duration_string("2s") == 2.0
    assert parse_duration_string("1.5s") == 1.5

def test_invalid_memory_format():
    """Invalid memory format should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid memory format"):
        parse_memory_string("16")

    with pytest.raises(ValueError):
        parse_memory_string("invalid")

def test_invalid_duration_format():
    """Invalid duration format should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid duration format"):
        parse_duration_string("2")

    with pytest.raises(ValueError):
        parse_duration_string("invalid")

def test_parse_limits():
    """Test parsing full limits dict."""
    raw = {
        "max_memory": "16mb",
        "max_duration": "2s",
        "max_recursion": 200,
    }
    parsed = parse_limits(raw)

    assert parsed["max_memory"] == 16 * 1024 * 1024
    assert parsed["max_duration"] == 2.0
    assert parsed["max_recursion"] == 200

def test_merge_limits():
    """Test merging limits dicts."""
    base = {"max_memory": "16mb", "max_recursion": 200}
    override = {"max_duration": "5s"}

    merged = merge_limits(base, override)

    assert merged["max_memory"] == 16 * 1024 * 1024
    assert merged["max_duration"] == 5.0
    assert merged["max_recursion"] == 200

def test_presets_are_dicts():
    """Presets should be plain dicts."""
    assert isinstance(STRICT, dict)
    assert isinstance(DEFAULT, dict)
    assert isinstance(PERMISSIVE, dict)

    assert STRICT["max_memory"] == "8mb"
    assert DEFAULT["max_memory"] == "16mb"
    assert PERMISSIVE["max_memory"] == "64mb"
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_limits.py` passes
- [ ] All string formats parse correctly
- [ ] Merging works as expected
- [ ] Presets are accessible

---

## Step 4: Test Fixtures - Create Reusable .pym Examples

**Why this comes before parser**: We need concrete examples to test the parser against.

### Work to be done

Create `tests/fixtures/` directory with example `.pym` files:

1. **`tests/fixtures/simple.pym`** - Basic valid .pym file:

```python
from grail import external, Input

x: int = Input("x")

@external
async def double(n: int) -> int:
    """Double a number."""
    ...

result = await double(x)
result
```

2. **`tests/fixtures/with_multiple_externals.pym`**:

```python
from grail import external, Input
from typing import Any

budget: float = Input("budget")
department: str = Input("department", default="Engineering")

@external
async def get_team(dept: str) -> dict[str, Any]:
    """Get team members."""
    ...

@external
async def get_expenses(user_id: int) -> dict[str, Any]:
    """Get expenses for user."""
    ...

team = await get_team(department)
members = team.get("members", [])

total = 0.0
for member in members:
    expenses = await get_expenses(member["id"])
    total += expenses.get("total", 0.0)

{
    "team_size": len(members),
    "total_expenses": total,
    "over_budget": total > budget
}
```

3. **`tests/fixtures/invalid_class.pym`** - For testing error detection:

```python
from grail import external

class MyClass:
    def __init__(self):
        self.value = 42
```

4. **`tests/fixtures/invalid_with.pym`** - For testing error detection:

```python
from grail import external

with open("file.txt") as f:
    content = f.read()
```

5. **`tests/fixtures/invalid_generator.pym`** - For testing error detection:

```python
from grail import external

def my_generator():
    yield 1
    yield 2
```

6. **`tests/fixtures/missing_annotation.pym`** - For testing CheckError:

```python
from grail import external

@external
def bad_func(x):  # Missing type annotation
    ...
```

7. **`tests/fixtures/non_ellipsis_body.pym`** - For testing CheckError:

```python
from grail import external

@external
def bad_func(x: int) -> int:
    return x * 2  # Should be ... not actual implementation
```

### Testing/Validation

Create `tests/fixtures/test_fixtures.py`:

```python
"""Verify test fixtures are valid Python."""
import ast
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent

def test_simple_pym_is_valid_python():
    """simple.pym should be syntactically valid Python."""
    content = (FIXTURES_DIR / "simple.pym").read_text()
    # Should not raise SyntaxError
    ast.parse(content)

def test_with_multiple_externals_is_valid():
    """with_multiple_externals.pym should be valid Python."""
    content = (FIXTURES_DIR / "with_multiple_externals.pym").read_text()
    ast.parse(content)

def test_invalid_fixtures_are_valid_python():
    """Invalid .pym files should still be valid Python syntax."""
    # They're invalid for Monty, but valid Python
    for name in ["invalid_class.pym", "invalid_with.pym", "invalid_generator.pym"]:
        content = (FIXTURES_DIR / name).read_text()
        ast.parse(content)  # Should not raise

def test_all_fixtures_exist():
    """All expected fixtures should exist."""
    expected = [
        "simple.pym",
        "with_multiple_externals.pym",
        "invalid_class.pym",
        "invalid_with.pym",
        "invalid_generator.pym",
        "missing_annotation.pym",
        "non_ellipsis_body.pym",
    ]

    for name in expected:
        path = FIXTURES_DIR / name
        assert path.exists(), f"Missing fixture: {name}"
```

**Validation checklist**:
- [ ] All fixture files created
- [ ] `pytest tests/fixtures/test_fixtures.py` passes
- [ ] All fixtures are valid Python (can be parsed with ast.parse())

---

## Summary - Steps 0-4 Complete

At this point you have:

✅ **Step 0**: Grail declarations (`external`, `Input`) that enable `.pym` files to work in IDEs
✅ **Step 1**: Core type definitions for all data structures
✅ **Step 2**: Complete error hierarchy with proper formatting
✅ **Step 3**: Resource limits parser with string format support
✅ **Step 4**: Comprehensive test fixtures to use in subsequent steps

**Next steps** (Steps 5-16):
- Step 5: Parser - Extract externals and inputs from AST
- Step 6: Checker - Validate Monty compatibility
- Step 7: Stubs Generator - Create .pyi files
- Step 8: Code Generator - Transform .pym to monty_code.py
- Step 9: Artifacts Manager - Manage .grail/ directory
- Step 10: Monty Integration - Test calling Monty directly
- Step 11: GrailScript Class - Main API implementation
- Step 12: CLI Commands - Command-line interface
- Step 13: Snapshot - Pause/resume wrapper
- Step 14: Public API - __init__.py exports
- Step 15: Integration Tests - Full workflow testing
- Step 16: Final Validation - Lint, typecheck, test

Each step will build on the solid foundation established in Steps 0-4.
