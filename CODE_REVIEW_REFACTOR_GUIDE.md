# Grail v3 — Refactor Guide

**Purpose:** Step-by-step guide for a junior developer to refactor Grail v2 into a production-ready v3 release.  
**Prerequisite reading:** `GRAIL_CONCEPT.md`, `CODE_REVIEW.md`, and the source files they reference.  
**Scope:** Fix all bugs and spec divergences from the code review, remove snapshot functionality, add comprehensive logging.

---

## Table of Contents

1. [Overview & Context](#1-overview--context)
2. [V3 Scope Changes](#2-v3-scope-changes)
3. [Logging Design Decision](#3-logging-design-decision)
4. [Step-by-Step Refactor Plan](#4-step-by-step-refactor-plan)
   - [Phase 1: Foundations](#phase-1-foundations-cleanup-types-version)
   - [Phase 2: Remove Snapshots](#phase-2-remove-snapshot-functionality)
   - [Phase 3: Fix Critical Bugs](#phase-3-fix-critical-bugs)
   - [Phase 4: Fix High-Priority Issues](#phase-4-fix-high-priority-issues)
   - [Phase 5: Add Logging](#phase-5-add-logging-system)
   - [Phase 6: Medium-Priority Fixes](#phase-6-medium-priority-fixes)
   - [Phase 7: Polish & Low-Priority](#phase-7-polish--low-priority)
   - [Phase 8: Spec & Documentation Updates](#phase-8-spec--documentation-updates)
5. [Final Verification Checklist](#5-final-verification-checklist)

---

## 1. Overview & Context

### What Grail Does

Grail wraps **Monty** (`pydantic-monty`), a secure Rust-based Python interpreter. The pipeline is:

1. **`.pym` file** (valid Python with `@external` and `Input()` declarations)
2. **Parser** extracts metadata via AST
3. **Checker** validates Monty compatibility
4. **Code Generator** strips declarations, produces clean `monty_code` + `SourceMap`
5. **Stub Generator** produces `.pyi` for Monty's type checker
6. **Artifacts Manager** writes outputs to `.grail/<name>/`
7. **Execution** via `pydantic_monty.Monty()` + `run_monty_async()`

### Current File Map

| File | Lines | Role |
|------|-------|------|
| `src/grail/__init__.py` | 64 | Public API exports |
| `src/grail/script.py` | 471 | Load/run orchestration (core) |
| `src/grail/parser.py` | 337 | AST extraction of `@external`, `Input()` |
| `src/grail/checker.py` | 268 | Monty compatibility validation |
| `src/grail/codegen.py` | 118 | `.pym` → monty_code transformation |
| `src/grail/stubs.py` | 77 | Stub generation |
| `src/grail/snapshot.py` | 176 | Pause/resume wrapper (**REMOVING**) |
| `src/grail/errors.py` | 128 | Error hierarchy |
| `src/grail/limits.py` | 149 | Limit parsing and presets |
| `src/grail/artifacts.py` | 149 | `.grail/` directory management |
| `src/grail/cli.py` | 401 | CLI commands |
| `src/grail/_types.py` | 97 | Core dataclasses |
| `src/grail/_external.py` | 27 | `@external` decorator |
| `src/grail/_input.py` | 38 | `Input()` function |

---

## 2. V3 Scope Changes

### Removed: Snapshot Functionality

**What it is:** Snapshots allow pausing script execution at external function boundaries, serializing the execution state, and resuming later. This wraps Monty's `MontySnapshot`/`MontyFutureSnapshot`/`MontyComplete` system.

**Why we're removing it:**
- Adds significant complexity (176-line `snapshot.py`, `start()` method in `script.py`, serialization concerns)
- Has multiple critical bugs (wrong async resume protocol, unhandled `MontyFutureSnapshot`)
- We don't use it in our actual workflows — we always use `run()` for complete execution
- Removing it eliminates 4 of the 4 critical bugs from the code review

**What gets removed:**
- `src/grail/snapshot.py` — entire file deleted
- `GrailScript.start()` method in `script.py`
- `Snapshot` import and export in `__init__.py`
- `Snapshot` from `__all__`
- All snapshot-related tests (`tests/unit/test_snapshot.py`, snapshot portions of `tests/integration/test_end_to_end.py`)
- Section 10 (Pause/Resume) from `GRAIL_CONCEPT.md`
- Any `Snapshot.load()` signature discussion from the spec

### Added: Comprehensive Logging

See [Section 3](#3-logging-design-decision) for the design decision and options.

---

## 3. Logging Design Decision

Monty supports a `print_callback` parameter with the signature:

```python
Callable[[Literal['stdout'], str], None]
```

This callback receives every `print()` call from inside the Monty sandbox. Currently, Grail **never passes this parameter**, so all script print output is silently discarded.

We need to integrate this with the Monty print system and our existing artifacts (`run.log`). Below are three options.

---

### Option A: Callback-Based (User Provides Their Own)

**How it works:** Expose a `print_callback` parameter on `script.run()` and `script.run_sync()`. The user provides a callable that receives print output. Grail also always captures output internally for `run.log`.

```python
# User code
def my_logger(stream: str, text: str) -> None:
    print(f"[script] {text}", end="")

result = await script.run(
    inputs={...},
    externals={...},
    print_callback=my_logger,
)
```

**Internal implementation:**
```python
# Inside GrailScript.run()
captured_output: list[str] = []

def _internal_callback(stream: str, text: str) -> None:
    captured_output.append(text)
    if user_callback:
        user_callback(stream, text)

result = await pydantic_monty.run_monty_async(
    monty, ..., print_callback=_internal_callback,
)

# Write captured output to run.log
stdout_text = "".join(captured_output)
```

**Pros:**
- Maximum flexibility — user controls what happens with output
- Zero overhead if no callback provided (just internal capture)
- Matches Monty's native API pattern exactly
- Simple implementation — thin pass-through

**Cons:**
- User must write their own callback for basic logging
- No structured logging out of the box
- Callback runs synchronously inside Monty's execution — long-running callbacks could affect performance

---

### Option B: Built-in GrailLogger with Monty Print Integration

**How it works:** Create a `GrailLogger` class that wraps Python's `logging` module and automatically receives Monty print output. The logger is configured at `load()` time and handles all output routing.

```python
# User code
import logging

result = await script.run(
    inputs={...},
    externals={...},
    log_level=logging.DEBUG,  # or "DEBUG"
)

# Or with custom logger
logger = logging.getLogger("myapp.grail")
result = await script.run(
    inputs={...},
    externals={...},
    logger=logger,
)
```

**Internal implementation:**
```python
class GrailLogger:
    """Wraps Python logging + Monty print capture."""
    
    def __init__(self, logger: logging.Logger | None = None):
        self._logger = logger or logging.getLogger("grail")
        self._captured: list[str] = []
    
    def print_callback(self, stream: str, text: str) -> None:
        """Monty print_callback handler."""
        self._captured.append(text)
        # Strip trailing newline for logging (logging adds its own)
        clean = text.rstrip("\n")
        if clean:
            self._logger.info("[script] %s", clean)
    
    def log_event(self, level: int, msg: str, **kwargs) -> None:
        """Log a grail lifecycle event."""
        self._logger.log(level, msg, **kwargs)
    
    @property
    def captured_output(self) -> str:
        return "".join(self._captured)
```

**Pros:**
- Structured logging out of the box via Python's `logging` module
- Users can configure handlers, formatters, levels using standard Python patterns
- Grail lifecycle events (load, check, run start/end, errors) are also logged
- Consistent with how most Python libraries handle logging

**Cons:**
- More code to maintain (GrailLogger class, integration points)
- Opinionated — forces `logging` module on users who may prefer something else
- May conflict with user's existing logging configuration if not carefully namespaced
- Adds coupling between Grail internals and the logging system

---

### Option C: Hybrid — Callback + Built-in Capture with Event Hooks (Recommended)

**How it works:** Combine the flexibility of callbacks with built-in output capture and structured event hooks. The user can:
1. Do nothing — output is captured internally and written to `run.log`
2. Pass a `print_callback` — receives raw Monty output (same as Option A)
3. Pass an `on_event` callback — receives structured lifecycle events

```python
# Simplest usage — output captured to run.log automatically
result = await script.run(inputs={...}, externals={...})

# With print output forwarding
result = await script.run(
    inputs={...},
    externals={...},
    print_callback=lambda stream, text: print(f"[script] {text}", end=""),
)

# With structured events (for logging/observability integration)
def handle_event(event: grail.ScriptEvent) -> None:
    if event.type == "print":
        my_logger.info("[script] %s", event.text)
    elif event.type == "run_start":
        my_logger.info("Starting %s with %d inputs", event.script_name, event.input_count)
    elif event.type == "run_complete":
        my_logger.info("Completed in %.2fms", event.duration_ms)
    elif event.type == "run_error":
        my_logger.error("Failed: %s", event.error)

result = await script.run(
    inputs={...},
    externals={...},
    on_event=handle_event,
)
```

**Internal implementation:**

```python
# In _types.py
@dataclass
class ScriptEvent:
    """Structured event from script execution."""
    type: Literal["run_start", "print", "run_complete", "run_error", "check_start", "check_complete"]
    script_name: str
    timestamp: float
    # Optional fields depending on type
    text: str | None = None          # for "print"
    duration_ms: float | None = None  # for "run_complete"
    error: str | None = None          # for "run_error"
    input_count: int | None = None    # for "run_start"
    result_type: str | None = None    # for "run_complete"

# In script.py
async def run(
    self,
    inputs: dict[str, Any] | None = None,
    externals: dict[str, Callable] | None = None,
    output_model: type | None = None,
    files: dict[str, str | bytes] | None = None,
    limits: dict[str, Any] | None = None,
    print_callback: Callable[[str, str], None] | None = None,
    on_event: Callable[[ScriptEvent], None] | None = None,
) -> Any:
    captured_output: list[str] = []

    def _monty_print_callback(stream: str, text: str) -> None:
        captured_output.append(text)
        if print_callback:
            print_callback(stream, text)
        if on_event:
            on_event(ScriptEvent(
                type="print", script_name=self.name,
                timestamp=time.time(), text=text,
            ))

    # Emit run_start event
    if on_event:
        on_event(ScriptEvent(
            type="run_start", script_name=self.name,
            timestamp=time.time(), input_count=len(inputs or {}),
        ))

    result = await pydantic_monty.run_monty_async(
        monty, ..., print_callback=_monty_print_callback,
    )

    # Write captured output to run.log
    stdout_text = "".join(captured_output)
    if self._artifacts:
        self._artifacts.write_run_log(
            self.name, stdout=stdout_text, ...,
        )
```

**Pros:**
- **Zero-config works** — output captured to `run.log` automatically, no user action needed
- **Simple path** — `print_callback` for users who just want raw output
- **Structured path** — `on_event` for users who want to integrate with logging/observability
- **No forced dependencies** — doesn't require `logging` module; works with any framework
- **Extensible** — new event types can be added without API changes
- **Testable** — events are dataclasses, easy to assert on in tests

**Cons:**
- Slightly more API surface than Option A (but both callbacks are optional)
- `ScriptEvent` is a new type to maintain
- `on_event` runs synchronously; if the user's handler is slow, it affects execution

---

### Recommendation: Option C (Hybrid)

Option C gives us the best balance:
- For users who don't care about logging: everything just works, output goes to `run.log`
- For users who want simple print forwarding: one callback parameter
- For users building production systems: structured events that integrate with any logging/observability stack
- It follows Grail's design philosophy: transparent, minimal, no forced abstractions

**Implementation note:** The `on_event` callback is optional and additive — it never breaks existing code. The `print_callback` matches Monty's native API. Both are thin wrappers, not heavy abstractions.

---

## 4. Step-by-Step Refactor Plan

### Ground Rules

1. **Run tests after every step.** The command is `python -m pytest tests/` from the project root. All tests should pass before moving to the next step (except tests you're intentionally removing).
2. **Commit after each phase.** Each phase is an atomic unit of work.
3. **Read before editing.** Always read the file you're about to modify. Don't edit blind.
4. **Follow existing code style.** snake_case functions, PascalCase classes, docstrings on all public functions with Args/Returns/Raises sections.

---

### Phase 1: Foundations (Cleanup, Types, Version)

This phase fixes small issues that other phases depend on or that are trivial to address now.

#### Step 1.1: Fix Version Mismatch

**Problem:** `__init__.py` says `"2.0.0"`, `pyproject.toml` says `"0.1.0"`. These must match.

**Files to modify:**
- `src/grail/__init__.py` — Change `__version__` to `"3.0.0"`
- `pyproject.toml` — Change `version` to `"3.0.0"`

**Verification:**
```bash
python -c "import grail; print(grail.__version__)"
# Should print: 3.0.0
```

#### Step 1.2: Fix `ResourceLimits` Type

**Problem:** `_types.py:96` defines `ResourceLimits = dict[str, Any]` — this loses all type information. Should be a `TypedDict`.

**File to modify:** `src/grail/_types.py`

**Change:**
```python
# BEFORE
ResourceLimits = dict[str, Any]

# AFTER
from typing import TypedDict

class ResourceLimits(TypedDict, total=False):
    """Resource limits for Monty execution (Monty's native format)."""
    max_allocations: int
    max_duration_secs: float
    max_memory: int
    gc_interval: int
    max_recursion_depth: int
```

**Then update** all type hints that reference `dict[str, Any]` for limits throughout the codebase to use `ResourceLimits` where appropriate. Note: The *user-facing* limits API still accepts `dict[str, Any]` (with string keys like `"max_memory": "16mb"`), but `parse_limits()` should return `ResourceLimits`. You'll need to add the import in files that reference it.

**Files to update:**
- `src/grail/limits.py` — `parse_limits()` return type → `ResourceLimits`, `merge_limits()` return type → `ResourceLimits`
- `src/grail/script.py` — `GrailScript.__init__` limits parameter and `_prepare_monty_limits` return type

**Verification:**
```bash
python -m pytest tests/unit/test_types.py tests/unit/test_limits.py -v
```

#### Step 1.3: Create `py.typed` Marker

**Problem:** PEP 561 requires a `py.typed` file for type checkers to recognize the package as typed.

**Action:** Create an empty file at `src/grail/py.typed`:
```bash
touch src/grail/py.typed
```

**Verification:** The file exists. No test needed.

---

### Phase 2: Remove Snapshot Functionality

This phase removes all snapshot-related code. Do this before fixing bugs so we don't waste time fixing code we're deleting.

#### Step 2.1: Delete `snapshot.py`

**Action:** Delete `src/grail/snapshot.py`.

#### Step 2.2: Remove Snapshot from `__init__.py`

**File to modify:** `src/grail/__init__.py`

**Remove:**
- The `from grail.snapshot import Snapshot` import line
- `"Snapshot"` from the `__all__` list

#### Step 2.3: Remove `GrailScript.start()` from `script.py`

**File to modify:** `src/grail/script.py`

**Remove:** The entire `start()` method (approximately lines 347-387). This includes:
- The method definition
- The `from grail.snapshot import Snapshot` lazy import inside it
- All the Monty snapshot creation logic

Also remove any imports that are only used by the snapshot code (check if `Snapshot` is imported anywhere else in the file).

#### Step 2.4: Remove Snapshot Tests

**Delete:** `tests/unit/test_snapshot.py`

**Modify:** `tests/integration/test_end_to_end.py` — Remove the `test_pause_resume_workflow` test function (and any other snapshot-related tests).

#### Step 2.5: Update Public API Test

**File to modify:** `tests/unit/test_public_api.py`

**Change:** Remove `"Snapshot"` from any assertions that check the public API surface.

#### Step 2.6: Verification

```bash
# All tests pass (snapshot tests should be gone, everything else green)
python -m pytest tests/ -v

# Verify Snapshot is not importable
python -c "from grail import Snapshot" 2>&1 | grep -i error
# Should show ImportError

# Verify all other public symbols still work
python -c "from grail import load, run, external, Input, STRICT, DEFAULT, PERMISSIVE, GrailError, ParseError, CheckError, InputError, ExternalError, ExecutionError, LimitError, OutputError, CheckResult, CheckMessage; print('All imports OK')"
```

---

### Phase 3: Fix Critical Bugs

These bugs would cause crashes or data corruption in normal usage.

#### Step 3.1: Fix AST Mutation in Code Generation

**Problem:** `codegen.py:97` calls `stripper.visit(parse_result.ast_module)` which mutates the AST **in-place**. If anyone reuses the `ParseResult` after code generation, the AST is corrupted — `@external` functions and `Input()` assignments are gone.

**File to modify:** `src/grail/codegen.py`

**Change:**
```python
# BEFORE (line ~96-97)
stripper = GrailDeclarationStripper(external_names, input_names)
transformed = stripper.visit(parse_result.ast_module)

# AFTER
import copy

stripper = GrailDeclarationStripper(external_names, input_names)
transformed = stripper.visit(copy.deepcopy(parse_result.ast_module))
```

Add `import copy` at the top of the file.

**Verification:**
```bash
python -m pytest tests/unit/test_codegen.py -v
```

Also write a new test in `tests/unit/test_codegen.py` that verifies the original AST is not mutated:

```python
def test_generate_monty_code_does_not_mutate_ast():
    """Verify that code generation doesn't modify the original ParseResult AST."""
    content = '''from grail import external, Input

x: int = Input("x")

@external
async def fetch(id: int) -> str:
    ...

result = await fetch(x)
result
'''
    parse_result = parse_pym_content(content)
    
    # Count nodes before
    original_body_len = len(parse_result.ast_module.body)
    
    # Generate code (should not mutate)
    generate_monty_code(parse_result)
    
    # AST should be unchanged
    assert len(parse_result.ast_module.body) == original_body_len
```

#### Step 3.2: Fix Source Map Construction

**Problem:** `codegen.py:66-68` uses `zip(ast.walk(transformed_ast), ast.walk(generated_ast))` which assumes two independently-created ASTs traverse in the same BFS order. This is fragile and can produce incorrect line mappings for complex code.

**File to modify:** `src/grail/codegen.py`

**Replace the `build_source_map` function entirely:**

The robust approach is to record the original line numbers from the transformed AST's nodes *before* unparsing, then after unparsing + re-parsing, walk the new AST to get generated line numbers. Since `ast.unparse()` doesn't preserve original line numbers, we need a different strategy.

**New approach:** Walk the transformed AST (which retains original `.lineno` from the `.pym` file) and record each statement's original line number. Then, after unparsing to `generated_code` and re-parsing it, walk the re-parsed AST statement by statement. Since statements appear in the same order (ast.unparse preserves statement order), we can match them by position.

```python
def build_source_map(transformed_ast: ast.Module, generated_code: str) -> SourceMap:
    """
    Build line number mapping between .pym and generated code.

    Strategy: Walk both ASTs at the statement level (not BFS over all nodes),
    matching statements by their sequential position. This is robust because
    ast.unparse() preserves statement order even when node structure changes
    during the unparse/re-parse round-trip.

    Args:
        transformed_ast: AST after stripping declarations (retains original line numbers)
        generated_code: Generated Monty code string

    Returns:
        SourceMap with line mappings
    """
    source_map = SourceMap()
    generated_ast = ast.parse(generated_code)

    def _collect_line_numbers(module: ast.Module) -> list[tuple[int, int]]:
        """Collect (lineno, end_lineno) for all statement-level nodes, recursively."""
        result = []
        for node in ast.walk(module):
            if isinstance(node, ast.stmt) and not isinstance(node, ast.Module):
                lineno = getattr(node, "lineno", None)
                if lineno is not None:
                    result.append(lineno)
        return result

    original_lines = _collect_line_numbers(transformed_ast)
    generated_lines = _collect_line_numbers(generated_ast)

    # Map each generated line to its original .pym line
    for orig_line, gen_line in zip(original_lines, generated_lines):
        source_map.add_mapping(pym_line=orig_line, monty_line=gen_line)

    return source_map
```

**Note:** This is still using `zip` but at the *statement* level, which is much more stable than the full BFS walk. Statement order is preserved by `ast.unparse()`. If the lists have different lengths (which shouldn't happen for correct transformations), `zip` safely truncates.

**Verification:**
```bash
python -m pytest tests/unit/test_codegen.py -v
```

The existing `test_source_map_accounts_for_stripped_lines` test should still pass. Add an additional test with more complex code (nested functions, comprehensions, multi-line expressions) to verify the source map is correct:

```python
def test_source_map_complex_code():
    """Source map should handle complex code structures correctly."""
    content = '''from grail import external, Input

x: int = Input("x")

@external
async def fetch(id: int) -> str:
    ...

async def helper(n):
    return n * 2

results = [
    await fetch(i)
    for i in range(x)
]

total = sum(len(r) for r in results)
total
'''
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)
    
    # The generated code should be valid
    ast.parse(monty_code)
    
    # Source map should have mappings
    assert len(source_map.monty_to_pym) > 0
    
    # Every generated line should map to a valid .pym line
    for gen_line, pym_line in source_map.monty_to_pym.items():
        assert pym_line >= 1
        assert pym_line <= len(parse_result.source_lines)
```

#### Step 3.3: Verification for Phase 3

```bash
python -m pytest tests/ -v
# All tests should pass, including the new ones
```

---

### Phase 4: Fix High-Priority Issues

#### Step 4.1: Use Structured Error Data from Monty

**Problem:** `script.py:192` uses regex (`r"line (\d+)"`) to extract line numbers from error messages, ignoring Monty's structured `Frame` objects with precise line/column info.

**File to modify:** `src/grail/script.py`

**Replace `_map_error_to_pym`:**

```python
def _map_error_to_pym(self, error: Exception) -> ExecutionError:
    """
    Map Monty error to .pym file line numbers.

    Uses structured traceback data from MontyRuntimeError when available,
    falling back to message parsing for other error types.

    Args:
        error: Original error from Monty

    Returns:
        ExecutionError with mapped line numbers
    """
    error_msg = str(error)
    error_msg_lower = error_msg.lower()
    lineno = None
    col_offset = None

    # Use structured traceback if available (MontyRuntimeError)
    if pydantic_monty is not None and isinstance(error, pydantic_monty.MontyRuntimeError):
        frames = error.traceback()
        if frames:
            # Use the innermost frame (last in the list)
            frame = frames[-1]
            monty_line = frame.line
            lineno = self.source_map.monty_to_pym.get(monty_line, monty_line)
            col_offset = getattr(frame, "column", None)
    else:
        # Fallback: try to extract line number from error message
        match = re.search(r"line (\d+)", error_msg, re.IGNORECASE)
        if match:
            monty_line = int(match.group(1))
            lineno = self.source_map.monty_to_pym.get(monty_line, monty_line)

    # Detect limit errors by type or message heuristics
    limit_type = None
    if "memory" in error_msg_lower:
        limit_type = "memory"
    elif "duration" in error_msg_lower:
        limit_type = "duration"
    elif "recursion" in error_msg_lower:
        limit_type = "recursion"

    if "limit" in error_msg_lower or limit_type is not None:
        return LimitError(error_msg, limit_type=limit_type)

    source_context = "\n".join(self.source_lines) if self.source_lines else None
    return ExecutionError(
        error_msg,
        lineno=lineno,
        col_offset=col_offset,
        source_context=source_context,
        suggestion=None,
    )
```

**Also update** the `except` block in `run()` (around line 287) to catch specific Monty error types instead of bare `Exception`:

```python
# BEFORE
except Exception as e:
    ...

# AFTER
except (pydantic_monty.MontyRuntimeError, pydantic_monty.MontyTypingError) as e:
    success = False
    error_msg = str(e)
    mapped_error = self._map_error_to_pym(e)
    ...
except Exception as e:
    # Catch unexpected errors (MontySyntaxError, etc.)
    success = False
    error_msg = str(e)
    mapped_error = self._map_error_to_pym(e)
    ...
```

**Verification:**
```bash
python -m pytest tests/unit/test_script.py tests/integration/ -v
```

#### Step 4.2: Move E006/E007/E008 from Parser to Checker

**Problem:** Missing type annotations on `@external` (E006), non-ellipsis body (E007), and `Input()` without annotation (E008) raise `CheckError` exceptions in `parser.py`, which crashes `grail check` instead of producing structured `CheckMessage` entries. These should be detected in the checker layer so they appear as structured errors in `check.json`.

**Files to modify:**
- `src/grail/parser.py` — Make validation lenient (extract what you can, skip malformed declarations)
- `src/grail/checker.py` — Add E006/E007/E008 detection

**Changes to `parser.py`:**

The key insight: the parser should *extract* declarations, not *validate* them. If an `@external` function is missing annotations, the parser should still record it (with `type_annotation=None` or `"<missing>"`) and let the checker flag it.

1. In `extract_function_params()`: Instead of raising `CheckError` when `arg.annotation is None`, set `type_annotation` to `"<missing>"`:

```python
# BEFORE
if arg.annotation is None:
    raise CheckError(
        f"Parameter '{arg.arg}' in function '{func_node.name}' missing type annotation",
        lineno=func_node.lineno,
    )

# AFTER
annotation_str = "<missing>" if arg.annotation is None else get_type_annotation_str(arg.annotation)
```

2. In `validate_external_function()`: Convert from raising exceptions to returning a list of issues, or simply remove the validation and let the checker handle it. The simplest approach: **remove `validate_external_function()` entirely** and add the validation logic to the checker.

   However, since the parser calls `validate_external_function(node)` before extracting, you need to make the parser tolerant:
   
   - In `extract_externals()`, remove the `validate_external_function(node)` call
   - When `node.returns is None`, set `return_type` to `"<missing>"` instead of raising
   - Store a new field on `ExternalSpec` indicating whether the body is valid (or just always extract and let checker validate)

3. In `extract_inputs()`: Instead of raising `CheckError` for missing annotation on `Input()`, still extract it with `type_annotation="<missing>"`.

4. Similarly, for unannotated assignments (`x = Input("x")`), instead of raising `CheckError`, extract it with `type_annotation="<missing>"` and let the checker flag it.

**Changes to `checker.py`:**

Add three new checks to `check_pym()` (or a new function called by it):

```python
def check_declarations(parse_result: ParseResult) -> list[CheckMessage]:
    """Check that @external and Input() declarations are well-formed.
    
    Errors detected:
    - E006: Missing type annotations on @external parameters or return type
    - E007: @external with non-ellipsis body
    - E008: Input() without type annotation
    """
    errors: list[CheckMessage] = []
    
    # E006: Check external functions for missing annotations
    for ext in parse_result.externals.values():
        if ext.return_type == "<missing>":
            errors.append(CheckMessage(
                code="E006",
                lineno=ext.lineno,
                col_offset=ext.col_offset,
                end_lineno=None,
                end_col_offset=None,
                severity="error",
                message=f"External function '{ext.name}' missing return type annotation",
                suggestion="Add a return type annotation: async def {name}(...) -> ReturnType:",
            ))
        for param in ext.parameters:
            if param.type_annotation == "<missing>":
                errors.append(CheckMessage(
                    code="E006",
                    lineno=ext.lineno,
                    col_offset=ext.col_offset,
                    end_lineno=None,
                    end_col_offset=None,
                    severity="error",
                    message=f"Parameter '{param.name}' in external function '{ext.name}' missing type annotation",
                    suggestion=f"Add a type annotation: {param.name}: type",
                ))
    
    # E007: Check external function bodies
    # This requires re-examining the AST for @external functions
    for node in parse_result.ast_module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        has_external = any(
            (isinstance(d, ast.Name) and d.id == "external")
            or (isinstance(d, ast.Attribute) and d.attr == "external")
            for d in node.decorator_list
        )
        if not has_external:
            continue
        
        # Skip optional docstring
        body_start = 0
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            body_start = 1
        
        remaining = node.body[body_start:]
        is_valid_body = (
            len(remaining) == 1
            and isinstance(remaining[0], ast.Expr)
            and isinstance(remaining[0].value, ast.Constant)
            and remaining[0].value.value is Ellipsis
        )
        if not is_valid_body:
            errors.append(CheckMessage(
                code="E007",
                lineno=node.lineno,
                col_offset=node.col_offset,
                end_lineno=node.end_lineno,
                end_col_offset=node.end_col_offset,
                severity="error",
                message=f"External function '{node.name}' body must be '...' (Ellipsis), not actual code",
                suggestion="Replace the function body with: ...",
            ))
    
    # E008: Check inputs for missing annotations
    for inp in parse_result.inputs.values():
        if inp.type_annotation == "<missing>":
            errors.append(CheckMessage(
                code="E008",
                lineno=inp.lineno,
                col_offset=inp.col_offset,
                end_lineno=None,
                end_col_offset=None,
                severity="error",
                message=f"Input '{inp.name}' missing type annotation",
                suggestion=f"Add a type annotation: {inp.name}: type = Input(\"{inp.name}\")",
            ))
    
    return errors
```

Then in `check_pym()`, call this function and include its errors:

```python
def check_pym(parse_result: ParseResult) -> CheckResult:
    checker = MontyCompatibilityChecker(parse_result.source_lines)
    checker.visit(parse_result.ast_module)
    
    # Add declaration validation errors
    declaration_errors = check_declarations(parse_result)
    all_errors = checker.errors + declaration_errors
    
    warnings = check_for_warnings(parse_result)
    warnings.extend(checker.warnings)
    
    info = { ... }
    
    return CheckResult(
        file="<unknown>",
        valid=len(all_errors) == 0,
        errors=all_errors,
        warnings=warnings,
        info=info,
    )
```

**Important note about backward compatibility:** Currently, `parse_pym_file()` raises `CheckError` on malformed declarations, which means `grail.load()` also raises `CheckError`. After this change, `load()` will succeed even with malformed declarations — the errors will appear in `check()` results instead. This is the *correct* behavior (as the spec intends), but it means:
- `grail check` will now produce structured output for E006/E007/E008 instead of crashing
- `grail.load()` will succeed but `script.run()` may fail at Monty execution time if declarations are invalid
- Consider adding a validation step in `load()` that checks for E006/E007/E008 and raises `CheckError` if found, to maintain the "fail fast on load" behavior while still using structured messages internally

**Verification:**
```bash
python -m pytest tests/unit/test_parser.py tests/unit/test_checker.py tests/unit/test_script.py -v
```

Write new tests:
```python
# In test_checker.py
def test_e006_missing_return_type():
    """E006: External function missing return type annotation."""
    content = '''from grail import external
@external
async def fetch(id: int):
    ...
'''
    parse_result = parse_pym_content(content)
    result = check_pym(parse_result)
    assert not result.valid
    assert any(e.code == "E006" for e in result.errors)

def test_e007_non_ellipsis_body():
    """E007: External function with actual code body."""
    content = '''from grail import external
@external
async def fetch(id: int) -> str:
    return "hello"
'''
    parse_result = parse_pym_content(content)
    result = check_pym(parse_result)
    assert not result.valid
    assert any(e.code == "E007" for e in result.errors)

def test_e008_input_missing_annotation():
    """E008: Input() without type annotation."""
    content = '''from grail import Input
x = Input("x")
'''
    parse_result = parse_pym_content(content)
    result = check_pym(parse_result)
    assert not result.valid
    assert any(e.code == "E008" for e in result.errors)
```

#### Step 4.3: Implement W002 and W003 Warnings

**Problem:** The checker doesn't detect unused `@external` functions (W002) or unused `Input()` variables (W003).

**File to modify:** `src/grail/checker.py`

**Add to `check_for_warnings()`:**

```python
def check_for_warnings(parse_result: ParseResult) -> list[CheckMessage]:
    warnings: list[CheckMessage] = []
    module = parse_result.ast_module
    
    # ... existing W001 check ...
    
    # W002: Unused @external functions
    # Collect all Name references in the AST (excluding the declarations themselves)
    external_names = set(parse_result.externals.keys())
    input_names = set(parse_result.inputs.keys())
    
    referenced_names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            referenced_names.add(node.id)
        # Also check function calls: await func_name(...)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            referenced_names.add(node.attr)
    
    for name, spec in parse_result.externals.items():
        if name not in referenced_names:
            warnings.append(CheckMessage(
                code="W002",
                lineno=spec.lineno,
                col_offset=spec.col_offset,
                end_lineno=None,
                end_col_offset=None,
                severity="warning",
                message=f"External function '{name}' is declared but never called",
                suggestion=f"Remove the @external declaration for '{name}' if it's not needed",
            ))
    
    # W003: Unused Input() variables
    for name, spec in parse_result.inputs.items():
        if name not in referenced_names:
            warnings.append(CheckMessage(
                code="W003",
                lineno=spec.lineno,
                col_offset=spec.col_offset,
                end_lineno=None,
                end_col_offset=None,
                severity="warning",
                message=f"Input '{name}' is declared but never referenced",
                suggestion=f"Remove the Input() declaration for '{name}' if it's not needed",
            ))
    
    # ... existing W004 check ...
    
    return warnings
```

**Verification:**
```bash
python -m pytest tests/unit/test_checker.py -v
```

Write new tests:
```python
def test_w002_unused_external():
    """W002: Declared @external function never called."""
    content = '''from grail import external

@external
async def fetch(id: int) -> str:
    ...

# Never calls fetch()
x = 42
x
'''
    parse_result = parse_pym_content(content)
    result = check_pym(parse_result)
    assert any(w.code == "W002" for w in result.warnings)

def test_w003_unused_input():
    """W003: Declared Input() variable never referenced."""
    content = '''from grail import Input

x: int = Input("x")
y: int = Input("y")

# Only uses x, not y
x + 1
'''
    parse_result = parse_pym_content(content)
    result = check_pym(parse_result)
    assert any(w.code == "W003" and "y" in w.message for w in result.warnings)
    assert not any(w.code == "W003" and "x" in w.message for w in result.warnings)
```

#### Step 4.4: Fix `MemoryFile` Constructor Argument Style

**Problem:** `script.py:173` uses `MemoryFile(path, content=content)` — `content` is a positional parameter, not keyword-only.

**File to modify:** `src/grail/script.py`

**Change:**
```python
# BEFORE
memory_files.append(pydantic_monty.MemoryFile(path, content=content))

# AFTER
memory_files.append(pydantic_monty.MemoryFile(path, content))
```

**Verification:**
```bash
python -m pytest tests/unit/test_script.py -v
```

#### Step 4.5: Verification for Phase 4

```bash
python -m pytest tests/ -v
# All tests should pass
```

---

### Phase 5: Add Logging System

This implements Option C (Hybrid) from [Section 3](#3-logging-design-decision).

#### Step 5.1: Add `ScriptEvent` Dataclass

**File to modify:** `src/grail/_types.py`

**Add:**
```python
@dataclass
class ScriptEvent:
    """Structured event emitted during script execution.
    
    Event types:
    - "run_start": Script execution beginning
    - "run_complete": Script execution finished successfully
    - "run_error": Script execution failed
    - "print": Print output from inside the Monty sandbox
    - "check_start": Validation check beginning
    - "check_complete": Validation check finished
    """
    type: Literal["run_start", "run_complete", "run_error", "print", "check_start", "check_complete"]
    script_name: str
    timestamp: float
    text: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    input_count: int | None = None
    external_count: int | None = None
    result_summary: str | None = None
```

You'll also need to add `ScriptEvent` to `__all__` in `__init__.py` and export it.

#### Step 5.2: Add `print_callback` and `on_event` to `GrailScript.run()`

**File to modify:** `src/grail/script.py`

**Changes to `run()` method signature:**

```python
async def run(
    self,
    inputs: dict[str, Any] | None = None,
    externals: dict[str, Callable] | None = None,
    output_model: type | None = None,
    files: dict[str, str | bytes] | None = None,
    limits: dict[str, Any] | None = None,
    print_callback: Callable[[str, str], None] | None = None,
    on_event: Callable[..., None] | None = None,
) -> Any:
```

**Changes to `run()` method body:**

1. Create the internal print callback that captures output and forwards to user callbacks:

```python
captured_output: list[str] = []

def _monty_print_callback(stream: str, text: str) -> None:
    captured_output.append(text)
    if print_callback is not None:
        print_callback(stream, text)
    if on_event is not None:
        on_event(ScriptEvent(
            type="print",
            script_name=self.name,
            timestamp=time.time(),
            text=text,
        ))
```

2. Emit `run_start` event before execution:

```python
if on_event is not None:
    on_event(ScriptEvent(
        type="run_start",
        script_name=self.name,
        timestamp=time.time(),
        input_count=len(inputs),
        external_count=len(externals),
    ))
```

3. Pass `print_callback=_monty_print_callback` to `run_monty_async()`:

```python
result = await pydantic_monty.run_monty_async(
    monty,
    inputs=inputs,
    external_functions=externals,
    os=os_access,
    limits=parsed_limits,
    print_callback=_monty_print_callback,
)
```

4. On success, emit `run_complete` event:

```python
if on_event is not None:
    on_event(ScriptEvent(
        type="run_complete",
        script_name=self.name,
        timestamp=time.time(),
        duration_ms=duration_ms,
        result_summary=f"{type(result).__name__}",
    ))
```

5. On error, emit `run_error` event:

```python
if on_event is not None:
    on_event(ScriptEvent(
        type="run_error",
        script_name=self.name,
        timestamp=time.time(),
        duration_ms=duration_ms,
        error=str(mapped_error),
    ))
```

6. Update artifact writing to include captured stdout:

```python
stdout_text = "".join(captured_output)

# In the success path:
if self._artifacts:
    self._artifacts.write_run_log(
        self.name,
        stdout=stdout_text,
        stderr="",
        duration_ms=duration_ms,
        success=True,
    )

# In the error path:
if self._artifacts:
    self._artifacts.write_run_log(
        self.name,
        stdout=stdout_text,
        stderr=str(mapped_error),
        duration_ms=duration_ms,
        success=False,
    )
```

7. Also update `_validate_inputs` and `_validate_externals` to remove the bare `print()` calls (lines 119 and 139). Replace with event emission or remove entirely — warnings about extra inputs/externals should go through the event system or be silent:

```python
# BEFORE
print(f"Warning: Extra input '{name}' not declared in script")

# AFTER
# Silent — the user explicitly passed these, they know what they're doing.
# Or emit an event:
# (This requires passing on_event through, which complicates the internal API.
#  The simpler approach is to just remove the print statements.)
```

#### Step 5.3: Add `print_callback` and `on_event` to `run_sync()`

**File to modify:** `src/grail/script.py`

**Change `run_sync()` signature to accept the new parameters:**

```python
def run_sync(
    self,
    inputs: dict[str, Any] | None = None,
    externals: dict[str, Callable] | None = None,
    **kwargs,
) -> Any:
```

The `**kwargs` already passes through to `run()`, so `print_callback` and `on_event` will work automatically.

#### Step 5.4: Add `print_callback` to `grail.run()` (Inline Escape Hatch)

**File to modify:** `src/grail/script.py`

**Update the module-level `run()` function:**

```python
async def run(
    code: str,
    inputs: dict[str, Any] | None = None,
    print_callback: Callable[[str, str], None] | None = None,
) -> Any:
    """
    Execute inline Monty code (escape hatch for simple cases).

    Args:
        code: Monty code to execute
        inputs: Input values
        print_callback: Optional callback for print() output from the script.
            Signature: (stream: str, text: str) -> None

    Returns:
        Result of code execution
    """
    if pydantic_monty is None:
        raise RuntimeError("pydantic-monty not installed")

    inputs = inputs or {}

    monty = pydantic_monty.Monty(code, inputs=list(inputs.keys()))
    result = await pydantic_monty.run_monty_async(
        monty, inputs=inputs, print_callback=print_callback,
    )
    return result
```

#### Step 5.5: Export `ScriptEvent` from `__init__.py`

**File to modify:** `src/grail/__init__.py`

**Add:**
```python
from grail._types import CheckResult, CheckMessage, ScriptEvent
```

And add `"ScriptEvent"` to `__all__`.

#### Step 5.6: Add Check Events to `GrailScript.check()`

**File to modify:** `src/grail/script.py`

**Update `check()` to accept `on_event`:**

```python
def check(self, on_event: Callable[..., None] | None = None) -> CheckResult:
    """
    Run validation checks on the script.

    Args:
        on_event: Optional callback for structured events

    Returns:
        CheckResult with errors, warnings, and info
    """
    if on_event is not None:
        on_event(ScriptEvent(
            type="check_start",
            script_name=self.name,
            timestamp=time.time(),
        ))
    
    parse_result = parse_pym_file(self.path)
    check_result = check_pym(parse_result)
    check_result.file = str(self.path)

    if self._artifacts:
        self._artifacts.write_script_artifacts(
            self.name, self.stubs, self.monty_code,
            check_result, self.externals, self.inputs,
        )

    if on_event is not None:
        on_event(ScriptEvent(
            type="check_complete",
            script_name=self.name,
            timestamp=time.time(),
            result_summary=f"{'valid' if check_result.valid else 'invalid'}: {len(check_result.errors)} errors, {len(check_result.warnings)} warnings",
        ))

    return check_result
```

#### Step 5.7: Write Logging Tests

**Create:** `tests/unit/test_logging.py`

```python
"""Tests for the logging/event system."""

import time
from grail._types import ScriptEvent


def test_script_event_creation():
    """ScriptEvent can be created with required fields."""
    event = ScriptEvent(
        type="run_start",
        script_name="test",
        timestamp=time.time(),
    )
    assert event.type == "run_start"
    assert event.script_name == "test"
    assert event.text is None


def test_script_event_print():
    """ScriptEvent can represent print output."""
    event = ScriptEvent(
        type="print",
        script_name="test",
        timestamp=time.time(),
        text="hello world\n",
    )
    assert event.type == "print"
    assert event.text == "hello world\n"


def test_script_event_run_complete():
    """ScriptEvent can represent run completion."""
    event = ScriptEvent(
        type="run_complete",
        script_name="test",
        timestamp=time.time(),
        duration_ms=42.5,
        result_summary="dict",
    )
    assert event.duration_ms == 42.5


def test_script_event_run_error():
    """ScriptEvent can represent run failure."""
    event = ScriptEvent(
        type="run_error",
        script_name="test",
        timestamp=time.time(),
        error="NameError: x is not defined",
    )
    assert event.error is not None
```

**Add integration tests** in `tests/integration/test_end_to_end.py`:

```python
@pytest.mark.asyncio
async def test_print_callback_captures_output():
    """print_callback receives output from print() inside Monty."""
    pydantic_monty = pytest.importorskip("pydantic_monty")
    
    output = []
    def capture(stream, text):
        output.append(text)
    
    result = await grail.run(
        'print("hello from monty")\n42',
        inputs={},
        print_callback=capture,
    )
    
    assert result == 42
    stdout = "".join(output)
    assert "hello from monty" in stdout


@pytest.mark.asyncio
async def test_on_event_receives_lifecycle_events():
    """on_event callback receives structured lifecycle events."""
    pydantic_monty = pytest.importorskip("pydantic_monty")
    
    # This test requires a .pym file — use the fixture
    script = grail.load("tests/fixtures/simple.pym", grail_dir=None)
    
    events = []
    
    async def mock_external(x):
        return x * 2
    
    result = await script.run(
        inputs={"x": 5},
        externals={"double": mock_external},
        on_event=lambda e: events.append(e),
    )
    
    event_types = [e.type for e in events]
    assert "run_start" in event_types
    assert "run_complete" in event_types
```

#### Step 5.8: Verification for Phase 5

```bash
python -m pytest tests/ -v

# Verify ScriptEvent is importable
python -c "from grail import ScriptEvent; print('OK')"
```

---

### Phase 6: Medium-Priority Fixes

#### Step 6.1: Set `script_name` on Monty

**Problem:** `Monty()` is never passed `script_name`, so all tracebacks show `main.py` instead of the actual `.pym` filename.

**File to modify:** `src/grail/script.py`

**Change in `run()` method (Monty construction):**

```python
# BEFORE
monty = pydantic_monty.Monty(
    self.monty_code,
    type_check=True,
    type_check_stubs=self.stubs,
    inputs=list(self.inputs.keys()),
    external_functions=list(self.externals.keys()),
)

# AFTER
monty = pydantic_monty.Monty(
    self.monty_code,
    script_name=f"{self.name}.pym",
    type_check=True,
    type_check_stubs=self.stubs,
    inputs=list(self.inputs.keys()),
    external_functions=list(self.externals.keys()),
)
```

**Verification:**
```bash
python -m pytest tests/ -v
```

#### Step 6.2: Add `dataclass_registry` Support

**Problem:** Monty's `Monty()` constructor accepts `dataclass_registry: list[type]` for proper `isinstance()` support on output, but Grail doesn't expose it.

**File to modify:** `src/grail/script.py`

**Add parameter to `GrailScript.__init__`:**

```python
def __init__(
    self,
    ...,
    dataclass_registry: list[type] | None = None,
):
    ...
    self.dataclass_registry = dataclass_registry
```

**Add parameter to `load()`:**

```python
def load(
    path: str | Path,
    limits: dict[str, Any] | None = None,
    files: dict[str, str | bytes] | None = None,
    grail_dir: str | Path | None = ".grail",
    dataclass_registry: list[type] | None = None,
) -> GrailScript:
```

Pass it through to `GrailScript()`.

**Use in `run()`:**

```python
monty = pydantic_monty.Monty(
    self.monty_code,
    script_name=f"{self.name}.pym",
    type_check=True,
    type_check_stubs=self.stubs,
    inputs=list(self.inputs.keys()),
    external_functions=list(self.externals.keys()),
    dataclass_registry=self.dataclass_registry,
)
```

**Verification:**
```bash
python -m pytest tests/unit/test_script.py -v
```

#### Step 6.3: Fix `run_sync` Event Loop Issues

**Problem:** `asyncio.run()` fails when called from within an existing event loop (Jupyter, FastAPI, etc.).

**File to modify:** `src/grail/script.py`

**Replace `run_sync` implementation:**

```python
def run_sync(
    self,
    inputs: dict[str, Any] | None = None,
    externals: dict[str, Callable] | None = None,
    **kwargs,
) -> Any:
    """
    Synchronous wrapper around run().

    Args:
        inputs: Input values
        externals: External function implementations
        **kwargs: Additional arguments for run()

    Returns:
        Result of script execution
    
    Raises:
        RuntimeError: If called from within an async context where a new
            event loop cannot be created. Use `await script.run()` instead.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(self.run(inputs, externals, **kwargs))
    else:
        raise RuntimeError(
            "run_sync() cannot be used inside an async context "
            "(e.g., Jupyter, FastAPI). Use 'await script.run()' instead."
        )
```

**Why not `nest_asyncio`?** Adding a dependency for this edge case is not worth it. A clear error message is better than a hidden dependency.

**Verification:**
```bash
python -m pytest tests/ -v
```

Add a test:
```python
def test_run_sync_raises_in_async_context():
    """run_sync should raise RuntimeError when called from an async context."""
    # This test validates the error message, not the actual async detection
    # (which is hard to test without actually being in an async context)
    pass  # See integration tests
```

#### Step 6.4: Add `max_allocations` and `gc_interval` to Limits

**Problem:** `parse_limits()` doesn't handle `max_allocations` or `gc_interval`, which are valid Monty `ResourceLimits` fields.

**File to modify:** `src/grail/limits.py`

**Update `parse_limits()`:**

```python
def parse_limits(limits: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}

    for key, value in limits.items():
        if key == "max_memory" and isinstance(value, str):
            parsed["max_memory"] = parse_memory_string(value)
        elif key == "max_memory":
            parsed["max_memory"] = value
        elif key == "max_duration" and isinstance(value, str):
            parsed["max_duration_secs"] = parse_duration_string(value)
        elif key == "max_duration":
            parsed["max_duration_secs"] = float(value)
        elif key == "max_recursion":
            parsed["max_recursion_depth"] = value
        elif key == "max_allocations":
            parsed["max_allocations"] = int(value)
        elif key == "gc_interval":
            parsed["gc_interval"] = int(value)
        else:
            parsed[key] = value

    return parsed
```

**Update presets** if appropriate (add `max_allocations` to `STRICT` if desired).

**Verification:**
```bash
python -m pytest tests/unit/test_limits.py -v
```

Add tests:
```python
def test_parse_max_allocations():
    result = parse_limits({"max_allocations": 10000})
    assert result["max_allocations"] == 10000

def test_parse_gc_interval():
    result = parse_limits({"gc_interval": 500})
    assert result["gc_interval"] == 500
```

#### Step 6.5: Fix CLI `cmd_run` to Pass Loaded Script

**Problem:** `cmd_run` loads and validates the `.pym` file, then loads the host module and calls `host_module.main()` without passing the `GrailScript`. The host re-parses the file independently.

**File to modify:** `src/grail/cli.py`

**Change:** After loading the script, pass it to the host's `main()`:

```python
def cmd_run(args):
    """Run a .pym file with a host file."""
    import asyncio
    import importlib.util

    try:
        script_path = Path(args.file)
        if not script_path.exists():
            print(f"Error: {script_path} not found", file=sys.stderr)
            return 1

        # Load and validate the .pym script
        script = load(script_path)

        # Parse inputs
        inputs = {}
        for item in args.input:
            if "=" not in item:
                print(f"Error: Invalid input format '{item}'. Use key=value.", file=sys.stderr)
                return 1
            key, value = item.split("=", 1)
            inputs[key.strip()] = value.strip()

        if args.host:
            host_path = Path(args.host)
            if not host_path.exists():
                print(f"Error: Host file {host_path} not found", file=sys.stderr)
                return 1

            spec = importlib.util.spec_from_file_location("host", host_path)
            host_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(host_module)

            if hasattr(host_module, "main"):
                main_fn = host_module.main
                # Always pass script and inputs to main()
                if asyncio.iscoroutinefunction(main_fn):
                    asyncio.run(main_fn(script=script, inputs=inputs))
                else:
                    main_fn(script=script, inputs=inputs)
            else:
                print("Error: Host file must define a main() function", file=sys.stderr)
                return 1
        else:
            print("Error: --host <host.py> is required", file=sys.stderr)
            return 1

        return 0
    except ParseError as e:
        # ... error handling unchanged ...
```

**Note:** This is a breaking change for existing host files. The host's `main()` now receives `script` and `inputs` as keyword arguments. Update the sample host file in `cmd_init` accordingly.

**Verification:**
```bash
python -m pytest tests/unit/test_cli.py -v
```

#### Step 6.6: Add Sync Wrapper for `grail.run()`

**Problem:** Module-level `grail.run()` is async-only. Users in non-async contexts have to write `asyncio.run(grail.run(...))`.

**File to modify:** `src/grail/script.py`

**Add:**
```python
def run_sync(
    code: str,
    inputs: dict[str, Any] | None = None,
    print_callback: Callable[[str, str], None] | None = None,
) -> Any:
    """
    Synchronous wrapper for inline Monty code execution.

    Args:
        code: Monty code to execute
        inputs: Input values
        print_callback: Optional callback for print() output

    Returns:
        Result of code execution
    
    Raises:
        RuntimeError: If called from within an async context.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run(code, inputs, print_callback=print_callback))
    else:
        raise RuntimeError(
            "run_sync() cannot be used inside an async context. "
            "Use 'await grail.run()' instead."
        )
```

**Export from `__init__.py`:**
```python
from grail.script import load, run, run_sync
```

Add `"run_sync"` to `__all__`.

**Verification:**
```bash
python -m pytest tests/ -v
python -c "from grail import run_sync; print('OK')"
```

#### Step 6.7: Verification for Phase 6

```bash
python -m pytest tests/ -v
```

---

### Phase 7: Polish & Low-Priority

#### Step 7.1: Make `pydantic` Optional

**Problem:** `pydantic` is listed as a required dependency but is only used for `output_model` validation.

**File to modify:** `pyproject.toml`

**Change:**
```toml
# BEFORE
dependencies = [
  "pydantic>=2.12.5",
  "pydantic-monty",
]

# AFTER
dependencies = [
  "pydantic-monty",
]

[project.optional-dependencies]
pydantic = ["pydantic>=2.12.5"]
dev = [
  "pydantic>=2.12.5",
  "pytest>=8.0",
  ...
]
```

**Also update** `script.py` to handle missing pydantic gracefully:

```python
# In the output_model validation section of run():
if output_model is not None:
    try:
        result = (
            output_model(**result) if isinstance(result, dict) else output_model(result)
        )
    except Exception as e:
        raise OutputError(f"Output validation failed: {e}", validation_errors=e)
```

This already works without importing pydantic — it just calls the model class. No change needed in the code, just the dependency.

**Verification:**
```bash
pip install -e .
python -c "import grail; print('OK')"
```

#### Step 7.2: Surface E1xx Type Checker Errors in `check()`

**Problem:** `grail check` doesn't run Monty's type checker, so E1xx errors are never surfaced.

**File to modify:** `src/grail/checker.py` or `src/grail/script.py`

**Add to `GrailScript.check()`:**

After running the AST-based checks, also run Monty's type checker and convert any `MontyTypingError` to `CheckMessage` entries:

```python
def check(self, on_event=None) -> CheckResult:
    parse_result = parse_pym_file(self.path)
    check_result = check_pym(parse_result)
    check_result.file = str(self.path)
    
    # Run Monty type checker if available
    if pydantic_monty is not None:
        try:
            pydantic_monty.Monty(
                self.monty_code,
                script_name=f"{self.name}.pym",
                type_check=True,
                type_check_stubs=self.stubs,
                inputs=list(self.inputs.keys()),
                external_functions=list(self.externals.keys()),
            )
        except pydantic_monty.MontyTypingError as e:
            # Convert to CheckMessage entries
            check_result.errors.append(CheckMessage(
                code="E100",
                lineno=0,
                col_offset=0,
                end_lineno=None,
                end_col_offset=None,
                severity="error",
                message=f"Type error: {str(e)}",
                suggestion="Fix the type error indicated above",
            ))
            check_result.valid = False
    
    # ... write artifacts, emit events ...
    
    return check_result
```

**Verification:**
```bash
python -m pytest tests/ -v
```

#### Step 7.3: Verify `from typing import ...` Handling in Codegen

**Problem:** The codegen passes `from typing import ...` through to Monty code. We need to verify this is correct.

**Investigation:** Check if Monty handles `from typing import ...` — look at the Monty test suite or try it.

**If Monty does NOT support it:** Add stripping of typing imports in `GrailDeclarationStripper.visit_ImportFrom()`:

```python
def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom | None:
    if node.module in ("grail", "typing"):
        return None  # Remove both grail and typing imports
    return node
```

**If Monty DOES support it:** No change needed, but add a comment explaining why typing imports are preserved.

**Verification:**
```bash
python -m pytest tests/unit/test_codegen.py -v
```

#### Step 7.4: Remove Bare `print()` Calls from Library Code

**Problem:** `script.py` uses bare `print()` for warnings (lines 119, 139). Library code should never use `print()` directly.

**Files to modify:** `src/grail/script.py`

**Change:** Remove the `print()` calls in `_validate_inputs()` and `_validate_externals()`. Extra inputs/externals are not errors — the user explicitly passed them. If we want to warn, use the `on_event` system or Python's `warnings` module:

```python
import warnings

# In _validate_inputs:
for name in inputs:
    if name not in self.inputs:
        warnings.warn(
            f"Extra input '{name}' not declared in script",
            stacklevel=2,
        )

# In _validate_externals:
for name in externals:
    if name not in self.externals:
        warnings.warn(
            f"Extra external '{name}' not declared in script",
            stacklevel=2,
        )
```

**Verification:**
```bash
python -m pytest tests/ -v
```

#### Step 7.5: Verification for Phase 7

```bash
python -m pytest tests/ -v
```

---

### Phase 8: Spec & Documentation Updates

#### Step 8.1: Update `GRAIL_CONCEPT.md`

**Remove:**
- Section 10 (Pause/Resume Snapshots) entirely
- `Snapshot` references from Section 5 (Host-Side Python API)
- `grail.Snapshot` from Section 13 (Package Structure) public API list
- `script.start(inputs, externals) -> Snapshot` from the GrailScript methods table
- Any `Snapshot.load(data) -> Snapshot` references

**Add:**
- Logging section (new Section 10 or incorporated into Section 5):
  - `print_callback` parameter on `script.run()`
  - `on_event` parameter on `script.run()`
  - `ScriptEvent` type documentation
  - Example usage
- `run_sync` module-level function in Section 5
- `dataclass_registry` parameter in Section 5
- `script_name` in Monty constructor (mention in architecture notes)

**Update:**
- Version references to v3
- Package structure to show `py.typed`, remove `snapshot.py`
- Public API surface to include `ScriptEvent`, `run_sync`, remove `Snapshot`
- Error codes table: add E006, E007, E008, E1xx as structured (not exception-throwing)
- Warning codes table: W002 and W003 as implemented
- Limits table: add `max_allocations` and `gc_interval`

#### Step 8.2: Update `CODE_REVIEW.md`

Add a note at the top indicating that the issues have been addressed in v3, referencing this refactor guide.

#### Step 8.3: Update `README.md`

Add a brief description of the library and its v3 status.

---

## 5. Final Verification Checklist

After completing all phases, run through this checklist:

### Tests

```bash
# All tests pass
python -m pytest tests/ -v

# Run with coverage if available
python -m pytest tests/ --cov=grail --cov-report=term-missing
```

### Public API

```python
# All public symbols importable
from grail import (
    load, run, run_sync,
    external, Input,
    ScriptEvent,
    STRICT, DEFAULT, PERMISSIVE,
    GrailError, ParseError, CheckError, InputError,
    ExternalError, ExecutionError, LimitError, OutputError,
    CheckResult, CheckMessage,
)
print(f"Version: {grail.__version__}")
# Should print: Version: 3.0.0

# Snapshot should NOT be importable
try:
    from grail import Snapshot
    assert False, "Snapshot should not exist"
except ImportError:
    print("Snapshot correctly removed")
```

### Version Consistency

```bash
python -c "import grail; print(grail.__version__)"
# 3.0.0

grep 'version' pyproject.toml | head -1
# version = "3.0.0"
```

### Typing

```bash
# py.typed exists
test -f src/grail/py.typed && echo "py.typed exists" || echo "MISSING"
```

### Feature Verification

| Feature | How to Verify |
|---------|---------------|
| AST not mutated by codegen | `test_generate_monty_code_does_not_mutate_ast` passes |
| Source map robust | `test_source_map_complex_code` passes |
| Structured error data used | Integration test with MontyRuntimeError |
| E006/E007/E008 structured | `test_e006_*`, `test_e007_*`, `test_e008_*` pass |
| W002/W003 implemented | `test_w002_*`, `test_w003_*` pass |
| MemoryFile positional | No kwargs on MemoryFile construction |
| print_callback works | `test_print_callback_captures_output` passes |
| on_event works | `test_on_event_receives_lifecycle_events` passes |
| Output captured in run.log | Check `.grail/*/run.log` after execution |
| script_name set | Error tracebacks show `.pym` filename |
| dataclass_registry exposed | Parameter accepted on `load()` |
| run_sync safe | Clear error in async context |
| max_allocations/gc_interval | `test_parse_max_allocations`, `test_parse_gc_interval` pass |
| No bare print() in library | grep for `print(` in `src/grail/` shows only necessary usage |
| Snapshot removed | `Snapshot` not in `__all__`, `snapshot.py` deleted |
| Version matches | `__init__.py` and `pyproject.toml` both say `3.0.0` |

### Summary of Files Changed

| File | Action | Phase |
|------|--------|-------|
| `src/grail/__init__.py` | Modify (version, exports) | 1, 2, 5, 6 |
| `src/grail/_types.py` | Modify (ResourceLimits TypedDict, ScriptEvent) | 1, 5 |
| `src/grail/py.typed` | Create | 1 |
| `src/grail/snapshot.py` | **Delete** | 2 |
| `src/grail/script.py` | Modify (remove start(), fix errors, add logging, add params) | 2, 3, 4, 5, 6, 7 |
| `src/grail/codegen.py` | Modify (deepcopy AST, fix source map) | 3 |
| `src/grail/checker.py` | Modify (add E006-E008, W002-W003) | 4 |
| `src/grail/parser.py` | Modify (lenient extraction) | 4 |
| `src/grail/limits.py` | Modify (max_allocations, gc_interval) | 6 |
| `src/grail/cli.py` | Modify (pass script to host) | 6 |
| `src/grail/errors.py` | No changes needed | — |
| `src/grail/stubs.py` | No changes needed | — |
| `src/grail/artifacts.py` | No changes needed | — |
| `src/grail/_external.py` | No changes needed | — |
| `src/grail/_input.py` | No changes needed | — |
| `pyproject.toml` | Modify (version, pydantic optional) | 1, 7 |
| `tests/unit/test_snapshot.py` | **Delete** | 2 |
| `tests/unit/test_public_api.py` | Modify | 2 |
| `tests/unit/test_codegen.py` | Modify (add tests) | 3 |
| `tests/unit/test_checker.py` | Modify (add tests) | 4 |
| `tests/unit/test_parser.py` | Modify (update expectations) | 4 |
| `tests/unit/test_logging.py` | **Create** | 5 |
| `tests/unit/test_limits.py` | Modify (add tests) | 6 |
| `tests/unit/test_cli.py` | Modify | 6 |
| `tests/integration/test_end_to_end.py` | Modify (remove snapshot, add logging) | 2, 5 |
| `GRAIL_CONCEPT.md` | Modify | 8 |
| `CODE_REVIEW.md` | Modify (add v3 note) | 8 |
