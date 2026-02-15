# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

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

