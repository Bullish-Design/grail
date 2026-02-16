# Grail Library - Implementation Refactoring Guide

**For**: Junior Developers
**Purpose**: Step-by-step guide to implement the Grail v2 library from scratch
**Based on**: ARCHITECTURE.md, SPEC.md, and detailed development guides

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Development Principles](#development-principles)
4. [Implementation Roadmap](#implementation-roadmap)
5. [Detailed Implementation Steps](#detailed-implementation-steps)
6. [Testing Strategy](#testing-strategy)
7. [Validation Checklist](#validation-checklist)

---

## Overview

### What is Grail?

Grail v2 is a minimalist Python library that provides a transparent, first-class programming experience for Monty (a secure Python interpreter written in Rust). It enables developers to write Monty scripts in `.pym` files with full IDE support, pre-flight validation, and seamless integration.

### Key Features

- **Transparent API**: ~15 public symbols, minimal abstraction
- **Type Safety**: Full type checking integration with Monty's type checker
- **IDE Support**: `.pym` files work like regular Python files
- **Pre-Flight Validation**: Catch Monty compatibility issues before runtime
- **Inspectable**: All generated code visible in `.grail/` directory
- **Security**: Inherits Monty's sandboxing with resource limits

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Grail Library                        │
├─────────────────────────────────────────────────────────────┤
│                                                         │
│  Parser → Checker → Stubs → Codegen → Script Runner    │
│                                                         │
│  Core Components:                                       │
│  • parser.py   - Extract @external and Input()          │
│  • checker.py  - Validate Monty compatibility           │
│  • stubs.py    - Generate .pyi type stubs               │
│  • codegen.py  - Transform .pym → monty_code.py         │
│  • script.py   - Main API (load, run, check)            │
│  • errors.py   - Error hierarchy with source mapping    │
│  • limits.py   - Resource limits parsing                │
│                                                         │
└─────────────────────────────────────────────────────────────┘
                          ↓
              ┌───────────────────────┐
              │  Monty (Rust-based)   │
              │  Python Interpreter   │
              └───────────────────────┘
```

---

## Prerequisites

### Required Knowledge

- Python 3.10+ fundamentals
- Python `ast` module basics
- Understanding of decorators and type hints
- Basic testing with pytest
- Git workflow

### Development Environment

```bash
# Install dependencies
pip install pydantic-monty pytest pytest-asyncio mypy ruff

# Verify installation
python -c "import pydantic_monty; print('Monty installed!')"
pytest --version
```

---

## Development Principles

Before starting, understand these core principles:

1. **Build Incrementally** - Each step should be fully tested before moving to the next
2. **Test Everything** - Unit tests before integration tests, validate before building
3. **Keep It Simple** - No premature optimization, no unnecessary abstractions
4. **Make Errors Visible** - All errors must map back to `.pym` file line numbers
5. **Type Safety** - Use type hints everywhere, validate with mypy
6. **Documentation** - Docstrings for all public APIs

---

## Implementation Roadmap

The implementation is broken down into 17 steps, organized into phases:

### Phase 1: Foundation (Steps 0-2)
- **Step 0**: Create `@external` decorator and `Input()` function
- **Step 1**: Define core type definitions (dataclasses)
- **Step 2**: Build error hierarchy

### Phase 2: Core Parsing (Steps 3-5)
- **Step 3**: Implement resource limits parsing
- **Step 4**: Create source mapping utilities
- **Step 5**: Build AST parser for `.pym` files

### Phase 3: Validation & Code Generation (Steps 6-8)
- **Step 6**: Implement Monty compatibility checker
- **Step 7**: Build type stub generator
- **Step 8**: Create code generator (`.pym` → Monty code)

### Phase 4: Artifacts & Script Management (Steps 9-11)
- **Step 9**: Implement artifacts manager (`.grail/` directory)
- **Step 10**: Build snapshot wrapper (pause/resume)
- **Step 11**: Create main `GrailScript` class

### Phase 5: Integration & CLI (Steps 12-14)
- **Step 12**: Implement runtime integration with Monty
- **Step 13**: Build input/external validation
- **Step 14**: Create CLI interface

### Phase 6: Polish & Testing (Steps 15-16)
- **Step 15**: Integration testing
- **Step 16**: End-to-end testing with real workflows

---

## Detailed Implementation Steps

### Step 0: Grail Declarations (@external & Input)

**Why this comes first**: The parser needs these to exist, and `.pym` files won't work in IDEs without them.

#### Files to Create

1. **`src/grail/_external.py`** - External function decorator
2. **`src/grail/_input.py`** - Input declaration function
3. **`src/grail/py.typed`** - PEP 561 marker (empty file)

#### Implementation Details

**`_external.py`**:
```python
"""External function decorator for .pym files."""
from typing import Any, Callable, TypeVar

F = TypeVar('F', bound=Callable[..., Any])

def external(func: F) -> F:
    """
    Mark a function as externally provided.

    This is a no-op at runtime - it exists for grail's parser
    to extract function signatures and generate type stubs.
    """
    func.__grail_external__ = True
    return func
```

**`_input.py`**:
```python
"""Input declaration for .pym files."""
from typing import TypeVar, overload, Any

T = TypeVar('T')

@overload
def Input(name: str) -> Any: ...

@overload
def Input(name: str, default: T) -> T: ...

def Input(name: str, default: Any = None) -> Any:
    """
    Declare an input variable provided at runtime.

    Usage:
        budget: float = Input("budget")
        dept: str = Input("dept", default="Engineering")
    """
    return default
```

#### Tests to Implement

Create `tests/unit/test_declarations.py`:

```python
def test_external_decorator_is_noop():
    """External decorator should not modify function behavior."""
    @external
    def dummy(x: int) -> int:
        ...
    assert hasattr(dummy, '__grail_external__')

def test_input_returns_default():
    """Input should return the default value."""
    result = Input("test", default="value")
    assert result == "value"

def test_input_without_default_returns_none():
    """Input without default should return None."""
    result = Input("test")
    assert result is None
```

#### Validation Checklist

- [ ] `pytest tests/unit/test_declarations.py` passes
- [ ] Can import: `from grail._external import external`
- [ ] Can import: `from grail._input import Input`
- [ ] IDE recognizes imports without errors
- [ ] `ruff check src/grail/` passes

---

### Step 1: Core Type Definitions

**Purpose**: Define all data structures used throughout the library.

#### Files to Create

1. **`src/grail/_types.py`** - Core dataclasses

#### Implementation Details

Create the following dataclasses:

1. **`ParamSpec`** - Function parameter specification
   - Fields: `name`, `type_annotation`, `default`

2. **`ExternalSpec`** - External function specification
   - Fields: `name`, `is_async`, `parameters`, `return_type`, `docstring`, `lineno`, `col_offset`

3. **`InputSpec`** - Input variable specification
   - Fields: `name`, `type_annotation`, `default`, `required`, `lineno`, `col_offset`

4. **`ParseResult`** - Result of parsing a `.pym` file
   - Fields: `externals`, `inputs`, `ast_module`, `source_lines`

5. **`SourceMap`** - Bidirectional line mapping between `.pym` and generated code
   - Fields: `monty_to_pym`, `pym_to_monty`
   - Method: `add_mapping(pym_line, monty_line)`

6. **`CheckMessage`** - Validation error/warning
   - Fields: `code`, `lineno`, `col_offset`, `end_lineno`, `end_col_offset`, `severity`, `message`, `suggestion`

7. **`CheckResult`** - Result of validation checks
   - Fields: `file`, `valid`, `errors`, `warnings`, `info`

8. **`ResourceLimits`** - Type alias for resource limits dictionary

#### Tests to Implement

Create `tests/unit/test_types.py`:

```python
def test_external_spec_creation():
    """Test creating ExternalSpec."""
    spec = ExternalSpec(
        name="test_func",
        is_async=True,
        parameters=[ParamSpec("x", "int", None)],
        return_type="str",
        docstring="Test",
        lineno=1,
        col_offset=0
    )
    assert spec.name == "test_func"

def test_source_map_bidirectional():
    """Test bidirectional source mapping."""
    smap = SourceMap()
    smap.add_mapping(pym_line=10, monty_line=5)
    assert smap.pym_to_monty[10] == 5
    assert smap.monty_to_pym[5] == 10

def test_check_message_creation():
    """Test creating CheckMessage."""
    msg = CheckMessage(
        code="E001",
        lineno=10,
        col_offset=4,
        end_lineno=10,
        end_col_offset=10,
        severity="error",
        message="Test error",
        suggestion="Fix it"
    )
    assert msg.severity == "error"
```

#### Validation Checklist

- [ ] All dataclasses are properly decorated with `@dataclass`
- [ ] All fields have type hints
- [ ] `SourceMap.add_mapping()` correctly creates bidirectional mappings
- [ ] `pytest tests/unit/test_types.py` passes
- [ ] `mypy src/grail/_types.py` passes with no errors

---

### Step 2: Error Hierarchy

**Purpose**: Create a comprehensive error hierarchy with source mapping support.

#### Files to Create

1. **`src/grail/errors.py`** - All error classes

#### Implementation Details

Create the following exception classes:

1. **`GrailError`** - Base exception class
2. **`ParseError`** - Syntax errors in `.pym` files
3. **`CheckError`** - Malformed `@external` or `Input()` declarations
4. **`InputError`** - Missing/invalid runtime inputs
5. **`ExternalError`** - Missing/invalid external functions
6. **`ExecutionError`** - Monty runtime errors with source context
7. **`LimitError`** - Resource limit exceeded (subclass of ExecutionError)
8. **`OutputError`** - Output validation failed

Key features:
- All errors should include line numbers when available
- Error messages should be formatted with context
- `ExecutionError` should support source context snippets

#### Tests to Implement

Create `tests/unit/test_errors.py`:

```python
def test_error_hierarchy():
    """All errors should inherit from GrailError."""
    assert issubclass(ParseError, GrailError)
    assert issubclass(LimitError, ExecutionError)

def test_parse_error_formatting():
    """ParseError should format with line numbers."""
    err = ParseError("unexpected token", lineno=10)
    assert "line 10" in str(err)

def test_execution_error_with_context():
    """ExecutionError should include source context."""
    err = ExecutionError(
        "NameError: undefined_var",
        lineno=22,
        source_context="  22 | if total > undefined_var:",
        suggestion="Check if variable is declared"
    )
    assert "Line 22" in str(err)
    assert "Suggestion:" in str(err)
```

#### Validation Checklist

- [ ] All exception classes inherit properly
- [ ] Error messages format correctly
- [ ] `pytest tests/unit/test_errors.py` passes
- [ ] Error classes are importable from `grail.errors`

---

### Step 3: Resource Limits Parsing

**Purpose**: Parse and validate resource limits with named presets.

#### Files to Create

1. **`src/grail/limits.py`** - Resource limits utilities

#### Implementation Details

Implement the following:

1. **Parse functions**:
   - `parse_memory(value: str | int) -> int` - Parse "16mb" → bytes
   - `parse_duration(value: str | float) -> float` - Parse "2s" → seconds
   - `parse_limit(key: str, value: Any) -> Any` - General limit parser

2. **Named presets**:
   ```python
   STRICT = {
       "max_memory": 8_388_608,      # 8MB
       "max_duration_secs": 0.5,
       "max_recursion_depth": 120,
   }

   DEFAULT = {
       "max_memory": 16_777_216,     # 16MB
       "max_duration_secs": 2.0,
       "max_recursion_depth": 200,
   }

   PERMISSIVE = {
       "max_memory": 67_108_864,     # 64MB
       "max_duration_secs": 5.0,
       "max_recursion_depth": 400,
   }
   ```

3. **Validation**:
   - Validate limit values are positive
   - Raise `ValueError` for invalid formats

#### Tests to Implement

Create `tests/unit/test_limits.py`:

```python
def test_parse_memory_string():
    """Test parsing memory strings."""
    assert parse_memory("8mb") == 8_388_608
    assert parse_memory("1gb") == 1_073_741_824
    assert parse_memory("512kb") == 524_288

def test_parse_duration_string():
    """Test parsing duration strings."""
    assert parse_duration("2s") == 2.0
    assert parse_duration("500ms") == 0.5

def test_named_presets():
    """Test named preset limits."""
    assert STRICT["max_memory"] == 8_388_608
    assert DEFAULT["max_memory"] == 16_777_216
    assert PERMISSIVE["max_memory"] == 67_108_864

def test_invalid_format_raises():
    """Test that invalid formats raise ValueError."""
    with pytest.raises(ValueError):
        parse_memory("invalid")
```

#### Validation Checklist

- [ ] Memory parsing handles kb/mb/gb/tb
- [ ] Duration parsing handles ms/s
- [ ] Named presets are defined
- [ ] Invalid inputs raise clear errors
- [ ] `pytest tests/unit/test_limits.py` passes

---

### Step 4: Source Mapping Utilities

**Purpose**: Map line numbers between `.pym` files and generated Monty code.

#### Files to Create

1. **`src/grail/sourcemap.py`** - Source mapping utilities

#### Implementation Details

Enhance the `SourceMap` class (from `_types.py`) with additional utilities:

1. **`map_pym_to_monty(line: int) -> int | None`** - Map `.pym` line to Monty line
2. **`map_monty_to_pym(line: int) -> int | None`** - Map Monty line to `.pym` line
3. **`format_error_context(pym_lines: list[str], lineno: int, context_lines: int = 2) -> str`** - Format error with surrounding context

#### Tests to Implement

Create `tests/unit/test_sourcemap.py`:

```python
def test_bidirectional_mapping():
    """Test bidirectional line mapping."""
    smap = SourceMap()
    smap.add_mapping(10, 5)
    assert smap.map_pym_to_monty(10) == 5
    assert smap.map_monty_to_pym(5) == 10

def test_format_error_context():
    """Test error context formatting."""
    lines = ["line 1", "line 2", "line 3", "line 4", "line 5"]
    context = format_error_context(lines, lineno=3, context_lines=1)
    assert "line 2" in context
    assert "line 3" in context
    assert "line 4" in context
    assert ">" in context  # Should highlight error line
```

#### Validation Checklist

- [ ] Bidirectional mapping works correctly
- [ ] Error context includes surrounding lines
- [ ] Error line is highlighted
- [ ] `pytest tests/unit/test_sourcemap.py` passes

---

### Step 5: Parser - Extract Externals and Inputs

**Purpose**: Parse `.pym` files and extract `@external` functions and `Input()` declarations.

#### Files to Create

1. **`src/grail/parser.py`** - AST parser

#### Implementation Details

Implement the following functions:

1. **`get_type_annotation_str(node: ast.expr | None) -> str`**
   - Convert AST annotation to string
   - Raise `CheckError` if missing

2. **`extract_function_params(func_node) -> list[ParamSpec]`**
   - Extract parameter specs from function
   - Handle defaults correctly
   - Validate all params have type annotations

3. **`validate_external_function(func_node)`**
   - Check return type exists
   - Check body is single Ellipsis
   - Raise `CheckError` on validation failure

4. **`extract_externals(module: ast.Module) -> dict[str, ExternalSpec]`**
   - Walk AST to find `@external` decorated functions
   - Validate each external function
   - Extract parameters, return type, docstring
   - Return dict of function name → ExternalSpec

5. **`extract_inputs(module: ast.Module) -> dict[str, InputSpec]`**
   - Walk AST to find `Input()` calls
   - Validate type annotations exist
   - Extract defaults from keyword args
   - Return dict of variable name → InputSpec

6. **`parse_pym_file(path: Path) -> ParseResult`**
   - Read file, parse AST
   - Extract externals and inputs
   - Return ParseResult

7. **`parse_pym_content(content: str) -> ParseResult`**
   - Parse from string (for testing)

#### Algorithm for extracting externals:

```python
for node in ast.walk(module):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for decorator in node.decorator_list:
            if decorator is @external:
                validate_external_function(node)
                extract params, return type, docstring
                create ExternalSpec
```

#### Algorithm for extracting inputs:

```python
for node in ast.walk(module):
    if isinstance(node, ast.AnnAssign):
        if node.value is Call to Input():
            validate annotation exists
            extract variable name
            extract default from keywords
            create InputSpec
```

#### Tests to Implement

Create `tests/unit/test_parser.py`:

```python
def test_parse_simple_external():
    """Test parsing simple external function."""
    content = """
from grail import external

@external
async def fetch(url: str) -> dict:
    ...
"""
    result = parse_pym_content(content)
    assert "fetch" in result.externals
    ext = result.externals["fetch"]
    assert ext.is_async is True
    assert ext.return_type == "dict"

def test_parse_input_with_default():
    """Test parsing Input with default."""
    content = """
from grail import Input

department: str = Input("department", default="Engineering")
"""
    result = parse_pym_content(content)
    assert "department" in result.inputs
    inp = result.inputs["department"]
    assert inp.required is False
    assert inp.default == "Engineering"

def test_missing_type_annotation_raises():
    """Missing annotation should raise CheckError."""
    content = """
from grail import external

@external
def bad(x):
    ...
"""
    with pytest.raises(CheckError, match="type annotation"):
        parse_pym_content(content)

def test_non_ellipsis_body_raises():
    """Non-ellipsis body should raise CheckError."""
    content = """
from grail import external

@external
def bad(x: int) -> int:
    return x * 2
"""
    with pytest.raises(CheckError, match="Ellipsis"):
        parse_pym_content(content)
```

Also create test fixtures in `tests/fixtures/`:
- `simple.pym` - Basic external and input
- `multiple_externals.pym` - Multiple externals and inputs
- `with_defaults.pym` - Functions and inputs with defaults

#### Validation Checklist

- [ ] Parser extracts `@external` functions correctly
- [ ] Parser extracts `Input()` declarations correctly
- [ ] Type annotations are properly extracted
- [ ] Defaults are correctly identified
- [ ] Validation errors raise `CheckError`
- [ ] Docstrings are extracted
- [ ] `pytest tests/unit/test_parser.py` passes
- [ ] All test fixtures parse without errors

---

### Step 6: Monty Compatibility Checker

**Purpose**: Validate that `.pym` files are compatible with Monty's limitations.

#### Files to Create

1. **`src/grail/checker.py`** - Compatibility checker

#### Implementation Details

Implement validation for Monty's limitations:

1. **Forbidden features to check**:
   - Classes (E001)
   - Generators/yield (E002)
   - `with` statements (E003)
   - `match` statements (E004)
   - Forbidden imports (E005) - only `grail` and `typing` allowed
   - `global`/`nonlocal` statements (E006)

2. **Functions to implement**:
   - `check_forbidden_features(ast_module) -> list[CheckMessage]`
   - `check_imports(ast_module) -> list[CheckMessage]`
   - `check_monty_compatibility(parse_result: ParseResult) -> CheckResult`

3. **Warning categories** (W0xx):
   - Unused external declarations
   - Unused input declarations
   - Bare dict returns (should specify types)

4. **Info gathering**:
   - Lines of code
   - Number of externals
   - Number of inputs
   - Async functions count

#### Algorithm:

```python
def check_forbidden_features(module):
    errors = []
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef):
            errors.append(CheckMessage(
                code="E001",
                severity="error",
                message="Classes not supported",
                lineno=node.lineno
            ))
        # ... check other forbidden features
    return errors
```

#### Tests to Implement

Create `tests/unit/test_checker.py`:

```python
def test_class_definition_raises_error():
    """Class definitions should be detected."""
    content = """
class MyClass:
    pass
"""
    result = parse_pym_content(content)
    check_result = check_monty_compatibility(result)
    assert not check_result.valid
    assert any(err.code == "E001" for err in check_result.errors)

def test_with_statement_raises_error():
    """With statements should be detected."""
    content = """
with open("file.txt") as f:
    pass
"""
    result = parse_pym_content(content)
    check_result = check_monty_compatibility(result)
    assert any(err.code == "E003" for err in check_result.errors)

def test_forbidden_import_raises_error():
    """Forbidden imports should be detected."""
    content = """
import os
"""
    result = parse_pym_content(content)
    check_result = check_monty_compatibility(result)
    assert any(err.code == "E005" for err in check_result.errors)

def test_valid_pym_passes():
    """Valid .pym should pass all checks."""
    content = """
from grail import external, Input

budget: float = Input("budget")

@external
async def fetch_data(url: str) -> dict:
    ...

result = await fetch_data("https://api.example.com")
"""
    result = parse_pym_content(content)
    check_result = check_monty_compatibility(result)
    assert check_result.valid
    assert len(check_result.errors) == 0
```

#### Validation Checklist

- [ ] All forbidden features are detected
- [ ] Error codes are correct (E001-E006)
- [ ] Warnings are generated appropriately
- [ ] Info statistics are collected
- [ ] Valid `.pym` files pass without errors
- [ ] `pytest tests/unit/test_checker.py` passes

---

### Step 7: Type Stub Generator

**Purpose**: Generate `.pyi` stub files from `@external` and `Input()` declarations.

#### Files to Create

1. **`src/grail/stubs.py`** - Stub generator

#### Implementation Details

Implement stub generation:

1. **`generate_external_stub(spec: ExternalSpec) -> str`**
   - Convert ExternalSpec to stub function signature
   - Include type annotations
   - Include docstring if present
   - Handle async functions

2. **`generate_input_stub(spec: InputSpec) -> str`**
   - Convert InputSpec to variable declaration
   - Include type annotation

3. **`generate_stubs(parse_result: ParseResult) -> str`**
   - Generate complete `.pyi` file
   - Include header comment
   - Import necessary types
   - Generate all external and input stubs

#### Example output:

```python
# Auto-generated by grail — do not edit
from typing import Any

budget_limit: float
department: str

async def get_team_members(department: str) -> dict[str, Any]:
    """Get list of team members for a department."""
    ...
```

#### Tests to Implement

Create `tests/unit/test_stubs.py`:

```python
def test_generate_external_stub():
    """Test generating stub for external function."""
    spec = ExternalSpec(
        name="fetch",
        is_async=True,
        parameters=[ParamSpec("url", "str", None)],
        return_type="dict",
        docstring="Fetch data",
        lineno=1,
        col_offset=0
    )
    stub = generate_external_stub(spec)
    assert "async def fetch" in stub
    assert "url: str" in stub
    assert "-> dict" in stub
    assert '"""Fetch data"""' in stub

def test_generate_input_stub():
    """Test generating stub for input."""
    spec = InputSpec(
        name="budget",
        type_annotation="float",
        default=None,
        required=True,
        lineno=1,
        col_offset=0
    )
    stub = generate_input_stub(spec)
    assert "budget: float" in stub

def test_generate_complete_stubs():
    """Test generating complete stub file."""
    content = """
from grail import external, Input

budget: float = Input("budget")

@external
async def fetch(url: str) -> dict:
    ...
"""
    result = parse_pym_content(content)
    stubs = generate_stubs(result)
    assert "from typing import" in stubs
    assert "budget: float" in stubs
    assert "async def fetch" in stubs
```

#### Validation Checklist

- [ ] External stubs generated correctly
- [ ] Input stubs generated correctly
- [ ] Type imports included
- [ ] Async functions marked correctly
- [ ] Docstrings preserved
- [ ] `pytest tests/unit/test_stubs.py` passes

---

### Step 8: Code Generator (`.pym` → Monty code)

**Purpose**: Transform `.pym` files into Monty-compatible Python code.

#### Files to Create

1. **`src/grail/codegen.py`** - Code generator

#### Implementation Details

The code generator must:

1. **Strip grail-specific code**:
   - Remove `from grail import ...` statements
   - Remove `@external` function definitions (keep declarations elsewhere)
   - Remove `Input()` calls (they become runtime bindings)

2. **Preserve executable code**:
   - Keep all non-declaration code
   - Preserve line numbers where possible

3. **Generate source map**:
   - Track which `.pym` lines map to which generated code lines
   - Create bidirectional mapping

4. **Functions to implement**:
   - `should_remove_node(node: ast.stmt) -> bool` - Check if node should be removed
   - `generate_monty_code(parse_result: ParseResult) -> CodegenResult` - Main generator
   - `CodegenResult` - Contains generated code and source map

#### Algorithm:

```python
def generate_monty_code(parse_result):
    source_map = SourceMap()
    output_lines = []
    monty_line = 1

    for pym_line, stmt in enumerate(parse_result.ast_module.body, 1):
        if should_remove_node(stmt):
            continue  # Skip grail-specific code

        # Generate code for this statement
        code = ast.unparse(stmt)
        output_lines.append(code)

        # Record mapping
        source_map.add_mapping(pym_line, monty_line)
        monty_line += code.count('\n') + 1

    return CodegenResult(
        code='\n'.join(output_lines),
        source_map=source_map
    )
```

#### Tests to Implement

Create `tests/unit/test_codegen.py`:

```python
def test_remove_grail_imports():
    """Test that grail imports are removed."""
    content = """
from grail import external, Input
from typing import Any

x = 10
"""
    result = parse_pym_content(content)
    codegen_result = generate_monty_code(result)
    assert "from grail import" not in codegen_result.code
    assert "from typing import" in codegen_result.code
    assert "x = 10" in codegen_result.code

def test_remove_external_definitions():
    """Test that external definitions are removed."""
    content = """
from grail import external

@external
async def fetch(url: str) -> dict:
    ...

result = await fetch("url")
"""
    result = parse_pym_content(content)
    codegen_result = generate_monty_code(result)
    assert "@external" not in codegen_result.code
    assert "async def fetch" not in codegen_result.code
    assert "result = await fetch" in codegen_result.code

def test_remove_input_declarations():
    """Test that Input() declarations are removed."""
    content = """
from grail import Input

budget: float = Input("budget")

total = budget * 2
"""
    result = parse_pym_content(content)
    codegen_result = generate_monty_code(result)
    assert "Input(" not in codegen_result.code
    assert "total = budget * 2" in codegen_result.code

def test_source_map_created():
    """Test that source map is created."""
    content = """
from grail import external

@external
def fetch() -> dict:
    ...

x = 10
y = 20
"""
    result = parse_pym_content(content)
    codegen_result = generate_monty_code(result)
    # Lines 1-5 should be skipped, line 7 should map
    assert 7 in codegen_result.source_map.pym_to_monty
```

#### Validation Checklist

- [ ] Grail imports removed
- [ ] External definitions removed
- [ ] Input declarations removed
- [ ] Executable code preserved
- [ ] Source map created correctly
- [ ] Line numbers tracked accurately
- [ ] `pytest tests/unit/test_codegen.py` passes

---

### Step 9: Artifacts Manager

**Purpose**: Manage `.grail/` directory structure and artifact files.

#### Files to Create

1. **`src/grail/artifacts.py`** - Artifacts manager

#### Implementation Details

Implement artifact management:

1. **Directory structure**:
   ```
   .grail/
   └── <script_name>/
       ├── stubs.pyi        # Type stubs
       ├── check.json       # Validation results
       ├── externals.json   # External specs
       ├── inputs.json      # Input specs
       ├── monty_code.py    # Generated code
       └── run.log          # Execution output
   ```

2. **Functions to implement**:
   - `create_grail_dir(base_path: Path, script_name: str) -> Path`
   - `write_stubs(grail_dir: Path, stubs: str)`
   - `write_check_result(grail_dir: Path, check_result: CheckResult)`
   - `write_externals(grail_dir: Path, externals: dict[str, ExternalSpec])`
   - `write_inputs(grail_dir: Path, inputs: dict[str, InputSpec])`
   - `write_monty_code(grail_dir: Path, code: str)`
   - `write_run_log(grail_dir: Path, log: str)`
   - `clean_grail_dir(base_path: Path)` - Remove `.grail/` directory

3. **Features**:
   - Create directories if they don't exist
   - Write JSON with indentation for readability
   - Optional: disable artifacts with `grail_dir=None`

#### Tests to Implement

Create `tests/unit/test_artifacts.py`:

```python
def test_create_grail_dir(tmp_path):
    """Test creating .grail directory."""
    grail_dir = create_grail_dir(tmp_path, "test_script")
    assert grail_dir.exists()
    assert grail_dir.name == "test_script"
    assert grail_dir.parent.name == ".grail"

def test_write_stubs(tmp_path):
    """Test writing stub file."""
    grail_dir = tmp_path / ".grail" / "test"
    grail_dir.mkdir(parents=True)
    write_stubs(grail_dir, "budget: float")

    stub_file = grail_dir / "stubs.pyi"
    assert stub_file.exists()
    assert "budget: float" in stub_file.read_text()

def test_write_check_result(tmp_path):
    """Test writing check result."""
    grail_dir = tmp_path / ".grail" / "test"
    grail_dir.mkdir(parents=True)

    check_result = CheckResult(
        file="test.pym",
        valid=True,
        errors=[],
        warnings=[],
        info={"loc": 10}
    )
    write_check_result(grail_dir, check_result)

    check_file = grail_dir / "check.json"
    assert check_file.exists()
    data = json.loads(check_file.read_text())
    assert data["valid"] is True

def test_clean_grail_dir(tmp_path):
    """Test cleaning .grail directory."""
    grail_dir = tmp_path / ".grail"
    grail_dir.mkdir()
    (grail_dir / "test.txt").write_text("test")

    clean_grail_dir(tmp_path)
    assert not grail_dir.exists()
```

#### Validation Checklist

- [ ] Directories created correctly
- [ ] All artifact types can be written
- [ ] JSON files are well-formatted
- [ ] Clean operation removes directory
- [ ] `pytest tests/unit/test_artifacts.py` passes

---

### Step 10: Snapshot Wrapper (Pause/Resume)

**Purpose**: Wrap Monty's pause/resume mechanism for external function calls.

#### Files to Create

1. **`src/grail/snapshot.py`** - Snapshot wrapper

#### Implementation Details

Implement the `Snapshot` class:

```python
class Snapshot:
    """Wrapper for Monty's pause/resume snapshots."""

    def __init__(self, monty_snapshot, source_map: SourceMap):
        self.monty_snapshot = monty_snapshot
        self.source_map = source_map

    @property
    def function_name(self) -> str:
        """Name of external function being called."""
        return self.monty_snapshot.function_name

    @property
    def args(self) -> tuple[Any, ...]:
        """Positional arguments for external call."""
        return self.monty_snapshot.args

    @property
    def kwargs(self) -> dict[str, Any]:
        """Keyword arguments for external call."""
        return self.monty_snapshot.kwargs

    @property
    def is_complete(self) -> bool:
        """Whether execution is complete."""
        return self.monty_snapshot.is_complete

    def resume(self, return_value: Any = None, **kwargs) -> 'Snapshot | Any':
        """Resume execution with return value."""
        next_snapshot = self.monty_snapshot.resume(
            return_value=return_value,
            **kwargs
        )
        if next_snapshot.is_complete:
            return next_snapshot.result
        return Snapshot(next_snapshot, self.source_map)

    def dump(self) -> bytes:
        """Serialize snapshot to bytes."""
        return self.monty_snapshot.dump()

    @staticmethod
    def load(data: bytes, source_map: SourceMap) -> 'Snapshot':
        """Deserialize snapshot from bytes."""
        monty_snapshot = pydantic_monty.MontySnapshot.load(data)
        return Snapshot(monty_snapshot, source_map)
```

#### Tests to Implement

Create `tests/unit/test_snapshot.py`:

```python
@pytest.mark.asyncio
async def test_snapshot_properties():
    """Test snapshot properties."""
    # Create a simple .pym with external
    content = """
from grail import external

@external
async def add(a: int, b: int) -> int:
    ...

result = await add(2, 3)
"""
    # Parse and run
    script = grail.load_from_string(content, "test")
    snapshot = script.start(
        inputs={},
        externals={}  # Don't provide, will pause
    )

    assert snapshot.function_name == "add"
    assert snapshot.args == (2, 3)
    assert snapshot.is_complete is False

def test_snapshot_resume():
    """Test resuming snapshot."""
    # ... create snapshot as above
    result = snapshot.resume(return_value=5)
    assert result == 5  # Or next snapshot

def test_snapshot_serialization():
    """Test dump/load."""
    # ... create snapshot
    data = snapshot.dump()
    assert isinstance(data, bytes)

    restored = Snapshot.load(data, source_map)
    assert restored.function_name == snapshot.function_name
```

#### Validation Checklist

- [ ] Snapshot properties accessible
- [ ] Resume works correctly
- [ ] Serialization round-trips
- [ ] `pytest tests/unit/test_snapshot.py` passes

---

### Step 11: Main GrailScript Class

**Purpose**: Implement the main `GrailScript` class that ties everything together.

#### Files to Create

1. **`src/grail/script.py`** - GrailScript class

#### Implementation Details

Implement the `GrailScript` class:

```python
class GrailScript:
    """Represents a loaded .pym script."""

    def __init__(
        self,
        path: Path,
        name: str,
        externals: dict[str, ExternalSpec],
        inputs: dict[str, InputSpec],
        monty_code: str,
        stubs: str,
        source_map: SourceMap,
        grail_dir: Path | None = None
    ):
        self.path = path
        self.name = name
        self.externals = externals
        self.inputs = inputs
        self.monty_code = monty_code
        self.stubs = stubs
        self.source_map = source_map
        self.grail_dir = grail_dir

    def check(self) -> CheckResult:
        """Run validation checks."""
        # Implement in Step 12

    async def run(
        self,
        inputs: dict[str, Any],
        externals: dict[str, Callable],
        **kwargs
    ) -> Any:
        """Run the script."""
        # Implement in Step 12

    def run_sync(self, inputs, externals, **kwargs) -> Any:
        """Synchronous wrapper for run()."""
        import asyncio
        return asyncio.run(self.run(inputs, externals, **kwargs))

    def start(
        self,
        inputs: dict[str, Any],
        externals: dict[str, Callable]
    ) -> Snapshot:
        """Start execution, pause on first external."""
        # Implement in Step 12


def load(
    path: str | Path,
    grail_dir: Path | None = None
) -> GrailScript:
    """
    Load a .pym file.

    Args:
        path: Path to .pym file
        grail_dir: Optional .grail directory path

    Returns:
        GrailScript instance
    """
    path = Path(path)
    name = path.stem

    # Parse
    parse_result = parse_pym_file(path)

    # Generate stubs
    stubs = generate_stubs(parse_result)

    # Generate code
    codegen_result = generate_monty_code(parse_result)

    # Write artifacts
    if grail_dir is not None:
        grail_script_dir = create_grail_dir(grail_dir, name)
        write_stubs(grail_script_dir, stubs)
        write_externals(grail_script_dir, parse_result.externals)
        write_inputs(grail_script_dir, parse_result.inputs)
        write_monty_code(grail_script_dir, codegen_result.code)

    return GrailScript(
        path=path,
        name=name,
        externals=parse_result.externals,
        inputs=parse_result.inputs,
        monty_code=codegen_result.code,
        stubs=stubs,
        source_map=codegen_result.source_map,
        grail_dir=grail_script_dir if grail_dir else None
    )
```

#### Tests to Implement

Create `tests/unit/test_script.py`:

```python
def test_load_pym_file(tmp_path):
    """Test loading a .pym file."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""
from grail import external, Input

budget: float = Input("budget")

@external
async def fetch(url: str) -> dict:
    ...

result = await fetch("url")
""")

    script = load(pym_file, grail_dir=tmp_path / ".grail")

    assert script.name == "test"
    assert "budget" in script.inputs
    assert "fetch" in script.externals
    assert "await fetch" in script.monty_code
    assert script.grail_dir.exists()

def test_load_without_grail_dir(tmp_path):
    """Test loading without creating artifacts."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("x = 10")

    script = load(pym_file, grail_dir=None)

    assert script.grail_dir is None
```

#### Validation Checklist

- [ ] `load()` function works
- [ ] Artifacts created when grail_dir provided
- [ ] No artifacts when grail_dir=None
- [ ] GrailScript properties accessible
- [ ] `pytest tests/unit/test_script.py` passes

---

### Step 12: Runtime Integration with Monty

**Purpose**: Implement the actual runtime integration to execute scripts with Monty.

#### Files to Update

1. **`src/grail/script.py`** - Add `run()`, `check()`, and `start()` implementations

#### Implementation Details

Implement the runtime methods:

1. **`GrailScript.check() -> CheckResult`**:
   ```python
   def check(self) -> CheckResult:
       """Run validation checks."""
       # Parse result is needed, so re-parse or cache
       parse_result = parse_pym_file(self.path)
       check_result = check_monty_compatibility(parse_result)

       # Write to artifacts if enabled
       if self.grail_dir:
           write_check_result(self.grail_dir, check_result)

       return check_result
   ```

2. **`GrailScript.run() -> Any`**:
   ```python
   async def run(
       self,
       inputs: dict[str, Any],
       externals: dict[str, Callable],
       limits: ResourceLimits | None = None,
       files: dict[str, str | bytes] | None = None,
       output_model: type[BaseModel] | None = None
   ) -> Any:
       """Run the script with Monty."""
       # Validate inputs (Step 13)
       validate_inputs(inputs, self.inputs)

       # Validate externals (Step 13)
       validate_externals(externals, self.externals)

       # Transform files to OSAccess
       os_access = None
       if files:
           os_access = create_os_access(files)

       # Create Monty instance
       monty = pydantic_monty.Monty(
           self.monty_code,
           type_check=True,
           type_check_stubs=self.stubs
       )

       # Run
       try:
           result = await pydantic_monty.run_monty_async(
               monty,
               inputs=inputs,
               externals=externals,
               limits=limits or DEFAULT,
               os_access=os_access
           )
       except Exception as e:
           # Map error to .pym line numbers
           raise map_execution_error(e, self.source_map, self.path)

       # Validate output
       if output_model:
           result = output_model.model_validate(result)

       return result
   ```

3. **`GrailScript.start() -> Snapshot`**:
   ```python
   def start(
       self,
       inputs: dict[str, Any],
       externals: dict[str, Callable],
       limits: ResourceLimits | None = None
   ) -> Snapshot:
       """Start execution, pause on first external."""
       # Validate inputs and externals
       validate_inputs(inputs, self.inputs)
       validate_externals(externals, self.externals)

       # Create Monty instance
       monty = pydantic_monty.Monty(
           self.monty_code,
           type_check=True,
           type_check_stubs=self.stubs
       )

       # Start with pause
       monty_snapshot = pydantic_monty.start_monty(
           monty,
           inputs=inputs,
           limits=limits or DEFAULT
       )

       return Snapshot(monty_snapshot, self.source_map)
   ```

#### Helper Functions

Create helper functions in `script.py`:

1. **`create_os_access(files: dict) -> OSAccess`** - Transform files dict to OSAccess
2. **`map_execution_error(error, source_map, path) -> ExecutionError`** - Map errors to `.pym` lines

#### Tests to Implement

Create `tests/integration/test_runtime.py`:

```python
@pytest.mark.asyncio
async def test_run_simple_script(tmp_path):
    """Test running a simple script."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""
from grail import Input

x: int = Input("x")
result = x * 2
""")

    script = load(pym_file)
    result = await script.run(inputs={"x": 5}, externals={})
    assert result == 10

@pytest.mark.asyncio
async def test_run_with_external(tmp_path):
    """Test running with external function."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""
from grail import external, Input

@external
async def add(a: int, b: int) -> int:
    ...

x: int = Input("x")
result = await add(x, 10)
""")

    async def add_impl(a, b):
        return a + b

    script = load(pym_file)
    result = await script.run(
        inputs={"x": 5},
        externals={"add": add_impl}
    )
    assert result == 15

@pytest.mark.asyncio
async def test_limit_exceeded_raises(tmp_path):
    """Test that limit violations raise LimitError."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""
x = [0] * 10000000  # Huge list
""")

    script = load(pym_file)
    with pytest.raises(LimitError):
        await script.run(
            inputs={},
            externals={},
            limits=STRICT
        )
```

#### Validation Checklist

- [ ] Scripts execute successfully
- [ ] External functions are called
- [ ] Inputs are bound correctly
- [ ] Limits are enforced
- [ ] Errors map to `.pym` line numbers
- [ ] `pytest tests/integration/test_runtime.py` passes

---

### Step 13: Input & External Validation

**Purpose**: Validate runtime inputs and externals against declarations.

#### Files to Create

1. **`src/grail/validation.py`** - Input/external validation

#### Implementation Details

Implement validation functions:

1. **`validate_inputs(provided: dict, specs: dict[str, InputSpec])`**:
   ```python
   def validate_inputs(provided: dict, specs: dict[str, InputSpec]):
       """Validate provided inputs against specs."""
       # Check all required inputs are provided
       for name, spec in specs.items():
           if spec.required and name not in provided:
               raise InputError(
                   f"Required input '{name}' not provided",
                   input_name=name
               )

       # Check for extra inputs
       extra = set(provided.keys()) - set(specs.keys())
       if extra:
           raise InputError(
               f"Unexpected inputs: {', '.join(extra)}"
           )

       # Type validation (basic)
       # Can be enhanced with runtime type checking
   ```

2. **`validate_externals(provided: dict, specs: dict[str, ExternalSpec])`**:
   ```python
   def validate_externals(provided: dict, specs: dict[str, ExternalSpec]):
       """Validate provided externals against specs."""
       # Check all externals are provided
       for name, spec in specs.items():
           if name not in provided:
               raise ExternalError(
                   f"External function '{name}' not provided",
                   function_name=name
               )

           # Check if callable
           if not callable(provided[name]):
               raise ExternalError(
                   f"External '{name}' must be callable",
                   function_name=name
               )

           # Check if async matches
           func = provided[name]
           is_async = asyncio.iscoroutinefunction(func)
           if spec.is_async and not is_async:
               raise ExternalError(
                   f"External '{name}' must be async",
                   function_name=name
               )

       # Check for extra externals (warning, not error)
       extra = set(provided.keys()) - set(specs.keys())
       if extra:
           # Could log warning
           pass
   ```

#### Tests to Implement

Create `tests/unit/test_validation.py`:

```python
def test_missing_required_input_raises():
    """Missing required input should raise InputError."""
    specs = {
        "x": InputSpec("x", "int", None, True, 1, 0)
    }
    with pytest.raises(InputError, match="Required input 'x'"):
        validate_inputs({}, specs)

def test_extra_input_raises():
    """Extra input should raise InputError."""
    specs = {
        "x": InputSpec("x", "int", None, True, 1, 0)
    }
    with pytest.raises(InputError, match="Unexpected inputs"):
        validate_inputs({"x": 1, "y": 2}, specs)

def test_missing_external_raises():
    """Missing external should raise ExternalError."""
    specs = {
        "fetch": ExternalSpec(
            "fetch", True, [], "dict", None, 1, 0
        )
    }
    with pytest.raises(ExternalError, match="not provided"):
        validate_externals({}, specs)

def test_non_callable_external_raises():
    """Non-callable external should raise."""
    specs = {
        "fetch": ExternalSpec(
            "fetch", True, [], "dict", None, 1, 0
        )
    }
    with pytest.raises(ExternalError, match="must be callable"):
        validate_externals({"fetch": "not a function"}, specs)

def test_async_mismatch_raises():
    """Async mismatch should raise."""
    specs = {
        "fetch": ExternalSpec(
            "fetch", True, [], "dict", None, 1, 0
        )
    }
    def sync_fetch():
        pass

    with pytest.raises(ExternalError, match="must be async"):
        validate_externals({"fetch": sync_fetch}, specs)
```

#### Validation Checklist

- [ ] Required inputs validated
- [ ] Extra inputs detected
- [ ] Missing externals detected
- [ ] Async/sync mismatch detected
- [ ] `pytest tests/unit/test_validation.py` passes

---

### Step 14: CLI Interface

**Purpose**: Create command-line interface for grail tooling.

#### Files to Create

1. **`src/grail/cli.py`** - CLI implementation
2. **`src/grail/__main__.py`** - Entry point for `python -m grail`

#### Implementation Details

Implement CLI commands using `argparse`:

1. **`grail check [files...]`** - Validate `.pym` files
2. **`grail run <file.pym> [--host <host.py>]`** - Execute script
3. **`grail init`** - Initialize project
4. **`grail watch [dir]`** - Watch and re-check (optional)
5. **`grail clean`** - Remove `.grail/` directory

Example implementation:

```python
import argparse
import sys
from pathlib import Path

def cmd_check(args):
    """Check .pym files."""
    from grail.script import load

    for file_path in args.files:
        path = Path(file_path)
        print(f"Checking {path}...")

        try:
            script = load(path)
            result = script.check()

            if result.valid:
                print(f"✓ {path} is valid")
            else:
                print(f"✗ {path} has errors:")
                for err in result.errors:
                    print(f"  Line {err.lineno}: {err.message}")
                sys.exit(1)
        except Exception as e:
            print(f"✗ Error: {e}")
            sys.exit(1)

def cmd_run(args):
    """Run a .pym script."""
    from grail.script import load
    import importlib.util

    # Load host file if provided
    externals = {}
    inputs = {}
    if args.host:
        spec = importlib.util.spec_from_file_location("host", args.host)
        host = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(host)
        externals = getattr(host, 'externals', {})
        inputs = getattr(host, 'inputs', {})

    # Load and run script
    script = load(Path(args.file))
    result = script.run_sync(inputs=inputs, externals=externals)
    print(f"Result: {result}")

def cmd_init(args):
    """Initialize grail project."""
    # Create sample .pym file
    sample = Path("sample.pym")
    sample.write_text("""
from grail import external, Input

@external
async def fetch_data(url: str) -> dict:
    '''Fetch data from URL.'''
    ...

url: str = Input("url")
data = await fetch_data(url)
print(f"Fetched: {data}")
""")
    print("Created sample.pym")

def cmd_clean(args):
    """Clean .grail directory."""
    from grail.artifacts import clean_grail_dir
    clean_grail_dir(Path.cwd())
    print("Cleaned .grail/")

def main():
    parser = argparse.ArgumentParser(description="Grail - Monty script manager")
    subparsers = parser.add_subparsers(dest="command")

    # grail check
    check_parser = subparsers.add_parser("check", help="Check .pym files")
    check_parser.add_argument("files", nargs="+", help=".pym files to check")

    # grail run
    run_parser = subparsers.add_parser("run", help="Run .pym file")
    run_parser.add_argument("file", help=".pym file to run")
    run_parser.add_argument("--host", help="Host file with externals/inputs")

    # grail init
    subparsers.add_parser("init", help="Initialize grail project")

    # grail clean
    subparsers.add_parser("clean", help="Clean .grail directory")

    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "clean":
        cmd_clean(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
```

**`__main__.py`**:
```python
from grail.cli import main
main()
```

#### Tests to Implement

Create `tests/integration/test_cli.py`:

```python
def test_cli_check_valid_file(tmp_path):
    """Test CLI check on valid file."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("x = 10")

    result = subprocess.run(
        ["python", "-m", "grail", "check", str(pym_file)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "valid" in result.stdout

def test_cli_check_invalid_file(tmp_path):
    """Test CLI check on invalid file."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("class Foo: pass")

    result = subprocess.run(
        ["python", "-m", "grail", "check", str(pym_file)],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    assert "error" in result.stdout.lower()

def test_cli_init(tmp_path):
    """Test CLI init command."""
    result = subprocess.run(
        ["python", "-m", "grail", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert (tmp_path / "sample.pym").exists()
```

#### Validation Checklist

- [ ] All CLI commands implemented
- [ ] Help text is clear
- [ ] Error handling works
- [ ] `python -m grail check` works
- [ ] `python -m grail run` works
- [ ] `python -m grail init` works
- [ ] `pytest tests/integration/test_cli.py` passes

---

### Step 15: Integration Testing

**Purpose**: Test full workflows end-to-end.

#### Files to Create

1. **`tests/integration/test_workflows.py`** - Complete workflow tests

#### Tests to Implement

```python
@pytest.mark.asyncio
async def test_complete_workflow_with_externals(tmp_path):
    """Test complete workflow with externals."""
    # Create .pym file
    pym_file = tmp_path / "analysis.pym"
    pym_file.write_text("""
from grail import external, Input

@external
async def fetch_expenses(dept: str) -> list[dict]:
    '''Fetch expenses for department.'''
    ...

department: str = Input("department", default="Engineering")
expenses = await fetch_expenses(department)
total = sum(e["amount"] for e in expenses)
result = {"department": department, "total": total}
""")

    # Mock external function
    async def mock_fetch(dept):
        return [
            {"amount": 100},
            {"amount": 200},
            {"amount": 300}
        ]

    # Load and run
    script = load(pym_file, grail_dir=tmp_path / ".grail")
    result = await script.run(
        inputs={},  # Use default
        externals={"fetch_expenses": mock_fetch}
    )

    assert result["department"] == "Engineering"
    assert result["total"] == 600

    # Verify artifacts created
    assert (tmp_path / ".grail" / "analysis" / "stubs.pyi").exists()
    assert (tmp_path / ".grail" / "analysis" / "monty_code.py").exists()

@pytest.mark.asyncio
async def test_pause_resume_workflow(tmp_path):
    """Test pause/resume workflow."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""
from grail import external, Input

@external
async def step1() -> int:
    ...

@external
async def step2(x: int) -> int:
    ...

a = await step1()
b = await step2(a)
result = b * 2
""")

    script = load(pym_file)

    # Start execution
    snapshot = script.start(inputs={}, externals={})
    assert snapshot.function_name == "step1"

    # Resume with step1 result
    snapshot = snapshot.resume(return_value=10)
    assert snapshot.function_name == "step2"
    assert snapshot.args[0] == 10

    # Resume with step2 result
    result = snapshot.resume(return_value=20)
    assert result == 40

@pytest.mark.asyncio
async def test_error_mapping(tmp_path):
    """Test that errors map to .pym line numbers."""
    pym_file = tmp_path / "test.pym"
    pym_file.write_text("""
from grail import Input

x: int = Input("x")
y = 10 / x  # Line 4 - will fail if x=0
""")

    script = load(pym_file)

    try:
        await script.run(inputs={"x": 0}, externals={})
        assert False, "Should have raised error"
    except ExecutionError as e:
        # Error should reference .pym file, not generated code
        assert "test.pym" in str(e) or e.lineno == 4
```

#### Validation Checklist

- [ ] Complete workflows execute successfully
- [ ] Pause/resume works end-to-end
- [ ] Errors map to correct line numbers
- [ ] Artifacts are created and readable
- [ ] `pytest tests/integration/test_workflows.py` passes

---

### Step 16: Public API Surface

**Purpose**: Define and expose the public API in `__init__.py`.

#### Files to Update

1. **`src/grail/__init__.py`** - Public API

#### Implementation Details

Define the public API (~15 symbols):

```python
"""
Grail - Transparent interface for Monty scripts.

Public API:
    - load()            Load a .pym file
    - GrailScript       Main script class
    - external          Decorator for external functions
    - Input             Input declaration function
    - Snapshot          Pause/resume snapshot

    Error types:
    - GrailError
    - ParseError
    - CheckError
    - InputError
    - ExternalError
    - ExecutionError
    - LimitError
    - OutputError

    Limits:
    - STRICT, DEFAULT, PERMISSIVE presets
"""

from grail.script import load, GrailScript
from grail._external import external
from grail._input import Input
from grail.snapshot import Snapshot
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
from grail.limits import STRICT, DEFAULT, PERMISSIVE

__all__ = [
    # Core API
    "load",
    "GrailScript",
    "external",
    "Input",
    "Snapshot",

    # Errors
    "GrailError",
    "ParseError",
    "CheckError",
    "InputError",
    "ExternalError",
    "ExecutionError",
    "LimitError",
    "OutputError",

    # Limits
    "STRICT",
    "DEFAULT",
    "PERMISSIVE",
]

__version__ = "2.0.0"
```

#### Tests to Implement

Create `tests/test_public_api.py`:

```python
def test_public_api_imports():
    """Test that all public APIs can be imported."""
    import grail

    # Core API
    assert hasattr(grail, 'load')
    assert hasattr(grail, 'GrailScript')
    assert hasattr(grail, 'external')
    assert hasattr(grail, 'Input')
    assert hasattr(grail, 'Snapshot')

    # Errors
    assert hasattr(grail, 'GrailError')
    assert hasattr(grail, 'ParseError')
    # ... etc

    # Limits
    assert hasattr(grail, 'STRICT')
    assert hasattr(grail, 'DEFAULT')
    assert hasattr(grail, 'PERMISSIVE')

def test_version():
    """Test version is defined."""
    import grail
    assert hasattr(grail, '__version__')
    assert isinstance(grail.__version__, str)
```

#### Validation Checklist

- [ ] All public APIs importable from `grail`
- [ ] `__all__` is defined correctly
- [ ] Version is set
- [ ] No internal modules exposed
- [ ] `pytest tests/test_public_api.py` passes

---

## Testing Strategy

### Test Organization

```
tests/
├── unit/                   # Unit tests for individual modules
│   ├── test_types.py
│   ├── test_errors.py
│   ├── test_limits.py
│   ├── test_parser.py
│   ├── test_checker.py
│   ├── test_stubs.py
│   ├── test_codegen.py
│   ├── test_artifacts.py
│   ├── test_validation.py
│   └── test_snapshot.py
├── integration/            # Integration tests
│   ├── test_runtime.py
│   ├── test_workflows.py
│   └── test_cli.py
├── fixtures/               # Test .pym files
│   ├── simple.pym
│   ├── multiple_externals.pym
│   └── with_defaults.pym
└── test_public_api.py      # Public API tests
```

### Testing Phases

1. **Unit Testing** (Steps 0-10)
   - Test each module in isolation
   - Mock dependencies
   - Fast execution
   - High coverage

2. **Integration Testing** (Steps 11-14)
   - Test module interactions
   - Use real Monty integration
   - Test full workflows
   - Verify artifacts

3. **E2E Testing** (Step 15)
   - Complete user workflows
   - Real `.pym` files
   - CLI testing
   - Error handling

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_parser.py

# Run with coverage
pytest --cov=grail --cov-report=html

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
```

### Test Coverage Goals

- **Unit tests**: 90%+ coverage
- **Integration tests**: All public APIs covered
- **E2E tests**: Key workflows covered

---

## Validation Checklist

### Phase 1: Foundation ✓
- [ ] Step 0: Declarations (`@external`, `Input()`)
  - [ ] Tests pass
  - [ ] IDE support works
  - [ ] Imports work

- [ ] Step 1: Type definitions
  - [ ] All dataclasses created
  - [ ] SourceMap works bidirectionally
  - [ ] Tests pass

- [ ] Step 2: Error hierarchy
  - [ ] All error types created
  - [ ] Error formatting works
  - [ ] Tests pass

### Phase 2: Core Parsing ✓
- [ ] Step 3: Resource limits
  - [ ] Memory parsing works
  - [ ] Duration parsing works
  - [ ] Presets defined
  - [ ] Tests pass

- [ ] Step 4: Source mapping
  - [ ] Bidirectional mapping works
  - [ ] Error context formatting works
  - [ ] Tests pass

- [ ] Step 5: Parser
  - [ ] Externals extracted correctly
  - [ ] Inputs extracted correctly
  - [ ] Validation works
  - [ ] Tests pass

### Phase 3: Validation & Code Generation ✓
- [ ] Step 6: Checker
  - [ ] All forbidden features detected
  - [ ] Warnings generated
  - [ ] Info collected
  - [ ] Tests pass

- [ ] Step 7: Stub generator
  - [ ] External stubs generated
  - [ ] Input stubs generated
  - [ ] Type imports included
  - [ ] Tests pass

- [ ] Step 8: Code generator
  - [ ] Grail code stripped
  - [ ] Executable code preserved
  - [ ] Source map created
  - [ ] Tests pass

### Phase 4: Artifacts & Script Management ✓
- [ ] Step 9: Artifacts manager
  - [ ] Directories created
  - [ ] All artifact types written
  - [ ] Clean works
  - [ ] Tests pass

- [ ] Step 10: Snapshot wrapper
  - [ ] Properties accessible
  - [ ] Resume works
  - [ ] Serialization works
  - [ ] Tests pass

- [ ] Step 11: GrailScript
  - [ ] Load function works
  - [ ] Artifacts created
  - [ ] Properties accessible
  - [ ] Tests pass

### Phase 5: Integration & CLI ✓
- [ ] Step 12: Runtime integration
  - [ ] Scripts execute
  - [ ] Externals called
  - [ ] Limits enforced
  - [ ] Errors mapped
  - [ ] Tests pass

- [ ] Step 13: Validation
  - [ ] Input validation works
  - [ ] External validation works
  - [ ] Async checking works
  - [ ] Tests pass

- [ ] Step 14: CLI
  - [ ] All commands implemented
  - [ ] Error handling works
  - [ ] Tests pass

### Phase 6: Polish & Testing ✓
- [ ] Step 15: Integration tests
  - [ ] Workflows execute
  - [ ] Pause/resume works
  - [ ] Error mapping verified
  - [ ] Tests pass

- [ ] Step 16: Public API
  - [ ] All APIs importable
  - [ ] `__all__` defined
  - [ ] Version set
  - [ ] Tests pass

### Final Validation ✓
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All E2E tests pass
- [ ] `mypy src/grail/` passes
- [ ] `ruff check src/grail/` passes
- [ ] Test coverage > 90%
- [ ] Documentation complete
- [ ] Examples work

---

## Additional Resources

### Reference Documentation

- **ARCHITECTURE.md** - Detailed architecture and design
- **SPEC.md** - Complete specification
- **`.roadmap/DEVELOPMENT_GUIDE-STEP_*.md`** - Detailed implementation guides for each step

### Monty Documentation

- [pydantic-monty](https://github.com/pydantic/monty) - Monty Python bindings
- Monty type checker documentation
- Monty resource limits

### Development Tools

```bash
# Linting
ruff check src/grail/

# Formatting
ruff format src/grail/

# Type checking
mypy src/grail/

# Testing
pytest --cov=grail

# Watch mode for development
pytest-watch
```

---

## Getting Help

If you encounter issues:

1. **Check the detailed guides**: `.roadmap/DEVELOPMENT_GUIDE-STEP_*.md` has more details for each step
2. **Review the architecture**: ARCHITECTURE.md explains the design decisions
3. **Check the spec**: SPEC.md has the complete specification
4. **Run tests**: Tests often demonstrate correct usage
5. **Check error messages**: Errors should be descriptive and helpful

---

## Next Steps

After completing all steps:

1. **Write examples**: Create example `.pym` files
2. **Write user documentation**: Usage guide for end users
3. **Performance testing**: Benchmark against bare Monty
4. **Security review**: Ensure no vulnerabilities
5. **Package for PyPI**: Create distribution package

---

**Good luck with the implementation!** Remember to:
- Build incrementally
- Test everything
- Keep it simple
- Make errors visible
