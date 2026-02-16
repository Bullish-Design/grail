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
