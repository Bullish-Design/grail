# Grail V3.1 — Detailed Refactoring Plan

**Based on:** CODE_REVIEW_V3.md (2026-02-25)  
**Purpose:** Step-by-step developer guide for implementing all fixes and improvements

---

## How to Use This Guide

This plan is organized into **phases**. Each phase contains tasks that:
- Can be completed **independently** of later phases
- Have **clear verification steps** so you know when you're done
- Are ordered **logically** so early work enables later work

**Recommended approach:** Complete Phase 1 first to build momentum, then work through phases in order.

---

## Phase 1: Quick Wins (Trivial/Low Effort)

*These are isolated fixes that don't depend on anything else. Do these first to build momentum.*

### 1.1 Export `GrailScript` from `__init__.py`
**File:** `src/grail/__init__.py`

Add `GrailScript` to the exports. Find the `__all__` list (around line 35) and add `"GrailScript"`.

```python
__all__ = [
    # ... existing exports ...
    "GrailScript",  # ADD THIS
]
```

Also add the import at the top of the file:
```python
from grail.script import GrailScript
```

**Verify:** Run `python -c "from grail import GrailScript; print('OK')"`

---

### 1.2 Export Limits Constants
**File:** `src/grail/__init__.py`

Add `STRICT`, `DEFAULT`, `PERMISSIVE` to `__all__` and add import:
```python
from grail.limits import STRICT, DEFAULT, PERMISSIVE
```

**Verify:** Run `python -c "from grail import STRICT, DEFAULT, PERMISSIVE; print(STRICT)"`

---

### 1.3 Export `ExternalSpec` and `InputSpec` Types
**File:** `src/grail/__init__.py`

Add `ExternalSpec` and `InputSpec` to `__all__`:
```python
from grail._types import ExternalSpec, InputSpec
```

**Verify:** Run `python -c "from grail import ExternalSpec, InputSpec; print('OK')"`

---

### 1.4 Fix Bare `assert` in Production Code
**File:** `src/grail/script.py:204`

Replace the bare assert with proper type narrowing:

```python
# BEFORE:
if base is None:
    assert override_limits is not None
    return override_limits.to_monty()

# AFTER:
if base is None:
    if override_limits is None:
        raise ValueError("Either base or override_limits must be provided")
    return override_limits.to_monty()
```

**Verify:** Run `python -O -c "from grail import Limits; L = Limits(); print(L.to_monty())"` (the `-O` flag should not cause errors)

---

### 1.5 Remove Dead `validate_external_function()`
**File:** `src/grail/parser.py:77-129`

Delete the entire `validate_external_function` function. It's never called.

**Verify:** Run parser tests: `python -m pytest tests/test_parser.py -v`

---

### 1.6 Remove Legacy Limits API
**File:** `src/grail/limits.py:176-201`

Delete these items:
- `parse_limits()` function
- `merge_limits()` function  
- `STRICT` dict constant
- `DEFAULT` dict constant
- `PERMISSIVE` dict constant

**Verify:** Run limit tests: `python -m pytest tests/test_limits.py -v`

---

### 1.7 Fix `spec.loader` Null Check in CLI
**File:** `src/grail/cli.py:217-219`

Add null checks around the import:

```python
spec = importlib.util.spec_from_file_location("host", host_path)
if spec is None or spec.loader is None:
    print(f"Error: Cannot load host file {host_path}", file=sys.stderr)
    return 1
host_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host_module)
```

**Verify:** Test with a file that can't be loaded as a module (tricky to test, but code review confirms the fix)

---

### 1.8 Fix Pydantic v2 API in `output_model` Validation
**File:** `src/grail/script.py:487-493`

Replace the incorrect Pydantic v1 API with v2:

```python
# BEFORE:
result = output_model(**result) if isinstance(result, dict) else output_model(result)

# AFTER:
from typing import Mapping
if isinstance(result, Mapping):
    result = output_model.model_validate(result)
else:
    result = output_model.model_validate(result)
```

**Verify:** Add test (see Phase 9) or manually test with a Pydantic model

---

### 1.9 Fix `GrailDeclarationStripper` for `ast.Assign`
**File:** `src/grail/codegen.py`

Add a `visit_Assign` method to handle non-annotated Input() calls:

```python
def visit_Assign(self, node: ast.Assign) -> ast.Module:
    # Check if this is an Input() assignment without annotation
    # e.g., x = Input("x") without type annotation
    for target in node.targets:
        if isinstance(target, ast.Name):
            # Check if value is Input() call
            if isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "Input":
                    # Remove this node by not visiting it
                    return self.module
    # Keep the assignment
    return self.generic_visit(node)
```

Actually, the cleaner approach is to add to `visit_Assign`:

```python
def visit_Assign(self, node: ast.Assign) -> ast.Module:
    for target in node.targets:
        if isinstance(target, ast.Name):
            if isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "Input":
                    # Skip this assignment entirely
                    return ast.Pass()  # Replace with pass
    return self.generic_visit(node)
```

**Verify:** Create a `.pym` file with `x = Input("x")` (no annotation), load it, run it, and ensure it works

---

### 1.10 Fix Stub Generator for `typing` Imports
**File:** `src/grail/stubs.py:30-45`

Expand the typing imports detected:

```python
def _needs_import(annotation: str) -> bool:
    """Check if annotation needs a typing import."""
    typing_names = {
        'Any', 'Optional', 'Union', 'List', 'Dict', 'Set', 'Tuple',
        'Callable', 'Type', 'Literal', 'Annotated', 'TypeVar',
        'Generic', 'Protocol', 'Final', 'TypedDict', 'NotRequired',
        'Required', 'overload', 'cast'
    }
    for name in typing_names:
        if re.search(rf'\b{name}\b', annotation):
            return True
    return False
```

Also fix the docstring escaping issue at line 71:
```python
stub_lines.append(f'    """{docstring.replace("\"\"\"", "\\\"\\\"\\\"")}"""')
```

**Verify:** Generate a stub for a file with `Optional[int]`, `List[str]`, etc., and check it compiles

---

## Phase 2: Core Bug Fixes (High Impact)

*These fix critical functionality that affects users directly.*

### 2.1 Fix `load()` Silently Ignoring Check Errors
**File:** `src/grail/script.py:560-561`

The current code:
```python
parse_result = parse_pym_file(path)
check_pym(parse_result)  # Result ignored!
```

Change to:
```python
parse_result = parse_pym_file(path)
check_result = check_pym(parse_result)
if not check_result.valid:
    # Collect all errors
    errors = [msg for msg in check_result.messages if msg.code.startswith("E")]
    raise CheckError(
        f"Script validation failed: {len(errors)} error(s) found",
        errors=errors
    )
```

**Verify:** Create a `.pym` with `@external class Foo: pass` (E001 error), try to load it, should raise CheckError

---

### 2.2 Fix `extract_function_params` to Handle All Parameter Types
**File:** `src/grail/parser.py:34-74**

The current code only handles positional arguments. Add support for:
- `vararg` (*args)
- `kwarg` (**kwargs)
- `kwonlyargs` (keyword-only)
- `posonlyargs` (positional-only)

```python
def extract_function_params(func_node: ast.FunctionDef) -> list[ParamSpec]:
    params = []
    args = func_node.args
    
    # Positional-only arguments (Python 3.8+)
    for i, arg in enumerate(args.posonlyargs):
        params.append(ParamSpec(
            name=arg.arg,
            annotation=_get_annotation(arg.annotation),
            has_default=i >= len(args.args) or args.args[i] is not None,  # simplified
            default=_get_default(arg, i, args.defaults),
            kind="positional-only"
        ))
    
    # Regular positional arguments
    for i, arg in enumerate(args.args):
        params.append(ParamSpec(
            name=arg.arg,
            annotation=_get_annotation(arg.annotation),
            has_default=i >= len(args.args) - len(args.defaults),
            default=_get_default(arg, i, args.defaults),
            kind="positional-or-keyword"
        ))
    
    # *args
    if args.vararg:
        params.append(ParamSpec(
            name=args.vararg.arg,
            annotation=_get_annotation(args.vararg.annotation),
            has_default=False,
            default=None,
            kind="vararg"
        ))
    
    # Keyword-only arguments
    for arg in args.kwonlyargs:
        params.append(ParamSpec(
            name=arg.arg,
            annotation=_get_annotation(arg.annotation),
            has_default=True,
            default=None,  # Need to track defaults properly
            kind="keyword-only"
        ))
    
    # **kwargs
    if args.kwarg:
        params.append(ParamSpec(
            name=args.kwarg.arg,
            annotation=_get_annotation(args.kwarg.annotation),
            has_default=False,
            default=None,
            kind="kwarg"
        ))
    
    return params
```

You may also need to update `ParamSpec` in `_types.py` to include a `kind` field.

**Verify:** Create a `.pym` with `@external def foo(*args, **kwargs): ...`, check that params are extracted correctly

---

## Phase 3: Design Improvements

### 3.1 Validate `Input()` Name Parameter
**File:** `src/grail/parser.py:222`

Add validation that the `Input()` name argument matches the variable name:

```python
def extract_inputs...:
    # Inside the extraction logic:
    if call_args:
        input_name = call_args[0].value if isinstance(call_args[0], ast.Constant) else None
        if input_name and input_name != target.id:
            raise CheckError(
                f"Input name '{input_name}' doesn't match variable name '{target.id}'",
                lineno=node.lineno
            )
```

**Verify:** Create `budget: float = Input("totally_wrong")`, should raise CheckError

---

### 3.2 Fix Import Allowlist
**File:** `src/grail/checker.py:129`

The current code only allows `{"grail", "typing"}`. Monty supports more standard library modules:

```python
ALLOWED_MODULES = {
    "grail", "typing",
    # Standard library that Monty supports
    "sys", "os", "asyncio", "dataclasses", "pathlib",
    "json", "re", "math", "random", "time", "datetime",
    "collections", "itertools", "functools", "operator",
    "string", "struct", "copy", "pprint", "warnings",
}
```

**Verify:** Create a `.pym` with `from dataclasses import dataclass`, should NOT produce E005

---

### 3.3 Deduplicate Error Handling
**File:** `src/grail/script.py:400-460**

Refactor the duplicate error handling blocks into a single method:

```python
def _handle_run_error(
    self,
    error: Exception,
    event_type: str,
    start_time: float
) -> None:
    duration_ms = (time.time() - start_time) * 1000
    
    success = False
    error_msg = str(error)
    mapped_error = self._map_error_to_pym(error)
    
    if self._on_event:
        self._on_event(ScriptEvent(
            type=event_type,
            success=False,
            duration_ms=duration_ms,
            error=str(mapped_error),
        ))
    
    if self._artifacts:
        self._artifacts.write_run_log(...)
    
    raise mapped_error
```

Then simplify the two `except` blocks to call this method.

Also remove the dead `success` and `error_msg` variables that are assigned but never read.

**Verify:** Run integration tests, ensure error paths still work correctly

---

### 3.4 Fix Regex Line Extraction
**File:** `src/grail/script.py:266-271`

Fix the fragile regex:

```python
# BEFORE:
re.search(r"line (\d+)", error_msg, re.IGNORECASE)

# AFTER:
match = re.search(r"\bline (\d+)\b", error_msg, re.IGNORECASE)
```

Better yet, be more conservative:

```python
# Only extract if we have a clear line number pattern
lineno = None
# Try structured traceback first (preferred)
# Then try regex only for clear patterns
if re.search(r"(?<![\w])line\s+(\d+)(?![\w])", error_msg, re.IGNORECASE):
    match = re.search(r"(?<![\w])line\s+(\d+)(?![\w])", error_msg, re.IGNORECASE)
    if match:
        lineno = int(match.group(1))
```

**Verify:** Test with messages like "Error processing inline 42 data" should NOT extract 42

---

### 3.5 Fix Limit Detection by String Matching
**File:** `src/grail/script.py:273-283`

Require both a limit keyword AND "limit" in the message:

```python
def _map_error_to_pym(self, error: Exception) -> GrailError:
    # ... existing logic ...
    
    # Limit detection - require "limit" keyword too
    error_msg_lower = str(error).lower()
    limit_type = None
    
    if "limit" in error_msg_lower:
        if "memory" in error_msg_lower:
            limit_type = "memory"
        elif "duration" in error_msg_lower or "time" in error_msg_lower:
            limit_type = "duration"
        elif "recursion" in error_msg_lower:
            limit_type = "recursion"
        elif "allocation" in error_msg_lower:
            limit_type = "allocations"
    
    if limit_type:
        return LimitError(str(error), limit_type=limit_type)
```

**Verify:** Test with "Failed to access memory address" should NOT become LimitError

---

### 3.6 Fix `check()` TOCTOU Issue
**File:** `src/grail/script.py:102`

Instead of re-parsing from disk, use the already-parsed AST:

```python
def check(self) -> CheckResult:
    # Option 1: Use cached parse result if available
    if hasattr(self, '_parse_result'):
        return check_pym(self._parse_result)
    
    # Option 2: Still parse from disk but document the TOCTOU
    # For now, just re-parse (existing behavior)
    parse_result = parse_pym_file(self._path)
    return check_pym(parse_result)
```

**Verify:** Load a script, modify it on disk, call check() - should ideally use cached version

---

## Phase 4: Data Type Enhancements

### 4.1 Add `kind` Field to `ParamSpec`
**File:** `src/grail/_types.py`

```python
@dataclass
class ParamSpec:
    name: str
    annotation: str | None
    has_default: bool
    default: Any | None = None
    kind: str = "positional-or-keyword"  # ADD THIS: "positional-only", "vararg", "keyword-only", "kwarg"
```

**Verify:** Run parser tests

---

### 4.2 Add `file` Field to `ParseResult`
**File:** `src/grail/_types.py`

```python
@dataclass
class ParseResult:
    ast_module: ast.Module
    externals: list[ExternalSpec]
    inputs: list[InputSpec]
    file: str | None = None  # ADD THIS
```

Update parser to pass file path when creating ParseResult.

**Verify:** Check results now include file path

---

### 4.3 Add `name` Field to `InputSpec`
**File:** `src/grail/_types.py`

```python
@dataclass
class InputSpec:
    name: str  # The variable name
    annotation: str | None
    has_default: bool
    default: Any | None = None
    input_name: str | None = None  # ADD THIS: The name="..." argument from Input()
```

**Verify:** Parser extracts the Input() name argument

---

## Phase 5: CLI Improvements

### 5.1 Add Error Handling to `cmd_watch`
**File:** `src/grail/cli.py`

Wrap the watch loop with try/except:

```python
def cmd_watch(args: argparse.Namespace) -> int:
    try:
        # ... existing watch loop ...
    except KeyboardInterrupt:
        print("\nWatch terminated.")
        return 0
    except Exception as e:
        print(f"Error during watch: {e}", file=sys.stderr)
        return 1
```

---

### 5.2 Fix JSON Output Ignoring `--strict`
**File:** `src/grail/cli.py`

In the JSON output path, respect the `--strict` flag:

```python
if args.json:
    # Apply strict mode to JSON output too
    if args.strict:
        failed = any(m.code.startswith(("E", "W")) for m in result.messages)
    else:
        failed = any(m.code.startswith("E") for m in result.messages)
```

---

### 5.3 Add `--version` Flag
**File:** `src/grail/cli.py`

Add to the argument parser:

```python
parser.add_argument("--version", action="version", version="%(prog)s 3.1.0")
```

---

## Phase 6: Monty API Coverage

### 6.1 OS Access Enrichment
**File:** `src/grail/script.py:_prepare_monty_files`

Allow passing environment variables:

```python
def _prepare_monty_files(
    self,
    files: dict[str, str | bytes] | None = None,
    environ: dict[str, str] | None = None,  # ADD THIS
) -> tuple[dict[str, MemoryFile], OSAccess]:
    # ... existing file handling ...
    
    os_access = OSAccess(
        files=files_dict,
        environ=environ or {},  # Pass through environment
    )
    return files_dict, os_access
```

Update `run()` and `load()` to accept `environ` parameter.

**Verify:** Create a script using `os.getenv("MY_VAR")`, pass it at runtime, works

---

### 6.2 Error Richness - Use `MontyError.exception()`
**File:** `src/grail/script.py:_map_error_to_pym`

When catching Monty errors, preserve the original exception:

```python
if isinstance(error, MontyError):
    original_exception = error.exception()  # Get inner Python exception
    # Include in error mapping
```

Also catch `MontySyntaxError` specifically:

```python
except MontySyntaxError as e:
    # Map to ParseError instead of generic ExecutionError
    raise ParseError(str(e), lineno=...) from e
```

---

### 6.3 Fix Print Callback Stream Type
**File:** `src/grail/script.py:334`

Update type hint:

```python
def _make_print_callback(self) -> Callable[[str, str], None]:
    def callback(msg: str, stream: Literal['stdout', 'stderr']) -> None:
        # ...
```

---

## Phase 7: Logging

### 7.1 Add Basic Logging
**File:** All modules in `src/grail/`

Add logging throughout. Example for `script.py`:

```python
import logging

logger = logging.getLogger(__name__)

# In load():
logger.debug("Loading script from %s", path)

# In run():
logger.info("Running script %s", self._path)
```

Set up basic configuration in `__init__.py` or a new `config.py`:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
```

---

## Phase 8: Error Hierarchy

### 8.1 Fix `LimitError` Hierarchy
**File:** `src/grail/errors.py`

Make `LimitError` a sibling of `ExecutionError` under `GrailError`:

```python
class LimitError(GrailError):  # NOT ExecutionError
    def __init__(self, message: str, limit_type: str):
        super().__init__(message)
        self.limit_type = limit_type
```

---

## Phase 9: Tests

*Write tests for the features that have zero coverage. These tests verify that the fixes work.*

### 9.1 Tests for `output_model` Validation
**File:** `tests/test_script.py`

```python
def test_output_model_valid():
    from pydantic import BaseModel
    
    class Output(BaseModel):
        result: int
        
    # Test with dict
    result = {"result": 42}
    validated = Output.model_validate(result)
    assert validated.result == 42
    
    # Test with object
    result = Output(result=42)
    validated = Output.model_validate(result)
    assert validated.result == 42

def test_output_model_invalid_raises():
    from grail.errors import OutputError
    
    class Output(BaseModel):
        result: int
    
    with pytest.raises(OutputError):
        # Should raise because "result" is missing
        Output.model_validate({})
```

---

### 9.2 Tests for Virtual Filesystem
**File:** `tests/test_integration.py`

```python
def test_run_with_virtual_file_read(tmp_path):
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""
from grail import external, Input

@external
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

result = read_file("test.txt")
""")
    
    script = grail.load(pym_file)
    result = script.run(
        files={"test.txt": "Hello World"},
        externals={...}
    )
    assert result == "Hello World"

def test_files_override_at_runtime():
    # Load with files
    script = grail.load(pym_file, files={"test.txt": "v1"})
    # Override at runtime
    result = script.run(files={"test.txt": "v2"})
    assert result == "v2"
```

---

### 9.3 Tests for External Exception Propagation
**File:** `tests/test_integration.py`

```python
def test_external_raises_value_error():
    def failing_external(x: int) -> int:
        raise ValueError("test error")
    
    with pytest.raises(grail.ExecutionError) as exc_info:
        script.run(externals={"fail": failing_external})
    
    assert "ValueError" in str(exc_info.value)

def test_external_raises_with_try_except():
    # Script wraps external in try/except
    # Verify exception is caught within Monty
```

---

### 9.4 Tests for Resource Limit Violations
**File:** `tests/test_integration.py`

```python
@pytest.mark.slow
def test_duration_limit_exceeded(tmp_path):
    pym_file = tmp_path / "infinite.pym"
    pym_file.write_text("""
while True:
    pass
""")
    
    script = grail.load(pym_file)
    with pytest.raises(grail.LimitError) as exc_info:
        script.run(limits=grail.Limits(max_duration="1ms"))
    
    assert exc_info.value.limit_type == "duration"
```

---

### 9.5 Tests for `dataclass_registry`
**File:** `tests/test_integration.py`

```python
from dataclasses import dataclass

@dataclass
class Person:
    name: str
    age: int

def test_run_with_dataclass_input():
    registry = {Person: Person}
    script = grail.load(pym_file, dataclass_registry=registry)
    result = script.run(inputs={"person": Person("Alice", 30)})
    # Verify dataclass passes through correctly
```

---

### 9.6 Tests for on_event Callbacks
**File:** `tests/test_integration.py`

```python
def test_on_event_error():
    events = []
    def on_event(e):
        events.append(e)
    
    script = grail.load(pym_file)
    try:
        script.run(on_event=on_event)
    except:
        pass
    
    assert any(e.type == "run_error" for e in events)

def test_on_event_print():
    events = []
    script = grail.load(pym_file)
    script.run(on_event=lambda e: events.append(e))
    assert any(e.type == "print" for e in events)
```

---

### 9.7 Tests for Parser Edge Cases
**File:** `tests/test_parser.py`

```python
def test_parse_grail_dot_external_style():
    code = """
@grail.external
def foo(x: int) -> int:
    return x
"""
    result = parse_pym_content(code)
    assert len(result.externals) == 1

def test_parse_sync_external():
    code = """
@external
def foo(x: int) -> int:
    return x
"""
    result = parse_pym_content(code)
    assert len(result.externals) == 1
```

---

## Summary Checklist

| Phase | Task | Status |
|-------|------|--------|
| 1.1 | Export GrailScript | [ ] |
| 1.2 | Export Limits constants | [ ] |
| 1.3 | Export ExternalSpec/InputSpec | [ ] |
| 1.4 | Fix bare assert | [ ] |
| 1.5 | Remove dead validate_external_function | [ ] |
| 1.6 | Remove legacy limits API | [ ] |
| 1.7 | Fix spec.loader null check | [ ] |
| 1.8 | Fix Pydantic v2 API | [ ] |
| 1.9 | Fix ast.Assign Input stripping | [ ] |
| 1.10 | Fix stub typing imports | [ ] |
| 2.1 | Fix load() ignoring check errors | [ ] |
| 2.2 | Fix extract_function_params | [ ] |
| 3.1 | Validate Input() name param | [ ] |
| 3.2 | Fix import allowlist | [ ] |
| 3.3 | Deduplicate error handling | [ ] |
| 3.4 | Fix regex line extraction | [ ] |
| 3.5 | Fix limit detection | [ ] |
| 3.6 | Fix check() TOCTOU | [ ] |
| 4.1 | Add ParamSpec.kind | [ ] |
| 4.2 | Add ParseResult.file | [ ] |
| 4.3 | Add InputSpec.name | [ ] |
| 5.1 | cmd_watch error handling | [ ] |
| 5.2 | JSON strict flag | [ ] |
| 5.3 | --version flag | [ ] |
| 6.1 | OS Access environ | [ ] |
| 6.2 | Error richness | [ ] |
| 6.3 | Print callback stream | [ ] |
| 7.1 | Add logging | [ ] |
| 8.1 | Fix LimitError hierarchy | [ ] |
| 9 | Write all tests | [ ] |

---

## Estimated Time

- **Phase 1 (Quick Wins):** 2-3 hours
- **Phase 2 (Core Bugs):** 3-4 hours
- **Phase 3 (Design):** 4-5 hours
- **Phase 4-8:** 4-6 hours
- **Phase 9 (Tests):** 6-8 hours

**Total:** ~20-25 hours
