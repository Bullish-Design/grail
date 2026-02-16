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
