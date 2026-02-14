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


def test_stub_generator_uses_cache_for_repeated_calls(monkeypatch) -> None:
    StubGenerator._cache.clear()
    generator = StubGenerator()
    call_count = 0
    original_generate_uncached = StubGenerator._generate_uncached

    def counting_generate_uncached(self, **kwargs) -> str:
        nonlocal call_count
        call_count += 1
        return original_generate_uncached(self, **kwargs)

    monkeypatch.setattr(StubGenerator, "_generate_uncached", counting_generate_uncached)

    first = generator.generate(input_model=InModel, output_model=OutModel, tools=[add])
    second = generator.generate(input_model=InModel, output_model=OutModel, tools=[add])

    assert first == second
    assert call_count == 1


def test_stub_generator_cache_key_changes_with_tool_signature() -> None:
    StubGenerator._cache.clear()

    def add(a: int, b: int) -> int:
        return a + b

    def add_with_extra(a: int, b: int, c: int) -> int:
        return a + b + c

    generator = StubGenerator()
    initial = generator.generate(input_model=InModel, output_model=OutModel, tools=[add])
    updated = generator.generate(
        input_model=InModel,
        output_model=OutModel,
        tools=[add_with_extra],
    )

    assert initial != updated
    assert len(StubGenerator._cache) == 2
