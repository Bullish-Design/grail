from __future__ import annotations

import sys
from types import SimpleNamespace

from grail.decorators import secure


class FakeMonty:
    def __init__(self, code: str, *, inputs: list[str], type_definitions: str) -> None:
        self.code = code


class FakeMontyError(Exception):
    pass


async def fake_run_monty_async(
    runner: FakeMonty, *, inputs: dict[str, object], tools: dict[str, object]
) -> dict[str, int]:
    payload = inputs["inputs"]
    return {"result": int(payload["a"]) + int(payload["b"])}


def test_secure_decorator_executes_with_inferred_models(monkeypatch) -> None:
    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=fake_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)

    @secure()
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 5) == 7
