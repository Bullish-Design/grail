from __future__ import annotations

from pydantic import BaseModel, ValidationError

from grail.errors import ErrorLocation, format_runtime_error, format_validation_error


class Nested(BaseModel):
    c: int


class Root(BaseModel):
    a: Nested


def test_format_validation_error_renders_dotted_paths() -> None:
    try:
        Root.model_validate({"a": {"c": "bad"}})
    except ValidationError as exc:
        message = format_validation_error("Input validation failed", exc)
    assert "a.c" in message


def test_format_runtime_error_includes_line_details() -> None:
    message = format_runtime_error(
        category="Monty runtime error",
        exc=RuntimeError("boom"),
        location=ErrorLocation(line=4, column=2),
    )
    assert "line 4" in message
    assert "boom" in message
