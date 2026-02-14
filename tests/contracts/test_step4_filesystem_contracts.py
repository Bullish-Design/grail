from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from tests.helpers.io_contracts import (
    assert_contract,
    load_expected,
    load_input,
    resolve_contract_payload,
)

from grail.context import GrailExecutionError, MontyContext
from grail.filesystem import FilePermission, callback_filesystem, memory_filesystem


class FilesystemInput(BaseModel):
    operations: list[dict[str, Any]]
    inspect_paths: list[str]


class FakeMonty:
    def __init__(self, code: str, **_: Any) -> None:
        self.code = code


class FakeMontyError(Exception):
    pass


async def fake_run_monty_async(
    runner: FakeMonty,
    *,
    inputs: dict[str, Any],
    limits: dict[str, Any],
    external_functions: dict[str, Any],
    os: Any,
) -> dict[str, Any]:
    del runner, limits, external_functions
    reads: list[str] = []

    for operation in inputs["inputs"]["operations"]:
        path = Path(operation["path"])
        kind = operation["op"]
        if kind == "read_text":
            reads.append(os.path_read_text(path))
        elif kind == "write_text":
            os.path_write_text(path, operation["data"])
        else:
            raise ValueError(f"Unsupported operation: {kind}")

    final: dict[str, str] = {}
    for path_text in inputs["inputs"]["inspect_paths"]:
        path = Path(path_text)
        if os.path_exists(path):
            final[path_text] = os.path_read_text(path)

    return {"reads": reads, "final_files": final}


def _permissions(payload: dict[str, Any]) -> dict[str, FilePermission]:
    return {path: FilePermission(value) for path, value in payload.get("permissions", {}).items()}


def _build_filesystem(payload: dict[str, Any]) -> Any:
    permissions = _permissions(payload)
    default_permission = FilePermission(payload.get("default_permission", "deny"))

    if payload["backend"] == "memory":
        return memory_filesystem(
            payload.get("files", {}),
            permissions=permissions,
            default_permission=default_permission,
            root_dir=payload.get("root_dir", "/"),
        )

    callback_storage: dict[str, str | bytes] = dict(payload.get("files", {}))

    def make_read(path_text: str) -> Any:
        def _read(_: Any) -> str | bytes:
            return callback_storage[path_text]

        return _read

    def make_write(path_text: str) -> Any:
        def _write(_: Any, data: str | bytes) -> None:
            callback_storage[path_text] = data

        return _write

    callbacks = {
        path: (make_read(path), make_write(path))
        for path in payload.get("callback_files", payload.get("files", {})).keys()
    }

    return callback_filesystem(
        callbacks,
        permissions=permissions,
        default_permission=default_permission,
        root_dir=payload.get("root_dir", "/"),
    )


@pytest.fixture
def fake_monty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = SimpleNamespace(
        Monty=FakeMonty,
        MontyError=FakeMontyError,
        MontyRuntimeError=FakeMontyError,
        run_monty_async=fake_run_monty_async,
    )
    monkeypatch.setitem(sys.modules, "pydantic_monty", fake_module)


@pytest.mark.contract
@pytest.mark.unit
def test_step4_filesystem_fixtures_contract(fake_monty: None) -> None:
    del fake_monty
    name = "step4-filesystem-seeded"
    payload = load_input(name)
    expected = load_expected(name)

    ctx = MontyContext(FilesystemInput, filesystem=_build_filesystem(payload))
    actual = resolve_contract_payload(output=ctx.execute(payload["code"], payload["inputs"]))

    assert_contract(name, expected=expected, actual=actual, input_payload=payload)


@pytest.mark.contract
@pytest.mark.unit
def test_step4_filesystem_permission_denied_contract(fake_monty: None) -> None:
    del fake_monty
    name = "step4-filesystem-permission-denied"
    payload = load_input(name)
    expected = load_expected(name)

    ctx = MontyContext(FilesystemInput, filesystem=_build_filesystem(payload))

    with pytest.raises(GrailExecutionError) as exc_info:
        _ = ctx.execute(payload["code"], payload["inputs"])

    actual = resolve_contract_payload(error={"error": str(exc_info.value)})
    assert_contract(name, expected=expected, actual=actual, input_payload=payload)


@pytest.mark.contract
@pytest.mark.unit
def test_step4_filesystem_isolation_violation_contract(fake_monty: None) -> None:
    del fake_monty
    name = "step4-filesystem-isolation-violation"
    payload = load_input(name)
    expected = load_expected(name)

    ctx = MontyContext(FilesystemInput, filesystem=_build_filesystem(payload))

    with pytest.raises(GrailExecutionError) as exc_info:
        _ = ctx.execute(payload["code"], payload["inputs"])

    actual = resolve_contract_payload(error={"error": str(exc_info.value)})
    assert_contract(name, expected=expected, actual=actual, input_payload=payload)
