from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from grail.stubs import StubGenerator


class StubInput(BaseModel):
    value: int


class StubOutput(BaseModel):
    result: int


def tool_sync(value: int) -> int:
    return value


async def tool_async(value: int) -> int:
    return value


@pytest.mark.contract
@pytest.mark.unit
def test_step2_stub_snapshot_contract() -> None:
    actual = StubGenerator().generate(
        input_model=StubInput,
        output_model=StubOutput,
        tools=[tool_async, tool_sync],
    )
    expected_path = Path("tests/fixtures/expected/stubs/step2-basic.pyi")
    expected = expected_path.read_text(encoding="utf-8")

    assert actual == expected
