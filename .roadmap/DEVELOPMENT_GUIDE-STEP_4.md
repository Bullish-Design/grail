# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 4: Test Fixtures - Create Reusable .pym Examples

**Why this comes before parser**: We need concrete examples to test the parser against.

### Work to be done

Create `tests/fixtures/` directory with example `.pym` files:

1. **`tests/fixtures/simple.pym`** - Basic valid .pym file:

```python
from grail import external, Input

x: int = Input("x")

@external
async def double(n: int) -> int:
    """Double a number."""
    ...

result = await double(x)
result
```

2. **`tests/fixtures/with_multiple_externals.pym`**:

```python
from grail import external, Input
from typing import Any

budget: float = Input("budget")
department: str = Input("department", default="Engineering")

@external
async def get_team(dept: str) -> dict[str, Any]:
    """Get team members."""
    ...

@external
async def get_expenses(user_id: int) -> dict[str, Any]:
    """Get expenses for user."""
    ...

team = await get_team(department)
members = team.get("members", [])

total = 0.0
for member in members:
    expenses = await get_expenses(member["id"])
    total += expenses.get("total", 0.0)

{
    "team_size": len(members),
    "total_expenses": total,
    "over_budget": total > budget
}
```

3. **`tests/fixtures/invalid_class.pym`** - For testing error detection:

```python
from grail import external

class MyClass:
    def __init__(self):
        self.value = 42
```

4. **`tests/fixtures/invalid_with.pym`** - For testing error detection:

```python
from grail import external

with open("file.txt") as f:
    content = f.read()
```

5. **`tests/fixtures/invalid_generator.pym`** - For testing error detection:

```python
from grail import external

def my_generator():
    yield 1
    yield 2
```

6. **`tests/fixtures/missing_annotation.pym`** - For testing CheckError:

```python
from grail import external

@external
def bad_func(x):  # Missing type annotation
    ...
```

7. **`tests/fixtures/non_ellipsis_body.pym`** - For testing CheckError:

```python
from grail import external

@external
def bad_func(x: int) -> int:
    return x * 2  # Should be ... not actual implementation
```

### Testing/Validation

Create `tests/fixtures/test_fixtures.py`:

```python
"""Verify test fixtures are valid Python."""
import ast
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent

def test_simple_pym_is_valid_python():
    """simple.pym should be syntactically valid Python."""
    content = (FIXTURES_DIR / "simple.pym").read_text()
    # Should not raise SyntaxError
    ast.parse(content)

def test_with_multiple_externals_is_valid():
    """with_multiple_externals.pym should be valid Python."""
    content = (FIXTURES_DIR / "with_multiple_externals.pym").read_text()
    ast.parse(content)

def test_invalid_fixtures_are_valid_python():
    """Invalid .pym files should still be valid Python syntax."""
    # They're invalid for Monty, but valid Python
    for name in ["invalid_class.pym", "invalid_with.pym", "invalid_generator.pym"]:
        content = (FIXTURES_DIR / name).read_text()
        ast.parse(content)  # Should not raise

def test_all_fixtures_exist():
    """All expected fixtures should exist."""
    expected = [
        "simple.pym",
        "with_multiple_externals.pym",
        "invalid_class.pym",
        "invalid_with.pym",
        "invalid_generator.pym",
        "missing_annotation.pym",
        "non_ellipsis_body.pym",
    ]

    for name in expected:
        path = FIXTURES_DIR / name
        assert path.exists(), f"Missing fixture: {name}"
```

**Validation checklist**:
- [ ] All fixture files created
- [ ] `pytest tests/fixtures/test_fixtures.py` passes
- [ ] All fixtures are valid Python (can be parsed with ast.parse())
