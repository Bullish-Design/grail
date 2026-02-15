# Grail v2 Development Guide

This guide provides step-by-step instructions for implementing Grail v2, a minimalist Python library that provides a transparent programming experience for Monty (a secure Python interpreter written in Rust).

## Prerequisites

- Python 3.13+
- pydantic-monty (the Monty Python bindings)
- Understanding of Python AST module

---

## Step 1: Project Setup & Type Definitions

### Work to be done

1. Create the module directory structure:
   ```
   src/grail/
   ├── __init__.py          # Already exists (empty)
   ├── _types.py            # Core type definitions
   ├── _types_stubs.pyi     # Type stubs for grail module
   └── py.typed             # PEP 561 marker (create empty file)
   ```

2. Implement `_types.py` with core data structures:
   - `ExternalSpec`: name, is_async, parameters, return_type, docstring, lineno, col_offset
   - `InputSpec`: name, type_annotation, default, required, lineno, col_offset
   - `ParamSpec`: name, type_annotation, default
   - `ParseResult`: externals, inputs, ast, source_lines
   - `SourceMap`: monty_lines, pym_lines (bidirectional mapping)
   - `CheckMessage`: code, lineno, col_offset, severity, message, suggestion
   - `CheckResult`: file, valid, errors, warnings, info
   - `ResourceLimits`: TypedDict for limits

3. Create `_types_stubs.pyi` with type stubs for `external` and `Input` decorators

4. Create empty `py.typed` marker file

### Testing/Validation

- Run `python -c "from grail._types import ExternalSpec, InputSpec, CheckResult"` to verify imports work
- Run `ruff check src/grail/_types.py` to verify linting passes
- Run `ty check src/grail/_types.py` to verify type checking passes (if ty is available)

---

## Step 2: Error Hierarchy

### Work to be done

Create `src/grail/errors.py` with the complete error hierarchy:

```python
class GrailError(Exception): ...

class ParseError(GrailError): ...
class CheckError(GrailError): ...

class InputError(GrailError): ...
class ExternalError(GrailError): ...

class ExecutionError(GrailError):
    def __init__(self, message: str, lineno: int | None = None, ...)

class LimitError(ExecutionError): ...
class OutputError(GrailError): ...
```

Include error formatting with source mapping capabilities.

### Testing/Validation

- Create `tests/unit/test_errors.py`:
  ```python
  def test_error_hierarchy():
      assert issubclass(ParseError, GrailError)
      assert issubclass(LimitError, ExecutionError)
      assert issubclass(ExecutionError, GrailError)
  ```
- Run `pytest tests/unit/test_errors.py` - should pass

---

## Step 3: Resource Limits

### Work to be done

Create `src/grail/limits.py`:

1. Implement string format parsing:
   - `"16mb"` → `16777216` (bytes)
   - `"1gb"` → `1073741824` (bytes)
   - `"500ms"` → `0.5` (seconds)
   - `"2s"` → `2.0` (seconds)

2. Define presets as plain dicts:
   ```python
   STRICT = {"max_memory": "8mb", "max_duration": "500ms", "max_recursion": 120}
   DEFAULT = {"max_memory": "16mb", "max_duration": "2s", "max_recursion": 200}
   PERMISSIVE = {"max_memory": "64mb", "max_duration": "5s", "max_recursion": 400}
   ```

3. Implement `parse_limits(limits: dict) -> dict` function

4. Implement `merge_limits(base: dict, override: dict) -> dict` function

### Testing/Validation

Create `tests/unit/test_limits.py`:

```python
def test_memory_parsing():
    assert parse_limit("16mb") == 16777216
    assert parse_limit("1GB") == 1073741824

def test_duration_parsing():
    assert parse_limit("500ms") == 0.5
    assert parse_limit("2s") == 2.0

def test_presets_are_plain_dicts():
    assert isinstance(STRICT, dict)
    assert STRICT["max_memory"] == "8mb"
```

Run `pytest tests/unit/test_limits.py` - all tests should pass.

---

## Step 4: Parser - AST Extraction

### Work to be done

Create `src/grail/parser.py`:

1. Implement `parse_pym_file(path: Path) -> ParseResult`:
   - Read file content
   - Parse with Python's `ast` module
   - Walk AST to find:
     - `@external` decorated functions → extract ExternalSpec
     - `Input()` calls → extract InputSpec
   - Validate basic structure

2. Implement helper functions:
   - `extract_external_specs(ast: ast.Module) -> dict[str, ExternalSpec]`
   - `extract_inputs(ast: ast.Module) -> dict[str, InputSpec]`
   - `_get_type_annotation_str(node: ast.AST) -> str`
   - `_get_lineno(node: ast.AST) -> tuple[int, int]`

3. Handle edge cases:
   - Missing type annotations → raise CheckError
   - `@external` with non-`...` body → raise CheckError
   - `Input()` without type annotation → raise CheckError

### Testing/Validation

Create `tests/unit/test_parser.py` with fixtures:

```python
# fixtures/valid_pym.py
VALID_PYM = """
from grail import external, Input

budget: float = Input("budget")

@external
async def get_data(id: int) -> dict[str, Any]:
    ...
"""

def test_parse_valid_pym():
    result = parse_pym_content(VALID_PYM)
    assert "get_data" in result.externals
    assert result.externals["get_data"].is_async is True
    assert "budget" in result.inputs
```

Also test error cases:

```python
def test_missing_type_annotation_raises():
    with pytest.raises(CheckError):
        parse_pym_content("@external\ndef foo(x): ...")

def test_non_ellipsis_body_raises():
    with pytest.raises(CheckError):
        parse_pym_content("@external\ndef foo(x): pass")
```

Run `pytest tests/unit/test_parser.py` - all tests should pass.

---

## Step 5: Checker - Monty Compatibility Validation

### Work to be done

Create `src/grail/checker.py`:

1. Implement `check_pym_ast(ast: ast.Module, source_lines: list[str]) -> CheckResult`

2. Implement detection for unsupported Python features:
   - E001: Class definitions (`ast.ClassDef`)
   - E002: Generator/yield (`ast.Yield`, `ast.YieldFrom`)
   - E003: `with` statements (`ast.With`)
   - E004: `match` statements (`ast.Match`)
   - E005: Forbidden imports (anything except `from grail import` or `from typing import`)

3. Implement validation for:
   - E006: Missing type annotations on `@external`
   - E007: `@external` with non-ellipsis body
   - E008: `Input()` without type annotation

4. Implement warnings:
   - W001: Bare dict/list as return value
   - W002: Unused `@external` function
   - W003: Unused `Input()` variable
   - W004: Very long script (>200 lines)

5. Implement info collection:
   - externals_count, inputs_count, lines_of_code
   - monty_features_used (async_await, for_loop, etc.)

### Testing/Validation

Create `tests/unit/test_checker.py`:

```python
def test_class_definition_detected():
    result = check_pym_ast(parse_ast("class Foo: pass"))
    assert any(e.code == "E001" for e in result.errors)

def test_generator_detected():
    result = check_pym_ast(parse_ast("def gen(): yield 1"))
    assert any(e.code == "E002" for e in result.errors)

def test_valid_pym_passes():
    result = check_pym_ast(parse_ast(VALID_PYM))
    assert result.valid is True
    assert len(result.errors) == 0
```

Run `pytest tests/unit/test_checker.py` - all tests should pass.

---

## Step 6: Stubs Generator

### Work to be done

Create `src/grail/stubs.py`:

1. Implement `generate_stubs(externals: dict[str, ExternalSpec], inputs: dict[str, InputSpec]) -> str`

2. Generate valid `.pyi` stub file content:
   - Include `from typing import Any` if needed
   - Generate input variable declarations: `budget_limit: float`
   - Generate external function signatures with docstrings

3. Handle type annotations:
   - Convert Python type annotations to stub format
   - Handle `Any`, `Union`, `Optional`, generics

4. Write to `.grail/<name>/stubs.pyi` (this will be done by artifacts manager)

### Testing/Validation

Create `tests/unit/test_stubs.py`:

```python
def test_generate_stubs_from_externals():
    externals = {
        "get_data": ExternalSpec(
            name="get_data",
            is_async=True,
            parameters=[ParamSpec(name="id", type_annotation="int", default=None)],
            return_type="dict[str, Any]",
            docstring="Fetch data by ID",
            lineno=1, col_offset=0
        )
    }
    inputs = {"budget": InputSpec(name="budget", type_annotation="float", default=None, required=True, lineno=2, col_offset=0)}
    
    stubs = generate_stubs(externals, inputs)
    
    assert "budget: float" in stubs
    assert "async def get_data(id: int) -> dict[str, Any]:" in stubs
    assert "Fetch data by ID" in stubs
```

Run `pytest tests/unit/test_stubs.py` - all tests should pass.

---

## Step 7: Code Generator - .pym to Monty Code

### Work to be done

Create `src/grail/codegen.py`:

1. Implement `generate_monty_code(parse_result: ParseResult) -> CodegenResult`

2. Transform `.pym` file to Monty-compatible code:
   - Strip `from grail import ...` statements
   - Remove `@external` decorated function definitions
   - Remove `Input()` calls (they become runtime bindings)
   - Preserve executable code section

3. Build source map:
   - Map monty_code.py line numbers back to .pym line numbers
   - This is critical for error reporting

4. Edge cases to handle:
   - Multiple statements on same line
   - Docstrings in functions
   - Nested structures

### Testing/Validation

Create `tests/unit/test_codegen.py`:

```python
def test_strips_grail_imports():
    pym_code = "from grail import external\nx = 1"
    result = generate_monty_code(pym_code)
    assert "from grail" not in result.code
    assert "x = 1" in result.code

def test_strips_external_decorators():
    pym_code = """
from grail import external

@external
async def foo(x: int) -> int:
    ...

result = foo(x=1)
"""
    result = generate_monty_code(pym_code)
    assert "@external" not in result.code
    assert "async def foo" not in result.code
    assert "result = foo(x=1)" in result.code

def test_source_map_preserved():
    # Line 5 in .pym should map to line 1 in monty_code.py
    result = generate_monty_code("x = 1\ny = 2")
    assert result.source_map.monty_lines[1] == 2
```

Run `pytest tests/unit/test_codegen.py` - all tests should pass.

---

## Step 8: Artifacts Manager

### Work to be done

Create `src/grail/artifacts.py`:

1. Implement `ArtifacterManager` class:
   - `__init__(grail_dir: Path)`
   - `write_script_artifacts(name: str, stubs: str, monty_code: str, check_result: CheckResult, externals: dict, inputs: dict)`
   - `write_run_log(name: str, stdout: str, stderr: str, duration_ms: float)`
   - `clean()`

2. Directory structure to create:
   ```
   .grail/
   └── <script_name>/
       ├── stubs.pyi
       ├── check.json
       ├── externals.json
       ├── inputs.json
       ├── monty_code.py
       └── run.log
   ```

3. JSON serialization for externals.json and inputs.json

### Testing/Validation

Create `tests/unit/test_artifacts.py`:

```python
def test_creates_directory_structure(tmp_path):
    mgr = ArtifacterManager(tmp_path)
    mgr.write_script_artifacts("test", "...", "...", CheckResult(...), {}, {})
    
    assert (tmp_path / "test" / "stubs.pyi").exists()
    assert (tmp_path / "test" / "externals.json").exists()

def test_clean_removes_grail_dir(tmp_path):
    mgr = ArtifacterManager(tmp_path)
    mgr.write_script_artifacts("test", "...", "...", CheckResult(...), {}, {})
    mgr.clean()
    
    assert not tmp_path.exists()
```

Run `pytest tests/unit/test_artifacts.py` - all tests should pass.

---

## Step 9: GrailScript Class - Core API

### Work to be done

Create `src/grail/script.py`:

1. Implement `GrailScript` class:
   - Properties: path, name, externals, inputs, monty_code, stubs, limits, grail_dir
   - `run(inputs, externals, **kwargs) -> Any` - async execution
   - `run_sync(inputs, externals, **kwargs) -> Any` - sync wrapper
   - `check() -> CheckResult` - run validation
   - `start(inputs, externals) -> Snapshot` - begin resumable execution

2. Implement `load(path, **options) -> GrailScript` function:
   - Calls parser, stubs generator, code generator
   - Writes artifacts
   - Returns GrailScript instance

3. Runtime validation in `run()`:
   - Validate inputs match Input[] declarations
   - Validate externals match @external declarations
   - Transform limits to Monty format
   - Transform files dict to OSAccess with MemoryFile
   - Call `pydantic_monty.run_monty_async()`
   - Map errors to .pym line numbers

### Testing/Validation

Create `tests/integration/test_script.py`:

```python
@pytest.mark.integration
async def test_load_valid_pym(tmp_path):
    # Create a valid .pym file
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""\
from grail import external, Input

x: int = Input("x")

@external
async def double(n: int) -> int:
    ...

result = double(x)
""")
    
    script = grail.load(str(pym_file))
    
    assert script.name == "test"
    assert "double" in script.externals
    assert "x" in script.inputs

@pytest.mark.integration
async def test_run_simple_script():
    script = grail.load("fixtures/simple.pym")
    
    result = await script.run(
        inputs={"x": 5},
        externals={"double": lambda n: n * 2}
    )
    
    assert result == 10
```

Run `pytest tests/integration/test_script.py` - integration tests should pass.

---

## Step 10: Snapshot - Pause/Resume

### Work to be done

Create `src/grail/snapshot.py`:

1. Implement `Snapshot` class wrapping `pydantic_monty.MontySnapshot`:
   - Properties: function_name, args, kwargs, is_complete, call_id
   - Methods: resume(), dump()
   - Static: load()

2. Integration with GrailScript.start()

3. Ensure source mapping works through snapshot resume

### Testing/Validation

Create `tests/integration/test_snapshot.py`:

```python
@pytest.mark.integration
async def test_pause_resume():
    script = grail.load("fixtures/with_external.pym")
    
    snapshot = script.start(
        inputs={"x": 1},
        externals={"external_func": mock_func}
    )
    
    assert snapshot.is_complete is False
    assert snapshot.function_name == "external_func"
    
    # Resume with result
    snapshot = snapshot.resume(return_value=42)
    
    # Continue until complete
    while not snapshot.is_complete:
        result = await externals[snapshot.function_name](*snapshot.args, **snapshot.kwargs)
        snapshot = snapshot.resume(return_value=result)
```

Run `pytest tests/integration/test_snapshot.py` - tests should pass.

---

## Step 11: CLI - Command-Line Interface

### Work to be done

Create `src/grail/cli.py`:

1. Implement CLI commands using `argparse`:

   - `grail init`: Create .grail/, update .gitignore, create sample .pym
   
   - `grail check [files...]`:
     - Parse .pym files
     - Run checker
     - Output results (human-readable or JSON)
     - Support `--strict` flag
   
   - `grail run <file.pym> [--host <host.py>]`:
     - Load .pym file
     - Execute with provided externals/inputs
     - Output results
   
   - `grail watch [dir]`: File watcher (use watchfiles)
   
   - `grail clean`: Remove .grail/ directory

2. Entry point in pyproject.toml:
   ```toml
   [project.scripts]
   grail = "grail.cli:main"
   ```

### Testing/Validation

Create `tests/integration/test_cli.py`:

```python
def test_cli_init_creates_grail_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    
    assert Path(".grail").exists()

def test_cli_check_valid_pym(tmp_path):
    # Create valid .pym file
    # Run grail check
    # Verify output shows OK
    
def test_cli_check_invalid_pym_shows_errors():
    # Create invalid .pym with class definition
    # Run grail check
    # Verify E001 error is shown
```

Run `pytest tests/integration/test_cli.py` - tests should pass.

---

## Step 12: Public API - Final __init__.py

### Work to be done

Update `src/grail/__init__.py` with the complete public API:

```python
# Core
from grail.script import GrailScript, load
from grail.codegen import run

# Declarations (for .pym files)
from grail._external import external
from grail._input import Input

# Snapshots
from grail.snapshot import Snapshot

# Limits
from grail.limits import STRICT, DEFAULT, PERMISSIVE, parse_limits

# Errors
from grail.errors import (
    GrailError,
    ParseError,
    CheckError,
    InputError,
    ExternalError,
    ExecutionError,
    LimitError,
    OutputError,
)

# Check results
from grail._types import CheckResult, CheckMessage

__all__ = [
    # Core
    "load",
    "run",
    # Declarations
    "external",
    "Input",
    # Snapshots
    "Snapshot",
    # Limits
    "STRICT",
    "DEFAULT",
    "PERMISSIVE",
    "parse_limits",
    # Errors
    "GrailError",
    "ParseError",
    "CheckError",
    "InputError",
    "ExternalError",
    "ExecutionError",
    "LimitError",
    "OutputError",
    # Check results
    "CheckResult",
    "CheckMessage",
]
```

### Testing/Validation

```python
def test_public_api_imports():
    import grail
    
    # Core
    assert hasattr(grail, "load")
    assert hasattr(grail, "run")
    
    # Declarations
    assert hasattr(grail, "external")
    assert hasattr(grail, "Input")
    
    # Snapshots
    assert hasattr(grail, "Snapshot")
    
    # Limits
    assert grail.STRICT is not None
    assert grail.DEFAULT is not None
    
    # Errors
    assert issubclass(grail.GrailError, Exception)
    
    # Check results
    assert hasattr(grail, "CheckResult")
```

Run `python -c "import grail; print(grail.__all__)"` to verify all exports work.

---

## Step 13: Integration & E2E Tests

### Work to be done

Create comprehensive integration tests that verify the full workflow:

1. `tests/integration/test_real_workflows.py`:
   - Test expense_analysis example from Monty examples
   - Test sql_playground example
   
2. `tests/integration/test_monty_integration.py`:
   - Test all Monty features work correctly
   - Test type checking integration

3. `tests/e2e/test_examples.py`:
   - End-to-end tests of complete use cases
   - Verify .grail/ artifacts are correct

### Testing/Validation

Run full test suite:

```bash
pytest tests/ -v
```

All tests should pass before proceeding.

---

## Step 14: Final Validation

### Work to be done

1. Run full linting:
   ```bash
   ruff check src/grail/
   ```

2. Run type checking:
   ```bash
   ty check src/grail/
   ```

3. Run all tests:
   ```bash
   pytest tests/ -v
   ```

4. Verify CLI works:
   ```bash
   grail init
   grail check
   ```

5. Verify package can be installed:
   ```bash
   pip install -e .
   ```

---

## Implementation Order Summary

| Step | Module | Description |
|------|--------|-------------|
| 1 | `_types.py`, `_types_stubs.pyi`, `py.typed` | Type definitions |
| 2 | `errors.py` | Error hierarchy |
| 3 | `limits.py` | Resource limits parsing |
| 4 | `parser.py` | AST extraction |
| 5 | `checker.py` | Monty compatibility validation |
| 6 | `stubs.py` | Type stub generation |
| 7 | `codegen.py` | .pym → Monty code transformation |
| 8 | `artifacts.py` | .grail/ directory management |
| 9 | `script.py` | GrailScript class, load/run |
| 10 | `snapshot.py` | Pause/resume wrapper |
| 11 | `cli.py` | CLI commands |
| 12 | `__init__.py` | Public API exports |
| 13 | Integration tests | Full workflow tests |
| 14 | Final validation | Lint, typecheck, test |

---

## Key Testing Principles

1. **Test each module in isolation** (unit tests) before integration
2. **Verify error cases** - check that invalid input raises appropriate errors
3. **Test edge cases** - empty files, missing annotations, etc.
4. **Verify source mapping** - errors must reference .pym line numbers, not generated code
5. **Integration tests require Monty** - mark with `@pytest.mark.integration`
6. **Always validate before building** - each step should pass its tests before moving on
