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
