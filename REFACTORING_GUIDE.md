# Grail v2 — Refactoring Guide

**Based on:** CODE_REVIEW.md (2026-02-16)
**Target audience:** Junior developers
**Goal:** Address all recommended fixes and improvements from the code review, organized as incremental, testable steps.

---

## How to Use This Guide

Work through the steps **in order**. Each step is self-contained: it tells you which files to change, what to change, and which tests to write or run to confirm your work. Do not skip ahead — later steps may depend on earlier ones.

Before starting, make sure you can run the existing test suite:

```bash
pytest tests/ -v
```

You should see 67 passing, 1 failing, 1 skipped. After completing Step 1, you should have 0 failures.

---

## Step 1: Fix Async Test Configuration

**Priority:** P0 — This unblocks the rest of the work.
**Files:** `pyproject.toml`, potentially `tests/integration/test_end_to_end.py`
**Estimated scope:** Small

### Background

The code review reports one failing test (`test_run_simple_script`) caused by a pytest-asyncio configuration issue. The error message is:

```
async def functions are not natively supported.
You need to install a suitable plugin for your async framework
```

`pytest-asyncio` is already listed in dev dependencies, and `asyncio_mode = "auto"` is already set in `pyproject.toml`. The issue is likely that either the package is not installed in the environment or the test is missing the proper marker.

### What to Do

1. Verify `pytest-asyncio` is installed:
   ```bash
   pip install pytest-asyncio
   ```

2. Check the failing test. If it uses `async def` without the `@pytest.mark.asyncio` marker **and** auto mode is not being picked up, explicitly add the marker:
   ```python
   @pytest.mark.asyncio
   async def test_run_simple_script(...):
   ```

3. Confirm the `pyproject.toml` pytest configuration has:
   ```toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   ```

4. Run the full test suite and confirm the previously-failing test now passes.

### Tests to Validate

```bash
# Run the full suite — expect 0 failures
pytest tests/ -v

# Run just the previously-failing test to confirm it passes
pytest tests/ -v -k "test_run_simple_script"
```

**Done when:** All 69 tests pass (68 passing + the previously-failing one fixed, 1 skipped is acceptable).

---

## Step 2: Clean Up Commented-Out Code

**Priority:** P0 — Low effort, improves code cleanliness before making functional changes.
**Files:** `src/grail/script.py`, `src/grail/snapshot.py`

### Background

The code review identifies two kinds of commented-out code:

1. **`script.py` lines 261–262:** Stale API migration comments:
   ```python
   external_functions=externals,  # Changed from: externals=externals
   os=os_access,  # Changed from: os_access=os_access
   ```
   These comments document a past API change and add noise. Remove them.

2. **`snapshot.py` lines 67–68:** Commented-out validation:
   ```python
   # if not self.is_complete:
   #    raise RuntimeError("Execution not complete")
   return self._monty_snapshot.output
   ```
   The review says this could return garbage if called prematurely. **Uncomment** this guard — it should raise if someone accesses `value` before execution completes.

### What to Do

1. **In `src/grail/script.py`:** Find the lines with `# Changed from:` comments and remove the trailing comments, keeping only the actual code.

2. **In `src/grail/snapshot.py`:** Uncomment the validation guard in the `value` property so it raises `RuntimeError("Execution not complete")` when `is_complete` is `False`.

### Tests to Validate

```bash
# Run existing tests to make sure nothing breaks
pytest tests/ -v

# Specifically test snapshot behavior
pytest tests/unit/test_snapshot.py -v
```

Write a new test in `tests/unit/test_snapshot.py`:

```python
def test_value_raises_when_not_complete():
    """Accessing .value before execution completes should raise RuntimeError."""
    # Create a Snapshot that is not yet complete (mock _monty_snapshot.is_complete = False)
    # Assert that accessing snapshot.value raises RuntimeError
```

**Done when:** All existing tests pass, and accessing `snapshot.value` on an incomplete snapshot raises `RuntimeError`.

---

## Step 3: Fix Parser to Use Top-Level Iteration Only

**Priority:** Medium
**Files:** `src/grail/parser.py`

### Background

The code review (Section 2.2) points out that `extract_externals()` uses `ast.walk()` which traverses the **entire** AST tree, including nested function definitions. This means a function decorated with `@external` that is defined inside another function would incorrectly be treated as a top-level external declaration.

The fix is to iterate over `module.body` (top-level statements only) instead of `ast.walk(module)`.

### What to Do

1. Open `src/grail/parser.py` and find the `extract_externals()` function (around line 134).

2. Replace the `ast.walk(module)` loop with iteration over `module.body`:
   ```python
   # Before (wrong — walks entire tree):
   for node in ast.walk(module):
       if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
           continue
       ...

   # After (correct — top-level only):
   for node in module.body:
       if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
           continue
       ...
   ```

3. Check if `extract_inputs()` has the same issue — if it also uses `ast.walk()`, apply the same fix there since `Input()` declarations should also only be recognized at top-level.

### Tests to Validate

```bash
# Run existing parser tests
pytest tests/unit/test_parser.py -v
```

Add a new test in `tests/unit/test_parser.py`:

```python
def test_nested_external_not_extracted():
    """An @external function inside another function should NOT be extracted."""
    content = '''
from grail import external

def outer():
    @external
    def inner(x: int) -> str: ...

    return inner(5)
'''
    result = parse_pym_content(content)
    # inner() should NOT appear in result.externals
    assert "inner" not in result.externals


def test_nested_input_not_extracted():
    """An Input() call inside a function should NOT be extracted."""
    content = '''
from grail import Input

def compute():
    x: int = Input("x")
    return x * 2
'''
    result = parse_pym_content(content)
    # x should NOT appear in result.inputs
    assert "x" not in result.inputs
```

**Done when:** Existing tests pass and the new tests confirm that nested declarations are ignored.

---

## Step 4: Fix String-Based `Any` Detection in Stubs

**Priority:** Low (edge-case fix)
**Files:** `src/grail/stubs.py`

### Background

The stub generator checks whether to add `from typing import Any` by doing:

```python
if "Any" in external.return_type:
```

This is a substring match, so it would incorrectly match types like `"Company"` or `"AnyThing"`. The fix is to use a regex word boundary or a proper check.

### What to Do

1. Open `src/grail/stubs.py`.

2. Replace all substring checks for `"Any"` with a regex word-boundary check:
   ```python
   import re

   def _needs_any_import(type_str: str) -> bool:
       """Check if a type annotation string references typing.Any."""
       return bool(re.search(r'\bAny\b', type_str))
   ```

3. Use this helper wherever the code currently checks `"Any" in some_string`.

### Tests to Validate

```bash
pytest tests/unit/test_stubs.py -v
```

Add new tests in `tests/unit/test_stubs.py`:

```python
def test_any_detection_does_not_match_substring():
    """Type annotations like 'Company' should not trigger an Any import."""
    from grail._types import ExternalSpec, InputSpec
    from grail.stubs import generate_stubs

    externals = {
        "get_company": ExternalSpec(
            name="get_company",
            is_async=False,
            parameters=[],
            return_type="Company",
            docstring=None,
            lineno=1,
            col_offset=0,
        )
    }
    result = generate_stubs(externals=externals, inputs={})
    assert "from typing import Any" not in result


def test_any_detection_matches_actual_any():
    """A return type of 'Any' should trigger the Any import."""
    from grail._types import ExternalSpec
    from grail.stubs import generate_stubs

    externals = {
        "get_data": ExternalSpec(
            name="get_data",
            is_async=False,
            parameters=[],
            return_type="Any",
            docstring=None,
            lineno=1,
            col_offset=0,
        )
    }
    result = generate_stubs(externals=externals, inputs={})
    assert "from typing import Any" in result
```

**Done when:** The stubs generator only imports `Any` when the literal type name `Any` is used, not when `Any` appears as a substring of another word.

---

## Step 5: Populate `LimitError.limit_type` When Raising

**Priority:** Medium
**Files:** `src/grail/errors.py`, `src/grail/script.py`

### Background

`LimitError` has a `limit_type` field, but the code review notes it is never populated when the error is raised. This means callers who catch `LimitError` cannot programmatically determine *which* resource limit was exceeded.

### What to Do

1. Open `src/grail/errors.py` and review the `LimitError` class (around line 97). Confirm it accepts `limit_type` as an optional parameter.

2. Open `src/grail/script.py` and find where `LimitError` is raised or where Monty limit errors are caught and re-raised.

3. When catching a Monty limit exceeded error, inspect the error message or error type to determine which limit was hit (e.g., `"memory"`, `"duration"`, `"recursion"`), and pass it as the `limit_type` argument:
   ```python
   raise LimitError(
       message=str(error),
       limit_type="memory",  # or "duration", "recursion" — based on error inspection
   )
   ```

4. If the Monty error message contains keywords like "memory", "duration", or "recursion", use string matching to infer the limit type. Document this heuristic with a comment.

### Tests to Validate

```bash
pytest tests/unit/test_errors.py -v
```

Add new tests in `tests/unit/test_errors.py`:

```python
def test_limit_error_has_limit_type():
    """LimitError should carry the limit_type field."""
    from grail.errors import LimitError

    err = LimitError(message="Memory limit exceeded", limit_type="memory")
    assert err.limit_type == "memory"
    assert "Memory limit exceeded" in str(err)


def test_limit_error_without_limit_type():
    """LimitError with no limit_type should default to None."""
    from grail.errors import LimitError

    err = LimitError(message="Unknown limit exceeded")
    assert err.limit_type is None
```

**Done when:** `LimitError` instances raised during execution carry the correct `limit_type` value.

---

## Step 6: Implement Proper Source Mapping

**Priority:** P0 — This is the highest-impact functional fix.
**Files:** `src/grail/codegen.py`, `src/grail/_types.py`

### Background

The current source map implementation in `codegen.py` (lines 50–84) is a **naive heuristic** — it matches lines by content between the original `.pym` source and the generated Monty code. This breaks when:

- Lines don't match exactly (e.g., removed decorators shift line numbers)
- Multiline statements are involved
- AST transformations change line structure

The fix is to track line numbers **during the AST transformation** itself.

### What to Do

1. **Understand the current flow:**
   - `GrailDeclarationStripper` (an `ast.NodeTransformer`) visits the AST and removes grail-specific nodes (`from grail import ...`, `@external` functions, `Input()` assignments).
   - After transformation, `ast.unparse()` produces the Monty code.
   - `build_source_map()` then tries to correlate the result with the original lines.

2. **Replace the heuristic with AST-based tracking:**

   In the `GrailDeclarationStripper`, every AST node already has a `lineno` attribute (its original line in the `.pym` file). The key insight is: after transformation, when you call `ast.unparse()`, the resulting code's line numbers correspond to the **remaining** AST nodes which still carry their original `.pym` line numbers.

   Modify the approach:
   - After stripping, call `ast.fix_missing_locations()` on the transformed module.
   - Walk the transformed AST and record the original `lineno` of each remaining node.
   - After `ast.unparse()`, parse the result back and build the mapping from the new code's line numbers to the original `.pym` line numbers.

   A practical implementation:

   ```python
   def build_source_map(original_ast: ast.Module, transformed_ast: ast.Module,
                         monty_code: str) -> SourceMap:
       source_map = SourceMap()

       # Re-parse the generated code to get new line numbers
       generated_ast = ast.parse(monty_code)

       # Walk both transformed and generated ASTs in parallel
       # Nodes in transformed_ast still have original .pym lineno
       # Nodes in generated_ast have the new Monty lineno
       for t_node, g_node in zip(ast.walk(transformed_ast), ast.walk(generated_ast)):
           if hasattr(t_node, 'lineno') and hasattr(g_node, 'lineno'):
               source_map.add_mapping(
                   monty_line=g_node.lineno,
                   pym_line=t_node.lineno,
               )

       return source_map
   ```

   > **Note:** This parallel-walk approach works because `ast.unparse()` preserves the structure of the AST — it just re-serializes it. The node order in `ast.walk()` will be the same for both trees.

3. **Update `generate_monty_code()`** to pass the transformed AST (before unparsing) to the new `build_source_map()`.

4. **Update the `SourceMap` class in `_types.py`** if needed — the `add_mapping()` method should handle duplicate keys gracefully (keep the first mapping for each Monty line).

### Tests to Validate

```bash
pytest tests/unit/test_codegen.py -v
```

Add new tests in `tests/unit/test_codegen.py`:

```python
def test_source_map_accounts_for_stripped_lines():
    """
    When @external functions are removed, the source map should still
    point Monty lines back to the correct .pym lines.
    """
    from grail.parser import parse_pym_content
    from grail.codegen import generate_monty_code

    content = '''\
from grail import external, Input

budget: float = Input("budget")

@external
async def fetch_data(key: str) -> dict: ...

result = budget * 2
'''
    parsed = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parsed)

    # "result = budget * 2" is line 8 in the .pym
    # In the Monty code it appears earlier since the import, Input, and @external are stripped
    # Find which Monty line contains "result = budget * 2"
    monty_lines = monty_code.strip().splitlines()
    result_monty_line = None
    for i, line in enumerate(monty_lines, 1):
        if "result = budget * 2" in line:
            result_monty_line = i
            break

    assert result_monty_line is not None, "Expected 'result = budget * 2' in Monty code"
    # The source map should point this Monty line back to line 8 of the .pym
    assert source_map.monty_to_pym.get(result_monty_line) == 8


def test_source_map_identity_for_unchanged_lines():
    """Lines that aren't affected by stripping should still map correctly."""
    from grail.parser import parse_pym_content
    from grail.codegen import generate_monty_code

    content = '''\
x = 1
y = 2
z = x + y
'''
    parsed = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parsed)

    # No stripping needed — all lines should map 1:1
    for monty_line, pym_line in source_map.monty_to_pym.items():
        assert monty_line == pym_line
```

**Done when:** Source maps correctly track line number offsets caused by stripping `@external` functions, `Input()` declarations, and `from grail import` statements.

---

## Step 7: Integrate Source Map into Error Mapping

**Priority:** P0 — Depends on Step 6.
**Files:** `src/grail/script.py`

### Background

Even though a source map exists, `_map_error_to_pym()` in `script.py` (lines 173–194) does not use it. The comment in the code reads:

```python
# (This is simplified - real implementation would parse Monty's traceback)
lineno = None
```

This means execution errors show Monty line numbers (or no line numbers) instead of the original `.pym` line numbers.

### What to Do

1. Open `src/grail/script.py` and find `_map_error_to_pym()` (around line 173).

2. Implement actual line extraction from the Monty error. Monty errors typically include line numbers in their message or traceback. Parse the line number from the error string using a regex:
   ```python
   import re

   match = re.search(r'line (\d+)', str(error), re.IGNORECASE)
   if match:
       monty_line = int(match.group(1))
       pym_line = self._source_map.monty_to_pym.get(monty_line, monty_line)
   ```

3. Use the mapped `.pym` line number when constructing the `ExecutionError`:
   ```python
   return ExecutionError(
       message=error_msg,
       lineno=pym_line,  # Was: lineno (always None)
   )
   ```

4. Remove the comment about being "simplified".

### Tests to Validate

```bash
pytest tests/unit/test_script.py -v
```

Add a new test in `tests/unit/test_script.py`:

```python
def test_map_error_to_pym_uses_source_map():
    """_map_error_to_pym should translate Monty line numbers to .pym line numbers."""
    from grail._types import SourceMap

    source_map = SourceMap()
    source_map.add_mapping(monty_line=3, pym_line=10)

    # Create a GrailScript instance with this source_map (use mocks for other deps)
    # Simulate a Monty error that says "line 3"
    # Confirm the resulting ExecutionError has lineno=10
```

**Done when:** Execution errors reported to the user reference `.pym` line numbers, not Monty-generated code line numbers.

---

## Step 8: Add Error Context Display

**Priority:** P1
**Files:** `src/grail/errors.py`

### Background

The spec shows rich error context like:

```
  20 |     total = sum(item["amount"] for item in items)
  21 |
> 22 |     if total > undefined_var:
  23 |         custom = await get_custom_budget(user_id=uid)
```

But the current `ExecutionError._format_message()` only outputs `"Line 22: NameError: name 'undefined_var' is not defined"`.

### What to Do

1. Open `src/grail/errors.py` and find `ExecutionError._format_message()` (around line 62).

2. The `ExecutionError` class already has a `source_context` field. Modify `_format_message()` to use it. If `source_context` is provided (as a `str` containing the full `.pym` source), display surrounding lines:

   ```python
   def _format_message(self) -> str:
       parts: list[str] = []
       if self.lineno is not None:
           parts.append(f"Line {self.lineno}")
       parts.append(self.message)

       # Add source context if available
       if self.source_context and self.lineno is not None:
           context_lines = self._build_context_display(
               source=self.source_context,
               error_line=self.lineno,
               context=2,  # lines above and below
           )
           parts.append("")  # blank line separator
           parts.append(context_lines)

       if self.suggestion:
           parts.append(f"Suggestion: {self.suggestion}")

       return "\n".join(parts)
   ```

3. Implement `_build_context_display()`:

   ```python
   def _build_context_display(self, source: str, error_line: int, context: int = 2) -> str:
       lines = source.splitlines()
       start = max(0, error_line - context - 1)
       end = min(len(lines), error_line + context)

       output = []
       for i in range(start, end):
           line_num = i + 1
           prefix = "> " if line_num == error_line else "  "
           output.append(f"{prefix}{line_num:>4} | {lines[i]}")
       return "\n".join(output)
   ```

4. **Update `script.py`** to pass the `.pym` source content as `source_context` when constructing `ExecutionError` in `_map_error_to_pym()`. The source lines are available via `self._parse_result.source_lines` or from reading the file.

### Tests to Validate

```bash
pytest tests/unit/test_errors.py -v
```

Add new tests in `tests/unit/test_errors.py`:

```python
def test_execution_error_shows_context():
    """ExecutionError with source_context should display surrounding lines."""
    from grail.errors import ExecutionError

    source = "x = 1\ny = 2\nz = undefined\nw = 4\nv = 5"
    err = ExecutionError(
        message="NameError: name 'undefined' is not defined",
        lineno=3,
        source_context=source,
    )
    formatted = str(err)
    assert "> " in formatted        # error line is highlighted
    assert "3 |" in formatted        # line number shown
    assert "z = undefined" in formatted
    assert "x = 1" in formatted      # context line above
    assert "w = 4" in formatted      # context line below


def test_execution_error_without_context():
    """ExecutionError without source_context should still format cleanly."""
    from grail.errors import ExecutionError

    err = ExecutionError(message="Something failed", lineno=5)
    formatted = str(err)
    assert "Line 5" in formatted
    assert "Something failed" in formatted
    assert "> " not in formatted  # no context display
```

**Done when:** Execution errors display the offending line with surrounding context, matching the spec's format.

---

## Step 9: Implement the `--input` CLI Flag

**Priority:** P1
**Files:** `src/grail/cli.py`

### Background

The spec says this should work:

```bash
grail run analysis.pym --host host.py --input budget_limit=5000
```

But `--input` is not implemented. The flag should accept `key=value` pairs and pass them as inputs to the script.

### What to Do

1. Open `src/grail/cli.py` and find the `grail run` subcommand setup (around where `argparse` subparsers are configured).

2. Add the `--input` argument:
   ```python
   run_parser.add_argument(
       "--input", "-i",
       action="append",
       default=[],
       help="Input value as key=value (can be repeated)",
   )
   ```

3. In the `run` command handler (around line 149), parse the `--input` values into a dictionary:
   ```python
   inputs = {}
   for item in args.input:
       if "=" not in item:
           print(f"Error: Invalid input format '{item}'. Use key=value.")
           return 1
       key, value = item.split("=", 1)
       inputs[key.strip()] = value.strip()
   ```

4. Pass `inputs` to the script execution. How this integrates depends on how the `--host` runner works — either pass inputs as arguments to the host's `main()` function, or set them in the environment. Review the existing `grail run` logic and choose the approach that fits.

5. If the host-based approach makes direct input passing impractical, consider an alternative mode where `grail run` can execute a `.pym` file directly (using `grail.load()` + `script.run()`) when `--host` is omitted:
   ```bash
   grail run analysis.pym --input budget_limit=5000 --external host.py
   ```

### Tests to Validate

```bash
pytest tests/unit/test_cli.py -v
```

Add new tests in `tests/unit/test_cli.py`:

```python
def test_run_parses_input_flag():
    """The --input flag should parse key=value pairs into a dict."""
    # Test the argument parsing logic
    # Input: --input budget=5000 --input dept=engineering
    # Expected: {"budget": "5000", "dept": "engineering"}


def test_run_rejects_invalid_input_format():
    """An --input value without '=' should produce an error."""
    # Input: --input "invalid_no_equals"
    # Expected: non-zero exit code and error message


def test_run_input_flag_appears_in_help():
    """The --input flag should appear in the grail run help text."""
    import subprocess
    result = subprocess.run(
        ["python", "-m", "grail", "run", "--help"],
        capture_output=True, text=True,
    )
    assert "--input" in result.stdout
```

**Done when:** `grail run --input key=value` correctly parses inputs, rejects malformed values, and passes them to the script execution.

---

## Step 10: Document and Clean Up Snapshot Module

**Priority:** P1
**Files:** `src/grail/snapshot.py`

### Background

The code review rates `snapshot.py` at B- for documentation. Specific issues:

1. The async/future handling logic (lines 86–110) is hard to follow.
2. `Snapshot.load()` requires `source_map` and `externals` which are not serialized with the snapshot — this limitation is not documented.
3. The async protocol (how Monty communicates with external async functions via futures and call IDs) is undocumented.

### What to Do

1. **Add a module-level docstring** to `snapshot.py` explaining:
   - What the snapshot pattern is for (pause/resume execution)
   - How external function calls are handled (sync vs async)
   - The serialization limitation

2. **Add docstrings to all methods** that lack them, especially `resume()`, `dump()`, and `load()`.

3. **Add inline comments** to the async/future handling block (lines 86–110) explaining each step of the protocol:
   ```python
   # Async external function protocol:
   # 1. Monty pauses at an external call, providing a call_id
   # 2. We call the async external function ourselves
   # 3. We create a "future" resume with the call_id
   # 4. We then resolve the future with the actual return value
   # This two-step resume is required because Monty's async model
   # uses futures to represent pending async operations.
   ```

4. **Add a docstring to `load()`** that explicitly warns about the serialization limitation:
   ```python
   @staticmethod
   def load(data: bytes, source_map: SourceMap, externals: dict) -> "Snapshot":
       """Deserialize a snapshot from bytes.

       Note: source_map and externals are NOT included in the serialized
       data and must be provided from the original GrailScript context.
       This means you must retain access to the original script to restore
       a snapshot.
       """
   ```

### Tests to Validate

```bash
pytest tests/unit/test_snapshot.py -v
```

Add a new test:

```python
def test_snapshot_dump_load_requires_original_context():
    """
    Loading a snapshot requires the same source_map and externals
    that were used when the snapshot was created.
    """
    # Create a snapshot, dump it, then load it with source_map and externals
    # Verify it works with the correct context
    # Verify that the loaded snapshot has the expected properties
```

**Done when:** All methods in `snapshot.py` have clear docstrings, the async protocol has inline comments, and the serialization limitation is documented.

---

## Step 11: Validate Generated Code in Codegen

**Priority:** Medium
**Files:** `src/grail/codegen.py`

### Background

The code review notes that `generate_monty_code()` does not validate that the generated Python code is syntactically valid. If a bug in the AST transformer produces invalid code, it would fail silently until Monty tries to run it.

### What to Do

1. Open `src/grail/codegen.py` and find `generate_monty_code()` (around line 87).

2. After calling `ast.unparse()` to produce the Monty code string, parse it back to verify it is valid Python:
   ```python
   monty_code = ast.unparse(transformed)

   # Validate generated code is syntactically valid
   try:
       ast.parse(monty_code)
   except SyntaxError as e:
       raise GrailError(
           f"Code generation produced invalid Python: {e}. "
           "This is a bug in grail — please report it."
       )
   ```

3. Import `GrailError` from `grail.errors` at the top of the file.

### Tests to Validate

```bash
pytest tests/unit/test_codegen.py -v
```

Add a new test:

```python
def test_generate_monty_code_produces_valid_python():
    """The output of generate_monty_code should always be valid Python."""
    from grail.parser import parse_pym_content
    from grail.codegen import generate_monty_code
    import ast

    content = '''\
from grail import external, Input

budget: float = Input("budget")

@external
async def fetch(url: str) -> str: ...

result = budget * 2
'''
    parsed = parse_pym_content(content)
    monty_code, _ = generate_monty_code(parsed)

    # Should not raise
    ast.parse(monty_code)
```

**Done when:** `generate_monty_code()` raises a clear error if it produces invalid Python, and the normal case is verified by a test.

---

## Step 12: Add Integration Tests

**Priority:** P2
**Files:** `tests/integration/`

### Background

The code review notes limited integration test coverage. Currently there is only 1 integration test. The review recommends:

- End-to-end workflow tests
- Artifact verification tests
- Error message quality tests

### What to Do

Add the following test files:

#### 12a. End-to-End Workflow (`tests/integration/test_end_to_end.py`)

If this file already exists with some tests, add more. If it has tests that require `pydantic-monty` at runtime, mark them appropriately.

```python
import pytest
from pathlib import Path

def test_load_check_run_workflow(tmp_path):
    """Full workflow: load a .pym file, check it, and run it."""
    # 1. Write a .pym file to tmp_path
    # 2. Call grail.load() with appropriate externals
    # 3. Call script.check() — should pass
    # 4. Call script.run() with inputs — should return a result
    # 5. Verify the result is correct


def test_load_produces_artifacts(tmp_path):
    """Loading a script should produce .grail/ artifacts."""
    # 1. Load a .pym file with grail_dir set
    # 2. Check that .grail/{name}/stubs.pyi exists
    # 3. Check that .grail/{name}/monty_code.py exists
    # 4. Check that .grail/{name}/check.json exists
    # 5. Verify the content of each artifact is reasonable
```

#### 12b. Artifact Content Verification (`tests/integration/test_artifacts_verify.py`)

```python
def test_stubs_artifact_matches_generated_stubs(tmp_path):
    """The stubs.pyi artifact should match what generate_stubs() produces."""
    # Load a .pym with known externals and inputs
    # Read .grail/{name}/stubs.pyi
    # Call generate_stubs() directly with the same externals/inputs
    # Compare the two outputs


def test_monty_code_artifact_is_valid_python(tmp_path):
    """The monty_code.py artifact should be parseable Python."""
    import ast
    # Load a .pym file
    # Read .grail/{name}/monty_code.py
    # ast.parse() should not raise
```

#### 12c. Error Message Quality (`tests/integration/test_error_quality.py`)

```python
def test_check_error_includes_line_number():
    """Check errors should include the line number of the problem."""
    from grail.parser import parse_pym_content
    from grail.checker import check_pym

    content = '''\
from grail import external

class Forbidden:
    pass
'''
    parsed = parse_pym_content(content)
    result = check_pym(parsed, filename="test.pym")
    assert not result.valid
    assert result.errors[0].lineno == 3


def test_check_warning_includes_suggestion():
    """Checker warnings should include actionable suggestions."""
    # Create a .pym with a known warning trigger
    # Verify the warning message includes a suggestion field
```

### Tests to Validate

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run all tests to confirm nothing is broken
pytest tests/ -v
```

**Done when:** At least 5 new integration tests pass, covering the load-check-run workflow, artifact contents, and error message quality.

---

## Step 13: Improve CLI Error Handling

**Priority:** P2
**Files:** `src/grail/cli.py`

### Background

The code review notes that CLI exceptions bubble up without user-friendly messages. Users running `grail check` on a bad file may see a raw Python traceback instead of a helpful message.

### What to Do

1. Wrap the main command handlers in try/except blocks that catch `GrailError` subclasses and print friendly messages:

   ```python
   def cmd_check(args):
       try:
           # ... existing logic ...
       except ParseError as e:
           print(f"Error: {e}", file=sys.stderr)
           return 1
       except GrailError as e:
           print(f"Error: {e}", file=sys.stderr)
           return 1
       except FileNotFoundError as e:
           print(f"Error: File not found: {e.filename}", file=sys.stderr)
           return 1
   ```

2. Do the same for `cmd_run`, `cmd_init`, and `cmd_clean`.

3. Add `--verbose` flag to show full tracebacks when debugging:
   ```python
   parser.add_argument("--verbose", "-v", action="store_true", help="Show full error tracebacks")
   ```

### Tests to Validate

```bash
pytest tests/unit/test_cli.py -v
```

Add new tests:

```python
def test_check_nonexistent_file_shows_friendly_error(capsys):
    """Running grail check on a missing file should show a clear error, not a traceback."""
    # Call the check command with a path that doesn't exist
    # Capture stderr
    # Assert it contains "Error:" and "not found"
    # Assert it does NOT contain "Traceback"


def test_check_invalid_pym_shows_friendly_error(tmp_path, capsys):
    """Running grail check on a malformed .pym should show the parse error clearly."""
    bad_file = tmp_path / "bad.pym"
    bad_file.write_text("def foo(:\n")  # syntax error

    # Call the check command
    # Assert output contains the syntax error message
    # Assert no raw traceback
```

**Done when:** CLI commands print clean, user-friendly error messages for common failure modes, and `--verbose` enables full tracebacks.

---

## Step 14: Document Checker Feature Tracking Inconsistency

**Priority:** Low
**Files:** `src/grail/checker.py`

### Background

The code review (Section 2.3) notes that the checker excludes external async functions from feature tracking but includes user-defined ones. This is inconsistent and undocumented.

### What to Do

1. Open `src/grail/checker.py` and find the async feature tracking (around line 154).

2. Add a comment explaining **why** external async functions are excluded:
   ```python
   # External async functions are excluded from feature tracking because
   # they are stripped during code generation and don't represent actual
   # async usage within the Monty sandbox. Only user-defined async code
   # counts as a Monty feature dependency.
   ```

3. If this reasoning is incorrect and externals *should* be tracked, change the logic to track all async functions consistently. Choose whichever approach aligns with the spec and document the decision.

### Tests to Validate

```bash
pytest tests/unit/test_checker.py -v
```

Add a test to document the expected behavior:

```python
def test_external_async_not_tracked_as_feature():
    """External async functions should not count toward async_await feature tracking."""
    from grail.parser import parse_pym_content
    from grail.checker import check_pym

    content = '''\
from grail import external

@external
async def fetch(url: str) -> str: ...

result = "hello"
'''
    parsed = parse_pym_content(content)
    result = check_pym(parsed, filename="test.pym")
    assert "async_await" not in result.info.get("monty_features_used", [])
```

**Done when:** The feature tracking behavior is documented with a comment, and a test captures the expected behavior.

---

## Step 15: Add `watchfiles` as an Optional Dependency

**Priority:** Low
**Files:** `pyproject.toml`

### Background

`grail watch` requires the `watchfiles` package but it is not listed in `pyproject.toml`. Users who try `grail watch` get an unhelpful error.

### What to Do

1. Open `pyproject.toml` and add an optional dependency group:
   ```toml
   [project.optional-dependencies]
   watch = ["watchfiles>=0.21"]
   ```

2. Update the `grail watch` error message in `cli.py` to tell users how to install it:
   ```python
   except ImportError:
       print(
           "Error: 'grail watch' requires the watchfiles package.\n"
           "Install it with: pip install grail[watch]",
           file=sys.stderr,
       )
       return 1
   ```

### Tests to Validate

```bash
# Verify pyproject.toml is valid
pip install -e ".[watch]" --dry-run

# Run CLI tests
pytest tests/unit/test_cli.py -v
```

Add a test:

```python
def test_watch_missing_dependency_shows_install_hint(capsys, monkeypatch):
    """When watchfiles is not installed, grail watch should suggest pip install grail[watch]."""
    # Monkeypatch the import to raise ImportError
    # Call the watch command
    # Assert output contains "pip install grail[watch]"
```

**Done when:** `pyproject.toml` lists `watchfiles` as an optional dependency, and the error message tells users how to install it.

---

## Summary Checklist

| Step | Description | Priority | Files Changed |
|------|-------------|----------|---------------|
| 1 | Fix async test configuration | P0 | `pyproject.toml`, tests |
| 2 | Clean up commented-out code | P0 | `script.py`, `snapshot.py` |
| 3 | Fix parser top-level iteration | Medium | `parser.py` |
| 4 | Fix `Any` detection in stubs | Low | `stubs.py` |
| 5 | Populate `LimitError.limit_type` | Medium | `errors.py`, `script.py` |
| 6 | Implement proper source mapping | P0 | `codegen.py`, `_types.py` |
| 7 | Integrate source map into errors | P0 | `script.py` |
| 8 | Add error context display | P1 | `errors.py`, `script.py` |
| 9 | Implement `--input` CLI flag | P1 | `cli.py` |
| 10 | Document snapshot module | P1 | `snapshot.py` |
| 11 | Validate generated code | Medium | `codegen.py` |
| 12 | Add integration tests | P2 | `tests/integration/` |
| 13 | Improve CLI error handling | P2 | `cli.py` |
| 14 | Document checker feature tracking | Low | `checker.py` |
| 15 | Add `watchfiles` optional dep | Low | `pyproject.toml`, `cli.py` |

After completing all steps, run the full test suite one final time:

```bash
pytest tests/ -v
```

All tests — including the new ones you wrote — should pass.
