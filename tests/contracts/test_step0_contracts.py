from __future__ import annotations

import asyncio

import pytest
from tests.helpers.io_contracts import assert_contract, load_expected, load_input


@pytest.mark.contract
@pytest.mark.integration
def test_smoke_expression_contract() -> None:
    monty = pytest.importorskip("pydantic_monty")

    fixture_name = "smoke-expression"
    payload = load_input(fixture_name)
    expected = load_expected(fixture_name)

    runner = monty.Monty(payload["expr"])
    actual = {"result": asyncio.run(monty.run_monty_async(runner))}

    assert_contract(
        fixture_name,
        expected=expected,
        actual=actual,
        input_payload=payload,
    )
