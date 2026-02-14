from __future__ import annotations

import pytest

from grail.tools import ToolRegistry


def add(a: int, b: int) -> int:
    return a + b


async def mul(a: int, b: int) -> int:
    return a * b


@pytest.mark.unit
def test_tool_registry_supports_sync_and_async() -> None:
    import asyncio

    registry = ToolRegistry([add, mul])

    assert registry.names == ("add", "mul")
    assert asyncio.run(registry.invoke("add", 2, 3)) == 5
    assert asyncio.run(registry.invoke("mul", 2, 3)) == 6


@pytest.mark.unit
def test_tool_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry([add])
    with pytest.raises(ValueError):
        registry.register(add)


@pytest.mark.unit
def test_tool_registry_unknown_tool_error() -> None:
    import asyncio

    registry = ToolRegistry([add])

    with pytest.raises(KeyError):
        asyncio.run(registry.invoke("missing", 1, 2))
