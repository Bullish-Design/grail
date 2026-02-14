from __future__ import annotations

import pytest
from pydantic import BaseModel

from grail.context import GrailExecutionError, GrailLimitError, GrailValidationError, MontyContext
from grail.types import merge_resource_limits


class UserInput(BaseModel):
    name: str
    count: int


@pytest.mark.unit
def test_merge_resource_limits_overrides_defaults() -> None:
    merged = merge_resource_limits({"max_duration_secs": 3.0})
    assert merged["max_duration_secs"] == 3.0
    assert merged["max_memory"] > 0


@pytest.mark.unit
def test_validate_inputs_failure() -> None:
    ctx = MontyContext(UserInput)
    with pytest.raises(GrailValidationError):
        ctx._validate_inputs({"name": "alice", "count": "oops"})


@pytest.mark.unit
def test_execute_validates_inputs() -> None:
    pytest.importorskip("pydantic_monty")
    ctx = MontyContext(UserInput)
    result = ctx.execute("inputs['count'] + 1", {"name": "alice", "count": 2})
    assert result == 3


@pytest.mark.unit
def test_execute_malformed_code_maps_execution_error() -> None:
    pytest.importorskip("pydantic_monty")
    ctx = MontyContext(UserInput)
    with pytest.raises(GrailExecutionError):
        ctx.execute("inputs['count'] +", {"name": "alice", "count": 2})


@pytest.mark.unit
def test_execute_limit_failure_maps_limit_error() -> None:
    pytest.importorskip("pydantic_monty")
    ctx = MontyContext(UserInput, limits={"max_recursion_depth": 30})
    with pytest.raises(GrailLimitError):
        ctx.execute(
            "\n".join(
                [
                    "def recurse(n):",
                    "    return recurse(n + 1)",
                    "recurse(0)",
                ]
            ),
            {"name": "alice", "count": 2},
        )
