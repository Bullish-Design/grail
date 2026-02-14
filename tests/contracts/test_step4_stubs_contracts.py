from dataclasses import dataclass
from pathlib import Path
from typing import NewType

import pytest
from pydantic import BaseModel

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
    actual = StubGenerator().generate(
        input_model=StubInput,
        output_model=StubOutput,
        tools=[transform],
    )
    expected_path = Path("tests/fixtures/expected/stubs/step4-complex-generics.pyi")
    expected = expected_path.read_text(encoding="utf-8")

    assert actual == expected
