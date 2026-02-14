from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from tests.helpers.io_contracts import (
    assert_contract,
    load_expected,
    load_input,
    resolve_contract_payload,
)

from grail.context import MontyContext


class ToolInput(BaseModel):
    a: int
    b: int


class ToolOutput(BaseModel):
    total: int


def add(a: int, b: int) -> int:
    return a + b


class FakeMonty:
    def __init__(self, code: str, **_: object) -> None:
        self.code = code


class FakeMontyError(Exception):
    pass


async def fake_run_monty_async(
    runner: FakeMonty,
    *,
    inputs: dict[str, object],
    tools: dict[str, object],
) -> dict[str, int]:
    print("hello")
    total = await tools["add"](int(inputs["inputs"]["a"]), int(inputs["inputs"]["b"]))
    return {"total": total}


@pytest.mark.contract
@pytest.mark.unit
def test_step3_debug_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=fake_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    fixture_name = "step3-debug"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name, section="debug")

    ctx = MontyContext(ToolInput, output_model=ToolOutput, tools=[add], debug=True)
    result = ctx.execute(payload["code"], payload["inputs"])

    actual = resolve_contract_payload(
        output={
            "result_total": result.total,
            "events": ctx.debug_payload["events"],
            "stdout": ctx.debug_payload["stdout"],
            "stderr": ctx.debug_payload["stderr"],
            "tool_call": ctx.debug_payload["tool_calls"][0],
        }
    )

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )
