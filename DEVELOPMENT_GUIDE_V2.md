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

---

## Step 5: Parser - Extract Externals and Inputs from AST

**Critical step**: This is where we extract `@external` functions and `Input()` calls from `.pym` files.

### Work to be done

Create `src/grail/parser.py`:

```python
"""Parser for .pym files - extracts externals and inputs from AST."""
import ast
from pathlib import Path
from typing import Any

from grail._types import (
    ExternalSpec, InputSpec, ParamSpec, ParseResult
)
from grail.errors import ParseError, CheckError


def get_type_annotation_str(node: ast.expr | None) -> str:
    """
    Convert AST type annotation node to string.

    Args:
        node: AST annotation node

    Returns:
        String representation of type (e.g., "int", "dict[str, Any]")

    Raises:
        CheckError: If annotation is missing or invalid
    """
    if node is None:
        raise CheckError("Missing type annotation")

    return ast.unparse(node)


def extract_function_params(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ParamSpec]:
    """
    Extract parameter specifications from function definition.

    Args:
        func_node: Function definition AST node

    Returns:
        List of parameter specifications

    Raises:
        CheckError: If parameters lack type annotations
    """
    params = []

    for arg in func_node.args.args:
        # Skip 'self' if present (shouldn't be in external funcs but be defensive)
        if arg.arg == 'self':
            continue

        if arg.annotation is None:
            raise CheckError(
                f"Parameter '{arg.arg}' in function '{func_node.name}' missing type annotation",
                lineno=func_node.lineno
            )

        # Check for default value
        default = None
        # Defaults are stored separately in args.defaults
        # They align with the last N args
        num_defaults = len(func_node.args.defaults)
        num_args = len(func_node.args.args)
        arg_index = func_node.args.args.index(arg)

        if arg_index >= num_args - num_defaults:
            default_index = arg_index - (num_args - num_defaults)
            default_node = func_node.args.defaults[default_index]
            # Try to extract literal default value
            try:
                default = ast.literal_eval(default_node)
            except (ValueError, TypeError):
                # If not a literal, store as string representation
                default = ast.unparse(default_node)

        params.append(ParamSpec(
            name=arg.arg,
            type_annotation=get_type_annotation_str(arg.annotation),
            default=default
        ))

    return params


def validate_external_function(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
    """
    Validate that external function meets requirements.

    Requirements:
    - Complete type annotations on all parameters
    - Return type annotation
    - Body is single Ellipsis statement

    Args:
        func_node: Function definition to validate

    Raises:
        CheckError: If validation fails
    """
    # Check return type
    if func_node.returns is None:
        raise CheckError(
            f"Function '{func_node.name}' missing return type annotation",
            lineno=func_node.lineno
        )

    # Check body is single Ellipsis
    if len(func_node.body) != 1:
        raise CheckError(
            f"External function '{func_node.name}' body must be single '...' (Ellipsis)",
            lineno=func_node.lineno
        )

    body_stmt = func_node.body[0]

    # Body should be Expr node containing Constant(value=Ellipsis)
    if not isinstance(body_stmt, ast.Expr):
        raise CheckError(
            f"External function '{func_node.name}' body must be '...' (Ellipsis)",
            lineno=func_node.lineno
        )

    if not isinstance(body_stmt.value, ast.Constant) or body_stmt.value.value != Ellipsis:
        raise CheckError(
            f"External function '{func_node.name}' body must be '...' (Ellipsis), not actual code",
            lineno=func_node.lineno
        )


def extract_externals(module: ast.Module) -> dict[str, ExternalSpec]:
    """
    Extract external function specifications from AST.

    Looks for functions decorated with @external.

    Args:
        module: Parsed AST module

    Returns:
        Dictionary mapping function names to ExternalSpec

    Raises:
        CheckError: If external declarations are malformed
    """
    externals = {}

    for node in ast.walk(module):
        # Check both regular and async function definitions
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Check if decorated with @external
        has_external = False
        for decorator in node.decorator_list:
            # Handle simple decorator: @external
            if isinstance(decorator, ast.Name) and decorator.id == 'external':
                has_external = True
                break
            # Handle attribute decorator: @grail.external (future-proofing)
            if isinstance(decorator, ast.Attribute) and decorator.attr == 'external':
                has_external = True
                break

        if not has_external:
            continue

        # Validate the external function
        validate_external_function(node)

        # Extract parameters
        params = extract_function_params(node)

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Create spec
        spec = ExternalSpec(
            name=node.name,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            parameters=params,
            return_type=get_type_annotation_str(node.returns),
            docstring=docstring,
            lineno=node.lineno,
            col_offset=node.col_offset
        )

        externals[node.name] = spec

    return externals


def extract_inputs(module: ast.Module) -> dict[str, InputSpec]:
    """
    Extract input specifications from AST.

    Looks for assignments like: x: int = Input("x")

    Args:
        module: Parsed AST module

    Returns:
        Dictionary mapping input names to InputSpec

    Raises:
        CheckError: If input declarations are malformed
    """
    inputs = {}

    for node in ast.walk(module):
        # Look for annotated assignments
        if not isinstance(node, ast.AnnAssign):
            continue

        # Check if RHS is a call to Input()
        if not isinstance(node.value, ast.Call):
            continue

        # Check if the function being called is 'Input'
        is_input_call = False
        if isinstance(node.value.func, ast.Name) and node.value.func.id == 'Input':
            is_input_call = True
        elif isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'Input':
            is_input_call = True

        if not is_input_call:
            continue

        # Validate annotation exists
        if node.annotation is None:
            raise CheckError(
                "Input() call must have type annotation",
                lineno=node.lineno
            )

        # Extract variable name
        if not isinstance(node.target, ast.Name):
            raise CheckError(
                "Input() must be assigned to a simple variable name",
                lineno=node.lineno
            )

        var_name = node.target.id

        # Extract Input() arguments
        # First positional arg should be the name (string)
        if len(node.value.args) == 0:
            raise CheckError(
                f"Input() call for '{var_name}' missing name argument",
                lineno=node.lineno
            )

        # Extract default value from 'default=' keyword argument
        default = None
        for keyword in node.value.keywords:
            if keyword.arg == 'default':
                try:
                    default = ast.literal_eval(keyword.value)
                except (ValueError, TypeError):
                    # If not a literal, store as string
                    default = ast.unparse(keyword.value)
                break

        # Create spec
        spec = InputSpec(
            name=var_name,
            type_annotation=get_type_annotation_str(node.annotation),
            default=default,
            required=(default is None),
            lineno=node.lineno,
            col_offset=node.col_offset
        )

        inputs[var_name] = spec

    return inputs


def parse_pym_file(path: Path) -> ParseResult:
    """
    Parse a .pym file and extract metadata.

    Args:
        path: Path to .pym file

    Returns:
        ParseResult with externals, inputs, AST, and source lines

    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If file has syntax errors
        CheckError: If declarations are malformed
    """
    if not path.exists():
        raise FileNotFoundError(f".pym file not found: {path}")

    # Read source
    source = path.read_text()
    source_lines = source.splitlines()

    # Parse AST
    try:
        module = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise ParseError(
            e.msg,
            lineno=e.lineno,
            col_offset=e.offset
        )

    # Extract externals and inputs
    externals = extract_externals(module)
    inputs = extract_inputs(module)

    return ParseResult(
        externals=externals,
        inputs=inputs,
        ast_module=module,
        source_lines=source_lines
    )


def parse_pym_content(content: str, filename: str = "<string>") -> ParseResult:
    """
    Parse .pym content from string (useful for testing).

    Args:
        content: .pym file content
        filename: Optional filename for error messages

    Returns:
        ParseResult

    Raises:
        ParseError: If content has syntax errors
        CheckError: If declarations are malformed
    """
    source_lines = content.splitlines()

    try:
        module = ast.parse(content, filename=filename)
    except SyntaxError as e:
        raise ParseError(
            e.msg,
            lineno=e.lineno,
            col_offset=e.offset
        )

    externals = extract_externals(module)
    inputs = extract_inputs(module)

    return ParseResult(
        externals=externals,
        inputs=inputs,
        ast_module=module,
        source_lines=source_lines
    )
```

### Testing/Validation

Create `tests/unit/test_parser.py`:

```python
"""Test .pym file parser."""
import pytest
from pathlib import Path

from grail.parser import parse_pym_file, parse_pym_content
from grail.errors import ParseError, CheckError

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_parse_simple_pym():
    """Parse simple.pym fixture."""
    result = parse_pym_file(FIXTURES_DIR / "simple.pym")

    # Should have 1 external: double
    assert "double" in result.externals
    ext = result.externals["double"]
    assert ext.is_async is True
    assert ext.return_type == "int"
    assert len(ext.parameters) == 1
    assert ext.parameters[0].name == "n"
    assert ext.parameters[0].type_annotation == "int"

    # Should have 1 input: x
    assert "x" in result.inputs
    inp = result.inputs["x"]
    assert inp.type_annotation == "int"
    assert inp.required is True


def test_parse_multiple_externals():
    """Parse fixture with multiple externals."""
    result = parse_pym_file(FIXTURES_DIR / "with_multiple_externals.pym")

    # Should have 2 externals
    assert "get_team" in result.externals
    assert "get_expenses" in result.externals

    # Should have 2 inputs
    assert "budget" in result.inputs
    assert "department" in result.inputs

    # Check input with default
    dept = result.inputs["department"]
    assert dept.required is False
    assert dept.default == "Engineering"


def test_missing_type_annotation_raises():
    """Missing type annotation should raise CheckError."""
    content = """
from grail import external

@external
def bad_func(x):
    ...
"""
    with pytest.raises(CheckError, match="missing type annotation"):
        parse_pym_content(content)


def test_missing_return_type_raises():
    """Missing return type should raise CheckError."""
    content = """
from grail import external

@external
def bad_func(x: int):
    ...
"""
    with pytest.raises(CheckError, match="missing return type annotation"):
        parse_pym_content(content)


def test_non_ellipsis_body_raises():
    """Non-ellipsis body should raise CheckError."""
    result = parse_pym_file(FIXTURES_DIR / "non_ellipsis_body.pym")
    # This should raise during parse

    # Actually, let's test directly
    content = """
from grail import external

@external
def bad_func(x: int) -> int:
    return x * 2
"""
    with pytest.raises(CheckError, match="body must be"):
        parse_pym_content(content)


def test_input_without_annotation_raises():
    """Input without type annotation should raise CheckError."""
    content = """
from grail import Input

x = Input("x")  # Missing annotation
"""
    with pytest.raises(CheckError, match="type annotation"):
        parse_pym_content(content)


def test_syntax_error_raises_parse_error():
    """Invalid Python syntax should raise ParseError."""
    content = "def bad syntax here"

    with pytest.raises(ParseError):
        parse_pym_content(content)


def test_extract_docstring():
    """Should extract function docstrings."""
    content = """
from grail import external

@external
async def fetch_data(url: str) -> dict:
    '''Fetch data from URL.'''
    ...
"""
    result = parse_pym_content(content)

    assert "fetch_data" in result.externals
    assert result.externals["fetch_data"].docstring == "Fetch data from URL."


def test_function_with_defaults():
    """Should handle function parameters with defaults."""
    content = """
from grail import external

@external
def process(x: int, y: int = 10) -> int:
    ...
"""
    result = parse_pym_content(content)

    func = result.externals["process"]
    assert len(func.parameters) == 2
    assert func.parameters[0].name == "x"
    assert func.parameters[0].default is None
    assert func.parameters[1].name == "y"
    assert func.parameters[1].default == 10
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_parser.py` passes
- [ ] Parser correctly extracts `@external` functions
- [ ] Parser correctly extracts `Input()` calls
- [ ] Validation errors are raised for malformed declarations
- [ ] Can parse all valid fixtures without errors

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

---

## Step 7: Stubs Generator

**Purpose**: Generate `.pyi` type stub files from `@external` and `Input()` declarations.

### Work to be done

Create `src/grail/stubs.py`:

```python
"""Type stub generator for Monty's type checker."""
from grail._types import ExternalSpec, InputSpec


def generate_stubs(
    externals: dict[str, ExternalSpec],
    inputs: dict[str, InputSpec]
) -> str:
    """
    Generate .pyi stub file content from declarations.

    Args:
        externals: External function specifications
        inputs: Input variable specifications

    Returns:
        .pyi file content as string
    """
    lines = [
        "# Auto-generated by grail — do not edit",
        ""
    ]

    # Check if we need Any import
    needs_any = False

    for ext in externals.values():
        if "Any" in ext.return_type:
            needs_any = True
        for param in ext.parameters:
            if "Any" in param.type_annotation:
                needs_any = True

    for inp in inputs.values():
        if "Any" in inp.type_annotation:
            needs_any = True

    # Add imports
    if needs_any:
        lines.append("from typing import Any")
        lines.append("")

    # Add input variable declarations
    if inputs:
        for inp in inputs.values():
            lines.append(f"{inp.name}: {inp.type_annotation}")
        lines.append("")

    # Add external function signatures
    for ext in externals.values():
        # Build parameter list
        params = []
        for param in ext.parameters:
            if param.default is not None:
                # Has default value
                if isinstance(param.default, str):
                    # String default (for non-literals)
                    params.append(f"{param.name}: {param.type_annotation} = {param.default}")
                else:
                    params.append(f"{param.name}: {param.type_annotation} = {repr(param.default)}")
            else:
                params.append(f"{param.name}: {param.type_annotation}")

        params_str = ", ".join(params)

        # Add function signature
        if ext.is_async:
            lines.append(f"async def {ext.name}({params_str}) -> {ext.return_type}:")
        else:
            lines.append(f"def {ext.name}({params_str}) -> {ext.return_type}:")

        # Add docstring if present
        if ext.docstring:
            lines.append(f'    """{ext.docstring}"""')

        # Add ellipsis body
        lines.append("    ...")
        lines.append("")

    return "\n".join(lines)
```

### Testing/Validation

Create `tests/unit/test_stubs.py`:

```python
"""Test type stub generation."""
from grail._types import ExternalSpec, InputSpec, ParamSpec
from grail.stubs import generate_stubs


def test_generate_simple_stub():
    """Generate stub for simple external function."""
    externals = {
        "double": ExternalSpec(
            name="double",
            is_async=True,
            parameters=[ParamSpec("n", "int", None)],
            return_type="int",
            docstring="Double a number.",
            lineno=1,
            col_offset=0
        )
    }
    inputs = {
        "x": InputSpec(
            name="x",
            type_annotation="int",
            default=None,
            required=True,
            lineno=1,
            col_offset=0
        )
    }

    stub = generate_stubs(externals, inputs)

    assert "x: int" in stub
    assert "async def double(n: int) -> int:" in stub
    assert "Double a number." in stub
    assert "..." in stub


def test_stub_with_any_import():
    """Stub should import Any when needed."""
    externals = {
        "fetch": ExternalSpec(
            name="fetch",
            is_async=True,
            parameters=[ParamSpec("url", "str", None)],
            return_type="dict[str, Any]",
            docstring=None,
            lineno=1,
            col_offset=0
        )
    }

    stub = generate_stubs(externals, {})

    assert "from typing import Any" in stub
    assert "dict[str, Any]" in stub


def test_stub_with_defaults():
    """Stub should include default parameter values."""
    externals = {
        "process": ExternalSpec(
            name="process",
            is_async=False,
            parameters=[
                ParamSpec("x", "int", None),
                ParamSpec("y", "int", 10),
            ],
            return_type="int",
            docstring=None,
            lineno=1,
            col_offset=0
        )
    }

    stub = generate_stubs(externals, {})

    assert "def process(x: int, y: int = 10) -> int:" in stub


def test_multiple_inputs_and_externals():
    """Stub should handle multiple declarations."""
    externals = {
        "func1": ExternalSpec("func1", True, [], "None", None, 1, 0),
        "func2": ExternalSpec("func2", False, [], "str", None, 2, 0),
    }
    inputs = {
        "a": InputSpec("a", "int", None, True, 1, 0),
        "b": InputSpec("b", "str", "default", False, 2, 0),
    }

    stub = generate_stubs(externals, inputs)

    assert "a: int" in stub
    assert "b: str" in stub
    assert "async def func1() -> None:" in stub
    assert "def func2() -> str:" in stub
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_stubs.py` passes
- [ ] Generated stubs are valid Python
- [ ] Imports are added when needed
- [ ] Docstrings are preserved

---

## Step 8: Code Generator - Transform .pym to Monty Code

**Critical step**: This strips grail declarations and produces the actual code that runs in Monty.

### Work to be done

Create `src/grail/codegen.py`:

```python
"""Code generator - transforms .pym to Monty-compatible code."""
import ast
from grail._types import ParseResult, SourceMap


class GrailDeclarationStripper(ast.NodeTransformer):
    """
    AST transformer that removes grail-specific declarations.

    Removes:
    - from grail import ... statements
    - @external decorated function definitions
    - Input() assignment statements

    Preserves:
    - All executable code
    - from typing import ... statements
    """

    def __init__(self, externals: set[str], inputs: set[str]):
        self.externals = externals  # Set of external function names
        self.inputs = inputs  # Set of input variable names

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom | None:
        """Remove 'from grail import ...' statements."""
        if node.module == "grail":
            return None  # Remove this node
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef | None:
        """Remove @external function definitions."""
        if node.name in self.externals:
            return None  # Remove this node
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef | None:
        """Remove @external async function definitions."""
        if node.name in self.externals:
            return None
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AnnAssign | None:
        """Remove Input() assignment statements."""
        if isinstance(node.target, ast.Name) and node.target.id in self.inputs:
            return None
        return node


def build_source_map(original_lines: list[str], generated_code: str) -> SourceMap:
    """
    Build line number mapping between .pym and generated code.

    This is a simplified version - for more accurate mapping,
    we'd need to track transformations during AST processing.

    Args:
        original_lines: Source lines from .pym file
        generated_code: Generated Monty code

    Returns:
        SourceMap with line mappings
    """
    source_map = SourceMap()

    # Simple heuristic: map based on matching content
    # For now, just create identity mapping for matching lines
    generated_lines = generated_code.splitlines()

    pym_idx = 0
    monty_idx = 0

    while pym_idx < len(original_lines) and monty_idx < len(generated_lines):
        pym_line = original_lines[pym_idx].strip()
        monty_line = generated_lines[monty_idx].strip()

        if pym_line == monty_line and pym_line:
            # Lines match - create mapping
            source_map.add_mapping(pym_line=pym_idx + 1, monty_line=monty_idx + 1)

        pym_idx += 1
        monty_idx += 1

    return source_map


def generate_monty_code(parse_result: ParseResult) -> tuple[str, SourceMap]:
    """
    Generate Monty-compatible code from parsed .pym file.

    Args:
        parse_result: Result from parse_pym_file()

    Returns:
        Tuple of (monty_code, source_map)
    """
    # Get sets of names to remove
    external_names = set(parse_result.externals.keys())
    input_names = set(parse_result.inputs.keys())

    # Transform AST
    stripper = GrailDeclarationStripper(external_names, input_names)
    transformed = stripper.visit(parse_result.ast_module)

    # Fix missing locations after transformation
    ast.fix_missing_locations(transformed)

    # Generate code from transformed AST
    monty_code = ast.unparse(transformed)

    # Build source map
    source_map = build_source_map(parse_result.source_lines, monty_code)

    return monty_code, source_map
```

### Testing/Validation

Create `tests/unit/test_codegen.py`:

```python
"""Test code generation."""
from grail.parser import parse_pym_content
from grail.codegen import generate_monty_code


def test_strips_grail_imports():
    """Should remove 'from grail import ...' statements."""
    content = """
from grail import external, Input
from typing import Any

x: int = Input("x")

@external
async def double(n: int) -> int:
    ...

result = await double(x)
result
"""
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    assert "from grail" not in monty_code
    assert "from typing import Any" in monty_code  # typing imports preserved


def test_strips_external_functions():
    """Should remove @external function definitions."""
    content = """
from grail import external

@external
async def double(n: int) -> int:
    ...

result = await double(5)
"""
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    assert "async def double" not in monty_code
    assert "await double(5)" in monty_code  # Call preserved


def test_strips_input_declarations():
    """Should remove Input() assignment statements."""
    content = """
from grail import Input

x: int = Input("x")
y = x * 2
"""
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    assert "Input(" not in monty_code
    assert "y = x * 2" in monty_code  # Usage preserved


def test_preserves_executable_code():
    """Should preserve all executable code."""
    content = """
from grail import external, Input

x: int = Input("x")

@external
async def process(n: int) -> int:
    ...

result = await process(x)
final = result * 2

{
    "value": final,
    "doubled": final * 2
}
"""
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    # Check executable code is preserved
    assert "result = await process(x)" in monty_code
    assert "final = result * 2" in monty_code
    assert '"value": final' in monty_code


def test_source_map_created():
    """Should create source map for line number mapping."""
    content = """x = 1
y = 2
z = x + y"""

    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    # Source map should have mappings
    assert len(source_map.pym_to_monty) > 0
    assert len(source_map.monty_to_pym) > 0
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_codegen.py` passes
- [ ] Grail imports are removed
- [ ] External functions are removed
- [ ] Input declarations are removed
- [ ] Executable code is preserved
- [ ] Source map is created

---

## Step 9: Artifacts Manager

**Purpose**: Manage the `.grail/` directory and all generated artifacts.

### Work to be done

Create `src/grail/artifacts.py`:

```python
"""Artifacts manager for .grail/ directory."""
import json
from pathlib import Path
from typing import Any

from grail._types import CheckResult, ExternalSpec, InputSpec


class ArtifactsManager:
    """Manages .grail/ directory and generated artifacts."""

    def __init__(self, grail_dir: Path):
        """
        Initialize artifacts manager.

        Args:
            grail_dir: Path to .grail/ directory
        """
        self.grail_dir = grail_dir

    def get_script_dir(self, script_name: str) -> Path:
        """Get directory for a specific script's artifacts."""
        return self.grail_dir / script_name

    def write_script_artifacts(
        self,
        script_name: str,
        stubs: str,
        monty_code: str,
        check_result: CheckResult,
        externals: dict[str, ExternalSpec],
        inputs: dict[str, InputSpec]
    ) -> None:
        """
        Write all artifacts for a script.

        Args:
            script_name: Name of the script
            stubs: Generated type stubs
            monty_code: Generated Monty code
            check_result: Validation results
            externals: External function specs
            inputs: Input specs
        """
        script_dir = self.get_script_dir(script_name)
        script_dir.mkdir(parents=True, exist_ok=True)

        # Write stubs.pyi
        (script_dir / "stubs.pyi").write_text(stubs)

        # Write monty_code.py
        (script_dir / "monty_code.py").write_text(
            "# Auto-generated by grail — this is what Monty actually executes\n\n"
            + monty_code
        )

        # Write check.json
        check_data = {
            "file": check_result.file,
            "valid": check_result.valid,
            "errors": [
                {
                    "line": e.lineno,
                    "column": e.col_offset,
                    "code": e.code,
                    "message": e.message,
                    "suggestion": e.suggestion
                }
                for e in check_result.errors
            ],
            "warnings": [
                {
                    "line": w.lineno,
                    "column": w.col_offset,
                    "code": w.code,
                    "message": w.message
                }
                for w in check_result.warnings
            ],
            "info": check_result.info
        }
        (script_dir / "check.json").write_text(
            json.dumps(check_data, indent=2)
        )

        # Write externals.json
        externals_data = {
            "externals": [
                {
                    "name": ext.name,
                    "async": ext.is_async,
                    "parameters": [
                        {
                            "name": p.name,
                            "type": p.type_annotation,
                            "default": p.default
                        }
                        for p in ext.parameters
                    ],
                    "return_type": ext.return_type,
                    "docstring": ext.docstring
                }
                for ext in externals.values()
            ]
        }
        (script_dir / "externals.json").write_text(
            json.dumps(externals_data, indent=2)
        )

        # Write inputs.json
        inputs_data = {
            "inputs": [
                {
                    "name": inp.name,
                    "type": inp.type_annotation,
                    "required": inp.required,
                    "default": inp.default
                }
                for inp in inputs.values()
            ]
        }
        (script_dir / "inputs.json").write_text(
            json.dumps(inputs_data, indent=2)
        )

    def write_run_log(
        self,
        script_name: str,
        stdout: str,
        stderr: str,
        duration_ms: float,
        success: bool
    ) -> None:
        """
        Write execution log.

        Args:
            script_name: Name of the script
            stdout: Standard output
            stderr: Standard error
            duration_ms: Execution duration in milliseconds
            success: Whether execution succeeded
        """
        script_dir = self.get_script_dir(script_name)
        script_dir.mkdir(parents=True, exist_ok=True)

        log_lines = []
        log_lines.append(f"[grail] Execution {'succeeded' if success else 'failed'}")
        log_lines.append(f"[grail] Duration: {duration_ms:.2f}ms")
        log_lines.append("")

        if stdout:
            log_lines.append("[stdout]")
            log_lines.append(stdout)
            log_lines.append("")

        if stderr:
            log_lines.append("[stderr]")
            log_lines.append(stderr)

        (script_dir / "run.log").write_text("\n".join(log_lines))

    def clean(self) -> None:
        """Remove the entire .grail/ directory."""
        import shutil
        if self.grail_dir.exists():
            shutil.rmtree(self.grail_dir)
```

### Testing/Validation

Create `tests/unit/test_artifacts.py`:

```python
"""Test artifacts manager."""
import json
from pathlib import Path

from grail.artifacts import ArtifactsManager
from grail._types import CheckResult, ExternalSpec, InputSpec, ParamSpec


def test_creates_directory_structure(tmp_path):
    """Should create .grail/<script>/ directory structure."""
    mgr = ArtifactsManager(tmp_path / ".grail")

    externals = {
        "test_func": ExternalSpec(
            name="test_func",
            is_async=True,
            parameters=[ParamSpec("x", "int", None)],
            return_type="str",
            docstring="Test",
            lineno=1,
            col_offset=0
        )
    }
    inputs = {
        "test_input": InputSpec(
            name="test_input",
            type_annotation="int",
            default=None,
            required=True,
            lineno=1,
            col_offset=0
        )
    }
    check_result = CheckResult(
        file="test.pym",
        valid=True,
        errors=[],
        warnings=[],
        info={}
    )

    mgr.write_script_artifacts(
        "test",
        "# stubs",
        "# code",
        check_result,
        externals,
        inputs
    )

    script_dir = tmp_path / ".grail" / "test"
    assert script_dir.exists()
    assert (script_dir / "stubs.pyi").exists()
    assert (script_dir / "monty_code.py").exists()
    assert (script_dir / "check.json").exists()
    assert (script_dir / "externals.json").exists()
    assert (script_dir / "inputs.json").exists()


def test_write_run_log(tmp_path):
    """Should write run.log with execution details."""
    mgr = ArtifactsManager(tmp_path / ".grail")

    mgr.write_run_log(
        "test",
        stdout="Hello world",
        stderr="",
        duration_ms=42.5,
        success=True
    )

    log_path = tmp_path / ".grail" / "test" / "run.log"
    assert log_path.exists()

    content = log_path.read_text()
    assert "succeeded" in content
    assert "42.50ms" in content
    assert "Hello world" in content


def test_clean_removes_directory(tmp_path):
    """Should remove entire .grail/ directory."""
    grail_dir = tmp_path / ".grail"
    grail_dir.mkdir()
    (grail_dir / "test.txt").write_text("test")

    mgr = ArtifactsManager(grail_dir)
    mgr.clean()

    assert not grail_dir.exists()


def test_json_artifacts_are_valid(tmp_path):
    """Generated JSON files should be valid JSON."""
    mgr = ArtifactsManager(tmp_path / ".grail")

    externals = {
        "func": ExternalSpec(
            "func", True, [ParamSpec("x", "int", 10)],
            "str", "Doc", 1, 0
        )
    }
    inputs = {"x": InputSpec("x", "int", None, True, 1, 0)}
    check_result = CheckResult("test.pym", True, [], [], {})

    mgr.write_script_artifacts("test", "stubs", "code", check_result, externals, inputs)

    # Should be able to parse JSON
    script_dir = tmp_path / ".grail" / "test"
    check_data = json.loads((script_dir / "check.json").read_text())
    externals_data = json.loads((script_dir / "externals.json").read_text())
    inputs_data = json.loads((script_dir / "inputs.json").read_text())

    assert check_data["valid"] is True
    assert len(externals_data["externals"]) == 1
    assert len(inputs_data["inputs"]) == 1
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_artifacts.py` passes
- [ ] All artifact files are created
- [ ] JSON files are valid
- [ ] Clean removes directory

---

## Step 10: Monty Integration - Test Calling Monty Directly

**Critical step**: Before building the full API, verify we can successfully call Monty.

### Work to be done

Create `tests/integration/test_monty_integration.py`:

```python
"""Test direct integration with Monty."""
import pytest

# This requires pydantic-monty to be installed
pytest.importorskip("pydantic_monty")

import pydantic_monty


@pytest.mark.integration
def test_basic_monty_execution():
    """Test calling Monty with simple code."""
    code = "x = 1 + 2\nx"

    m = pydantic_monty.Monty(code)
    result = pydantic_monty.run_monty(m, inputs={})

    assert result == 3


@pytest.mark.integration
async def test_monty_with_external_function():
    """Test Monty with external functions."""
    code = """
result = await double(x)
result
"""

    stubs = """
x: int

async def double(n: int) -> int:
    ...
"""

    async def double_impl(n: int) -> int:
        return n * 2

    m = pydantic_monty.Monty(code, type_check_stubs=stubs)
    result = await pydantic_monty.run_monty_async(
        m,
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    assert result == 10


@pytest.mark.integration
def test_monty_with_resource_limits():
    """Test Monty with resource limits."""
    code = "x = 1\nx"

    m = pydantic_monty.Monty(
        code,
        max_memory=1024 * 1024,  # 1MB
        max_duration_secs=1.0,
        max_recursion_depth=100
    )

    result = pydantic_monty.run_monty(m, inputs={})
    assert result == 1


@pytest.mark.integration
def test_monty_type_checking():
    """Test Monty's type checker integration."""
    code = """
result = await get_data("test")
result
"""

    stubs = """
async def get_data(id: str) -> dict:
    ...
"""

    # This should type-check successfully
    m = pydantic_monty.Monty(code, type_check=True, type_check_stubs=stubs)

    # Note: Actual execution would need the external function


@pytest.mark.integration
async def test_monty_error_handling():
    """Test that Monty errors can be caught and inspected."""
    code = "x = undefined_variable"

    m = pydantic_monty.Monty(code)

    with pytest.raises(Exception) as exc_info:
        await pydantic_monty.run_monty_async(m, inputs={})

    # Should get some kind of error about undefined variable
    assert "undefined" in str(exc_info.value).lower() or "name" in str(exc_info.value).lower()
```

Create `tests/integration/conftest.py`:

```python
"""Configuration for integration tests."""
import pytest


def pytest_configure(config):
    """Add integration marker."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires pydantic-monty)"
    )
```

**Validation checklist**:
- [ ] `pytest tests/integration/test_monty_integration.py -m integration` passes
- [ ] Can execute simple Monty code
- [ ] Can call Monty with external functions
- [ ] Can pass resource limits to Monty
- [ ] Can handle Monty errors
- [ ] Type checking integration works

**Note**: These tests require `pydantic-monty` to be installed. If not available, tests will be skipped.

---

## Summary - Steps 5-10 Complete

You now have:

✅ **Step 5**: Parser that extracts `@external` and `Input()` from AST
✅ **Step 6**: Checker that validates Monty compatibility
✅ **Step 7**: Stubs generator that creates `.pyi` files
✅ **Step 8**: Code generator that transforms `.pym` to Monty code
✅ **Step 9**: Artifacts manager for `.grail/` directory
✅ **Step 10**: Verified Monty integration works

**You're now ready for the next phase** (Steps 11-16):
- Step 11: GrailScript Class - The main API
- Step 12: CLI Commands - Command-line interface
- Step 13: Snapshot - Pause/resume wrapper
- Step 14: Public API - `__init__.py` exports
- Step 15: Integration Tests - Full workflow testing
- Step 16: Final Validation - Ship it!

The foundation is solid. The next steps will tie everything together into the complete grail library.

---

## Step 11: GrailScript Class - The Main API

**Purpose**: Implement the main `GrailScript` class that ties together parsing, checking, code generation, and Monty execution.

### Work to be done

Create `src/grail/script.py`:

```python
"""GrailScript - Main API for loading and executing .pym files."""
import asyncio
from pathlib import Path
from typing import Any, Callable
import time

try:
    import pydantic_monty
except ImportError:
    pydantic_monty = None

from grail._types import ExternalSpec, InputSpec, CheckResult, SourceMap
from grail.parser import parse_pym_file
from grail.checker import check_pym
from grail.stubs import generate_stubs
from grail.codegen import generate_monty_code
from grail.artifacts import ArtifactsManager
from grail.limits import merge_limits, parse_limits
from grail.errors import (
    InputError, ExternalError, ExecutionError,
    LimitError, OutputError
)


class GrailScript:
    """
    Main interface for loading and executing .pym files.

    This class encapsulates:
    - Parsed .pym file metadata
    - Generated Monty code and stubs
    - Validation results
    - Execution interface
    """

    def __init__(
        self,
        path: Path,
        externals: dict[str, ExternalSpec],
        inputs: dict[str, InputSpec],
        monty_code: str,
        stubs: str,
        source_map: SourceMap,
        limits: dict[str, Any] | None = None,
        files: dict[str, str | bytes] | None = None,
        grail_dir: Path | None = None,
    ):
        """
        Initialize GrailScript.

        Args:
            path: Path to original .pym file
            externals: External function specifications
            inputs: Input specifications
            monty_code: Generated Monty code
            stubs: Generated type stubs
            source_map: Line number mapping
            limits: Resource limits
            files: Virtual filesystem files
            grail_dir: Directory for artifacts (None disables)
        """
        self.path = path
        self.name = path.stem
        self.externals = externals
        self.inputs = inputs
        self.monty_code = monty_code
        self.stubs = stubs
        self.source_map = source_map
        self.limits = limits
        self.files = files
        self.grail_dir = grail_dir

        # Initialize artifacts manager if grail_dir is set
        self._artifacts = ArtifactsManager(grail_dir) if grail_dir else None

    def check(self) -> CheckResult:
        """
        Run validation checks on the script.

        Returns:
            CheckResult with errors, warnings, and info
        """
        # Re-parse and check
        parse_result = parse_pym_file(self.path)
        check_result = check_pym(parse_result)
        check_result.file = str(self.path)

        # Write check results to artifacts if enabled
        if self._artifacts:
            self._artifacts.write_script_artifacts(
                self.name,
                self.stubs,
                self.monty_code,
                check_result,
                self.externals,
                self.inputs
            )

        return check_result

    def _validate_inputs(self, inputs: dict[str, Any]) -> None:
        """
        Validate that provided inputs match declarations.

        Args:
            inputs: Runtime input values

        Raises:
            InputError: If validation fails
        """
        # Check for missing required inputs
        for name, spec in self.inputs.items():
            if spec.required and name not in inputs:
                raise InputError(
                    f"Missing required input: '{name}' (type: {spec.type_annotation})",
                    input_name=name
                )

        # Check for extra inputs (warn but don't fail)
        for name in inputs:
            if name not in self.inputs:
                print(f"Warning: Extra input '{name}' not declared in script")

    def _validate_externals(self, externals: dict[str, Callable]) -> None:
        """
        Validate that provided externals match declarations.

        Args:
            externals: Runtime external function implementations

        Raises:
            ExternalError: If validation fails
        """
        # Check for missing externals
        for name in self.externals:
            if name not in externals:
                raise ExternalError(
                    f"Missing external function: '{name}'",
                    function_name=name
                )

        # Check for extra externals (warn but don't fail)
        for name in externals:
            if name not in self.externals:
                print(f"Warning: Extra external '{name}' not declared in script")

    def _prepare_monty_limits(self, override_limits: dict[str, Any] | None) -> dict[str, Any]:
        """
        Merge and parse limits for Monty.

        Args:
            override_limits: Runtime limit overrides

        Returns:
            Parsed limits dict ready for Monty
        """
        return merge_limits(self.limits, override_limits)

    def _prepare_monty_files(self, override_files: dict[str, str | bytes] | None):
        """
        Prepare files for Monty's OSAccess.

        Args:
            override_files: Runtime file overrides

        Returns:
            OSAccess object or None
        """
        if pydantic_monty is None:
            return None

        files = override_files if override_files is not None else self.files
        if not files:
            return None

        # Convert dict to Monty's MemoryFile + OSAccess
        memory_files = []
        for path, content in files.items():
            memory_files.append(pydantic_monty.MemoryFile(path, content=content))

        return pydantic_monty.OSAccess(memory_files)

    def _map_error_to_pym(self, error: Exception) -> ExecutionError:
        """
        Map Monty error to .pym file line numbers.

        Args:
            error: Original error from Monty

        Returns:
            ExecutionError with mapped line numbers
        """
        # Extract error message
        error_msg = str(error)

        # Try to extract line number from Monty error
        # (This is simplified - real implementation would parse Monty's traceback)
        lineno = None

        # Check if it's a limit error
        if "memory" in error_msg.lower() or "limit" in error_msg.lower():
            return LimitError(error_msg)

        return ExecutionError(
            error_msg,
            lineno=lineno,
            source_context=None,
            suggestion=None
        )

    async def run(
        self,
        inputs: dict[str, Any] | None = None,
        externals: dict[str, Callable] | None = None,
        output_model: type | None = None,
        files: dict[str, str | bytes] | None = None,
        limits: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute the script in Monty.

        Args:
            inputs: Input values
            externals: External function implementations
            output_model: Optional Pydantic model for output validation
            files: Override files from load()
            limits: Override limits from load()

        Returns:
            Result of script execution

        Raises:
            InputError: Missing or invalid inputs
            ExternalError: Missing external functions
            ExecutionError: Monty runtime error
            OutputError: Output validation failed
        """
        if pydantic_monty is None:
            raise RuntimeError("pydantic-monty not installed")

        inputs = inputs or {}
        externals = externals or {}

        # Validate inputs and externals
        self._validate_inputs(inputs)
        self._validate_externals(externals)

        # Prepare Monty configuration
        parsed_limits = self._prepare_monty_limits(limits)
        os_access = self._prepare_monty_files(files)

        # Create Monty instance
        monty = pydantic_monty.Monty(
            self.monty_code,
            type_check=True,
            type_check_stubs=self.stubs,
            **parsed_limits
        )

        # Execute
        start_time = time.time()
        try:
            result = await pydantic_monty.run_monty_async(
                monty,
                inputs=inputs,
                externals=externals,
                os_access=os_access
            )
            success = True
            error_msg = None
        except Exception as e:
            success = False
            error_msg = str(e)
            mapped_error = self._map_error_to_pym(e)

            # Write error log
            if self._artifacts:
                duration_ms = (time.time() - start_time) * 1000
                self._artifacts.write_run_log(
                    self.name,
                    stdout="",
                    stderr=str(mapped_error),
                    duration_ms=duration_ms,
                    success=False
                )

            raise mapped_error

        duration_ms = (time.time() - start_time) * 1000

        # Write success log
        if self._artifacts:
            self._artifacts.write_run_log(
                self.name,
                stdout=f"Result: {result}",
                stderr="",
                duration_ms=duration_ms,
                success=True
            )

        # Validate output if model provided
        if output_model is not None:
            try:
                result = output_model(**result) if isinstance(result, dict) else output_model(result)
            except Exception as e:
                raise OutputError(
                    f"Output validation failed: {e}",
                    validation_errors=e
                )

        return result

    def run_sync(
        self,
        inputs: dict[str, Any] | None = None,
        externals: dict[str, Callable] | None = None,
        **kwargs
    ) -> Any:
        """
        Synchronous wrapper around run().

        Args:
            inputs: Input values
            externals: External function implementations
            **kwargs: Additional arguments for run()

        Returns:
            Result of script execution
        """
        return asyncio.run(self.run(inputs, externals, **kwargs))

    def start(
        self,
        inputs: dict[str, Any] | None = None,
        externals: dict[str, Callable] | None = None,
    ):
        """
        Begin resumable execution (pause/resume pattern).

        Args:
            inputs: Input values
            externals: External function implementations

        Returns:
            Snapshot object
        """
        # Import here to avoid circular dependency
        from grail.snapshot import Snapshot

        if pydantic_monty is None:
            raise RuntimeError("pydantic-monty not installed")

        inputs = inputs or {}
        externals = externals or {}

        # Validate inputs and externals
        self._validate_inputs(inputs)
        self._validate_externals(externals)

        # Create Monty instance
        monty = pydantic_monty.Monty(
            self.monty_code,
            type_check=True,
            type_check_stubs=self.stubs,
        )

        # Start execution (this will pause on first external call)
        monty_snapshot = pydantic_monty.start_monty(monty, inputs=inputs)

        return Snapshot(monty_snapshot, self.source_map, externals)


def load(
    path: str | Path,
    limits: dict[str, Any] | None = None,
    files: dict[str, str | bytes] | None = None,
    grail_dir: str | Path | None = ".grail",
) -> GrailScript:
    """
    Load and parse a .pym file.

    Args:
        path: Path to .pym file
        limits: Resource limits
        files: Virtual filesystem files
        grail_dir: Directory for artifacts (None disables)

    Returns:
        GrailScript instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If file has syntax errors
        CheckError: If declarations are malformed
    """
    path = Path(path)

    # Parse the file
    parse_result = parse_pym_file(path)

    # Run validation checks
    check_result = check_pym(parse_result)
    check_result.file = str(path)

    # Generate stubs
    stubs = generate_stubs(parse_result.externals, parse_result.inputs)

    # Generate Monty code
    monty_code, source_map = generate_monty_code(parse_result)

    # Setup grail_dir
    grail_dir_path = Path(grail_dir) if grail_dir else None

    # Write artifacts
    if grail_dir_path:
        artifacts = ArtifactsManager(grail_dir_path)
        artifacts.write_script_artifacts(
            path.stem,
            stubs,
            monty_code,
            check_result,
            parse_result.externals,
            parse_result.inputs
        )

    return GrailScript(
        path=path,
        externals=parse_result.externals,
        inputs=parse_result.inputs,
        monty_code=monty_code,
        stubs=stubs,
        source_map=source_map,
        limits=limits,
        files=files,
        grail_dir=grail_dir_path,
    )


async def run(code: str, inputs: dict[str, Any] | None = None) -> Any:
    """
    Execute inline Monty code (escape hatch for simple cases).

    Args:
        code: Monty code to execute
        inputs: Input values

    Returns:
        Result of code execution
    """
    if pydantic_monty is None:
        raise RuntimeError("pydantic-monty not installed")

    inputs = inputs or {}

    monty = pydantic_monty.Monty(code)
    result = await pydantic_monty.run_monty_async(monty, inputs=inputs)
    return result
```

### Testing/Validation

Create `tests/unit/test_script.py`:

```python
"""Test GrailScript class."""
import pytest
from pathlib import Path

from grail.script import load
from grail.errors import InputError, ExternalError

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_load_pym_file():
    """Should load and parse .pym file."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    assert script.name == "simple"
    assert "double" in script.externals
    assert "x" in script.inputs
    assert len(script.monty_code) > 0
    assert len(script.stubs) > 0


def test_check_returns_result():
    """Should return CheckResult."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)
    result = script.check()

    assert result.valid is True
    assert result.file == str(FIXTURES_DIR / "simple.pym")


def test_validate_inputs_missing_required():
    """Should raise InputError for missing required input."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    with pytest.raises(InputError, match="Missing required input"):
        script._validate_inputs({})


def test_validate_inputs_extra_input_warns(capsys):
    """Should warn for extra inputs."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    script._validate_inputs({"x": 1, "extra": 2})
    captured = capsys.readouterr()
    assert "Extra input 'extra'" in captured.out


def test_validate_externals_missing():
    """Should raise ExternalError for missing external."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    with pytest.raises(ExternalError, match="Missing external function"):
        script._validate_externals({})


def test_validate_externals_extra_warns(capsys):
    """Should warn for extra externals."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    script._validate_externals({"double": lambda x: x*2, "extra": lambda: None})
    captured = capsys.readouterr()
    assert "Extra external 'extra'" in captured.out


@pytest.mark.integration
async def test_run_simple_script():
    """Should execute simple script."""
    pytest.importorskip("pydantic_monty")

    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    async def double_impl(n: int) -> int:
        return n * 2

    result = await script.run(
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    assert result == 10


@pytest.mark.integration
def test_run_sync():
    """Should execute script synchronously."""
    pytest.importorskip("pydantic_monty")

    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    async def double_impl(n: int) -> int:
        return n * 2

    result = script.run_sync(
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    assert result == 10


def test_load_with_limits():
    """Should accept limits parameter."""
    script = load(
        FIXTURES_DIR / "simple.pym",
        limits={"max_memory": "8mb"},
        grail_dir=None
    )

    assert script.limits == {"max_memory": "8mb"}


def test_load_with_files():
    """Should accept files parameter."""
    script = load(
        FIXTURES_DIR / "simple.pym",
        files={"/data/test.txt": "content"},
        grail_dir=None
    )

    assert script.files == {"/data/test.txt": "content"}


def test_load_creates_artifacts(tmp_path):
    """Should create artifacts in grail_dir."""
    script = load(
        FIXTURES_DIR / "simple.pym",
        grail_dir=tmp_path / ".grail"
    )

    artifacts_dir = tmp_path / ".grail" / "simple"
    assert artifacts_dir.exists()
    assert (artifacts_dir / "stubs.pyi").exists()
    assert (artifacts_dir / "monty_code.py").exists()
    assert (artifacts_dir / "check.json").exists()
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_script.py` passes
- [ ] Can load .pym files successfully
- [ ] Validation works for inputs and externals
- [ ] Integration tests with Monty pass
- [ ] Artifacts are created correctly
- [ ] Limits and files are handled properly

---

## Step 12: CLI Commands

**Purpose**: Implement the command-line interface for grail tooling.

### Work to be done

Create `src/grail/cli.py`:

```python
"""Command-line interface for grail."""
import argparse
import sys
import json
from pathlib import Path
from typing import List

from grail.script import load
from grail.artifacts import ArtifactsManager
from grail.limits import DEFAULT


def cmd_init(args):
    """Initialize grail project."""
    grail_dir = Path(".grail")
    grail_dir.mkdir(exist_ok=True)

    # Add to .gitignore if it exists
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if ".grail/" not in content:
            with gitignore.open("a") as f:
                f.write("\n# Grail artifacts\n.grail/\n")
            print("✓ Added .grail/ to .gitignore")

    # Create sample .pym file
    sample_pym = Path("example.pym")
    if not sample_pym.exists():
        sample_pym.write_text("""from grail import external, Input
from typing import Any

# Declare inputs
name: str = Input("name")

# Declare external functions
@external
async def greet(name: str) -> str:
    '''Generate a greeting message.'''
    ...

# Execute
message = await greet(name)
{"greeting": message}
""")
        print("✓ Created example.pym")

    print("\n✓ Grail initialized!")
    print("\nNext steps:")
    print("  1. Edit example.pym")
    print("  2. Run: grail check example.pym")
    print("  3. Create a host file and run: grail run example.pym --host host.py")


def cmd_check(args):
    """Check .pym files for Monty compatibility."""
    # Find files to check
    if args.files:
        files = [Path(f) for f in args.files]
    else:
        # Find all .pym files recursively
        files = list(Path.cwd().rglob("*.pym"))

    if not files:
        print("No .pym files found")
        return 1

    results = []
    for file_path in files:
        try:
            script = load(file_path, grail_dir=None)
            result = script.check()
            results.append((file_path, result))
        except Exception as e:
            print(f"{file_path}: ERROR - {e}")
            return 1

    # Output results
    if args.format == "json":
        # JSON output for CI
        output = []
        for file_path, result in results:
            output.append({
                "file": str(file_path),
                "valid": result.valid,
                "errors": [
                    {
                        "line": e.lineno,
                        "column": e.col_offset,
                        "code": e.code,
                        "message": e.message,
                        "suggestion": e.suggestion
                    }
                    for e in result.errors
                ],
                "warnings": [
                    {
                        "line": w.lineno,
                        "column": w.col_offset,
                        "code": w.code,
                        "message": w.message
                    }
                    for w in result.warnings
                ],
                "info": result.info
            })
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        passed = 0
        failed = 0

        for file_path, result in results:
            if result.valid and (not args.strict or not result.warnings):
                print(f"{file_path}: OK ({result.info['externals_count']} externals, "
                      f"{result.info['inputs_count']} inputs, "
                      f"{len(result.errors)} errors, {len(result.warnings)} warnings)")
                passed += 1
            else:
                print(f"{file_path}: FAIL")
                failed += 1

                for error in result.errors:
                    print(f"  {file_path}:{error.lineno}:{error.col_offset}: "
                          f"{error.code} {error.message}")

                if args.strict:
                    for warning in result.warnings:
                        print(f"  {file_path}:{warning.lineno}:{warning.col_offset}: "
                              f"{warning.code} {warning.message}")

        print(f"\nChecked {len(files)} files: {passed} passed, {failed} failed")

        if failed > 0:
            return 1

    return 0


def cmd_run(args):
    """Run a .pym file with a host file."""
    import asyncio
    import importlib.util

    # Load the .pym script
    script_path = Path(args.file)
    if not script_path.exists():
        print(f"Error: {script_path} not found")
        return 1

    # Load host file if provided
    if args.host:
        host_path = Path(args.host)
        if not host_path.exists():
            print(f"Error: Host file {host_path} not found")
            return 1

        # Import host module
        spec = importlib.util.spec_from_file_location("host", host_path)
        host_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(host_module)

        # Run host's main()
        if hasattr(host_module, "main"):
            if asyncio.iscoroutinefunction(host_module.main):
                asyncio.run(host_module.main())
            else:
                host_module.main()
        else:
            print("Error: Host file must define a main() function")
            return 1
    else:
        print("Error: --host <host.py> is required")
        return 1

    return 0


def cmd_watch(args):
    """Watch .pym files and re-run check on changes."""
    try:
        import watchfiles
    except ImportError:
        print("Error: watchfiles not installed. Install with: pip install watchfiles")
        return 1

    watch_dir = Path(args.dir) if args.dir else Path.cwd()

    print(f"Watching {watch_dir} for .pym file changes...")
    print("Press Ctrl+C to stop")

    # Initial check
    print("\n=== Initial check ===")
    cmd_check(argparse.Namespace(files=None, format="text", strict=False))

    # Watch for changes
    for changes in watchfiles.watch(watch_dir, recursive=True):
        # Filter for .pym files
        pym_changes = [c for c in changes if c[1].endswith(".pym")]
        if pym_changes:
            print(f"\n=== Changes detected ===")
            cmd_check(argparse.Namespace(files=None, format="text", strict=False))


def cmd_clean(args):
    """Remove .grail/ directory."""
    grail_dir = Path(".grail")

    if grail_dir.exists():
        mgr = ArtifactsManager(grail_dir)
        mgr.clean()
        print("✓ Removed .grail/")
    else:
        print(".grail/ does not exist")

    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Grail - Transparent Python for Monty",
        prog="grail"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # grail init
    parser_init = subparsers.add_parser("init", help="Initialize grail project")
    parser_init.set_defaults(func=cmd_init)

    # grail check
    parser_check = subparsers.add_parser("check", help="Check .pym files")
    parser_check.add_argument("files", nargs="*", help=".pym files to check")
    parser_check.add_argument("--format", choices=["text", "json"], default="text",
                             help="Output format")
    parser_check.add_argument("--strict", action="store_true",
                             help="Treat warnings as errors")
    parser_check.set_defaults(func=cmd_check)

    # grail run
    parser_run = subparsers.add_parser("run", help="Run a .pym file")
    parser_run.add_argument("file", help=".pym file to run")
    parser_run.add_argument("--host", help="Host Python file with main() function")
    parser_run.set_defaults(func=cmd_run)

    # grail watch
    parser_watch = subparsers.add_parser("watch", help="Watch and check .pym files")
    parser_watch.add_argument("dir", nargs="?", help="Directory to watch")
    parser_watch.set_defaults(func=cmd_watch)

    # grail clean
    parser_clean = subparsers.add_parser("clean", help="Remove .grail/ directory")
    parser_clean.set_defaults(func=cmd_clean)

    # Parse and execute
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

Create `setup.py` or update `pyproject.toml` with CLI entry point:

```toml
[project.scripts]
grail = "grail.cli:main"
```

### Testing/Validation

Create `tests/unit/test_cli.py`:

```python
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
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_cli.py` passes
- [ ] `grail init` creates project structure
- [ ] `grail check` validates .pym files
- [ ] `grail clean` removes artifacts
- [ ] CLI commands work from terminal

---

## Step 13: Snapshot - Pause/Resume Wrapper

**Purpose**: Thin wrapper over Monty's snapshot mechanism for pause/resume execution.

### Work to be done

Create `src/grail/snapshot.py`:

```python
"""Snapshot wrapper for pause/resume execution."""
from typing import Any, Callable

try:
    import pydantic_monty
except ImportError:
    pydantic_monty = None

from grail._types import SourceMap


class Snapshot:
    """
    Wrapper around Monty's snapshot for pause/resume execution.

    Allows inspecting external function calls and resuming with results.
    """

    def __init__(
        self,
        monty_snapshot: Any,
        source_map: SourceMap,
        externals: dict[str, Callable]
    ):
        """
        Initialize snapshot wrapper.

        Args:
            monty_snapshot: Underlying Monty snapshot
            source_map: Line number mapping
            externals: External function implementations
        """
        self._monty_snapshot = monty_snapshot
        self._source_map = source_map
        self._externals = externals

    @property
    def function_name(self) -> str:
        """Name of the external function being called."""
        return self._monty_snapshot.function_name

    @property
    def args(self) -> tuple[Any, ...]:
        """Positional arguments for the function call."""
        return self._monty_snapshot.args

    @property
    def kwargs(self) -> dict[str, Any]:
        """Keyword arguments for the function call."""
        return self._monty_snapshot.kwargs

    @property
    def is_complete(self) -> bool:
        """Whether execution has finished."""
        return self._monty_snapshot.is_complete

    @property
    def call_id(self) -> int:
        """Unique identifier for this external call."""
        return getattr(self._monty_snapshot, "call_id", 0)

    @property
    def value(self) -> Any:
        """
        Final result value (only available when is_complete=True).

        Returns:
            Final script result

        Raises:
            RuntimeError: If execution not complete
        """
        if not self.is_complete:
            raise RuntimeError("Execution not complete")
        return self._monty_snapshot.value

    def resume(
        self,
        return_value: Any = None,
        exception: BaseException | None = None
    ) -> "Snapshot":
        """
        Resume execution with a return value or exception.

        Args:
            return_value: Value to return from external function
            exception: Exception to raise in Monty

        Returns:
            New Snapshot if more calls pending, or final result
        """
        if exception is not None:
            next_snapshot = self._monty_snapshot.resume(exception=exception)
        else:
            next_snapshot = self._monty_snapshot.resume(return_value=return_value)

        return Snapshot(next_snapshot, self._source_map, self._externals)

    def dump(self) -> bytes:
        """
        Serialize snapshot to bytes.

        Returns:
            Serialized snapshot data
        """
        return self._monty_snapshot.dump()

    @staticmethod
    def load(data: bytes, source_map: SourceMap, externals: dict[str, Callable]) -> "Snapshot":
        """
        Deserialize snapshot from bytes.

        Args:
            data: Serialized snapshot data
            source_map: Line number mapping
            externals: External function implementations

        Returns:
            Restored Snapshot instance
        """
        if pydantic_monty is None:
            raise RuntimeError("pydantic-monty not installed")

        monty_snapshot = pydantic_monty.MontySnapshot.load(data)
        return Snapshot(monty_snapshot, source_map, externals)
```

### Testing/Validation

Create `tests/unit/test_snapshot.py`:

```python
"""Test snapshot pause/resume functionality."""
import pytest

pytest.importorskip("pydantic_monty")

from pathlib import Path
from grail.script import load

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.mark.integration
def test_snapshot_basic_properties():
    """Should expose snapshot properties."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    async def double_impl(n: int) -> int:
        return n * 2

    snapshot = script.start(
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    # Should be paused on first external call
    assert snapshot.function_name == "double"
    assert snapshot.args == () or 5 in snapshot.args or snapshot.kwargs.get("n") == 5
    assert snapshot.is_complete is False


@pytest.mark.integration
def test_snapshot_resume():
    """Should resume execution with return value."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    async def double_impl(n: int) -> int:
        return n * 2

    snapshot = script.start(
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    # Resume with return value
    result_snapshot = snapshot.resume(return_value=10)

    # Should be complete now
    assert result_snapshot.is_complete is True
    assert result_snapshot.value == 10


@pytest.mark.integration
def test_snapshot_serialization():
    """Should serialize and deserialize snapshots."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    async def double_impl(n: int) -> int:
        return n * 2

    snapshot = script.start(
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    # Serialize
    data = snapshot.dump()
    assert isinstance(data, bytes)

    # Deserialize
    from grail.snapshot import Snapshot
    restored = Snapshot.load(data, script.source_map, {"double": double_impl})

    assert restored.function_name == snapshot.function_name
    assert restored.is_complete == snapshot.is_complete
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_snapshot.py -m integration` passes
- [ ] Snapshot properties are accessible
- [ ] Resume works correctly
- [ ] Serialization/deserialization works

---

## Step 14: Public API - __init__.py Exports

**Purpose**: Define the public API surface (~15 symbols).

### Work to be done

Create `src/grail/__init__.py`:

```python
"""
Grail - Transparent Python for Monty.

A minimalist library for writing Monty code with full IDE support.
"""

__version__ = "2.0.0"

# Core functions
from grail.script import load, run

# Declarations (for .pym files)
from grail._external import external
from grail._input import Input

# Snapshot
from grail.snapshot import Snapshot

# Limits presets
from grail.limits import STRICT, DEFAULT, PERMISSIVE

# Errors
from grail.errors import (
    GrailError,
    ParseError,
    CheckError,
    InputError,
    ExternalError,
    ExecutionError,
    LimitError,
    OutputError,
)

# Check result types
from grail._types import CheckResult, CheckMessage

# Define public API
__all__ = [
    # Core
    "load",
    "run",
    # Declarations
    "external",
    "Input",
    # Snapshot
    "Snapshot",
    # Limits
    "STRICT",
    "DEFAULT",
    "PERMISSIVE",
    # Errors
    "GrailError",
    "ParseError",
    "CheckError",
    "InputError",
    "ExternalError",
    "ExecutionError",
    "LimitError",
    "OutputError",
    # Check results
    "CheckResult",
    "CheckMessage",
]
```

### Testing/Validation

Create `tests/unit/test_public_api.py`:

```python
"""Test public API surface."""
import grail


def test_public_api_symbols():
    """Verify all public symbols are exported."""
    expected = {
        # Core
        "load",
        "run",
        # Declarations
        "external",
        "Input",
        # Snapshot
        "Snapshot",
        # Limits
        "STRICT",
        "DEFAULT",
        "PERMISSIVE",
        # Errors
        "GrailError",
        "ParseError",
        "CheckError",
        "InputError",
        "ExternalError",
        "ExecutionError",
        "LimitError",
        "OutputError",
        # Check results
        "CheckResult",
        "CheckMessage",
    }

    for symbol in expected:
        assert hasattr(grail, symbol), f"Missing public symbol: {symbol}"


def test_version_exists():
    """Should have __version__ attribute."""
    assert hasattr(grail, "__version__")
    assert isinstance(grail.__version__, str)


def test_all_list():
    """Should have __all__ list."""
    assert hasattr(grail, "__all__")
    assert isinstance(grail.__all__, list)
    assert len(grail.__all__) >= 15


def test_can_import_all():
    """Should be able to import all public symbols."""
    from grail import (
        load, run, external, Input, Snapshot,
        STRICT, DEFAULT, PERMISSIVE,
        GrailError, ParseError, CheckError, InputError,
        ExternalError, ExecutionError, LimitError, OutputError,
        CheckResult, CheckMessage
    )

    assert load is not None
    assert run is not None
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_public_api.py` passes
- [ ] All 15+ public symbols are exported
- [ ] __version__ is defined
- [ ] __all__ list is correct

---

## Step 15: Integration & E2E Tests

**Purpose**: Test complete workflows end-to-end.

### Work to be done

Create `tests/integration/test_end_to_end.py`:

```python
"""End-to-end integration tests."""
import pytest
from pathlib import Path
import tempfile

pytest.importorskip("pydantic_monty")

import grail


@pytest.mark.integration
async def test_full_workflow():
    """Test complete workflow: load -> check -> run."""
    # Create a temporary .pym file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pym', delete=False) as f:
        f.write("""
from grail import external, Input
from typing import Any

budget: float = Input("budget")
department: str = Input("department", default="Engineering")

@external
async def get_team_size(dept: str) -> int:
    '''Get team size for department.'''
    ...

@external
async def calculate_budget(size: int, per_person: float) -> float:
    '''Calculate total budget.'''
    ...

size = await get_team_size(department)
total = await calculate_budget(size, budget / 10)

{
    "department": department,
    "team_size": size,
    "total_budget": total,
    "over_budget": total > budget
}
""")
        pym_path = Path(f.name)

    try:
        # Load
        script = grail.load(pym_path, grail_dir=None)

        # Check
        check_result = script.check()
        assert check_result.valid is True

        # Run
        async def get_team_size_impl(dept: str) -> int:
            return 5

        async def calculate_budget_impl(size: int, per_person: float) -> float:
            return size * per_person

        result = await script.run(
            inputs={"budget": 1000.0, "department": "Engineering"},
            externals={
                "get_team_size": get_team_size_impl,
                "calculate_budget": calculate_budget_impl,
            }
        )

        assert result["department"] == "Engineering"
        assert result["team_size"] == 5
        assert result["total_budget"] == 500.0
        assert result["over_budget"] is False

    finally:
        pym_path.unlink()


@pytest.mark.integration
def test_inline_run():
    """Test grail.run() for inline code."""
    import asyncio

    result = asyncio.run(grail.run("x + y", inputs={"x": 1, "y": 2}))
    assert result == 3


@pytest.mark.integration
async def test_with_resource_limits():
    """Test execution with resource limits."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pym', delete=False) as f:
        f.write("""
from grail import Input

x: int = Input("x")

x * 2
""")
        pym_path = Path(f.name)

    try:
        script = grail.load(
            pym_path,
            limits=grail.STRICT,
            grail_dir=None
        )

        result = await script.run(inputs={"x": 5})
        assert result == 10

    finally:
        pym_path.unlink()


@pytest.mark.integration
async def test_pause_resume_workflow():
    """Test pause/resume execution pattern."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pym', delete=False) as f:
        f.write("""
from grail import external, Input

x: int = Input("x")

@external
async def add_one(n: int) -> int:
    ...

@external
async def double(n: int) -> int:
    ...

step1 = await add_one(x)
step2 = await double(step1)
step2
""")
        pym_path = Path(f.name)

    try:
        async def add_one_impl(n: int) -> int:
            return n + 1

        async def double_impl(n: int) -> int:
            return n * 2

        externals = {
            "add_one": add_one_impl,
            "double": double_impl,
        }

        script = grail.load(pym_path, grail_dir=None)
        snapshot = script.start(inputs={"x": 5}, externals=externals)

        # Execute pause/resume loop
        while not snapshot.is_complete:
            func_name = snapshot.function_name
            args = snapshot.args
            kwargs = snapshot.kwargs

            # Call the external function
            result = await externals[func_name](*args, **kwargs)
            snapshot = snapshot.resume(return_value=result)

        final_result = snapshot.value
        assert final_result == 12  # (5 + 1) * 2

    finally:
        pym_path.unlink()


@pytest.mark.integration
def test_error_handling():
    """Test that errors are properly caught and mapped."""
    import asyncio

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pym', delete=False) as f:
        f.write("""
from grail import Input

x: int = Input("x")

y = undefined_variable
""")
        pym_path = Path(f.name)

    try:
        script = grail.load(pym_path, grail_dir=None)

        with pytest.raises(grail.ExecutionError):
            asyncio.run(script.run(inputs={"x": 5}))

    finally:
        pym_path.unlink()
```

Create `tests/integration/test_artifacts.py`:

```python
"""Test artifact generation and management."""
import pytest
import tempfile
from pathlib import Path
import json

import grail


@pytest.mark.integration
def test_artifacts_created():
    """Test that artifacts are created correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create .pym file
        pym_file = tmpdir / "test.pym"
        pym_file.write_text("""
from grail import external, Input

x: int = Input("x")

@external
async def process(n: int) -> int:
    ...

await process(x)
""")

        # Load with artifacts enabled
        script = grail.load(pym_file, grail_dir=tmpdir / ".grail")

        # Check artifacts exist
        artifacts_dir = tmpdir / ".grail" / "test"
        assert artifacts_dir.exists()
        assert (artifacts_dir / "stubs.pyi").exists()
        assert (artifacts_dir / "monty_code.py").exists()
        assert (artifacts_dir / "check.json").exists()
        assert (artifacts_dir / "externals.json").exists()
        assert (artifacts_dir / "inputs.json").exists()

        # Verify JSON artifacts are valid
        check_data = json.loads((artifacts_dir / "check.json").read_text())
        assert "valid" in check_data

        externals_data = json.loads((artifacts_dir / "externals.json").read_text())
        assert "externals" in externals_data

        inputs_data = json.loads((artifacts_dir / "inputs.json").read_text())
        assert "inputs" in inputs_data
```

**Validation checklist**:
- [ ] `pytest tests/integration/ -m integration` passes
- [ ] Full workflow test works
- [ ] Pause/resume works end-to-end
- [ ] Error handling works correctly
- [ ] Artifacts are generated properly

---

## Step 16: Final Validation

**Purpose**: Ensure everything works together and the library is ready to ship.

### Work to be done

1. **Run all tests**:

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -m integration -v

# All tests
pytest tests/ -v
```

2. **Run linters and formatters**:

```bash
# Format code
ruff format src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/grail/
```

3. **Test CLI commands**:

```bash
# Install in development mode
pip install -e .

# Test CLI
grail --help
grail init
grail check
grail clean
```

4. **Build documentation** (optional):

```bash
# If using sphinx or similar
cd docs
make html
```

5. **Create release checklist**:

Create `RELEASE_CHECKLIST.md`:

```markdown
# Release Checklist

## Pre-Release

- [ ] All tests pass (unit + integration)
- [ ] Code is formatted with ruff
- [ ] No linter errors
- [ ] Type checking passes
- [ ] CLI commands work correctly
- [ ] Documentation is up to date
- [ ] CHANGELOG.md is updated
- [ ] Version bumped in __init__.py

## Testing

- [ ] Test in fresh virtual environment
- [ ] Test with pydantic-monty installed
- [ ] Test without pydantic-monty (should skip integration tests)
- [ ] Test on Python 3.10, 3.11, 3.12, 3.13
- [ ] Test CLI on Linux/macOS/Windows

## Release

- [ ] Tag release in git
- [ ] Build distributions: `python -m build`
- [ ] Upload to PyPI: `twine upload dist/*`
- [ ] Create GitHub release with notes
- [ ] Update documentation site

## Post-Release

- [ ] Verify package installs from PyPI
- [ ] Test example workflows
- [ ] Monitor for issues
```

6. **Create comprehensive example**:

Create `examples/expense_analysis/`:

```
examples/expense_analysis/
├── analysis.pym          # The Monty script
├── host.py              # Host implementation
├── data.py              # Mock data/external functions
└── README.md            # Usage instructions
```

**`examples/expense_analysis/analysis.pym`**:
```python
from grail import external, Input
from typing import Any

# Inputs
budget_limit: float = Input("budget_limit")
department: str = Input("department", default="Engineering")

# External functions
@external
async def get_team_members(department: str) -> dict[str, Any]:
    """Get list of team members for a department."""
    ...

@external
async def get_expenses(user_id: int) -> dict[str, Any]:
    """Get expense line items for a user."""
    ...

@external
async def get_custom_budget(user_id: int) -> dict[str, Any] | None:
    """Get custom budget for a user if they have one."""
    ...

# Analysis logic
team_data = await get_team_members(department=department)
members = team_data.get("members", [])

over_budget = []

for member in members:
    uid = member["id"]
    expenses = await get_expenses(user_id=uid)
    items = expenses.get("items", [])

    total = sum(item["amount"] for item in items)

    if total > budget_limit:
        custom = await get_custom_budget(user_id=uid)
        if custom is None or total > custom.get("limit", budget_limit):
            over_budget.append({
                "user_id": uid,
                "name": member["name"],
                "total": total,
                "over_by": total - budget_limit
            })

{
    "analyzed": len(members),
    "over_budget_count": len(over_budget),
    "details": over_budget,
}
```

**`examples/expense_analysis/host.py`**:
```python
"""Host file for expense analysis example."""
import asyncio
from grail import load
from data import get_team_members, get_expenses, get_custom_budget


async def main():
    # Load the script
    script = load("analysis.pym")

    # Check for errors
    check_result = script.check()
    if not check_result.valid:
        print("Script has errors:")
        for error in check_result.errors:
            print(f"  Line {error.lineno}: {error.message}")
        return

    # Run the analysis
    result = await script.run(
        inputs={
            "budget_limit": 5000.0,
            "department": "Engineering"
        },
        externals={
            "get_team_members": get_team_members,
            "get_expenses": get_expenses,
            "get_custom_budget": get_custom_budget,
        },
    )

    print(f"Analyzed {result['analyzed']} team members")
    print(f"Found {result['over_budget_count']} over budget")

    if result['details']:
        print("\nDetails:")
        for item in result['details']:
            print(f"  {item['name']}: ${item['total']:.2f} (over by ${item['over_by']:.2f})")


if __name__ == "__main__":
    asyncio.run(main())
```

**`examples/expense_analysis/data.py`**:
```python
"""Mock data and external function implementations."""
from typing import Any


async def get_team_members(department: str) -> dict[str, Any]:
    """Mock implementation of get_team_members."""
    return {
        "members": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"},
        ]
    }


async def get_expenses(user_id: int) -> dict[str, Any]:
    """Mock implementation of get_expenses."""
    expenses = {
        1: [{"amount": 3000}, {"amount": 2500}],
        2: [{"amount": 1000}],
        3: [{"amount": 4000}, {"amount": 2000}],
    }

    return {
        "items": expenses.get(user_id, [])
    }


async def get_custom_budget(user_id: int) -> dict[str, Any] | None:
    """Mock implementation of get_custom_budget."""
    # Alice has a custom budget
    if user_id == 1:
        return {"limit": 6000.0}
    return None
```

7. **Final test run**:

```bash
# Test the example
cd examples/expense_analysis
python host.py

# Should output:
# Analyzed 3 team members
# Found 1 over budget
#
# Details:
#   Charlie: $6000.00 (over by $1000.00)
```

### Validation Checklist

**Code Quality**:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] No linter errors
- [ ] No type checking errors
- [ ] Code coverage > 80%

**Functionality**:
- [ ] Can load .pym files
- [ ] Parser extracts externals and inputs correctly
- [ ] Checker validates Monty compatibility
- [ ] Stubs are generated correctly
- [ ] Code generation works
- [ ] Artifacts are created
- [ ] Monty integration works
- [ ] Error handling and mapping works
- [ ] Limits work correctly
- [ ] Snapshot pause/resume works

**CLI**:
- [ ] `grail init` works
- [ ] `grail check` works
- [ ] `grail run` works
- [ ] `grail clean` works
- [ ] `grail watch` works (if watchfiles installed)

**Public API**:
- [ ] All 15+ symbols are exported
- [ ] Documentation is complete
- [ ] Examples work correctly

**Distribution**:
- [ ] Package builds successfully
- [ ] Can install from wheel
- [ ] CLI entry point works after install
- [ ] Dependencies are correct

---

## Completion Summary

Congratulations! You've successfully implemented Grail v2 from scratch. Here's what you've built:

### Core Components (Steps 0-10)
✅ **Step 0**: Grail declarations (`external`, `Input`)
✅ **Step 1**: Core type definitions
✅ **Step 2**: Error hierarchy
✅ **Step 3**: Resource limits parser
✅ **Step 4**: Test fixtures
✅ **Step 5**: Parser (AST extraction)
✅ **Step 6**: Checker (Monty compatibility)
✅ **Step 7**: Stubs generator
✅ **Step 8**: Code generator
✅ **Step 9**: Artifacts manager
✅ **Step 10**: Monty integration

### High-Level API (Steps 11-16)
✅ **Step 11**: GrailScript class (main API)
✅ **Step 12**: CLI commands
✅ **Step 13**: Snapshot wrapper
✅ **Step 14**: Public API exports
✅ **Step 15**: Integration tests
✅ **Step 16**: Final validation

### What You've Achieved

1. **~15 public symbols** - Clean, minimal API surface
2. **Full IDE support** - `.pym` files work in VSCode, PyCharm, etc.
3. **Pre-flight validation** - Catch errors before runtime
4. **Transparent execution** - All artifacts visible in `.grail/`
5. **Pause/resume** - First-class support for long-running workflows
6. **Type safety** - Full integration with Monty's type checker
7. **CLI tooling** - Complete command-line interface
8. **Comprehensive tests** - Unit + integration + E2E coverage

### Next Steps

1. **Ship it**: Follow the release checklist
2. **Gather feedback**: Share with early users
3. **Iterate**: Based on real-world usage
4. **Document**: Write tutorials and guides
5. **Extend**: Add features as Monty evolves

You've built a production-ready library that makes Monty programming delightful. Well done!
