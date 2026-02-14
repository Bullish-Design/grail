from typing import TypedDict, NewType


UserId = NewType("UserId", int)

AliasPayload = dict[str, list[tuple[UserId, str | None]]]

class ContractProfile:
    user_id: UserId
    aliases: tuple[str, ...]

ContractPayload = AliasPayload | list[AliasPayload]

class ContractEnvelope:
    profile: ContractProfile
    payload: ContractPayload

class StubInput(TypedDict):
    payload: ContractPayload

class StubOutput(TypedDict):
    summary: ContractEnvelope | None

def transform(payload: ContractPayload) -> tuple[ContractEnvelope | None, ContractPayload]: ...
