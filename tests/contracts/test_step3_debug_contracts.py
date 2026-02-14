from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

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

    payload = Path("tests/fixtures/inputs/step3-debug.json").read_text(encoding="utf-8")
    expected_payload = Path("tests/fixtures/expected/debug/step3-debug.json").read_text(
        encoding="utf-8"
    )

    import json

    payload_json = json.loads(payload)
    expected = json.loads(expected_payload)

    ctx = MontyContext(ToolInput, output_model=ToolOutput, tools=[add], debug=True)
    result = ctx.execute(payload_json["code"], payload_json["inputs"])

    assert result.total == 6
    assert ctx.debug_payload["events"] == expected["events"]
    assert expected["stdout_fragment"] in ctx.debug_payload["stdout"]
    assert ctx.debug_payload["stderr"] == expected["stderr"]
    assert ctx.debug_payload["tool_calls"][0] == expected["tool_call"]
