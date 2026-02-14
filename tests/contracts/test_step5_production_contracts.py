from __future__ import annotations

import io
import runpy
import sys
from contextlib import redirect_stdout
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

from grail import MetricsCollector, MontyContext, RetryPolicy, StructuredLogger


class InModel(BaseModel):
    value: int


class OutModel(BaseModel):
    total: int


class FakeMonty:
    def __init__(self, code: str, **_: Any) -> None:
        self.code = code


class FakeMontyError(Exception):
    pass


async def fake_run_monty_async(*_: Any, **__: Any) -> dict[str, int]:
    raise FakeMontyError("boom")


@pytest.mark.contract
@pytest.mark.unit
def test_step5_resilience_fallback_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=fake_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    fixture_name = "production/step5-resilience-fallback"
    payload = load_input(fixture_name)
    expected = load_expected("step5-resilience-fallback", section="production")

    events: list[dict[str, Any]] = []
    ctx = MontyContext(
        InModel,
        output_model=OutModel,
        logger=StructuredLogger(events.append),
        metrics=MetricsCollector(),
    )
    result = ctx.execute_with_resilience(
        payload["code"],
        payload["inputs"],
        retry_policy=RetryPolicy(**payload["retry_policy"], retry_on=(Exception,)),
        fallback=payload["fallback"],
    )

    actual = resolve_contract_payload(output={
        "attempts_logged": len([e for e in events if e.get("event") == "grail.execution.attempt"]),
        "fallback_total": result["total"],
        "metrics_fallback_count": ctx.metrics.snapshot()["counters"].get("executions_fallback", 0),
    })
    assert_contract(
        "step5-resilience-fallback",
        expected=expected,
        actual=actual,
        input_payload=payload,
    )


@pytest.mark.contract
@pytest.mark.unit
def test_step5_example_basic_calculator_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_ok_run_monty_async(*_: Any, **kwargs: Any) -> dict[str, int]:
        values = kwargs["inputs"]["inputs"]
        return {"total": int(values["a"]) + int(values["b"])}

    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=fake_ok_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    fixture_name = "examples/basic-calculator"
    payload = load_input(fixture_name)
    expected = load_expected("basic-calculator", section="examples")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        runpy.run_path(payload["script"], run_name="__main__")

    actual = resolve_contract_payload(output={"stdout": buffer.getvalue().strip()})
    assert_contract(
        "basic-calculator",
        expected=expected,
        actual=actual,
        input_payload=payload,
    )
