# Grail v2 — Comprehensive Code Review

**Reviewer:** AI Code Review Agent
**Date:** 2026-02-25
**Scope:** Full codebase review against `GRAIL_CONCEPT.md` spec and `pydantic_monty` API
**Verdict:** Not production-ready. Multiple correctness bugs, spec divergences, and missing features.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Spec Compliance Matrix](#2-spec-compliance-matrix)
3. [Monty API Alignment](#3-monty-api-alignment)
4. [Bugs & Correctness Issues](#4-bugs--correctness-issues)
5. [Missing Features](#5-missing-features)
6. [Production Readiness](#6-production-readiness)
7. [Test Coverage Gaps](#7-test-coverage-gaps)
8. [Architecture & Code Quality](#8-architecture--code-quality)
9. [Prioritized Recommendations](#9-prioritized-recommendations)

---

## 1. Executive Summary

Grail v2 is architecturally sound — the module structure, error hierarchy, and public API surface closely follow the spec. The core load/check/run pipeline works for simple cases. However, the implementation has **critical correctness bugs** that will cause failures in non-trivial usage:

- The snapshot resume protocol is **wrong** for async external functions
- Code generation **mutates the shared AST in-place**, corrupting subsequent operations on the same `ParseResult`
- The source map construction is **fragile** — it relies on `zip(ast.walk(...), ast.walk(...))` across two different ASTs
- Error mapping **ignores structured traceback data** from Monty in favor of regex parsing
- Several spec-defined checker errors and warnings are **missing or implemented in the wrong layer**

The library needs focused fixes before it can be relied upon. The good news: most issues are localized and fixable without architectural changes.

### Severity Summary

| Severity | Count | Examples |
|----------|-------|---------|
| Critical (will crash/corrupt) | 4 | AST mutation, snapshot async protocol, source map fragility, `MontyFutureSnapshot` unhandled |
| High (incorrect behavior) | 5 | Error mapping ignores `Frame`, E006/E007/E008 crash vs structured errors, missing W002/W003, `MemoryFile` kwarg |
| Medium (spec divergence) | 6 | Version mismatch, `Snapshot.load()` signature, no `print_callback`, no `dataclass_registry`, `run_sync` event loop, CLI `cmd_run` |
| Low (quality/polish) | 4 | `pydantic` dependency underused, no `gc_interval` limit, `py.typed` marker missing, `from typing` stripping |

---

## 2. Spec Compliance Matrix

### 2.1 `.pym` File Format (Spec Section 2)

| Requirement | Status | Notes |
|-------------|--------|-------|
| Valid Python 3.10+ | **Pass** | Parser uses `ast.parse()` |
| `@external` with full type annotations | **Pass** | `parser.py:82-100` validates annotations |
| `@external` body must be `...` | **Pass** | `parser.py:113-141` validates ellipsis body |
| `Input()` must have type annotation | **Pass** | `parser.py:173` raises `CheckError` |
| Only `grail` and `typing` imports allowed | **Pass** | `checker.py:99-128` (E005) |
| Final expression as return value | **Pass** | Monty handles this natively |

### 2.2 `.grail/` Directory (Spec Section 3)

| Artifact | Status | Notes |
|----------|--------|-------|
| `stubs.pyi` | **Pass** | `artifacts.py` writes it |
| `check.json` | **Pass** | Written with correct structure |
| `externals.json` | **Pass** | Written with correct structure |
| `inputs.json` | **Pass** | Written with correct structure |
| `monty_code.py` | **Pass** | Written with header comment |
| `run.log` | **Pass** | Written on execution |

### 2.3 CLI Tooling (Spec Section 4)

| Command | Status | Notes |
|---------|--------|-------|
| `grail check [files...]` | **Partial** | Works but E006/E007/E008 crash instead of structured errors. `--format json` implemented. `--strict` implemented. |
| `grail run <file.pym> --host` | **Partial** | Loads host but **does not pass the script** to the host's `main()` — see [4.7](#47-cli-cmd_run-doesnt-use-the-loaded-script) |
| `grail init` | **Pass** | Creates `.grail/`, sample `.pym`, updates `.gitignore` |
| `grail watch` | **Pass** | Implemented with `watchfiles` dependency |
| `grail clean` | **Pass** | Removes `.grail/` |
| `--input key=value` flag | **Pass** | Parses and passes to host |

### 2.4 Host-Side Python API (Spec Section 5)

| Feature | Status | Notes |
|---------|--------|-------|
| `grail.load(path, **options) -> GrailScript` | **Pass** | |
| `await script.run(inputs, externals, **kwargs)` | **Pass** | |
| `script.run_sync(...)` | **Partial** | Uses `asyncio.run()` which fails in existing event loops — see [4.8](#48-run_sync-event-loop-issues) |
| `script.check() -> CheckResult` | **Pass** | |
| `script.start(inputs, externals) -> Snapshot` | **Partial** | Does not handle `MontyFutureSnapshot` return from `monty.start()` |
| `grail.run(code, inputs)` | **Partial** | Async-only, no sync wrapper — see [5.5](#55-no-sync-wrapper-for-grailrun) |
| `output_model` parameter | **Pass** | Validates with Pydantic |
| `files` override at `run()` | **Pass** | |
| `limits` override at `run()` | **Pass** | |

### 2.5 Resource Limits (Spec Section 6)

| Feature | Status | Notes |
|---------|--------|-------|
| `max_memory` (str/int) | **Pass** | Parsed correctly |
| `max_duration` (str/float) | **Pass** | Parsed correctly |
| `max_recursion` (int) | **Pass** | Mapped to `max_recursion_depth` |
| `max_allocations` (int) | **Missing** | Spec lists it, `parse_limits()` doesn't handle it |
| Named presets (STRICT, DEFAULT, PERMISSIVE) | **Pass** | Plain dicts as spec requires |
| Runtime override | **Pass** | `merge_limits()` works |

### 2.6 Filesystem Access (Spec Section 7)

| Feature | Status | Notes |
|---------|--------|-------|
| `files` dict -> `OSAccess` | **Pass** | Correctly creates `MemoryFile` + `OSAccess` |
| `MemoryFile` construction | **Bug** | Uses `content=content` keyword — see [4.5](#45-memoryfile-constructor-argument-style) |

### 2.7 Type Checking & Stubs (Spec Section 8)

| Feature | Status | Notes |
|---------|--------|-------|
| Stub generation from `@external` | **Pass** | |
| Stub generation from `Input()` | **Pass** | |
| `type_check=True` passed to Monty | **Pass** | |
| `py.typed` marker | **Missing** | Listed in spec's package structure but not present |

### 2.8 Error Reporting (Spec Section 9)

| Feature | Status | Notes |
|---------|--------|-------|
| Error hierarchy | **Pass** | Matches spec exactly |
| Line mapping back to `.pym` | **Partial** | Uses regex instead of `Frame` objects — see [4.6](#46-error-mapping-ignores-structured-traceback-data) |
| Source context display | **Pass** | `ExecutionError._build_context_display()` works |
| Full traceback in `run.log` | **Partial** | Only writes `str(error)`, not full Monty traceback |

### 2.9 Pause/Resume Snapshots (Spec Section 10)

| Feature | Status | Notes |
|---------|--------|-------|
| `script.start()` -> Snapshot | **Partial** | Doesn't handle `MontyFutureSnapshot` return type |
| `snapshot.resume()` | **Bug** | Async resume protocol is wrong — see [4.1](#41-snapshot-resume-protocol-is-wrong-for-async-externals) |
| `snapshot.dump()` -> bytes | **Pass** | Direct pass-through |
| `Snapshot.load(data)` | **Divergence** | Spec says `Snapshot.load(data) -> Snapshot`, implementation requires `source_map` and `externals` — see [4.3](#43-snapshotload-signature-diverges-from-spec) |
| `snapshot.is_complete` | **Partial** | Only checks `MontyComplete`, not `MontyFutureSnapshot` |
| `snapshot.value` | **Pass** | Returns `output` from `MontyComplete` |

### 2.10 Checker Error Codes (Spec Section 4)

| Code | Severity | Spec Description | Status |
|------|----------|-----------------|--------|
| E001 | Error | Class definitions | **Pass** — `checker.py:35` |
| E002 | Error | Generator/yield | **Pass** — `checker.py:48,61` |
| E003 | Error | `with` statements | **Pass** — `checker.py:74` |
| E004 | Error | `match` statements | **Pass** — `checker.py:87` |
| E005 | Error | Forbidden imports | **Pass** — `checker.py:99,115` |
| E006 | Error | Missing type annotations on `@external` | **Wrong layer** — Caught by `parser.py` as `CheckError` exception, not as structured `CheckMessage` |
| E007 | Error | `@external` with non-ellipsis body | **Wrong layer** — Same issue as E006 |
| E008 | Error | `Input()` without type annotation | **Wrong layer** — Same issue as E006 |
| E1xx | Error | Monty type checker errors | **Not implemented** — Grail doesn't relay `MontyTypingError` diagnostics through `check()` |
| W001 | Warning | Bare dict/list as return value | **Pass** — `checker.py:154` |
| W002 | Warning | Unused `@external` function | **Missing** — Not implemented |
| W003 | Warning | Unused `Input()` variable | **Missing** — Not implemented |
| W004 | Warning | Very long script (>200 lines) | **Pass** — `checker.py:169` |

---

## 3. Monty API Alignment

### 3.1 `Monty` Constructor

**Grail calls** (`script.py:236-243`):
```python
monty = pydantic_monty.Monty(
    self.monty_code,
    type_check=True,
    type_check_stubs=self.stubs,
    inputs=list(self.inputs.keys()),
    external_functions=list(self.externals.keys()),
)
```

**Monty accepts** (`_monty.pyi:21-39`):
```python
Monty(
    code: str,
    script_name: str = 'main.py',
    inputs: list[str] | None = None,
    external_functions: list[str] | None = None,
    type_check: bool = False,
    type_check_stubs: str | None = None,
    dataclass_registry: list[type] | None = None,  # <-- NOT USED BY GRAIL
)
```

**Issues:**
- `dataclass_registry` is never exposed. Users cannot register dataclass types for proper output handling.
- `script_name` is never set. Monty defaults to `'main.py'`, but grail could pass the `.pym` filename for better tracebacks.

### 3.2 `run_monty_async()`

**Grail calls** (`script.py:254-260`):
```python
result = await pydantic_monty.run_monty_async(
    monty,
    inputs=inputs,
    external_functions=externals,
    os=os_access,
    limits=parsed_limits,
)
```

**Monty accepts** (`__init__.py:54-60`):
```python
run_monty_async(
    monty_runner: Monty,
    inputs: dict[str, Any] | None = None,
    external_functions: dict[str, Callable[..., Any]] | None = None,
    limits: ResourceLimits | None = None,
    print_callback: Callable[[Literal['stdout'], str], None] | None = None,  # <-- NOT USED
    os: AbstractOS | None = None,
)
```

**Issues:**
- `print_callback` is never passed. There is no way to capture `print()` output from Monty scripts. The `run.log` artifact writes timing info but not script stdout.

### 3.3 `Monty.start()`

**Grail calls** (`script.py:317`):
```python
monty_snapshot = monty.start(inputs=inputs)
```

**Monty's `start()` signature** (`_monty.pyi:80-87`):
```python
def start(
    self,
    inputs: dict[str, Any] | None = None,
    limits: ResourceLimits | None = None,      # <-- NOT PASSED
    print_callback: ... | None = None,           # <-- NOT PASSED
) -> MontySnapshot | MontyFutureSnapshot | MontyComplete:
```

**Issues:**
- `limits` is not passed to `start()`. Snapshot execution is always unlimited.
- `print_callback` is not passed.
- Return type can be `MontyFutureSnapshot` or `MontyComplete`, but grail's `Snapshot.__init__` assumes it's always `MontySnapshot`.

### 3.4 `MontySnapshot.resume()`

**Monty's overloads** (`_monty.pyi:108-138`):
```python
def resume(self, *, return_value: Any) -> MontySnapshot | MontyFutureSnapshot | MontyComplete
def resume(self, *, exception: BaseException) -> ...
def resume(self, *, future: EllipsisType) -> ...
```

**Grail's snapshot.py uses** (lines 116-122):
```python
future_snapshot = self._monty_snapshot.resume(future=...)
next_snapshot = future_snapshot.resume({call_id: {"return_value": return_value}})
```

This is **wrong** — see [4.1](#41-snapshot-resume-protocol-is-wrong-for-async-externals).

### 3.5 `MontyFutureSnapshot.resume()`

**Monty signature** (`_monty.pyi:186-190`):
```python
def resume(
    self,
    results: dict[int, ExternalResult],
) -> MontySnapshot | MontyFutureSnapshot | MontyComplete
```

Where `ExternalResult = ExternalReturnValue | ExternalException | ExternalFuture`.

Grail's snapshot code calls `future_snapshot.resume({call_id: {"return_value": return_value}})` which passes the correct dict shape, but **the intermediate state may not be a `MontyFutureSnapshot`** — `resume(future=...)` returns `MontySnapshot | MontyFutureSnapshot | MontyComplete`, and grail doesn't check which one it got back.

### 3.6 `MontyRuntimeError`

**Monty provides**:
```python
class MontyRuntimeError(MontyError):
    def traceback(self) -> list[Frame]   # Structured traceback with line/column/source_line
    def display(format=...) -> str       # Formatted error string
```

**Grail ignores** the structured traceback. Instead (`script.py:194-197`):
```python
match = re.search(r"line (\d+)", error_msg, re.IGNORECASE)
```

This is both less reliable and loses information (column, end_line, function_name, source_line).

### 3.7 `ResourceLimits` TypedDict

**Monty expects**:
```python
class ResourceLimits(TypedDict, total=False):
    max_allocations: int
    max_duration_secs: float
    max_memory: int
    gc_interval: int
    max_recursion_depth: int
```

**Grail produces** (from `parse_limits()`): a plain `dict` with correct keys (`max_memory`, `max_duration_secs`, `max_recursion_depth`) but:
- `max_allocations` is not parsed (spec mentions it but code ignores it)
- `gc_interval` is not exposed
- No type narrowing — the dict is `dict[str, Any]`, not `ResourceLimits`

### 3.8 Error Types

| Monty Error | Grail Handling |
|-------------|---------------|
| `MontyTypingError` | Caught in `script.py:244-250`, converted to `ExecutionError`. `display()` method not used. |
| `MontyRuntimeError` | Caught as generic `Exception`. `traceback()` and `display()` not used. |
| `MontySyntaxError` | Not explicitly caught — would fall through to generic handler. |

---

## 4. Bugs & Correctness Issues

### 4.1 Snapshot Resume Protocol is Wrong for Async Externals

**File:** `snapshot.py:104-122`

**The bug:** When an async external function is detected, the code does:

```python
call_id = self._monty_snapshot.call_id
future_snapshot = self._monty_snapshot.resume(future=...)
next_snapshot = future_snapshot.resume({call_id: {"return_value": return_value}})
```

**Problems:**

1. `resume(future=...)` can return `MontySnapshot | MontyFutureSnapshot | MontyComplete`. The code assumes it always returns something with a `.resume()` method that accepts a dict — but if it returns `MontySnapshot`, calling `.resume({...})` will fail because `MontySnapshot.resume()` expects keyword arguments (`return_value=`, `exception=`, or `future=`), not a positional dict.

2. The entire approach is wrong for the `Snapshot` API's purpose. The `snapshot.resume()` method receives the **already-computed** return value from the caller. The caller (the user code in the pause/resume loop) has already called the external function and gotten the result. There's no need for the future protocol at all — that protocol exists inside `run_monty_async()` where Monty dispatches async calls concurrently. In the manual pause/resume pattern, all calls are sequential by design.

3. The `asyncio.iscoroutinefunction()` check is meaningless here. The `resume()` method receives the return value, not the callable itself. Whether the external function is async or sync is irrelevant — the value is already computed by the time `resume()` is called.

**The fix:** `snapshot.resume()` should always use `self._monty_snapshot.resume(return_value=return_value)`, regardless of whether the external is async. The async/future protocol is an implementation detail of `run_monty_async()` and should not leak into the manual pause/resume API.

### 4.2 Code Generation Mutates the Shared AST In-Place

**File:** `codegen.py:68-72`

```python
stripper = GrailDeclarationStripper(external_names, input_names)
transformed = stripper.visit(parse_result.ast_module)  # MUTATES ast_module
```

`ast.NodeTransformer.visit()` modifies the tree **in-place**. The `transformed` variable is the same object as `parse_result.ast_module`. This means:

1. After `generate_monty_code()` runs, the `ParseResult.ast_module` is permanently altered — `@external` functions, `Input()` assignments, and `from grail import` statements have been removed from the AST.

2. In `load()` (`script.py:345-349`), the sequence is:
   ```python
   parse_result = parse_pym_file(path)
   check_result = check_pym(parse_result)  # Uses original AST
   stubs = generate_stubs(parse_result.externals, parse_result.inputs)
   monty_code, source_map = generate_monty_code(parse_result)  # MUTATES AST
   ```
   This happens to work because `check_pym()` runs before `generate_monty_code()`. But if anyone reorders these calls or reuses the `parse_result`, the AST is corrupted.

3. `GrailScript.check()` (`script.py:89`) re-parses from the file, so it avoids the bug. But the underlying design is fragile.

**The fix:** Deep-copy the AST before transforming it:
```python
import copy
transformed = stripper.visit(copy.deepcopy(parse_result.ast_module))
```

### 4.3 `Snapshot.load()` Signature Diverges from Spec

**File:** `snapshot.py:140`

**Spec says:**
```python
grail.Snapshot.load(data) -> Snapshot
```

**Implementation:**
```python
@staticmethod
def load(data: bytes, source_map: SourceMap, externals: dict[str, Callable]) -> "Snapshot":
```

This is technically documented in the docstring ("source_map and externals are NOT included in the serialized data"), but it breaks the spec's stated API. The spec presents `Snapshot.load(data)` as a simple one-argument call.

The implementation is arguably more correct (source_map and externals can't be serialized), but the spec should be updated to match, or grail should find a way to bundle the necessary context.

### 4.4 `MontyFutureSnapshot` Not Handled in `Snapshot`

**File:** `snapshot.py:162`

```python
@property
def is_complete(self) -> bool:
    return isinstance(self._monty_snapshot, pydantic_monty.MontyComplete)
```

`monty.start()` can return `MontyFutureSnapshot`. If it does, `is_complete` returns `False`, and the user tries `snapshot.function_name` which doesn't exist on `MontyFutureSnapshot` (it has `pending_call_ids` instead). This will raise `AttributeError`.

Similarly, `MontySnapshot.resume()` can return `MontyFutureSnapshot`, meaning subsequent `resume()` calls could get a `MontyFutureSnapshot` wrapped in a `Snapshot`, and all property access (`function_name`, `args`, `kwargs`) would fail.

**The fix:** `Snapshot` needs to detect and handle `MontyFutureSnapshot` — either by resolving pending futures internally or by exposing a different API for the future state.

### 4.5 `MemoryFile` Constructor Argument Style

**File:** `script.py:173`

```python
memory_files.append(pydantic_monty.MemoryFile(path, content=content))
```

**Monty's `MemoryFile.__init__`** (`os_access.py:158`):
```python
def __init__(self, path: str | PurePosixPath, content: str | bytes, *, permissions: int = 0o644) -> None:
```

`content` is a **positional** parameter, not keyword-only (the `*` comes after `content`). Using `content=content` as a keyword argument works in Python since `content` is not keyword-only, but it's non-idiomatic and could break if Monty ever changes `content` to positional-only. More importantly, looking at the Monty docs and examples, `MemoryFile('/config.json', '{"debug": true}')` is the canonical usage — positional style.

**Severity:** Low — this works but is fragile.

### 4.6 Error Mapping Ignores Structured Traceback Data

**File:** `script.py:190-210`

```python
match = re.search(r"line (\d+)", error_msg, re.IGNORECASE)
lineno = None
if match:
    monty_line = int(match.group(1))
    lineno = self.source_map.monty_to_pym.get(monty_line, monty_line)
```

**What Monty provides:**
```python
class MontyRuntimeError(MontyError):
    def traceback(self) -> list[Frame]
```

Where each `Frame` has `.line`, `.column`, `.end_line`, `.end_column`, `.function_name`, `.source_line`.

Grail throws away all this structured data and tries to regex-parse the line number from the error message string. This is:
- **Unreliable** — the regex pattern `r"line (\d+)"` could match other text containing "line" followed by a number
- **Incomplete** — loses column numbers, function names, and multi-frame tracebacks
- **Fragile** — depends on Monty's error message format not changing

**The fix:**
```python
if isinstance(error, pydantic_monty.MontyRuntimeError):
    frames = error.traceback()
    if frames:
        monty_line = frames[-1].line
        lineno = self.source_map.monty_to_pym.get(monty_line, monty_line)
```

### 4.7 CLI `cmd_run` Doesn't Use the Loaded Script

**File:** `cli.py` (the `cmd_run` function)

The `grail run` command:
1. Loads and validates the `.pym` file
2. Loads the host module
3. Calls `host_module.main(inputs=inputs)`

But it never passes the `GrailScript` to the host's `main()`. The host module is expected to independently call `grail.load()` to get the script. This means:
- The script is parsed and validated **twice** (once by CLI, once by host)
- The CLI's validation is wasted — the host may load a different file
- The `--input` flag values are passed to the host, but the host has no obligation to use them with the same `.pym` file

**The spec** describes `grail run` as executing a `.pym` file with a host, but the implementation just calls the host's `main()` and hopes for the best.

### 4.8 `run_sync` Event Loop Issues

**File:** `script.py:282`

```python
def run_sync(self, inputs, externals, **kwargs):
    return asyncio.run(self.run(inputs, externals, **kwargs))
```

`asyncio.run()` creates a new event loop and fails if called from within an existing loop. This is common in:
- Jupyter notebooks (`RuntimeError: asyncio.run() cannot be called from a running event loop`)
- Async frameworks (FastAPI, etc.)
- Nested async contexts

**The fix:** Use `asyncio.get_event_loop().run_until_complete()` or detect the running loop and handle it, or document this limitation explicitly.

### 4.9 Source Map Construction is Fragile

**File:** `codegen.py:37-53`

```python
for transformed_node, generated_node in zip(
    ast.walk(transformed_ast),
    ast.walk(generated_ast),
):
```

This zips two AST walks and assumes they traverse in the same order. But:
1. `transformed_ast` is the original AST with nodes removed (via `NodeTransformer`)
2. `generated_ast` is parsed from `ast.unparse(transformed_ast)` — a round-trip through text

`ast.walk()` uses BFS and its order depends on the tree structure. After `ast.unparse()` + `ast.parse()`, the AST may have different structure (e.g., implicit parentheses, operator precedence changes, comment-related differences). If the two walks diverge at any point, all subsequent line mappings are wrong.

**Evidence:** The test `test_source_map_accounts_for_stripped_lines` passes, but only because the test case is simple enough that the round-trip doesn't change traversal order. More complex code (nested functions, comprehensions, multi-line expressions) could produce incorrect mappings.

**The fix:** Build the source map from the `transformed_ast` directly — its nodes retain the original `.lineno` attributes, and `ast.unparse()` + `ast.parse()` on the result gives the generated line numbers. Map from the transformed AST's line numbers (which are original `.pym` line numbers) to the re-parsed code's line numbers by tracking node correspondence more carefully.

### 4.10 `check_for_warnings` Operates on Potentially Mutated AST

**File:** `checker.py:145`

`check_for_warnings()` reads `parse_result.ast_module`. If `generate_monty_code()` has already run on the same `ParseResult`, the AST is mutated (see [4.2](#42-code-generation-mutates-the-shared-ast-in-place)) and the checker would be operating on the stripped AST, potentially missing the last statement (if it was an `Input()` assignment that got stripped).

In practice, `load()` calls `check_pym()` before `generate_monty_code()`, so this hasn't manifested. But `GrailScript.check()` re-parses from the file, avoiding the issue. Still, the design is accident-prone.

---

## 5. Missing Features

### 5.1 W002 and W003 Warnings Not Implemented

**Spec requires:**
- **W002**: Unused `@external` function (declared but never called)
- **W003**: Unused `Input()` variable (declared but never referenced)

**`checker.py:140-181`**: `check_for_warnings()` only implements W001 (bare dict/list return) and W004 (long script). W002 and W003 are not present.

**How to implement:** After extracting external names and input names, walk the AST looking for `ast.Name` nodes that reference them (excluding the declarations themselves). Any unreferenced name is a warning.

### 5.2 No `print_callback` Support

Monty supports `print_callback` in `run_monty_async()`, `Monty.run()`, and `Monty.start()`. Grail never passes this parameter, so there is no way for users to capture `print()` output from their `.pym` scripts.

The `run.log` artifact captures execution timing but not actual stdout from the Monty sandbox.

### 5.3 No `dataclass_registry` Support

Monty's `Monty()` constructor accepts `dataclass_registry: list[type]` for proper `isinstance()` support on output. Grail doesn't expose this, and `MontySnapshot.load()` also accepts it.

### 5.4 Missing `max_allocations` and `gc_interval` Limits

The spec lists `max_allocations` as an available limit. Monty's `ResourceLimits` TypedDict also includes `gc_interval`. Neither is handled by `parse_limits()` in `limits.py`.

`parse_limits()` only handles `max_memory`, `max_duration`, and `max_recursion`.

### 5.5 No Sync Wrapper for `grail.run()`

`grail.run()` (`script.py:333-347`) is `async`. The spec presents it as an escape hatch for quick usage, but there's no synchronous version. Users who want to use it in non-async contexts have to write `asyncio.run(grail.run(...))` themselves.

### 5.6 E1xx Type Checker Errors Not Surfaced

The spec defines E1xx as "Monty type checker errors" that should appear in `grail check` output. The current `check()` method doesn't run Monty's type checker — it only checks Monty compatibility via AST analysis. To surface E1xx errors, `check()` would need to:
1. Generate stubs
2. Generate monty code
3. Create a `Monty()` instance with `type_check=True`
4. Catch `MontyTypingError` and convert diagnostics to `CheckMessage` entries

### 5.7 `script_name` Not Set

When creating `Monty()`, grail doesn't pass `script_name`. This means all tracebacks show `main.py` instead of the actual `.pym` filename. Setting `script_name=str(self.path)` or `script_name=self.name + '.pym'` would improve error messages.

### 5.8 `py.typed` Marker Missing

The spec's package structure lists `py.typed` (PEP 561 marker for IDE type checking), but the file doesn't exist in `src/grail/`. This means type checkers won't treat grail as a typed package.

---

## 6. Production Readiness

### 6.1 Version Mismatch

- `__init__.py` declares `__version__ = "2.0.0"`
- `pyproject.toml` declares `version = "0.1.0"`

These should match. The `pyproject.toml` version is what `pip show grail` reports.

### 6.2 `pydantic` Dependency Barely Used

`pyproject.toml` lists `pydantic` as a dependency, and the library calls itself "Pydantic-native." But pydantic is only used in one place: `script.py:281-285` for `output_model` validation:

```python
result = output_model(**result) if isinstance(result, dict) else output_model(result)
```

This works without importing pydantic at all — it just calls the model class as a constructor. The actual pydantic dependency could be optional (`extras_require`).

### 6.3 `pydantic_monty` Import Handling

Grail gracefully handles missing `pydantic_monty` at the module level:
```python
try:
    import pydantic_monty
except ImportError:
    pydantic_monty = None
```

This is done in `script.py` and `snapshot.py`. This is good — it allows `grail check` to work without Monty installed. However, the `None` assignment means `pydantic_monty.Monty`, `pydantic_monty.MontyComplete`, etc. will raise `AttributeError` rather than a clear error message when Monty isn't installed.

### 6.4 No `from typing import ...` Stripping in Codegen

The spec says `from typing import ...` is allowed in `.pym` files. The checker correctly allows it (E005 skips `typing`). But `codegen.py:26` only strips `from grail import ...`:

```python
def visit_ImportFrom(self, node):
    if node.module == "grail":
        return None  # Remove this node
    return node
```

`from typing import ...` is passed through to the generated Monty code. Whether Monty supports this import depends on Monty's implementation — it may or may not cause errors. This should be verified.

### 6.5 No Rate Limiting or Timeout on Host-Side External Calls

In the `run_monty_async()` flow, external function calls have no timeout. A malicious or buggy external function could hang indefinitely, and grail has no mechanism to cancel it. This is arguably a host-side concern, but worth noting.

### 6.6 `limits` Not Passed to `start()`

In `GrailScript.start()` (`script.py:307-317`), limits are not passed to `monty.start()`:

```python
monty_snapshot = monty.start(inputs=inputs)
```

But `Monty.start()` accepts `limits`. This means snapshot-based execution has no resource limits, even if the user specified them in `grail.load()`.

---

## 7. Test Coverage Gaps

### 7.1 What's Well Tested

- **Parser**: Good coverage of `@external` extraction, `Input()` extraction, validation errors, edge cases (nested definitions, missing annotations)
- **Checker**: All E001-E005 codes tested, W001 and W004 tested, feature tracking tested
- **Stubs**: Various scenarios (simple, with `Any`, with defaults, multiple declarations, substring matching)
- **Codegen**: Import stripping, external stripping, input stripping, source map creation, valid Python output
- **Errors**: Hierarchy, formatting, context display
- **Limits**: Parsing, merging, presets
- **Artifacts**: Directory creation, JSON validity, run.log, cleanup
- **CLI**: init, check, clean, run (with input parsing), watch dependency check
- **End-to-end**: Full workflow (load/check/run), pause/resume, inline run, resource limits

### 7.2 What's Not Tested

| Gap | Severity | Notes |
|-----|----------|-------|
| Snapshot with async external functions | **Critical** | No test exercises the async resume protocol in `snapshot.py:104-122` |
| `MontyFutureSnapshot` handling | **Critical** | No test creates a scenario where `monty.start()` or `resume()` returns `MontyFutureSnapshot` |
| Error mapping with `MontyRuntimeError` | **High** | `test_map_error_to_pym_uses_source_map` uses a plain `RuntimeError`, not a `MontyRuntimeError` with `traceback()` |
| `LimitError` detection from Monty errors | **High** | No test verifies that actual Monty limit violations are caught and converted to `LimitError` |
| `output_model` validation | **Medium** | No test verifies that `output_model` parameter works with an actual Pydantic model |
| Multiple external calls in sequence | **Medium** | `test_pause_resume_workflow` tests this but only with sync externals |
| `files` parameter with actual Monty execution | **Medium** | No test verifies that files passed to `grail.load()` or `script.run()` are actually accessible inside Monty |
| `--format json` output in CLI | **Low** | `test_cmd_check_valid_file` only tests `format="text"` |
| `--strict` mode in CLI | **Low** | Not tested |
| Concurrent external calls | **Low** | Not applicable to pause/resume, but no test for `run_monty_async` with multiple concurrent async externals |
| Source map accuracy for complex code | **Medium** | Only simple cases tested; nested functions, comprehensions, multi-line expressions untested |

### 7.3 Test Configuration

- Integration tests use `pytest.importorskip("pydantic_monty")` — good
- `@pytest.mark.integration` marker is defined but not consistently used (some integration tests in unit/ directory)
- No `conftest.py` at the root `tests/` level — only `tests/integration/conftest.py`
- Some async test functions in `test_monty_integration.py` lack `@pytest.mark.asyncio` (e.g., `test_monty_with_external_function`, `test_monty_error_handling`)

---

## 8. Architecture & Code Quality

### 8.1 Module Responsibilities

The module structure is clean and follows the spec:

| Module | Responsibility | Assessment |
|--------|---------------|------------|
| `script.py` | Load/run orchestration | **Good** — clear flow, but too many responsibilities (validation, preparation, execution, error mapping) |
| `parser.py` | AST extraction | **Good** — clean separation, but does validation that should be in `checker.py` (E006/E007/E008) |
| `checker.py` | Compatibility validation | **Good** — clean AST visitor pattern |
| `codegen.py` | Code transformation | **Needs fix** — AST mutation bug |
| `stubs.py` | Stub generation | **Good** — simple and correct |
| `snapshot.py` | Pause/resume | **Needs fix** — async protocol bug |
| `errors.py` | Error hierarchy | **Good** — well-structured |
| `limits.py` | Limit parsing | **Good** — simple and correct |
| `artifacts.py` | Artifact I/O | **Good** — clean separation |
| `cli.py` | CLI commands | **Good** — proper argparse usage |
| `_types.py` | Dataclasses | **Good** — minimal, correct |

### 8.2 Error Handling Patterns

**Good:**
- Consistent use of custom exception hierarchy
- `GrailScript._validate_inputs()` and `_validate_externals()` provide clear error messages
- `parse_pym_file()` wraps `SyntaxError` in `ParseError` with proper context

**Needs improvement:**
- `script.py:254-269`: Catches bare `Exception` from `run_monty_async()`. Should catch specific Monty error types (`MontyRuntimeError`, `MontyTypingError`, `MontySyntaxError`) for proper handling.
- `cli.py`: `cmd_check` catches `FileNotFoundError`, `ParseError`, and `CheckError`, but doesn't catch `Exception` for unexpected errors — good practice, actually.

### 8.3 Type Safety

- `ResourceLimits` in `_types.py:96` is defined as `dict[str, Any]` — loses all type information. Should be a `TypedDict`.
- `parse_limits()` returns `dict[str, Any]` instead of Monty's `ResourceLimits` TypedDict.
- `GrailScript.__init__` accepts `limits: dict[str, Any] | None` — no type narrowing.
- The `externals` parameter in `run()` is `dict[str, Callable]` which is correct but could be more specific with `Protocol` or `overload`.

### 8.4 Naming Conventions

Consistent and idiomatic Python:
- `snake_case` for functions and variables
- `PascalCase` for classes
- `UPPER_CASE` for constants (presets)
- Private methods prefixed with `_`

### 8.5 Documentation

- All public functions have docstrings with Args/Returns/Raises sections
- Module-level docstrings explain purpose
- `snapshot.py` has a detailed module docstring explaining the protocol
- `GRAIL_CONCEPT.md` is thorough and well-written

---

## 9. Prioritized Recommendations

### P0 — Critical (Fix Before Any Use)

1. **Fix AST mutation in `codegen.py`** — Add `copy.deepcopy(parse_result.ast_module)` before `stripper.visit()`. Without this, reusing `ParseResult` objects corrupts data. (`codegen.py:68`)

2. **Fix snapshot resume protocol** — Remove the async/sync branching in `snapshot.py:104-122`. Always use `resume(return_value=return_value)`. The future protocol belongs in `run_monty_async()`, not in the manual pause/resume API. (`snapshot.py:95-130`)

3. **Handle `MontyFutureSnapshot` in `Snapshot`** — `monty.start()` and `MontySnapshot.resume()` can return `MontyFutureSnapshot`. Add type checking in `Snapshot.__init__` and `Snapshot.resume()`. Either resolve futures internally or raise a clear error explaining the limitation. (`snapshot.py:162`)

4. **Fix source map construction** — Replace `zip(ast.walk(), ast.walk())` with a more robust approach. Options: (a) walk only the transformed AST and use `ast.unparse()` line tracking, (b) use `ast.get_source_segment()` to match nodes, (c) build the map during the transformation pass rather than after. (`codegen.py:37-53`)

### P1 — High (Fix Before Beta)

5. **Use structured error data from Monty** — When catching `MontyRuntimeError`, use `.traceback()` to get `Frame` objects with precise line/column info instead of regex parsing the message string. (`script.py:188-210`)

6. **Move E006/E007/E008 from parser to checker** — Currently these raise `CheckError` exceptions in `parser.py`, which crashes `grail check` instead of producing structured `CheckMessage` entries. The parser should extract what it can and let the checker validate. (`parser.py:82-141`)

7. **Implement W002 and W003 warnings** — Add unused `@external` and unused `Input()` detection to `check_for_warnings()`. Walk the AST for `ast.Name` references. (`checker.py:140`)

8. **Pass `limits` to `monty.start()`** — Snapshot execution currently has no resource limits. (`script.py:317`)

9. **Fix `MemoryFile` construction** — Use positional `content` argument: `MemoryFile(path, content)` instead of `MemoryFile(path, content=content)`. (`script.py:173`)

### P2 — Medium (Fix Before Release)

10. **Fix version mismatch** — Align `__init__.py` (`"2.0.0"`) and `pyproject.toml` (`"0.1.0"`). Decide on the actual version.

11. **Add `print_callback` support** — Expose a callback parameter on `script.run()` and `script.start()` for capturing print output. Write captured output to `run.log`.

12. **Set `script_name` on Monty** — Pass `script_name=self.name + '.pym'` to `Monty()` for better tracebacks.

13. **Add `dataclass_registry` support** — Expose on `grail.load()` or `script.run()` and pass through to `Monty()`.

14. **Handle `run_sync` event loop issues** — Either use `asyncio.get_event_loop().run_until_complete()`, use `nest_asyncio`, or document the limitation clearly.

15. **Fix CLI `cmd_run`** — Pass the loaded `GrailScript` to the host's `main()` function so the host doesn't have to re-parse the file.

16. **Add `max_allocations` and `gc_interval` to `parse_limits()`** — These are valid Monty limits that users may want to set.

### P3 — Low (Polish)

17. **Create `py.typed` marker file** — Add empty `src/grail/py.typed` for PEP 561 compliance.

18. **Make `pydantic` optional** — Move to `extras_require` since it's only used for `output_model`.

19. **Add sync wrapper for `grail.run()`** — For convenience in non-async contexts.

20. **Surface E1xx type checker errors in `check()`** — Run Monty's type checker during `grail check` and convert `MontyTypingError` diagnostics to `CheckMessage` entries.

21. **Verify `from typing import ...` in Monty** — Confirm whether Monty handles `from typing import ...` statements or if codegen should strip them too.

---

## Appendix: File Reference

| File | Lines | Key Issues |
|------|-------|------------|
| `src/grail/__init__.py` | 54 | Version mismatch |
| `src/grail/script.py` | 347 | Error mapping, MemoryFile kwarg, limits not passed to start(), no print_callback |
| `src/grail/parser.py` | 231 | E006/E007/E008 in wrong layer |
| `src/grail/checker.py` | 187 | Missing W002, W003 |
| `src/grail/codegen.py` | 82 | AST mutation, fragile source map |
| `src/grail/snapshot.py` | 167 | Async resume bug, MontyFutureSnapshot unhandled, load() signature |
| `src/grail/errors.py` | 112 | Clean |
| `src/grail/limits.py` | 133 | Missing max_allocations, gc_interval |
| `src/grail/artifacts.py` | ~100 | Clean |
| `src/grail/cli.py` | ~200 | cmd_run doesn't pass script |
| `src/grail/stubs.py` | 77 | Clean |
| `src/grail/_types.py` | 97 | ResourceLimits is untyped dict |
| `src/grail/_external.py` | 27 | Clean |
| `src/grail/_input.py` | 38 | Clean |
| `pyproject.toml` | ~30 | Version 0.1.0 vs 2.0.0 |
