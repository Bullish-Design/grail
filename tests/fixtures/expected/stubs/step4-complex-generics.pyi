from typing import TypedDict, NewType


UserId = NewType("UserId", int)

class ContractProfile:
    user_id: UserId
    aliases: tuple[str, ...]

class StubInput(TypedDict):
    profile: ContractProfile

class StubOutput(TypedDict):
    summary: ContractProfile | None

def transform(payload: dict[str, list[tuple[UserId, str | None]]] | list[dict[str, list[tuple[UserId, str | None]]]]) -> tuple[ContractProfile | None, dict[str, list[tuple[UserId, str | None]]]]: ...
