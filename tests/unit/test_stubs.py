from __future__ import annotations

from pydantic import BaseModel

from grail.stubs import StubGenerator


class InModel(BaseModel):
    count: int
    name: str


class OutModel(BaseModel):
    total: int


def add(a: int, b: int) -> int:
    return a + b


def test_stub_generator_is_deterministic() -> None:
    stubs = StubGenerator().generate(input_model=InModel, output_model=OutModel, tools=[add])

    expected = "\n".join(
        [
            "from typing import TypedDict",
            "",
            "",
            "class InModel(TypedDict):",
            "    count: int",
            "    name: str",
            "",
            "class OutModel(TypedDict):",
            "    total: int",
            "",
            "def add(a: int, b: int) -> int: ...",
            "",
        ]
    )
    assert stubs == expected
