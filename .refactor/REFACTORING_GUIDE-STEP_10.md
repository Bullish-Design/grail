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
