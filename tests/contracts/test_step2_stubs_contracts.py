from __future__ import annotations

import pytest
from pydantic import BaseModel

from tests.helpers.io_contracts import assert_contract, load_expected_text, load_input

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
    fixture_name = "step2-basic"
    payload = load_input("step2-sync-tool")

    actual = StubGenerator().generate(
        input_model=StubInput,
        output_model=StubOutput,
        tools=[tool_async, tool_sync],
    )
    expected = load_expected_text(fixture_name, section="stubs")

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )
