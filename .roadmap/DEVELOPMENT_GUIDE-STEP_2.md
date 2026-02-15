# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

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
