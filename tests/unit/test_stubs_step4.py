from dataclasses import dataclass
from typing import NewType

from pydantic import BaseModel
from typing_extensions import TypeAliasType

from grail.stubs import StubGenerator

UserId = NewType("UserId", int)
Payload = TypeAliasType("Payload", dict[str, list[tuple[UserId, str | None]]])
MaybeManyPayloads = TypeAliasType("MaybeManyPayloads", Payload | list[Payload])


@dataclass
class Profile:
    user_id: UserId
    tags: set[str]


@dataclass
class Envelope:
    profile: Profile
    payloads: MaybeManyPayloads


class InputModel(BaseModel):
    payload: MaybeManyPayloads


class OutputModel(BaseModel):
    result: Envelope | None


def normalize(
    items: list[MaybeManyPayloads],
) -> tuple[Envelope | None, MaybeManyPayloads]:
    return None, {}


def test_step4_stub_generation_renders_deterministic_nested_generics_and_custom_types() -> None:
    actual = StubGenerator().generate(
        input_model=InputModel,
        output_model=OutputModel,
        tools=[normalize],
    )

    expected = "\n".join(
        [
            "from typing import TypedDict, NewType",
            "",
            "",
            "UserId = NewType(\"UserId\", int)",
            "",
            "class Profile:",
            "    user_id: UserId",
            "    tags: set[str]",
            "",
            "Payload = dict[str, list[tuple[UserId, str | None]]]",
            "",
            "MaybeManyPayloads = Payload | list[Payload]",
            "",
            "class Envelope:",
            "    profile: Profile",
            "    payloads: MaybeManyPayloads",
            "",
            "class InputModel(TypedDict):",
            "    payload: MaybeManyPayloads",
            "",
            "class OutputModel(TypedDict):",
            "    result: Envelope | None",
            "",
            (
                "def normalize(items: list[MaybeManyPayloads])"
                " -> tuple[Envelope | None, MaybeManyPayloads]: ..."
            ),
            "",
        ]
    )

    assert actual == expected


def _legacy_generate_uncached(
    generator: StubGenerator,
    *,
    input_model: type[BaseModel],
    output_model: type[BaseModel] | None,
    tools: list,
) -> str:
    generator._reset()
    generator._collect_model_annotations(input_model)
    if output_model is not None:
        generator._collect_model_annotations(output_model)
    for tool in tools:
        generator._collect_tool_annotations(tool)

    import_names = ["TypedDict"]
    if generator._uses_any:
        import_names.insert(0, "Any")
    if generator._uses_callable:
        import_names.append("Callable")
    if generator._new_types:
        import_names.append("NewType")

    lines = [f"from typing import {', '.join(import_names)}", ""]
    custom_blocks = generator._render_custom_definitions(
        skip_model_names={
            input_model.__name__,
            output_model.__name__ if output_model is not None else "",
        }
    )
    if custom_blocks:
        lines.extend(["", "\n\n".join(custom_blocks)])

    lines.extend(["", generator._model_stub(input_model)])
    if output_model is not None:
        lines.extend(["", generator._model_stub(output_model)])

    for tool in sorted(tools, key=lambda item: item.__name__):
        lines.extend(["", generator._tool_stub(tool)])

    return "\n".join(lines).strip() + "\n"


def test_step4_generate_matches_legacy_output_assembly() -> None:
    actual = StubGenerator().generate(
        input_model=InputModel,
        output_model=OutputModel,
        tools=[normalize],
    )

    expected = _legacy_generate_uncached(
        StubGenerator(),
        input_model=InputModel,
        output_model=OutputModel,
        tools=[normalize],
    )

    assert actual == expected
