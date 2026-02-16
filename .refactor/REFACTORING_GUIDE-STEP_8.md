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
