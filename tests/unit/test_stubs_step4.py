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
