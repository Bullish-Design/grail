from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from grail.context import (
    GrailExecutionError,
    GrailLimitError,
    GrailOutputValidationError,
    GrailValidationError,
    MontyContext,
)
from grail.resource_guard import ResourceGuard
from grail.types import merge_resource_limits


class UserInput(BaseModel):
    name: str
    count: int


class CountOutput(BaseModel):
    total: int


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


@pytest.mark.unit
def test_context_accepts_guard_object_for_limit_resolution() -> None:
    ctx = MontyContext(UserInput, guard=ResourceGuard(max_duration_secs=0.25))
    assert ctx.limits["max_duration_secs"] == 0.25


@pytest.mark.unit
def test_context_preserves_limits_precedence_over_guard_and_policy() -> None:
    ctx = MontyContext(
        UserInput,
        policy="strict",
        guard=ResourceGuard(max_duration_secs=0.4),
        limits={"max_duration_secs": 2.0},
    )
    assert ctx.limits["max_duration_secs"] == 2.0


@pytest.mark.unit
def test_output_validation_uses_output_model(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMonty:
        def __init__(self, code: str, *, inputs: list[str], type_definitions: str) -> None:
            self.code = code
            self.inputs = inputs
            self.type_definitions = type_definitions

    class FakeMontyError(Exception):
        pass

    async def fake_run_monty_async(
        runner: FakeMonty,
        *,
        inputs: dict[str, object],
        limits: dict[str, object],
        tools: dict[str, object],
    ) -> dict[str, int]:
        return {"total": 9}

    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=fake_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    ctx = MontyContext(UserInput, output_model=CountOutput)
    result = ctx.execute("ignored", {"name": "alice", "count": 2})

    assert isinstance(result, CountOutput)
    assert result.total == 9


@pytest.mark.unit
def test_output_validation_error_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMonty:
        def __init__(self, code: str, *, inputs: list[str], type_definitions: str) -> None:
            self.code = code
            self.inputs = inputs
            self.type_definitions = type_definitions

    class FakeMontyError(Exception):
        pass

    async def fake_run_monty_async(
        runner: FakeMonty,
        *,
        inputs: dict[str, object],
        limits: dict[str, object],
        tools: dict[str, object],
    ) -> dict[str, str]:
        return {"total": "bad"}

    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=fake_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    ctx = MontyContext(UserInput, output_model=CountOutput)

    with pytest.raises(GrailOutputValidationError):
        ctx.execute("ignored", {"name": "alice", "count": 2})
