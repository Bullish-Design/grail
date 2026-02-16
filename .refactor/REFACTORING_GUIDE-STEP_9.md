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
