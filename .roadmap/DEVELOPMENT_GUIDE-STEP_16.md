# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 16: Final Validation

**Purpose**: Ensure everything works together and the library is ready to ship.

### Work to be done

1. **Run all tests**:

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -m integration -v

# All tests
pytest tests/ -v
```

2. **Run linters and formatters**:

```bash
# Format code
ruff format src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/grail/
```

3. **Test CLI commands**:

```bash
# Install in development mode
pip install -e .

# Test CLI
grail --help
grail init
grail check
grail clean
```

6. **Create comprehensive example**:

Create `examples/expense_analysis/`:

```
examples/expense_analysis/
├── analysis.pym          # The Monty script
├── host.py              # Host implementation
├── data.py              # Mock data/external functions
└── README.md            # Usage instructions
```

**`examples/expense_analysis/analysis.pym`**:
```python
from grail import external, Input
from typing import Any

# Inputs
budget_limit: float = Input("budget_limit")
department: str = Input("department", default="Engineering")

# External functions
@external
async def get_team_members(department: str) -> dict[str, Any]:
    """Get list of team members for a department."""
    ...

@external
async def get_expenses(user_id: int) -> dict[str, Any]:
    """Get expense line items for a user."""
    ...

@external
async def get_custom_budget(user_id: int) -> dict[str, Any] | None:
    """Get custom budget for a user if they have one."""
    ...

# Analysis logic
team_data = await get_team_members(department=department)
members = team_data.get("members", [])

over_budget = []

for member in members:
    uid = member["id"]
    expenses = await get_expenses(user_id=uid)
    items = expenses.get("items", [])

    total = sum(item["amount"] for item in items)

    if total > budget_limit:
        custom = await get_custom_budget(user_id=uid)
        if custom is None or total > custom.get("limit", budget_limit):
            over_budget.append({
                "user_id": uid,
                "name": member["name"],
                "total": total,
                "over_by": total - budget_limit
            })

{
    "analyzed": len(members),
    "over_budget_count": len(over_budget),
    "details": over_budget,
}
```

**`examples/expense_analysis/host.py`**:
```python
"""Host file for expense analysis example."""
import asyncio
from grail import load
from data import get_team_members, get_expenses, get_custom_budget


async def main():
    # Load the script
    script = load("analysis.pym")

    # Check for errors
    check_result = script.check()
    if not check_result.valid:
        print("Script has errors:")
        for error in check_result.errors:
            print(f"  Line {error.lineno}: {error.message}")
        return

    # Run the analysis
    result = await script.run(
        inputs={
            "budget_limit": 5000.0,
            "department": "Engineering"
        },
        externals={
            "get_team_members": get_team_members,
            "get_expenses": get_expenses,
            "get_custom_budget": get_custom_budget,
        },
    )

    print(f"Analyzed {result['analyzed']} team members")
    print(f"Found {result['over_budget_count']} over budget")

    if result['details']:
        print("\nDetails:")
        for item in result['details']:
            print(f"  {item['name']}: ${item['total']:.2f} (over by ${item['over_by']:.2f})")


if __name__ == "__main__":
    asyncio.run(main())
```

**`examples/expense_analysis/data.py`**:
```python
"""Mock data and external function implementations."""
from typing import Any


async def get_team_members(department: str) -> dict[str, Any]:
    """Mock implementation of get_team_members."""
    return {
        "members": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"},
        ]
    }


async def get_expenses(user_id: int) -> dict[str, Any]:
    """Mock implementation of get_expenses."""
    expenses = {
        1: [{"amount": 3000}, {"amount": 2500}],
        2: [{"amount": 1000}],
        3: [{"amount": 4000}, {"amount": 2000}],
    }

    return {
        "items": expenses.get(user_id, [])
    }


async def get_custom_budget(user_id: int) -> dict[str, Any] | None:
    """Mock implementation of get_custom_budget."""
    # Alice has a custom budget
    if user_id == 1:
        return {"limit": 6000.0}
    return None
```

7. **Final test run**:

```bash
# Test the example
cd examples/expense_analysis
python host.py

# Should output:
# Analyzed 3 team members
# Found 1 over budget
#
# Details:
#   Charlie: $6000.00 (over by $1000.00)
```

### Validation Checklist

**Code Quality**:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] No linter errors
- [ ] No type checking errors
- [ ] Code coverage > 80%

**Functionality**:
- [ ] Can load .pym files
- [ ] Parser extracts externals and inputs correctly
- [ ] Checker validates Monty compatibility
- [ ] Stubs are generated correctly
- [ ] Code generation works
- [ ] Artifacts are created
- [ ] Monty integration works
- [ ] Error handling and mapping works
- [ ] Limits work correctly
- [ ] Snapshot pause/resume works

**CLI**:
- [ ] `grail init` works
- [ ] `grail check` works
- [ ] `grail run` works
- [ ] `grail clean` works
- [ ] `grail watch` works (if watchfiles installed)

**Public API**:
- [ ] All 15+ symbols are exported
- [ ] Documentation is complete
- [ ] Examples work correctly

**Distribution**:
- [ ] Package builds successfully
- [ ] Can install from wheel
- [ ] CLI entry point works after install
- [ ] Dependencies are correct

