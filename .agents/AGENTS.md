# AGENTS.md - AI Agent Guide for Grail Development

## Purpose

This document guides AI agents working on the Grail library. It provides context about the project architecture, development patterns, and when to use specialized skills.

## Project Overview

Grail v2 is a minimalist Python library that provides a transparent programming experience for Monty (a secure Python interpreter written in Rust). The library consists of ~12 modules with a public API surface of ~15 symbols.

### Core Philosophy

1. **Transparency over Abstraction** — Make Monty's limitations visible, not hidden
2. **Minimal Surface Area** — Keep public API small, everything else is implementation
3. **Files as First-Class Citizens** — `.pym` files with full IDE support
4. **Pre-Flight Validation** — Catch Monty compatibility before runtime
5. **Inspectable Internals** — All generated artifacts visible in `.grail/`

### Architecture

```
User Code (.pym files)
    ↓
grail.load()
    ↓
Parser → Checker → Stubs Gen → Codegen
    ↓
GrailScript
    ↓
run() / check() / start()
    ↓
pydantic-monty (Monty interpreter)
```

## Module Reference

### Core Modules

| Module | Purpose | Dependencies | When to Use |
|--------|---------|--------------|--------------|
| `parser.py` | Parse `.pym` files, extract `@external` and `Input()` | `ast` module | Working with `.pym` file format |
| `checker.py` | Validate Monty compatibility, detect errors | Monty's `ty` checker | Adding validation rules |
| `stubs.py` | Generate `.pyi` stub files from declarations | None | Generating type stubs |
| `codegen.py` | Transform `.pym` → Monty code | `ast` module | Stripping grail-specific syntax |
| `script.py` | Main API: load, run, check scripts | `pydantic_monty` | Core script lifecycle |
| `snapshot.py` | Thin wrapper over Monty's pause/resume | `pydantic_monty` | Implementing pause/resume |
| `artifacts.py` | Manage `.grail/` directory | None | Writing generated files |
| `limits.py` | Parse and validate resource limits | None | Resource limit handling |
| `errors.py` | Error hierarchy with source mapping | None | Error formatting |
| `cli.py` | Command-line interface | argparse | CLI implementation |

### Supporting Modules

| Module | Purpose |
|--------|---------|
| `__init__.py` | Public API surface (~15 symbols) |
| `_types.pyi` | Type stubs for grail module (PEP 561) |
| `py.typed` | PEP 561 marker for type checking |

## When to Use Specialized Skills

### SKILL-monty-api

**Use when**: Writing code that interfaces directly with Monty

**Modules that need this skill**:
- `script.py` — Creating Monty instances, running code
- `snapshot.py` — Wrapping pause/resume mechanism
- Any tests that verify Monty integration

**Common tasks requiring this skill**:
- Creating `pydantic-monty.Monty` instances
- Calling `run()` or `start()` methods
- Handling `MontySnapshot`, `MontyComplete`, `MontyFutureSnapshot`
- Translating Grail resource limits to Monty format
- Creating `OSAccess` with `MemoryFile` objects
- Passing external functions to Monty
- Handling Monty errors (`MontyError`, `MontyRuntimeError`, etc.)
- Using type checking with `type_check_stubs`
- Serializing/deserializing Monty instances and snapshots

**Example**:
```python
# script.py needs Monty API knowledge
from pydantic_monty import Monty, OSAccess, MemoryFile

def run_script(self, inputs, externals):
    m = Monty(self.monty_code, external_functions=list(self.externals.keys()))
    fs = OSAccess([MemoryFile(path, content) for path, content in self.files.items()])
    return m.run(inputs=inputs, external_functions=externals, os=fs)
```

### SKILL-ast-parsing (Recommended)

**Use when**: Working with Python AST to parse or transform `.pym` files

**Modules that need this skill**:
- `parser.py` — Walking AST to extract declarations
- `codegen.py` — Transforming AST to generate Monty code

**Common tasks requiring this skill**:
- Parsing `.pym` files with `ast.parse()`
- Walking AST with `ast.walk()` or `NodeVisitor`
- Finding decorated functions (`@external`)
- Extracting function signatures and type annotations
- Finding `Input()` calls
- Removing specific AST nodes
- Preserving line numbers for source mapping
- Handling `async def` vs `def`

**Example**:
```python
# parser.py needs AST knowledge
import ast

def extract_externals(tree: ast.Module) -> dict[str, ExternalSpec]:
    externals = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and has_external_decorator(node):
            externals[node.name] = ExternalSpec.from_ast(node)
    return externals
```

## Development Workflow

### 1. Implementing a New Module

**Steps**:
1. Review module responsibility in ARCHITECTURE.md
2. Identify dependencies (Monty API, AST, etc.)
3. Load relevant skill document(s)
4. Implement following existing patterns
5. Write comprehensive tests
6. Update type stubs in `_types.pyi`
7. Update public API in `__init__.py` if needed

### 2. Adding a New Check Rule

**Steps**:
1. Define error code (e.g., `E010`)
2. Add check in `checker.py`
3. Update SPEC.md with error description
4. Write tests in `test_checker.py`
5. Add to CLI output formatting

### 3. Extending Monty Integration

**Steps**:
1. Review Monty API via SKILL-monty-api
2. Study Monty test examples in `.context/monty-main/`
3. Implement wrapper or adapter in appropriate module
4. Write integration tests
5. Update documentation

### 4. Fixing a Bug

**Steps**:
1. Locate bug in relevant module
2. Identify root cause (Monty integration? AST parsing? Validation?)
3. Load relevant skill document
4. Review related tests
5. Implement fix
6. Add regression test
7. Run full test suite

## Testing Guidelines

### Test Structure

```
tests/
├── test_parser.py      # AST extraction, validation
├── test_checker.py     # Monty rule detection
├── test_stubs.py       # Stub generation
├── test_codegen.py      # Code transformation
├── test_script.py      # Full load → check → run workflow
├── test_artifacts.py   # Artifact generation
├── test_limits.py      # Limit parsing
├── test_snapshot.py    # Pause/resume
├── test_errors.py      # Error formatting
└── test_cli.py        # CLI commands
```

### Testing Patterns

**1. Unit Tests**: Test single function/module in isolation
```python
def test_extract_external_function():
    code = """
    @external
    async def fetch(url: str) -> dict[str, Any]:
        ...
    """
    result = extract_externals(ast.parse(code))
    assert "fetch" in result
```

**2. Integration Tests**: Test complete workflows
```python
def test_load_check_run_workflow():
    script = grail.load("example.pym")
    assert script.check().valid
    result = script.run(inputs=..., externals=...)
    assert result == expected
```

**3. Monty Integration Tests**: Verify correct Monty usage
```python
def test_monty_external_functions():
    # Requires Monty API knowledge
    script = grail.load("example.pym")
    m = Monty(script.monty_code, external_functions=list(script.externals.keys()))
    # Verify Monty accepts the code
```

### Test Organization

- Group related tests with classes or sections
- Use descriptive test names (`test_<module>_<feature>_<scenario>`)
- Test both happy path and error cases
- Use fixtures for common setup (Monty instances, sample code)

## Common Patterns

### Error Handling

```python
# Pattern: Check before acting
if not os.path.exists(path):
    raise grail.ParseError(f"File not found: {path}")

# Pattern: Try/except with specific error
try:
    ast.parse(code)
except SyntaxError as e:
    raise grail.ParseError(f"Syntax error at line {e.lineno}: {e.msg}")
```

### Source Mapping

```python
# Pattern: Track line numbers throughout transformation
class SourceMap:
    pym_to_monty: dict[int, int] = {}  # pym_line → monty_line
    monty_to_pym: dict[int, int] = {}  # monty_line → pym_line

# When transforming, map lines
def transform_line(pym_line: int) -> int:
    if pym_line not in self.pym_to_monty:
        new_monty_line = len(self.monty_lines) + 1
        self.pym_to_monty[pym_line] = new_monty_line
        self.monty_to_pym[new_monty_line] = pym_line
    return self.pym_to_monty[pym_line]
```

### Async Wrappers

```python
# Pattern: Provide both async and sync interfaces
async def run(self, ...) -> Any:
    # Actual async implementation
    return await pydantic_monty.run_monty_async(...)

def run_sync(self, ...) -> Any:
    # Sync wrapper
    import asyncio
    return asyncio.run(self.run(...))
```

## Code Style

### Type Annotations

- All public functions must have type annotations
- Use `dict[str, Any]` instead of `Dict[str, Any]` (Python 3.9+)
- Use `str | None` instead of `Optional[str]` (Python 3.10+)
- Use `list[T]` instead of `List[T]` (Python 3.9+)

### Docstrings

- Use Google-style docstrings
- Include Args, Returns, Raises sections
- Keep descriptions concise but complete

### Error Messages

- Reference `.pym` file, not generated code
- Include line numbers from source map
- Provide actionable suggestions when possible

## Common Pitfalls

### 1. Confusing `.pym` with `monty_code.py`

- `.pym` is the source file developers edit
- `monty_code.py` is generated code sent to Monty
- Always map errors back to `.pym` line numbers

### 2. Forgetting to Strip Grail Imports

- `.pym` files have `from grail import ...` statements
- These must be removed before sending to Monty
- Monty doesn't recognize the `grail` module

### 3. Not Preserving Line Numbers

- When transforming code, maintain source map
- Errors must reference original `.pym` lines
- Test line number mapping thoroughly

### 4. Incorrect Monty Parameter Names

- Monty uses `external_functions` (plural)
- Grail uses `externals` (singular) for consistency
- Map correctly when calling Monty

### 5. Type Annotation Mismatches

- `.pym` files use Python 3.10+ type syntax
- Grail stubs use same syntax
- Ensure consistency between `.pym` and generated stubs

## Debugging Tips

### 1. Inspect Generated Artifacts

When debugging, check `.grail/<name>/`:
- `monty_code.py` — What was sent to Monty
- `stubs.pyi` — Type stubs used
- `check.json` — Validation results
- `run.log` — Actual execution output

### 2. Test with Bare Monty

When unsure if code will work in Monty:
```python
# Test directly with Monty
import pydantic_monty
m = pydantic_monty.Monty(code, type_check=True, type_check_stubs=stubs)
result = m.run()
```

### 3. Use Python AST Dump

When working with AST:
```python
import ast
tree = ast.parse(code)
print(ast.dump(tree, indent=2))
```

### 4. Verify Type Checking

```python
# Check type errors
m.type_check()  # Raises MontyTypingError if issues
```

## When to Ask for Clarification

- **Ambiguous requirements**: Ask for clarification on feature behavior
- **Trade-off decisions**: Present options with pros/cons
- **Monty compatibility**: Verify if a feature is supported by Monty
- **Breaking changes**: Discuss impact on public API
- **Performance concerns**: Ask about acceptable overhead

## Resources

- **ARCHITECTURE.md**: Detailed system architecture
- **SPEC.md**: Complete API specification
- **SKILL-monty-api.md**: Monty API reference (use when interfacing with Monty)
- **SKILL-ast-parsing.md**: AST patterns (use when parsing `.pym` files)
- **.context/monty-main/**: Monty source code and examples
- **GRAIL_CONCEPT.md**: Original concept document

## Quick Reference

### Public API Symbols (~15 total)

**Functions**:
- `grail.load(path, **options) -> GrailScript`
- `grail.run(code, inputs) -> Any`

**Declarations**:
- `grail.external` (decorator)
- `grail.Input(name, default=...)` (function)

**Classes**:
- `grail.Snapshot`

**Presets**:
- `grail.STRICT`
- `grail.DEFAULT`
- `grail.PERMISSIVE`

**Errors**:
- `grail.GrailError` (base)
- `grail.ParseError`
- `grail.CheckError`
- `grail.InputError`
- `grail.ExternalError`
- `grail.ExecutionError`
- `grail.LimitError`
- `grail.OutputError`

**Check Results**:
- `grail.CheckResult`
- `grail.CheckMessage`

### Module Quick Reference

**Need to parse `.pym` files?** → `parser.py`, `SKILL-ast-parsing.md`

**Need to validate Monty compatibility?** → `checker.py`

**Need to generate type stubs?** → `stubs.py`

**Need to transform `.pym` → Monty code?** → `codegen.py`, `SKILL-ast-parsing.md`

**Need to run code in Monty?** → `script.py`, `SKILL-monty-api.md`

**Need pause/resume?** → `snapshot.py`, `SKILL-monty-api.md`

**Need to manage `.grail/` directory?** → `artifacts.py`

**Need resource limits?** → `limits.py`

**Need error formatting?** → `errors.py`

**Need CLI?** → `cli.py`
