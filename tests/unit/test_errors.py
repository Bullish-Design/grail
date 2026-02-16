"""Test error hierarchy."""

from grail.errors import (
    CheckError,
    ExecutionError,
    ExternalError,
    GrailError,
    InputError,
    LimitError,
    OutputError,
    ParseError,
)


def test_error_hierarchy() -> None:
    """All errors should inherit from GrailError."""
    assert issubclass(ParseError, GrailError)
    assert issubclass(CheckError, GrailError)
    assert issubclass(InputError, GrailError)
    assert issubclass(ExternalError, GrailError)
    assert issubclass(ExecutionError, GrailError)
    assert issubclass(LimitError, ExecutionError)
    assert issubclass(OutputError, GrailError)


def test_parse_error_formatting() -> None:
    """ParseError should format with line numbers."""
    err = ParseError("unexpected token", lineno=10, col_offset=5)
    assert "line 10" in str(err)
    assert "unexpected token" in str(err)


def test_execution_error_with_context() -> None:
    """ExecutionError should include source context."""
    err = ExecutionError(
        "NameError: undefined_var",
        lineno=22,
        source_context="  22 | if total > undefined_var:",
        suggestion="Check if variable is declared",
    )
    msg = str(err)
    assert "Line 22" in msg
    assert "undefined_var" in msg
    assert "Suggestion:" in msg


def test_limit_error_is_execution_error() -> None:
    """LimitError should be a subclass of ExecutionError."""
    err = LimitError("Memory limit exceeded", limit_type="memory")
    assert isinstance(err, ExecutionError)
    assert err.limit_type == "memory"
