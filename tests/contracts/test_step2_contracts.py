from __future__ import annotations

import pytest
from pydantic import BaseModel

pytest.importorskip("pydantic_monty")

from tests.helpers.io_contracts import assert_contract, load_expected, load_input

from grail.context import GrailExecutionError, GrailOutputValidationError, MontyContext


class ToolInput(BaseModel):
    a: int
    b: int


class ToolOutput(BaseModel):
    total: int


def add(a: int, b: int) -> int:
    return a + b


async def mul(a: int, b: int) -> int:
    return a * b


def fail_tool(a: int, b: int) -> int:
    raise RuntimeError("boom")


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(
    ("fixture_name", "tools", "output_model"),
    [
        ("step2-sync-tool", [add], ToolOutput),
        ("step2-async-tool", [mul], ToolOutput),
    ],
)
def test_step2_tool_success_contracts(
    fixture_name: str,
    tools: list,
    output_model: type[BaseModel],
) -> None:
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)
    ctx = MontyContext(ToolInput, output_model=output_model, tools=tools)

    actual = {
        "result": ctx.execute(payload["code"], payload["inputs"]).model_dump(mode="python"),
        "tool_calls": payload["tool_calls"],
    }

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )


@pytest.mark.contract
@pytest.mark.integration
def test_step2_tool_exception_contract() -> None:
    fixture_name = "step2-tool-exception"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)
    ctx = MontyContext(ToolInput, output_model=ToolOutput, tools=[fail_tool])

    with pytest.raises(GrailExecutionError) as exc_info:
        ctx.execute(payload["code"], payload["inputs"])

    actual = {"error_type": type(exc_info.value).__name__, "tool_calls": payload["tool_calls"]}

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )


@pytest.mark.contract
@pytest.mark.integration
def test_step2_unknown_tool_contract() -> None:
    fixture_name = "step2-unknown-tool"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)
    ctx = MontyContext(ToolInput, output_model=ToolOutput, tools=[add])

    with pytest.raises(GrailExecutionError) as exc_info:
        ctx.execute(payload["code"], payload["inputs"])

    actual = {"error_type": type(exc_info.value).__name__, "tool_calls": payload["tool_calls"]}

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )


@pytest.mark.contract
@pytest.mark.integration
def test_step2_output_validation_failure_contract() -> None:
    fixture_name = "step2-output-validation-failure"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)
    ctx = MontyContext(ToolInput, output_model=ToolOutput, tools=[add])

    with pytest.raises(GrailOutputValidationError) as exc_info:
        ctx.execute(payload["code"], payload["inputs"])

    actual = {"error_type": type(exc_info.value).__name__, "tool_calls": payload["tool_calls"]}

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )
