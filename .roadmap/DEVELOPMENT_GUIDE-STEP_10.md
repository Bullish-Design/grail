# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 10: Monty Integration - Test Calling Monty Directly

**Critical step**: Before building the full API, verify we can successfully call Monty.

### Work to be done

Create `tests/integration/test_monty_integration.py`:

```python
"""Test direct integration with Monty."""
import pytest

# This requires pydantic-monty to be installed
pytest.importorskip("pydantic_monty")

import pydantic_monty


@pytest.mark.integration
def test_basic_monty_execution():
    """Test calling Monty with simple code."""
    code = "x = 1 + 2\nx"

    m = pydantic_monty.Monty(code)
    result = pydantic_monty.run_monty(m, inputs={})

    assert result == 3


@pytest.mark.integration
async def test_monty_with_external_function():
    """Test Monty with external functions."""
    code = """
result = await double(x)
result
"""

    stubs = """
x: int

async def double(n: int) -> int:
    ...
"""

    async def double_impl(n: int) -> int:
        return n * 2

    m = pydantic_monty.Monty(code, type_check_stubs=stubs)
    result = await pydantic_monty.run_monty_async(
        m,
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    assert result == 10


@pytest.mark.integration
def test_monty_with_resource_limits():
    """Test Monty with resource limits."""
    code = "x = 1\nx"

    m = pydantic_monty.Monty(
        code,
        max_memory=1024 * 1024,  # 1MB
        max_duration_secs=1.0,
        max_recursion_depth=100
    )

    result = pydantic_monty.run_monty(m, inputs={})
    assert result == 1


@pytest.mark.integration
def test_monty_type_checking():
    """Test Monty's type checker integration."""
    code = """
result = await get_data("test")
result
"""

    stubs = """
async def get_data(id: str) -> dict:
    ...
"""

    # This should type-check successfully
    m = pydantic_monty.Monty(code, type_check=True, type_check_stubs=stubs)

    # Note: Actual execution would need the external function


@pytest.mark.integration
async def test_monty_error_handling():
    """Test that Monty errors can be caught and inspected."""
    code = "x = undefined_variable"

    m = pydantic_monty.Monty(code)

    with pytest.raises(Exception) as exc_info:
        await pydantic_monty.run_monty_async(m, inputs={})

    # Should get some kind of error about undefined variable
    assert "undefined" in str(exc_info.value).lower() or "name" in str(exc_info.value).lower()
```

Create `tests/integration/conftest.py`:

```python
"""Configuration for integration tests."""
import pytest


def pytest_configure(config):
    """Add integration marker."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires pydantic-monty)"
    )
```

**Validation checklist**:
- [ ] `pytest tests/integration/test_monty_integration.py -m integration` passes
- [ ] Can execute simple Monty code
- [ ] Can call Monty with external functions
- [ ] Can pass resource limits to Monty
- [ ] Can handle Monty errors
- [ ] Type checking integration works

**Note**: These tests require `pydantic-monty` to be installed. If not available, tests will be skipped.

