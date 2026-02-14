from dataclasses import dataclass
from typing import NewType

import pytest
from pydantic import BaseModel

from tests.helpers.io_contracts import assert_contract, load_expected_text, load_input

from grail.stubs import StubGenerator

UserId = NewType("UserId", int)
AliasPayload = dict[str, list[tuple[UserId, str | None]]]


@dataclass
class ContractProfile:
    user_id: UserId
    aliases: tuple[str, ...]


class StubInput(BaseModel):
    profile: ContractProfile


class StubOutput(BaseModel):
    summary: ContractProfile | None


def transform(
    payload: AliasPayload | list[AliasPayload],
) -> tuple[ContractProfile | None, AliasPayload]:
    return None, {}


@pytest.mark.contract
@pytest.mark.unit
def test_step4_stub_contract_dataclass_and_nested_annotations() -> None:
    fixture_name = "step4-complex-generics"
    payload = load_input("step4-fresh-context")

    actual = StubGenerator().generate(
        input_model=StubInput,
        output_model=StubOutput,
        tools=[transform],
    )
    expected = load_expected_text(fixture_name, section="stubs")

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )
