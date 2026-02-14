from __future__ import annotations

import asyncio

import pytest


@pytest.mark.integration
def test_pydantic_monty_smoke() -> None:
    monty = pytest.importorskip("pydantic_monty")

    runner = monty.Monty("1 + 1")
    result = asyncio.run(monty.run_monty_async(runner))
    assert result == 2
