## Step 12: Add Integration Tests

**Priority:** P2
**Files:** `tests/integration/`

### Background

The code review notes limited integration test coverage. Currently there is only 1 integration test. The review recommends:

- End-to-end workflow tests
- Artifact verification tests
- Error message quality tests

### What to Do

Add the following test files:

#### 12a. End-to-End Workflow (`tests/integration/test_end_to_end.py`)

If this file already exists with some tests, add more. If it has tests that require `pydantic-monty` at runtime, mark them appropriately.

```python
import pytest
from pathlib import Path

def test_load_check_run_workflow(tmp_path):
    """Full workflow: load a .pym file, check it, and run it."""
    # 1. Write a .pym file to tmp_path
    # 2. Call grail.load() with appropriate externals
    # 3. Call script.check() — should pass
    # 4. Call script.run() with inputs — should return a result
    # 5. Verify the result is correct


def test_load_produces_artifacts(tmp_path):
    """Loading a script should produce .grail/ artifacts."""
    # 1. Load a .pym file with grail_dir set
    # 2. Check that .grail/{name}/stubs.pyi exists
    # 3. Check that .grail/{name}/monty_code.py exists
    # 4. Check that .grail/{name}/check.json exists
    # 5. Verify the content of each artifact is reasonable
```

#### 12b. Artifact Content Verification (`tests/integration/test_artifacts_verify.py`)

```python
def test_stubs_artifact_matches_generated_stubs(tmp_path):
    """The stubs.pyi artifact should match what generate_stubs() produces."""
    # Load a .pym with known externals and inputs
    # Read .grail/{name}/stubs.pyi
    # Call generate_stubs() directly with the same externals/inputs
    # Compare the two outputs


def test_monty_code_artifact_is_valid_python(tmp_path):
    """The monty_code.py artifact should be parseable Python."""
    import ast
    # Load a .pym file
    # Read .grail/{name}/monty_code.py
    # ast.parse() should not raise
```

#### 12c. Error Message Quality (`tests/integration/test_error_quality.py`)

```python
def test_check_error_includes_line_number():
    """Check errors should include the line number of the problem."""
    from grail.parser import parse_pym_content
    from grail.checker import check_pym

    content = '''\
from grail import external

class Forbidden:
    pass
'''
    parsed = parse_pym_content(content)
    result = check_pym(parsed, filename="test.pym")
    assert not result.valid
    assert result.errors[0].lineno == 3


def test_check_warning_includes_suggestion():
    """Checker warnings should include actionable suggestions."""
    # Create a .pym with a known warning trigger
    # Verify the warning message includes a suggestion field
```

### Tests to Validate

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run all tests to confirm nothing is broken
pytest tests/ -v
```

**Done when:** At least 5 new integration tests pass, covering the load-check-run workflow, artifact contents, and error message quality.
