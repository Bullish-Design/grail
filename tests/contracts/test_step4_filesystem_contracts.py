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
from grail.filesystem import (
    FilePermission,
    GrailFilesystem,
    callback_filesystem,
    hooked_filesystem,
    memory_filesystem,
)


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


class _ResolveAwareOS:
    def __init__(self, *, absolute_map: dict[str, str] | None = None, resolve_map: dict[str, str] | None = None) -> None:
        self.absolute_map = absolute_map or {}
        self.resolve_map = resolve_map or {}

    def path_absolute(self, path: Path) -> str:
        return self.absolute_map.get(str(path), str(path))

    def path_resolve(self, path: Path) -> str:
        return self.resolve_map.get(str(path), str(path))


@pytest.mark.unit
def test_step4_filesystem_allows_symlink_resolving_within_root() -> None:
    filesystem = GrailFilesystem(
        _ResolveAwareOS(resolve_map={"/sandbox/link": "/sandbox/target"}),
        root_dir="/sandbox",
    )

    normalized = filesystem._normalize(Path("/sandbox/link"))

    assert normalized == Path("/sandbox/link")


@pytest.mark.unit
def test_step4_filesystem_denies_symlink_resolving_outside_root() -> None:
    filesystem = GrailFilesystem(
        _ResolveAwareOS(resolve_map={"/sandbox/link": "/etc/passwd"}),
        root_dir="/sandbox",
    )

    with pytest.raises(PermissionError, match="Path escapes filesystem root: /etc/passwd"):
        _ = filesystem._normalize(Path("/sandbox/link"))


@pytest.mark.unit
def test_step4_filesystem_denies_direct_parent_traversal() -> None:
    filesystem = GrailFilesystem(
        _ResolveAwareOS(absolute_map={"../secret": "/sandbox/../secret"}),
        root_dir="/sandbox",
    )

    with pytest.raises(PermissionError, match="Path escapes filesystem root: /sandbox/../secret"):
        _ = filesystem._normalize(Path("../secret"))


@pytest.mark.unit
def test_step4_hooked_filesystem_supports_seed_files_and_prefix_hooks() -> None:
    writes: list[tuple[Path, str | bytes]] = []

    filesystem = hooked_filesystem(
        files={"/sandbox/seed.txt": "seed"},
        read_hooks={"/sandbox": lambda path: f"hooked:{path.name}"},
        write_hooks={"/sandbox": lambda path, data: writes.append((path, data))},
        permissions={"/sandbox": FilePermission.WRITE},
        root_dir="/sandbox",
    )

    assert filesystem.path_read_text(Path("/sandbox/seed.txt")) == "hooked:seed.txt"
    assert filesystem.path_read_bytes(Path("/sandbox/seed.txt")) == b"hooked:seed.txt"

    written = filesystem.path_write_text(Path("/sandbox/new.txt"), "new-value")

    assert written == len("new-value")
    assert writes == [(Path("/sandbox/new.txt"), "new-value")]


@pytest.mark.unit
def test_step4_hooked_filesystem_uses_seed_content_without_read_hook() -> None:
    filesystem = hooked_filesystem(
        files={"/sandbox/seed.txt": "seed"},
        permissions={"/sandbox": FilePermission.READ},
        root_dir="/sandbox",
    )

    assert filesystem.path_read_text(Path("/sandbox/seed.txt")) == "seed"
