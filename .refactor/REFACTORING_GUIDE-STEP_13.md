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
