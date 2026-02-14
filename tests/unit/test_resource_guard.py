from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from grail.context import GrailLimitError, MontyContext
from grail.resource_guard import ResourceGuard, ResourceUsageMetrics


class InputModel(BaseModel):
    value: int


@pytest.mark.unit
def test_resource_guard_validates_ranges() -> None:
    with pytest.raises(Exception):
        ResourceGuard(max_duration_secs=0)
    with pytest.raises(Exception):
        ResourceGuard(max_memory=100)


@pytest.mark.unit
def test_resource_guard_to_monty_limits_omits_none() -> None:
    guard = ResourceGuard(max_duration_secs=1.0, max_memory=5_000_000)
    payload = guard.to_monty_limits()
    assert payload == {"max_duration_secs": 1.0, "max_memory": 5_000_000}


@pytest.mark.unit
def test_resource_usage_metrics_accepts_runtime_payload() -> None:
    metrics = ResourceUsageMetrics.from_runtime_payload(
        {"max_duration_secs": 0.4, "max_memory": 1024 * 1024, "exceeded": ["max_memory"]}
    )
    assert metrics.max_duration_secs == 0.4
    assert metrics.exceeded == ["max_memory"]


@pytest.mark.unit
def test_context_exposes_runtime_metrics_from_result(monkeypatch: pytest.MonkeyPatch) -> None:
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
    ) -> dict[str, object]:
        return {
            "value": 2,
            "resource_metrics": {
                "max_duration_secs": 0.12,
                "max_memory": 1_000_000,
                "exceeded": [],
            },
        }

    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=fake_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    ctx = MontyContext(InputModel, debug=True)
    result = ctx.execute("ignored", {"value": 1})

    assert isinstance(result, dict)
    assert ctx.resource_metrics.max_duration_secs == 0.12
    assert ctx.debug_payload["resource_metrics"]["max_memory"] == 1_000_000


@pytest.mark.unit
def test_runtime_limit_violation_tracks_exceeded_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMonty:
        def __init__(self, code: str, *, inputs: list[str], type_definitions: str) -> None:
            self.code = code
            self.inputs = inputs
            self.type_definitions = type_definitions

    class FakeMontyError(Exception):
        pass

    class FakeMontyRuntimeError(FakeMontyError):
        pass

    async def fake_run_monty_async(
        runner: FakeMonty,
        *,
        inputs: dict[str, object],
        limits: dict[str, object],
        tools: dict[str, object],
    ) -> dict[str, object]:
        raise FakeMontyRuntimeError("limit exceeded")

    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyRuntimeError,
        run_monty_async=fake_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    ctx = MontyContext(InputModel)
    with pytest.raises(GrailLimitError):
        ctx.execute("ignored", {"value": 1})

    assert "runtime_limit" in ctx.resource_metrics.exceeded
