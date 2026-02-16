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
