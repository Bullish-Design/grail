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
