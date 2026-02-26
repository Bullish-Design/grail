# Grail V3.2 — Comprehensive Refactoring Plan

**Based on:** CODE_REVIEW_V3.md (2026-02-25), V3_1_REFACTOR_PLAN.md review  
**Purpose:** Corrected and expanded refactoring guide addressing all code review findings  
**Backwards compatibility:** Not a concern. Best possible codebase for the future only.

---

## Status of V3.1 Phase 1

The following Phase 1 items from V3_1 were already applied and are **not repeated** here:

| V3.1 Task | Status |
|-----------|--------|
| 1.1 Export `GrailScript` | Done |
| 1.2 Export Limits constants (`STRICT`, `DEFAULT`, `PERMISSIVE`) | Done |
| 1.3 Export `ExternalSpec`, `InputSpec` | Done |
| 1.4 Fix bare `assert` | Done |
| 1.5 Remove dead `validate_external_function()` | Done |
| 1.6 Remove legacy limits API (`parse_limits`, `merge_limits`) | Done |
| 1.7 Fix `spec.loader` null check in CLI | Done |

The following Phase 1 items were **NOT applied** or were **applied incorrectly** and are addressed below:

| V3.1 Task | Problem |
|-----------|---------|
| 1.8 Fix Pydantic v2 API | Proposed fix was a no-op (both branches identical) |
| 1.9 Fix `ast.Assign` Input stripping | Proposed fix had wrong return types and conflicting implementations |
| 1.10 Fix stub `typing` imports | Incomplete — only addresses detection, not generation |

---

## How to Use This Guide

This plan is organized into **6 phases**, ordered by dependency:

1. **Phase 1: Critical Bug Fixes** — Correctness issues that produce wrong behavior
2. **Phase 2: Architecture & Deduplication** — Structural improvements that simplify the codebase
3. **Phase 3: Data Model & Type Improvements** — Type safety and data completeness
4. **Phase 4: API Surface & Monty Coverage** — Exposing missing capabilities
5. **Phase 5: CLI & Peripheral Improvements** — CLI, artifacts, logging
6. **Phase 6: Tests** — Comprehensive test coverage for all changes

Within each phase, tasks are independent unless noted. Cross-phase dependencies are called out explicitly.

---

## Phase 1: Critical Bug Fixes

*These fix incorrect behavior that will bite users.*

### 1.1 Fix `load()` Silently Ignoring Check Errors
**File:** `src/grail/script.py` — `load()` function  
**Review ref:** CODE_REVIEW_V3 §1.4, §7 #1

**Problem:** `load()` calls `check_pym()` but never inspects the result. Invalid scripts load silently and only fail at runtime.

**Fix:** After calling `check_pym()`, raise if there are errors:

```python
parse_result = parse_pym_file(path)
check_result = check_pym(parse_result)

errors = [msg for msg in check_result.messages if msg.code.startswith("E")]
if errors:
    error_summary = "; ".join(f"{m.code}: {m.message} (line {m.lineno})" for m in errors)
    raise CheckError(f"Script validation failed with {len(errors)} error(s): {error_summary}")
```

**Important:** Verify that `CheckError.__init__` accepts this signature. If it only accepts `message`, use just the string. Do NOT pass an `errors=` kwarg without confirming the constructor supports it.

**Also:** Store the `parse_result` on the `GrailScript` instance (needed for Phase 1.6 TOCTOU fix):

```python
script = GrailScript(...)
script._parse_result = parse_result  # Cache for check() reuse
```

**Verify:** Create a `.pym` with `class Foo: pass` (triggers E001), call `grail.load()`, assert `CheckError` is raised.

---

### 1.2 Fix `output_model` Validation (Pydantic v2 API)
**File:** `src/grail/script.py` — around the `output_model` handling  
**Review ref:** CODE_REVIEW_V3 §3.7

**Problem:** The current code uses `output_model(**result)` / `output_model(result)` — Pydantic v1 API. The V3.1 plan proposed identical branches (no-op fix).

**Fix:** Use `model_validate()` consistently, with `from_attributes=True` for non-dict results:

```python
if output_model is not None:
    try:
        if isinstance(result, dict):
            result = output_model.model_validate(result)
        else:
            result = output_model.model_validate(result, from_attributes=True)
    except Exception as e:
        raise OutputError(
            f"Output validation failed: {e}",
            validation_errors=e
        ) from e
```

**Also fix:** Tighten the `output_model` parameter type from `type` to `type[BaseModel]` in the method signature. Add the import at module level:

```python
from pydantic import BaseModel
```

**Verify:** Test with a Pydantic model receiving both a dict and a model instance.

---

### 1.3 Fix `extract_function_params` — Silent Data Loss
**File:** `src/grail/parser.py` — `extract_function_params`  
**File:** `src/grail/_types.py` — `ParamSpec`  
**Review ref:** CODE_REVIEW_V3 §2.1

**Problem:** Only iterates `func_node.args.args`. Silently drops `*args`, `**kwargs`, keyword-only, and positional-only params.

**Step 1 — Update `ParamSpec`** (do this first):

```python
from enum import Enum

class ParamKind(str, Enum):
    POSITIONAL_ONLY = "positional-only"
    POSITIONAL_OR_KEYWORD = "positional-or-keyword"
    VAR_POSITIONAL = "var-positional"      # *args
    KEYWORD_ONLY = "keyword-only"
    VAR_KEYWORD = "var-keyword"            # **kwargs

@dataclass
class ParamSpec:  # Consider renaming to ParameterSpec to avoid shadowing typing.ParamSpec
    name: str
    annotation: str | None
    has_default: bool
    default: Any | None = None
    kind: ParamKind = ParamKind.POSITIONAL_OR_KEYWORD
```

**Step 2 — Rewrite `extract_function_params`:**

```python
def extract_function_params(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ParamSpec]:
    params = []
    args = func_node.args

    # Defaults are right-aligned: if there are 3 args and 1 default,
    # the default applies to the 3rd arg.
    num_posonly = len(args.posonlyargs)
    num_regular = len(args.args)
    num_pos_defaults = len(args.defaults)
    # defaults apply to the LAST N of (posonlyargs + args)
    total_positional = num_posonly + num_regular
    first_default_idx = total_positional - num_pos_defaults

    # Positional-only arguments
    for i, arg in enumerate(args.posonlyargs):
        global_idx = i
        has_default = global_idx >= first_default_idx
        default_val = None
        if has_default:
            default_val = ast.dump(args.defaults[global_idx - first_default_idx])
        params.append(ParamSpec(
            name=arg.arg,
            annotation=_get_annotation(arg.annotation),
            has_default=has_default,
            default=default_val,
            kind=ParamKind.POSITIONAL_ONLY,
        ))

    # Regular positional-or-keyword arguments
    for i, arg in enumerate(args.args):
        global_idx = num_posonly + i
        has_default = global_idx >= first_default_idx
        default_val = None
        if has_default:
            default_val = ast.dump(args.defaults[global_idx - first_default_idx])
        params.append(ParamSpec(
            name=arg.arg,
            annotation=_get_annotation(arg.annotation),
            has_default=has_default,
            default=default_val,
            kind=ParamKind.POSITIONAL_OR_KEYWORD,
        ))

    # *args
    if args.vararg:
        params.append(ParamSpec(
            name=args.vararg.arg,
            annotation=_get_annotation(args.vararg.annotation),
            has_default=False,
            kind=ParamKind.VAR_POSITIONAL,
        ))

    # Keyword-only arguments (kw_defaults aligns 1:1 with kwonlyargs)
    for i, arg in enumerate(args.kwonlyargs):
        kw_default = args.kw_defaults[i]  # None if no default
        params.append(ParamSpec(
            name=arg.arg,
            annotation=_get_annotation(arg.annotation),
            has_default=kw_default is not None,
            default=ast.dump(kw_default) if kw_default is not None else None,
            kind=ParamKind.KEYWORD_ONLY,
        ))

    # **kwargs
    if args.kwarg:
        params.append(ParamSpec(
            name=args.kwarg.arg,
            annotation=_get_annotation(args.kwarg.annotation),
            has_default=False,
            kind=ParamKind.VAR_KEYWORD,
        ))

    return params
```

**Verify:** Parse `@external def foo(a, /, b, *args, c=1, **kwargs): ...` and confirm all 5 params are extracted with correct kinds and defaults.

---

### 1.4 Fix `GrailDeclarationStripper` for `ast.Assign` Input()
**File:** `src/grail/codegen.py`  
**Review ref:** CODE_REVIEW_V3 §2.3

**Problem:** The current `visit_Assign` implementation exists but has issues. Additionally, `visit_AnnAssign` strips *any* annotated assignment where the target name is in `self.inputs`, even if the value isn't an `Input()` call (e.g., `x: int = 42` would be incorrectly stripped if `x` is an input name).

**Fix both visitors:**

```python
def _is_input_call(self, node: ast.expr | None) -> bool:
    """Check if an expression is an Input() or grail.Input() call."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "Input":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "Input":
        return True
    return False

def visit_Assign(self, node: ast.Assign) -> ast.AST | None:
    if self._is_input_call(node.value):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in self.inputs:
                return None  # Remove this node entirely
    return self.generic_visit(node)

def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST | None:
    if isinstance(node.target, ast.Name) and node.target.id in self.inputs:
        if self._is_input_call(node.value):
            return None  # Remove this node entirely
    return self.generic_visit(node)
```

**Key corrections from V3.1 plan:**
- Return `None` to remove nodes, not `self.module` or `ast.Pass()`
- Handle both `Input()` and `grail.Input()` call styles
- Add value check to `visit_AnnAssign` to avoid stripping non-Input assignments

**Verify:** Parse and codegen a `.pym` with both `x: int = Input("x")` and `y = Input("y")`. Confirm both are stripped. Also confirm `z: int = 42` is NOT stripped even if there's an input named `z`.

---

### 1.5 Fix Stub Generator for `typing` Imports
**File:** `src/grail/stubs.py`  
**Review ref:** CODE_REVIEW_V3 §2.4

**Problem:** Only detects `Any`. Other typing names (`Optional`, `Union`, `List`, etc.) produce invalid stubs. Also, docstrings containing triple quotes break stub syntax.

**Fix — Track which typing names are needed and import only those:**

```python
_TYPING_NAMES: set[str] = {
    "Any", "Optional", "Union", "List", "Dict", "Set", "Tuple",
    "Callable", "Type", "Literal", "Annotated", "TypeVar",
    "Generic", "Protocol", "Final", "TypedDict", "NotRequired",
    "Required", "ClassVar", "TypeGuard", "Never", "Self",
}

def _collect_typing_imports(annotations: list[str]) -> set[str]:
    """Return the set of typing names used across all annotations."""
    needed: set[str] = set()
    for ann in annotations:
        for name in _TYPING_NAMES:
            if re.search(rf"\b{name}\b", ann):
                needed.add(name)
    return needed
```

Then in stub generation, collect all annotations first, determine which typing names are needed, and emit only those imports:

```python
typing_imports = _collect_typing_imports(all_annotations)
if typing_imports:
    stub_lines.insert(0, f"from typing import {', '.join(sorted(typing_imports))}")
```

**Also fix docstring escaping:**

```python
if docstring:
    escaped = docstring.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
    stub_lines.append(f'    """{escaped}"""')
```

**Also fix:** Remove the duplicate `"Protocol"` entry in `_TYPING_NAMES` if present.

**Verify:** Generate a stub for a file with `Optional[int]`, `list[Dict[str, Any]]`, confirm valid Python syntax with correct imports.

---

### 1.6 Fix `check()` TOCTOU Issue
**File:** `src/grail/script.py` — `GrailScript.check()`  
**Review ref:** CODE_REVIEW_V3 §1.4

**Problem:** `check()` re-parses from disk, so it validates different code than what was loaded if the file changed between `load()` and `check()`.

**Fix:** Use the cached `_parse_result` stored in Task 1.1:

```python
def check(self) -> CheckResult:
    """Check this script for Monty compatibility issues.

    Uses the parse result from load-time, not a fresh disk read,
    to ensure consistency with the loaded code.
    """
    return check_pym(self._parse_result)
```

**Depends on:** Task 1.1 (storing `_parse_result` on the instance).

**Verify:** Load a script, modify the file on disk, call `check()` — should return results for the *original* code, not the modified file.

---

### 1.7 Fix `_map_error_to_pym` — Regex and Limit Detection
**File:** `src/grail/script.py` — `_map_error_to_pym`  
**Review ref:** CODE_REVIEW_V3 §3.5, §3.6

**Problem 1 — Regex:** `re.search(r"line (\d+)", ...)` matches "inline 42", "deadline 3", etc.

**Problem 2 — Limit detection:** Any error containing "memory" becomes `LimitError`, even "Failed to access memory address".

**Fix — Prioritize exception type, then structured data, then regex as last resort:**

```python
def _map_error_to_pym(self, error: Exception) -> GrailError:
    error_msg = str(error)

    # 1. Check exception type first (most reliable)
    if hasattr(error, 'limit_type'):
        # Monty limit errors should carry structured data
        return LimitError(error_msg, limit_type=error.limit_type)

    # 2. Extract line number from structured traceback if available
    lineno = None
    if hasattr(error, 'traceback') and callable(error.traceback):
        tb = error.traceback()
        if tb and tb.frames:
            frame = tb.frames[-1]
            monty_line = frame.line
            lineno = self._source_map.monty_to_pym.get(monty_line)
            # Do NOT fall back to monty_line — it's meaningless to users

    # 3. Regex fallback — only for well-structured patterns
    if lineno is None:
        match = re.search(r"(?:^|,\s*)line\s+(\d+)(?:\s*,|\s*$)", error_msg)
        if match:
            raw_line = int(match.group(1))
            lineno = self._source_map.monty_to_pym.get(raw_line)
            # Still don't fall back — None is better than a wrong number

    # 4. Limit detection — require exception type OR "limit" + keyword
    error_msg_lower = error_msg.lower()
    if "limit" in error_msg_lower or "exceeded" in error_msg_lower:
        limit_type = None
        if "memory" in error_msg_lower:
            limit_type = "memory"
        elif "duration" in error_msg_lower or "timeout" in error_msg_lower:
            limit_type = "duration"
        elif "recursion" in error_msg_lower:
            limit_type = "recursion"
        elif "allocation" in error_msg_lower:
            limit_type = "allocations"
        if limit_type:
            return LimitError(error_msg, limit_type=limit_type)

    # 5. Map MontySyntaxError to ParseError
    if type(error).__name__ == "MontySyntaxError":
        return ParseError(error_msg, lineno=lineno)

    # 6. Default to ExecutionError
    return ExecutionError(
        error_msg,
        lineno=lineno,
        source_context=...,  # preserve existing context extraction
    )
```

**Key changes from V3.1:**
- Don't fall back to raw Monty line numbers when source map lookup fails — `None` is better than misleading
- Regex uses anchored patterns (comma/line-start boundaries, not bare `\b`)
- Limit detection requires "limit" OR "exceeded" in the message alongside the keyword
- `MontySyntaxError` maps to `ParseError`, not generic `ExecutionError`

**Verify:**
- `"Error processing inline 42 data"` — should NOT extract line 42
- `"Failed to access memory address"` — should NOT become `LimitError`
- `"Memory limit exceeded"` — should become `LimitError(limit_type="memory")`

---

### 1.8 Fix `pydantic-monty` Dependency Contradiction
**File:** `src/grail/script.py`  
**Review ref:** CODE_REVIEW_V3 §1.6

**Problem:** `pyproject.toml` lists `pydantic-monty` as required, but `script.py` wraps the import in `try/except ImportError`. These contradict each other.

**Fix:** Since we don't care about backwards compatibility — make it a hard dependency. Remove the `try/except ImportError` wrapper:

```python
# BEFORE:
try:
    from pydantic_monty import Monty, run_monty_async, ...
except ImportError:
    Monty = None  # type: ignore

# AFTER:
from pydantic_monty import Monty, run_monty_async, ...
```

Remove any `if Monty is None: raise RuntimeError(...)` guards that exist as a consequence.

**Verify:** `python -c "from grail.script import Monty; print(Monty)"` succeeds without try/except.

---

## Phase 2: Architecture & Deduplication

*Structural improvements that simplify the codebase and establish clear ownership.*

### 2.1 Deduplicate Error Handling in `GrailScript.run()`
**File:** `src/grail/script.py`  
**Review ref:** CODE_REVIEW_V3 §3.1

**Problem:** Two `except` blocks (~60 lines) are structurally identical. Dead stores for `success` and `error_msg`. `duration_ms` computed twice per block.

**Fix:** Extract a `_handle_run_error` method and collapse to a single `except Exception`:

```python
def _handle_run_error(
    self,
    error: Exception,
    start_time: float,
    on_event: Callable | None,
) -> NoReturn:
    """Map a runtime error, fire events, write logs, and re-raise."""
    duration_ms = (time.time() - start_time) * 1000
    mapped_error = self._map_error_to_pym(error)

    if on_event:
        on_event(ScriptEvent(
            type="run_error",
            success=False,
            duration_ms=duration_ms,
            error=str(mapped_error),
        ))

    if self._artifacts:
        self._artifacts.write_run_log(
            success=False,
            duration_ms=duration_ms,
            error=str(mapped_error),
        )

    raise mapped_error from error
```

Then in `run()`, replace both `except` blocks with:

```python
except Exception as e:
    self._handle_run_error(e, start_time, on_event)
```

**Key corrections from V3.1:**
- No dead `success`/`error_msg` stores
- `duration_ms` computed exactly once
- Uses `raise ... from error` to preserve the exception chain
- Return type is `NoReturn` for clarity

**Verify:** Run integration tests covering both Monty-specific errors and generic exceptions.

---

### 2.2 Deduplicate `parse_pym_file` and `parse_pym_content`
**File:** `src/grail/parser.py`  
**Review ref:** CODE_REVIEW_V3 §2.1

**Problem:** These two functions contain nearly identical parse-extract-build logic.

**Fix:** Make `parse_pym_file` delegate to `parse_pym_content`:

```python
def parse_pym_file(path: str | Path) -> ParseResult:
    """Parse a .pym file from disk."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Script file not found: {path}")
    source = path.read_text(encoding="utf-8")
    return parse_pym_content(source, filename=str(path))
```

**Verify:** All existing parser tests still pass.

---

### 2.3 Establish Validation Ownership: Parser vs Checker
**File:** `src/grail/parser.py`, `src/grail/checker.py`  
**Review ref:** CODE_REVIEW_V3 §2.1, §2.2

**Problem:** The parser raises `CheckError` (hard failure) for some conditions, while the checker emits `CheckMessage` (soft reporting) for overlapping conditions. No clear ownership.

**Fix — Establish this rule:**

- **Parser** is responsible for *extraction*. It should only raise on conditions that make extraction impossible (malformed AST, syntax errors, missing required decorators). These are `ParseError`.
- **Checker** is responsible for *validation*. All Monty compatibility rules (E001-E008, W001-W004) live here and produce `CheckMessage` objects. The checker never raises — it always returns a `CheckResult`.
- **`load()`** is the enforcement point. It calls the checker and raises `CheckError` for any errors (Task 1.1).

Audit the parser for any `CheckError` raises that should be `CheckMessage` emissions in the checker instead. Move validation logic from the parser to the checker where appropriate.

**Verify:** The parser never raises `CheckError`. Validation errors are always surfaced through `CheckResult.messages`.

---

### 2.4 Deduplicate `extract_inputs` Logic
**File:** `src/grail/parser.py`  
**Review ref:** CODE_REVIEW_V3 §2.1

**Problem:** The `ast.AnnAssign` and `ast.Assign` branches for Input detection contain duplicated `is_input_call` and default extraction logic.

**Fix:** Extract a helper:

```python
def _is_input_call(node: ast.expr) -> bool:
    """Check if an expression is Input() or grail.Input()."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "Input":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "Input":
        return True
    return False

def _extract_input_from_call(call_node: ast.Call, var_name: str, lineno: int) -> InputSpec:
    """Extract InputSpec from an Input() call node."""
    # Extract name argument
    input_name = None
    if call_node.args:
        if isinstance(call_node.args[0], ast.Constant):
            input_name = call_node.args[0].value

    # Validate name matches variable
    if input_name is not None and input_name != var_name:
        raise ParseError(
            f"Input name '{input_name}' doesn't match variable name '{var_name}' "
            f"at line {lineno}. Use Input(\"{var_name}\") or omit the name argument."
        )

    # Extract default
    default = None
    has_default = False
    for kw in call_node.keywords:
        if kw.arg == "default":
            has_default = True
            default = ast.literal_eval(kw.value) if isinstance(kw.value, ast.Constant) else None

    return InputSpec(
        name=var_name,
        input_name=input_name,
        has_default=has_default,
        default=default,
        lineno=lineno,
        ...
    )
```

Then both `ast.AnnAssign` and `ast.Assign` handlers call `_extract_input_from_call()`.

**Verify:** Inputs extracted correctly from both annotated and non-annotated assignments. `Input("wrong_name")` raises.

---

### 2.5 Remove Dead `__grail_external__` Attribute
**File:** `src/grail/_external.py`  
**Review ref:** CODE_REVIEW_V3 §1.5, §6.3

**Problem:** The `external` decorator sets `__grail_external__ = True` on the function, but this attribute is never read anywhere in the codebase. The parser uses AST-based detection.

**Fix:** Remove the `setattr` line. The decorator becomes a pure identity function (which is correct — its purpose is to be detected at parse time via AST, not at runtime):

```python
def external(func: F) -> F:
    """Mark a function as an external dependency for Grail scripts."""
    return func
```

**Verify:** All tests pass. Grep for `__grail_external__` confirms zero references.

---

### 2.6 Simplify Module-Level `run()` Function
**File:** `src/grail/script.py` — module-level `run()`  
**Review ref:** CODE_REVIEW_V3 §3.8

**Problem:** The 2x3 branching matrix for creating `Monty` and calling `run_monty_async` is unnecessarily complex. No limits support, no error handling, no type checking.

**Fix:** Collapse to a single code path with keyword args, add `limits` parameter:

```python
async def run(
    source: str,
    *,
    inputs: dict[str, Any] | None = None,
    limits: Limits | None = None,
    print_callback: Callable[[str, str], None] | None = None,
) -> Any:
    """Run a Monty script from source code.

    This is a simple escape hatch for quick execution. For production use,
    prefer grail.load() which provides full validation and error mapping.
    """
    monty = Monty(
        source,
        input_values=inputs or {},
        limits=(limits or Limits.default()).to_monty(),
    )
    return await run_monty_async(
        monty,
        print_callback=print_callback,
    )
```

**Verify:** `grail.run("x = 1 + 1", limits=grail.Limits.strict())` works. Infinite loop with default limits times out instead of hanging.

---

### 2.7 Deduplicate CLI Error Handling
**File:** `src/grail/cli.py`  
**Review ref:** CODE_REVIEW_V3 §6.1

**Problem:** The same `try/except` pattern for `ParseError`, `GrailError`, `FileNotFoundError` is copy-pasted across 5 `cmd_*` functions.

**Fix:** Create a decorator:

```python
def cli_error_handler(func: Callable[..., int]) -> Callable[..., int]:
    """Wrap a CLI command with standard error handling."""
    @functools.wraps(func)
    def wrapper(args: argparse.Namespace) -> int:
        try:
            return func(args)
        except ParseError as e:
            print(f"Parse error: {e}", file=sys.stderr)
            return 1
        except CheckError as e:
            print(f"Check error: {e}", file=sys.stderr)
            return 1
        except GrailError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        except FileNotFoundError as e:
            print(f"File not found: {e}", file=sys.stderr)
            return 1
    return wrapper

@cli_error_handler
def cmd_check(args: argparse.Namespace) -> int:
    ...
```

**Verify:** All CLI commands still produce friendly error messages.

---

### 2.8 Centralize `.grail` Directory Constant
**File:** New constant in `src/grail/artifacts.py`, referenced from `cli.py` and `script.py`  
**Review ref:** CODE_REVIEW_V3 §6.4

**Problem:** The `.grail` directory name appears in 3 files with no central constant.

**Fix:** Define in `artifacts.py` and import elsewhere:

```python
# artifacts.py
ARTIFACTS_DIR_NAME = ".grail"
```

Update all hardcoded `".grail"` references in `cli.py` and `script.py` to use this constant.

**Verify:** Grep for `".grail"` string literal — should only appear in `artifacts.py`.

---

## Phase 3: Data Model & Type Improvements

### 3.1 Add `file` Field to `ParseResult`
**File:** `src/grail/_types.py`, `src/grail/parser.py`, `src/grail/checker.py`  
**Review ref:** CODE_REVIEW_V3 §2.5, §2.2

**Fix:** Add `file` to `ParseResult`:

```python
@dataclass
class ParseResult:
    ast_module: ast.Module
    externals: list[ExternalSpec]
    inputs: list[InputSpec]
    source_lines: list[str]
    file: str | None = None
```

Update `parse_pym_content` to accept and store `filename`. Update `check_pym` to use `parse_result.file` instead of hardcoded `"<unknown>"`.

**Verify:** Check messages include the actual filename.

---

### 3.2 Add `input_name` Field to `InputSpec`
**File:** `src/grail/_types.py`  
**Review ref:** CODE_REVIEW_V3 §2.5

**Fix:** Add `input_name` to capture the `Input()` string argument:

```python
@dataclass
class InputSpec:
    name: str              # The variable name
    type_annotation: str | None
    default: Any | None
    required: bool
    lineno: int
    col_offset: int
    input_name: str | None = None  # The name="..." arg from Input(), for validation
```

**Depends on:** Task 2.4 (`_extract_input_from_call` populates this field).

---

### 3.3 Fix `OutputError.validation_errors` Type
**File:** `src/grail/errors.py`  
**Review ref:** CODE_REVIEW_V3 §3.10

**Fix:** Change from `Any` to a proper type:

```python
class OutputError(GrailError):
    def __init__(self, message: str, validation_errors: Exception | None = None):
        super().__init__(message)
        self.validation_errors = validation_errors
```

---

### 3.4 Fix `LimitError` Hierarchy
**File:** `src/grail/errors.py`  
**Review ref:** CODE_REVIEW_V3 §3.10

**Problem:** `LimitError` extends `ExecutionError`, but limits are a resource concern, not a code error. Users catching `ExecutionError` unintentionally catch `LimitError`.

**Fix:** Make `LimitError` a sibling of `ExecutionError` under `GrailError`:

```python
class LimitError(GrailError):
    """Raised when a resource limit is exceeded during script execution."""
    def __init__(self, message: str, limit_type: str):
        super().__init__(message)
        self.limit_type = limit_type
```

**Impact:** Users who currently `except ExecutionError` to catch limits will need `except (ExecutionError, LimitError)` or `except GrailError`. Since we don't care about backwards compatibility, this is fine.

**Verify:** `isinstance(LimitError(...), ExecutionError)` returns `False`. `isinstance(LimitError(...), GrailError)` returns `True`.

---

### 3.5 Rename `ParamSpec` to `ParameterSpec`
**File:** `src/grail/_types.py` and all references  
**Review ref:** Shadows `typing.ParamSpec`

**Fix:** Rename the class and update all imports. This avoids confusion with `typing.ParamSpec` (PEP 612).

**Verify:** `grep -r "ParamSpec" src/` only returns `typing.ParamSpec` references (if any).

---

## Phase 4: API Surface & Monty Coverage

### 4.1 Fix Import Allowlist
**File:** `src/grail/checker.py`  
**Review ref:** CODE_REVIEW_V3 §2.2

**Problem:** Only allows `{"grail", "typing"}`. Monty supports more.

**Fix:** Expand the allowlist, but **verify each module against Monty's actual capabilities** first. Do NOT guess:

```python
# Modules known to be supported by Monty's runtime.
# Verify each entry against pydantic-monty documentation before adding.
ALLOWED_MODULES: set[str] = {
    "grail",
    "typing",
    "__future__",  # from __future__ import annotations
    # Add others ONLY after verification:
    # "math", "json", "re", "datetime", "dataclasses", "collections",
    # "itertools", "functools", "os", "sys", "pathlib", "time", "random",
}
```

**Also fix `visit_Import` asymmetry:** `import grail` should be allowed (not just `from grail import ...`):

```python
def visit_Import(self, node: ast.Import) -> None:
    for alias in node.names:
        root_module = alias.name.split(".")[0]
        if root_module not in ALLOWED_MODULES:
            self._add_message(...)
```

**Verify:** `from __future__ import annotations` does not trigger E005. `import grail` does not trigger E005.

---

### 4.2 Add Missing Checker Rules
**File:** `src/grail/checker.py`  
**Review ref:** CODE_REVIEW_V3 §2.2

**Problem:** Missing checks for `global`/`nonlocal`, `del` statements, and `lambda` expressions. Whether Monty supports these needs verification.

**Fix:** Investigate Monty's support for each, then add checks for unsupported constructs:

```python
def visit_Global(self, node: ast.Global) -> None:
    self._add_message("E009", "global statements", node.lineno, node.col_offset)

def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
    self._add_message("E010", "nonlocal statements", node.lineno, node.col_offset)

def visit_Delete(self, node: ast.Delete) -> None:
    self._add_message("E011", "del statements", node.lineno, node.col_offset)
```

**Important:** Only add these rules if Monty actually doesn't support the construct. Test each one in Monty first.

---

### 4.3 OS Access Enrichment — Environment Variables
**File:** `src/grail/script.py`  
**Review ref:** CODE_REVIEW_V3 §4.5

**Fix:** Add `environ` parameter to `run()` and `_prepare_monty_files`:

```python
async def run(
    self,
    *,
    inputs: dict[str, Any] | None = None,
    externals: dict[str, Callable] | None = None,
    limits: Limits | None = None,
    files: dict[str, str | bytes] | None = None,
    environ: dict[str, str] | None = None,  # NEW
    ...
) -> Any:
```

Pass through to `OSAccess(files=..., environ=environ or {})`.

**Verify:** A script using `os.getenv("MY_VAR")` receives the value when `environ={"MY_VAR": "hello"}` is passed.

---

### 4.4 Error Richness — Preserve Monty Exception Details
**File:** `src/grail/script.py`  
**Review ref:** CODE_REVIEW_V3 §4.9

**Fix:** Use `MontyError.exception()` to preserve the original Python exception, and use more `Frame` fields:

```python
if hasattr(error, 'exception') and callable(error.exception):
    original = error.exception()
    # Preserve the original exception type in the error message
    error_msg = f"{type(original).__name__}: {original}"

if hasattr(error, 'traceback') and callable(error.traceback):
    tb = error.traceback()
    if tb and tb.frames:
        frame = tb.frames[-1]
        # Use all available frame information
        source_context = frame.source_line if hasattr(frame, 'source_line') else None
        function_name = frame.function_name if hasattr(frame, 'function_name') else None
```

**Also:** Catch `MontySyntaxError` explicitly in `run()`:

```python
except MontySyntaxError as e:
    raise ParseError(str(e), lineno=getattr(e, 'lineno', None)) from e
except Exception as e:
    self._handle_run_error(e, start_time, on_event)
```

---

### 4.5 Fix Print Callback Stream Type
**File:** `src/grail/script.py`  
**Review ref:** CODE_REVIEW_V3 §4.4

**Fix:** Check what Monty actually sends for the stream parameter. If Monty only sends `'stdout'`, use `Literal['stdout']`. If it can also send `'stderr'`, use `Literal['stdout', 'stderr']`. Do not guess — check the Monty documentation or source.

```python
# After verification:
from typing import Literal

StreamType = Literal["stdout", "stderr"]  # or just Literal["stdout"] if Monty only sends stdout

print_callback: Callable[[str, StreamType], None] | None = None
```

---

### 4.6 Expose Opt-in Strict Input/External Validation
**File:** `src/grail/script.py`  
**Review ref:** CODE_REVIEW_V3 §3.3

**Problem:** Extra (undeclared) inputs/externals produce `warnings.warn()` — typos become silent failures.

**Fix:** Make extra inputs/externals a hard error by default:

```python
async def run(
    self,
    *,
    ...,
    strict_validation: bool = True,  # NEW — errors on undeclared inputs/externals
) -> Any:
```

When `strict_validation=True`: raise `InputError` for undeclared inputs, `ExternalError` for undeclared externals.  
When `strict_validation=False`: warn (current behavior).

**Also fix:** `warnings.warn` `stacklevel` — should be high enough to point at the caller's code, not internal `run()` code. Test interactively to determine correct level.

---

## Phase 5: CLI & Peripheral Improvements

### 5.1 Fix `cmd_watch` Error Handling and Return
**File:** `src/grail/cli.py`  
**Review ref:** CODE_REVIEW_V3 §6.1

**Fix:**

```python
@cli_error_handler
def cmd_watch(args: argparse.Namespace) -> int:
    try:
        while True:
            # ... existing watch loop ...
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nWatch terminated.")
    return 0
```

**Also propagate `--strict` and `--verbose` flags** to inner `cmd_check` calls. Currently the inner `Namespace` is hardcoded without these flags.

---

### 5.2 Fix JSON Output Ignoring `--strict`
**File:** `src/grail/cli.py`  
**Review ref:** CODE_REVIEW_V3 §6.1

**Fix:** In the JSON output path, compute `valid` respecting the `--strict` flag:

```python
if args.format == "json":
    if args.strict:
        valid = not any(m.code.startswith(("E", "W")) for m in result.messages)
    else:
        valid = not any(m.code.startswith("E") for m in result.messages)
    output = {"valid": valid, "messages": [...]}
```

---

### 5.3 Add `--version` Flag
**File:** `src/grail/cli.py`, `src/grail/__init__.py`  
**Review ref:** CODE_REVIEW_V3 §6.1

```python
from grail import __version__

parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
```

---

### 5.4 Make Artifact Writes Non-Blocking
**File:** `src/grail/artifacts.py`, `src/grail/script.py`  
**Review ref:** CODE_REVIEW_V3 §6.2

**Problem:** `PermissionError` during artifact writing prevents `load()` from succeeding.

**Fix:** Wrap artifact writes in try/except within `load()`:

```python
# In load():
try:
    artifacts.write_script_artifacts(...)
except OSError as e:
    logger.warning("Failed to write artifacts: %s", e)
    # Continue loading — artifacts are optional
```

---

### 5.5 Add `clean()` Safety Check
**File:** `src/grail/artifacts.py`  
**Review ref:** CODE_REVIEW_V3 §6.2

**Fix:** Verify the directory basename before `rmtree`:

```python
def clean(self) -> None:
    if self._dir.name != ARTIFACTS_DIR_NAME:
        raise ValueError(f"Refusing to delete directory: {self._dir}")
    if self._dir.exists():
        shutil.rmtree(self._dir)
```

---

### 5.6 Add Logging (Library-Safe)
**File:** All modules in `src/grail/`  
**Review ref:** CODE_REVIEW_V3 §6.4

**Fix:** Add loggers to each module. **Do NOT call `logging.basicConfig()`** — that's the application's responsibility, not a library's.

```python
# In each module:
import logging
logger = logging.getLogger(__name__)
```

In `__init__.py`, add a `NullHandler` to prevent "No handlers could be found" warnings:

```python
import logging
logging.getLogger("grail").addHandler(logging.NullHandler())
```

Add `logger.debug()` calls at key points:
- `load()`: "Loading script from %s"
- `run()`: "Running script %s with %d inputs, %d externals"
- `check()`: "Checking script %s"
- Error paths: `logger.warning("Script execution failed: %s", error)`

---

### 5.7 Document `ast.unparse()` Formatting Loss
**Review ref:** CODE_REVIEW_V3 §2.3

**Problem:** `ast.unparse()` destroys all comments, blank lines, and formatting. This is inherent to the AST approach and cannot be fixed, but it should be documented.

**Fix:** Add a note to `codegen.py` and to user-facing documentation:

```python
# In codegen.py, at the top or in generate_monty_code docstring:
"""
NOTE: Generated Monty code loses all comments, blank lines, and original
formatting. This is inherent to ast.unparse(). The source map preserves
line number mapping for error reporting.
"""
```

---

## Phase 6: Tests

*All tests should exercise the Grail API end-to-end, not test third-party libraries directly.*

### 6.1 Tests for `load()` Check Enforcement

```python
def test_load_raises_on_checker_error(tmp_path):
    """load() should raise CheckError for invalid scripts."""
    pym = tmp_path / "bad.pym"
    pym.write_text("class Foo:\n    pass\n")  # E001: classes not allowed

    with pytest.raises(CheckError, match="E001"):
        grail.load(pym)

def test_load_succeeds_for_valid_script(tmp_path):
    pym = tmp_path / "good.pym"
    pym.write_text("""
from grail import external

@external
async def fetch(url: str) -> str: ...

result = await fetch("https://example.com")
""")
    script = grail.load(pym)
    assert script is not None
```

---

### 6.2 Tests for `output_model` Validation

```python
def test_output_model_validates_dict_result(tmp_path):
    """output_model should validate dict results via model_validate."""
    from pydantic import BaseModel

    class Output(BaseModel):
        value: int

    pym = tmp_path / "test.pym"
    pym.write_text('result = {"value": 42}')

    script = grail.load(pym)
    result = await script.run(output_model=Output)
    assert isinstance(result, Output)
    assert result.value == 42

def test_output_model_invalid_raises_output_error(tmp_path):
    from pydantic import BaseModel

    class Output(BaseModel):
        value: int

    pym = tmp_path / "test.pym"
    pym.write_text('result = {"wrong_field": "not_int"}')

    script = grail.load(pym)
    with pytest.raises(OutputError):
        await script.run(output_model=Output)
```

---

### 6.3 Tests for Virtual Filesystem

```python
def test_run_with_virtual_file(tmp_path):
    """Scripts should be able to read virtual files via open()."""
    pym = tmp_path / "test.pym"
    pym.write_text("""
with open("data.txt") as f:
    result = f.read()
""")

    script = grail.load(pym)
    result = await script.run(files={"data.txt": "Hello World"})
    assert result == "Hello World"

def test_run_files_override(tmp_path):
    pym = tmp_path / "test.pym"
    pym.write_text("""
with open("data.txt") as f:
    result = f.read()
""")

    script = grail.load(pym, files={"data.txt": "v1"})
    result = await script.run(files={"data.txt": "v2"})
    assert result == "v2"
```

---

### 6.4 Tests for External Exception Propagation

```python
def test_external_exception_maps_to_execution_error(tmp_path):
    pym = tmp_path / "test.pym"
    pym.write_text("""
from grail import external

@external
async def fail() -> str: ...

result = await fail()
""")

    async def failing_external() -> str:
        raise ValueError("test error")

    script = grail.load(pym)
    with pytest.raises(ExecutionError, match="ValueError"):
        await script.run(externals={"fail": failing_external})

def test_external_exception_caught_in_script(tmp_path):
    pym = tmp_path / "test.pym"
    pym.write_text("""
from grail import external

@external
async def fail() -> str: ...

try:
    result = await fail()
except ValueError:
    result = "caught"
""")

    async def failing_external() -> str:
        raise ValueError("boom")

    script = grail.load(pym)
    result = await script.run(externals={"fail": failing_external})
    assert result == "caught"
```

---

### 6.5 Tests for Resource Limit Violations

```python
@pytest.mark.slow
def test_duration_limit_exceeded(tmp_path):
    pym = tmp_path / "infinite.pym"
    pym.write_text("while True:\n    pass\n")

    script = grail.load(pym)
    with pytest.raises(LimitError) as exc_info:
        await script.run(limits=Limits(max_duration=0.001))  # Use numeric seconds

    assert exc_info.value.limit_type == "duration"

def test_recursion_limit_exceeded(tmp_path):
    pym = tmp_path / "recursive.pym"
    pym.write_text("""
def recurse(n):
    return recurse(n + 1)

result = recurse(0)
""")

    script = grail.load(pym)
    with pytest.raises(LimitError) as exc_info:
        await script.run(limits=Limits(max_recursion=10))

    assert exc_info.value.limit_type == "recursion"
```

---

### 6.6 Tests for `LimitError` Hierarchy Change

```python
def test_limit_error_is_grail_error():
    err = LimitError("test", limit_type="memory")
    assert isinstance(err, GrailError)

def test_limit_error_is_not_execution_error():
    err = LimitError("test", limit_type="memory")
    assert not isinstance(err, ExecutionError)

def test_except_execution_error_does_not_catch_limit_error(tmp_path):
    """Ensure catching ExecutionError doesn't accidentally catch LimitError."""
    pym = tmp_path / "infinite.pym"
    pym.write_text("while True:\n    pass\n")

    script = grail.load(pym)
    with pytest.raises(LimitError):
        try:
            await script.run(limits=Limits(max_duration=0.001))
        except ExecutionError:
            pytest.fail("LimitError should not be caught by ExecutionError handler")
```

---

### 6.7 Tests for Parameter Extraction

```python
def test_extract_all_param_kinds():
    code = """
from grail import external

@external
async def fetch(a, /, b, *args, c=1, **kwargs) -> str: ...
"""
    result = parse_pym_content(code)
    params = result.externals[0].params
    assert len(params) == 5
    assert params[0].kind == ParamKind.POSITIONAL_ONLY
    assert params[1].kind == ParamKind.POSITIONAL_OR_KEYWORD
    assert params[2].kind == ParamKind.VAR_POSITIONAL
    assert params[3].kind == ParamKind.KEYWORD_ONLY
    assert params[3].has_default is True
    assert params[4].kind == ParamKind.VAR_KEYWORD

def test_extract_kwonly_without_default():
    code = """
from grail import external

@external
async def fetch(*, required_kwarg: str) -> str: ...
"""
    result = parse_pym_content(code)
    params = result.externals[0].params
    assert params[0].kind == ParamKind.KEYWORD_ONLY
    assert params[0].has_default is False
```

---

### 6.8 Tests for `check()` TOCTOU Fix

```python
def test_check_uses_cached_parse_result(tmp_path):
    """check() should validate the loaded code, not current disk contents."""
    pym = tmp_path / "test.pym"
    pym.write_text("result = 42\n")

    script = grail.load(pym)

    # Modify file on disk to be invalid
    pym.write_text("class Foo:\n    pass\n")

    # check() should still pass — it uses the cached parse result
    result = script.check()
    assert result.valid
```

---

### 6.9 Tests for Input Name Validation

```python
def test_input_name_mismatch_raises(tmp_path):
    pym = tmp_path / "test.pym"
    pym.write_text('budget: float = Input("totally_wrong")\n')

    with pytest.raises((ParseError, CheckError)):
        grail.load(pym)

def test_input_name_matches_variable(tmp_path):
    pym = tmp_path / "test.pym"
    pym.write_text('budget: float = Input("budget")\n')

    script = grail.load(pym)
    assert any(i.name == "budget" for i in script.inputs)
```

---

### 6.10 Tests for Codegen Declaration Stripping

```python
def test_codegen_strips_annotated_input():
    code = 'x: int = Input("x")\nresult = x + 1\n'
    result = parse_pym_content(code)
    monty = generate_monty_code(result)
    assert "Input" not in monty.code
    assert "result = x + 1" in monty.code

def test_codegen_strips_unannotated_input():
    code = 'x = Input("x")\nresult = x + 1\n'
    result = parse_pym_content(code)
    monty = generate_monty_code(result)
    assert "Input" not in monty.code

def test_codegen_preserves_non_input_assignment():
    code = 'x: int = 42\nresult = x + 1\n'
    result = parse_pym_content(code)
    monty = generate_monty_code(result)
    assert "x: int = 42" in monty.code or "x:int = 42" in monty.code

def test_codegen_strips_grail_dot_input():
    code = 'x: int = grail.Input("x")\nresult = x + 1\n'
    result = parse_pym_content(code)
    monty = generate_monty_code(result)
    assert "Input" not in monty.code
```

---

### 6.11 Tests for Stub Generator

```python
def test_stub_imports_optional():
    code = """
from grail import external

@external
async def fetch(url: str) -> Optional[str]: ...
"""
    result = parse_pym_content(code)
    stub = generate_stub(result)
    assert "from typing import Optional" in stub

def test_stub_imports_multiple_typing_names():
    code = """
from grail import external

@external
async def fetch(items: List[Dict[str, Any]]) -> Optional[int]: ...
"""
    result = parse_pym_content(code)
    stub = generate_stub(result)
    # All needed typing names should be imported
    for name in ["Any", "Dict", "List", "Optional"]:
        assert name in stub

def test_stub_escapes_triple_quotes():
    code = '''
from grail import external

@external
async def fetch(url: str) -> str:
    """Returns data with \\"\\"\\" in it."""
    ...
'''
    result = parse_pym_content(code)
    stub = generate_stub(result)
    # Should compile without syntax errors
    compile(stub, "<stub>", "exec")
```

---

### 6.12 Tests for Parser Edge Cases

```python
def test_parse_grail_dot_external():
    code = """
@grail.external
async def foo(x: int) -> int: ...
"""
    result = parse_pym_content(code)
    assert len(result.externals) == 1

def test_parse_sync_external():
    code = """
from grail import external

@external
def foo(x: int) -> int: ...
"""
    result = parse_pym_content(code)
    assert len(result.externals) == 1

def test_parse_empty_file():
    result = parse_pym_content("")
    assert len(result.externals) == 0
    assert len(result.inputs) == 0

def test_parse_grail_dot_input():
    code = 'x: int = grail.Input("x")\n'
    result = parse_pym_content(code)
    assert len(result.inputs) == 1
```

---

### 6.13 Tests for Checker Edge Cases

```python
def test_e004_match_statement():
    code = """
match x:
    case 1:
        pass
"""
    result = parse_pym_content(code)
    check = check_pym(result)
    assert any(m.code == "E004" for m in check.messages)

def test_w004_long_script():
    code = "\n".join(f"x_{i} = {i}" for i in range(201))
    result = parse_pym_content(code)
    check = check_pym(result)
    assert any(m.code == "W004" for m in check.messages)

def test_yield_from_detected():
    code = """
def gen():
    yield from range(10)
"""
    result = parse_pym_content(code)
    check = check_pym(result)
    assert any(m.code == "E002" for m in check.messages)

def test_multiple_errors_accumulated():
    code = """
class Foo: pass
class Bar: pass
def gen():
    yield 1
"""
    result = parse_pym_content(code)
    check = check_pym(result)
    errors = [m for m in check.messages if m.code.startswith("E")]
    assert len(errors) >= 3
```

---

### 6.14 Tests for on_event Callbacks

```python
def test_on_event_captures_run_error(tmp_path):
    pym = tmp_path / "bad.pym"
    pym.write_text("1 / 0\n")

    events = []
    script = grail.load(pym)
    with pytest.raises(ExecutionError):
        await script.run(on_event=lambda e: events.append(e))

    error_events = [e for e in events if e.type == "run_error"]
    assert len(error_events) == 1
    assert error_events[0].success is False

def test_on_event_captures_print(tmp_path):
    pym = tmp_path / "printer.pym"
    pym.write_text('print("hello")\nresult = 42\n')

    events = []
    script = grail.load(pym)
    await script.run(on_event=lambda e: events.append(e))

    print_events = [e for e in events if e.type == "print"]
    assert len(print_events) >= 1
```

---

### 6.15 Tests for `dataclass_registry`

```python
from dataclasses import dataclass

@dataclass
class Person:
    name: str
    age: int

def test_dataclass_roundtrip(tmp_path):
    pym = tmp_path / "test.pym"
    pym.write_text("""
from grail import Input

person = Input("person")
result = f"{person.name} is {person.age}"
""")

    script = grail.load(pym, dataclass_registry={Person: Person})
    result = await script.run(inputs={"person": Person("Alice", 30)})
    assert result == "Alice is 30"
```

---

### 6.16 Additional Edge Case Tests

```python
def test_empty_script_through_pipeline(tmp_path):
    pym = tmp_path / "empty.pym"
    pym.write_text("")
    script = grail.load(pym)
    result = await script.run()
    assert result is None

def test_script_with_only_imports(tmp_path):
    pym = tmp_path / "imports_only.pym"
    pym.write_text("from grail import external\n")
    script = grail.load(pym)
    result = await script.run()
    assert result is None

def test_run_sync_in_async_context():
    """run_sync() should raise RuntimeError when called from async context."""
    pym = ...  # create a valid .pym
    script = grail.load(pym)

    async def async_caller():
        with pytest.raises(RuntimeError):
            script.run_sync()

    asyncio.run(async_caller())
```

---

## Issues NOT Addressed in This Plan (Documented Omissions)

These items from the code review are intentionally deferred or documented as known limitations:

| Issue | Reason |
|-------|--------|
| `build_source_map` BFS ordering fragility (§2.3) | Only fails if AST transformation restructures nodes. Current stripping-only approach is safe. Add a comment explaining the invariant. |
| Aliased decorator imports (`external as ext`) (§2.1) | Edge case. Document as unsupported in user docs. |
| Monty serialization `dump()`/`load()` (§4.10) | Intentionally not wrapped. Document in user docs. |
| Threading/GIL safety (§4.12) | Works implicitly. Document that concurrent `run()` calls are safe. |
| `CallbackFile` and `AbstractOS` (§4.5) | Advanced feature. Consider for v3.3. |
| Type checking display formats (§4.6) | 9 display formats from Monty are unused. Consider for v3.3. |
| CLI `--input` type coercion (§6.1) | Requires significant design work (type inference from annotations). Defer. |
| Atomic artifact writes (§6.2) | Low risk in practice. Defer. |
| JSON artifact schema versioning (§6.2) | Defer until artifact format stabilizes. |
| `_input.py` "no default" vs "default is None" ambiguity (§6.3) | Parser handles this at AST level. Runtime distinction not needed. |
| Splitting `script.py` into multiple modules (§1.2) | After all other refactors are complete, reassess whether the module is still too large. The deduplication in Phase 2 should significantly reduce its size. |
| Redundant type checking in `run()` after `check()` (§1.4) | Consider adding a `type_checked: bool` flag to `GrailScript` that `run()` checks to skip redundant work. Defer until profiling shows this matters. |

---

## Summary Checklist

| Phase | Task | Description |
|-------|------|-------------|
| 1.1 | Fix `load()` check enforcement | Raise on checker errors |
| 1.2 | Fix `output_model` Pydantic v2 API | Use `model_validate()`, tighten types |
| 1.3 | Fix `extract_function_params` | Handle all param kinds, add `ParamKind` enum |
| 1.4 | Fix codegen `ast.Assign`/`ast.AnnAssign` | Correct return types, handle `grail.Input()` |
| 1.5 | Fix stub typing imports | Track and import all needed typing names |
| 1.6 | Fix `check()` TOCTOU | Use cached parse result |
| 1.7 | Fix `_map_error_to_pym` | Better regex, type-first limit detection |
| 1.8 | Fix `pydantic-monty` dependency | Remove try/except, treat as hard dep |
| 2.1 | Deduplicate `run()` error handling | Extract `_handle_run_error` |
| 2.2 | Deduplicate parser functions | `parse_pym_file` delegates to `parse_pym_content` |
| 2.3 | Establish validation ownership | Parser extracts, checker validates |
| 2.4 | Deduplicate `extract_inputs` | Extract `_is_input_call` and `_extract_input_from_call` helpers |
| 2.5 | Remove dead `__grail_external__` | Clean identity decorator |
| 2.6 | Simplify module-level `run()` | Single code path, add limits |
| 2.7 | Deduplicate CLI error handling | Error handler decorator |
| 2.8 | Centralize `.grail` constant | Single `ARTIFACTS_DIR_NAME` constant |
| 3.1 | Add `file` to `ParseResult` | Enables meaningful checker messages |
| 3.2 | Add `input_name` to `InputSpec` | Enables name mismatch validation |
| 3.3 | Fix `OutputError.validation_errors` type | `Exception \| None` instead of `Any` |
| 3.4 | Fix `LimitError` hierarchy | Sibling of `ExecutionError`, not child |
| 3.5 | Rename `ParamSpec` to `ParameterSpec` | Avoid shadowing `typing.ParamSpec` |
| 4.1 | Fix import allowlist | Add verified modules, fix asymmetry |
| 4.2 | Add missing checker rules | `global`, `nonlocal`, `del` (verify first) |
| 4.3 | OS Access — environ | Pass env vars through to Monty |
| 4.4 | Error richness | Use `MontyError.exception()`, `Frame` fields |
| 4.5 | Print callback stream type | Use correct `Literal` type |
| 4.6 | Strict input/external validation | Hard errors by default |
| 5.1 | Fix `cmd_watch` | Error handling, return value, flag propagation |
| 5.2 | Fix JSON strict mode | Respect `--strict` in JSON output |
| 5.3 | Add `--version` flag | Use `__version__` from package |
| 5.4 | Non-blocking artifact writes | `OSError` in artifacts doesn't block `load()` |
| 5.5 | `clean()` safety check | Verify basename before `rmtree` |
| 5.6 | Add logging | Library-safe `NullHandler` pattern |
| 5.7 | Document `ast.unparse()` loss | Comment in codegen |
| 6.* | Tests | 16 test groups covering all changes |

---

## Estimated Time

- **Phase 1 (Critical Bugs):** 6-8 hours
- **Phase 2 (Architecture):** 4-6 hours
- **Phase 3 (Data Model):** 2-3 hours
- **Phase 4 (API Surface):** 4-6 hours
- **Phase 5 (CLI & Peripheral):** 3-4 hours
- **Phase 6 (Tests):** 8-10 hours

**Total:** ~27-37 hours
