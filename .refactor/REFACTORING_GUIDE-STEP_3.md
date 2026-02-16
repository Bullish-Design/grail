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
