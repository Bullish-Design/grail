from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from tests.helpers.io_contracts import (
    assert_contract,
    load_expected,
    load_input,
    resolve_contract_payload,
)

from grail.context import GrailOutputValidationError, MontyContext


class SnapshotInput(BaseModel):
    a: int
    b: int


class SnapshotOutput(BaseModel):
    total: int


class FakeMontyComplete:
    def __init__(self, output: Any) -> None:
        self.output = output


class FakeMontySnapshot:
    def __init__(
        self,
        *,
        function_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        final_output: Any,
    ) -> None:
        self.function_name = function_name
        self.args = args
        self.kwargs = kwargs
        self._final_output = final_output

    def dump(self) -> bytes:
        payload = {
            "function_name": self.function_name,
            "args": list(self.args),
            "kwargs": self.kwargs,
            "final_output": self._final_output,
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    def resume(self, *, return_value: int) -> FakeMontyComplete:
        output = self._final_output
        if isinstance(output, dict) and "total" in output:
            output = dict(output)
            output["total"] = int(return_value)
        return FakeMontyComplete(output)

    @classmethod
    def load(cls, payload: bytes, **_: Any) -> FakeMontySnapshot:
        item = json.loads(payload.decode("utf-8"))
        return cls(
            function_name=str(item["function_name"]),
            args=tuple(item["args"]),
            kwargs=dict(item["kwargs"]),
            final_output=item["final_output"],
        )


class FakeMonty:
    def __init__(self, code: str, **_: Any) -> None:
        self.code = code

    def start(self, *, inputs: dict[str, Any], **_: Any) -> FakeMontySnapshot:
        values = inputs["inputs"]
        return FakeMontySnapshot(
            function_name="add",
            args=(int(values["a"]), int(values["b"])),
            kwargs={},
            final_output={"total": int(values["a"]) + int(values["b"])},
        )


class FakeMontyError(Exception):
    pass


@pytest.fixture
def fake_monty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontySnapshot=FakeMontySnapshot,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=None,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)


@pytest.mark.contract
@pytest.mark.unit
def test_step4_pause_resume_contract(fake_monty: None) -> None:
    del fake_monty
    fixture_name = "step4-pause-resume"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)

    ctx = MontyContext(SnapshotInput, output_model=SnapshotOutput, debug=True)
    snapshot = asyncio.run(ctx.start(payload["code"], payload["inputs"]))
    completed = snapshot.resume(return_value=payload["resume_return_value"])

    actual = resolve_contract_payload(
        output={
            "paused": {
                "function_name": snapshot.function_name,
                "args": list(snapshot.args or ()),
                "kwargs": snapshot.kwargs or {},
            },
            "result": completed.output.model_dump(mode="python"),
        }
    )

    assert_contract(fixture_name, expected=expected, actual=actual, input_payload=payload)


@pytest.mark.contract
@pytest.mark.unit
def test_step4_dump_load_binary_integrity_contract(fake_monty: None) -> None:
    del fake_monty
    fixture_name = "step4-dump-load"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)

    ctx = MontyContext(SnapshotInput, output_model=SnapshotOutput)
    snapshot = asyncio.run(ctx.start(payload["code"], payload["inputs"]))
    data = snapshot.dump()
    restored = ctx.load_snapshot(data)

    actual = resolve_contract_payload(
        output={
            "dump_hex": data.hex(),
            "restored": {
                "function_name": restored.function_name,
                "args": list(restored.args or ()),
                "kwargs": restored.kwargs or {},
            },
        }
    )

    assert_contract(fixture_name, expected=expected, actual=actual, input_payload=payload)


@pytest.mark.contract
@pytest.mark.unit
def test_step4_restore_fresh_context_contract(fake_monty: None) -> None:
    del fake_monty
    fixture_name = "step4-fresh-context"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)

    first = MontyContext(SnapshotInput, output_model=SnapshotOutput, debug=True)
    paused = asyncio.run(first.start(payload["code"], payload["inputs"]))
    data = paused.dump()

    second = MontyContext(SnapshotInput, output_model=SnapshotOutput, debug=True)
    restored = second.load_snapshot(data)
    completed = restored.resume(return_value=payload["resume_return_value"])

    actual = resolve_contract_payload(
        output={
            "first_events": first.debug_payload["events"],
            "second_events": second.debug_payload["events"],
            "result": completed.output.model_dump(mode="python"),
        }
    )

    assert_contract(fixture_name, expected=expected, actual=actual, input_payload=payload)


@pytest.mark.unit
def test_step4_restored_snapshot_output_validation_parity(fake_monty: None) -> None:
    del fake_monty
    ctx = MontyContext(SnapshotInput, output_model=SnapshotOutput)
    payload = {
        "function_name": "add",
        "args": [1, 2],
        "kwargs": {},
        "final_output": "invalid",
    }
    restored = ctx.load_snapshot(json.dumps(payload).encode("utf-8"))

    with pytest.raises(GrailOutputValidationError):
        _ = restored.resume(return_value=3).output


@pytest.mark.unit
def test_step4_start_and_resume_resolves_registered_tools_by_symbol_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ToolAwareMonty:
        def __init__(self, code: str, **kwargs: Any) -> None:
            del code
            self._tools = kwargs.get("tools") or kwargs.get("functions") or kwargs.get("globals")

        def start(self, *, inputs: dict[str, Any], **_: Any) -> FakeMontySnapshot:
            if not isinstance(self._tools, dict):
                raise AssertionError("Expected constructor-injected tools mapping")
            add_fn = self._tools["add"]
            values = inputs["inputs"]
            return FakeMontySnapshot(
                function_name="add",
                args=(int(values["a"]), int(values["b"])),
                kwargs={},
                final_output={"total": add_fn(int(values["a"]), int(values["b"]))},
            )

    fake_module = SimpleNamespace(
        Monty=ToolAwareMonty,
        MontySnapshot=FakeMontySnapshot,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=None,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    def add(a: int, b: int) -> int:
        return a + b

    ctx = MontyContext(SnapshotInput, output_model=SnapshotOutput, tools=[add])
    snapshot = asyncio.run(ctx.start("{'total': add(inputs['a'], inputs['b'])}", {"a": 4, "b": 5}))

    assert snapshot.function_name == "add"
    assert snapshot.resume(return_value=9).output.total == 9
