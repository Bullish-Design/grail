from __future__ import annotations

import pytest
from pydantic import BaseModel

pytest.importorskip("pydantic_monty")

from tests.helpers.io_contracts import assert_contract, load_expected, load_input

from grail.context import GrailValidationError, MontyContext


class ArithmeticInput(BaseModel):
    a: int
    b: int


class NestedUser(BaseModel):
    name: str


class NestedInput(BaseModel):
    user: NestedUser


class ValueInput(BaseModel):
    value: int


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(
    ("fixture_name", "model"),
    [
        ("step1-arithmetic", ArithmeticInput),
        ("step1-nested-model", NestedInput),
        ("step1-complex-return", ValueInput),
    ],
)
def test_step1_success_contracts(fixture_name: str, model: type[BaseModel]) -> None:
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)
    ctx = MontyContext(model)

    actual = {"result": ctx.execute(payload["code"], payload["inputs"])}

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )


@pytest.mark.contract
@pytest.mark.integration
def test_step1_validation_failure_contract() -> None:
    fixture_name = "step1-validation-failure"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)
    ctx = MontyContext(ValueInput)

    with pytest.raises(GrailValidationError) as exc_info:
        ctx.execute(payload["code"], payload["inputs"])

    actual = {"error_type": type(exc_info.value).__name__}
    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )
