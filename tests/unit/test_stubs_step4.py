from dataclasses import dataclass
from typing import NewType

from pydantic import BaseModel

from grail.stubs import StubGenerator

UserId = NewType("UserId", int)
Payload = dict[str, list[tuple[UserId, str | None]]]


@dataclass
class Profile:
    user_id: UserId
    tags: set[str]


class InputModel(BaseModel):
    profile: Profile


class OutputModel(BaseModel):
    result: Profile | None


def normalize(
    items: list[Payload | dict[str, list[tuple[UserId, str | None]]]],
) -> tuple[Profile | None, Payload]:
    return None, {}


def test_step4_stub_generation_handles_dataclass_and_nested_parameterized_annotations() -> None:
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
            "class InputModel(TypedDict):",
            "    profile: Profile",
            "",
            "class OutputModel(TypedDict):",
            "    result: Profile | None",
            "",
            (
                "def normalize(items: list[dict[str, list[tuple[UserId, str | None]]]])"
                " -> tuple[Profile | None, dict[str, list[tuple[UserId, str | None]]]]: ..."
            ),
            "",
        ]
    )

    assert actual == expected
