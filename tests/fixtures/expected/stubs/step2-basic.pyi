from typing import TypedDict


class StubInput(TypedDict):
    value: int

class StubOutput(TypedDict):
    result: int

def tool_async(value: int) -> int: ...

def tool_sync(value: int) -> int: ...
