from dataclasses import dataclass
from typing import NewType

import pytest
from pydantic import BaseModel
from tests.helpers.io_contracts import assert_contract, load_expected_text, load_input
from typing_extensions import TypeAliasType

from grail.stubs import StubGenerator

UserId = NewType("UserId", int)
AliasPayload = TypeAliasType("AliasPayload", dict[str, list[tuple[UserId, str | None]]])
ContractPayload = TypeAliasType("ContractPayload", AliasPayload | list[AliasPayload])


@dataclass
class ContractProfile:
    user_id: UserId
    aliases: tuple[str, ...]


@dataclass
class ContractEnvelope:
    profile: ContractProfile
    payload: ContractPayload


class StubInput(BaseModel):
    payload: ContractPayload


class StubOutput(BaseModel):
    summary: ContractEnvelope | None


def transform(
    payload: ContractPayload,
) -> tuple[ContractEnvelope | None, ContractPayload]:
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
