"""End-to-end integration tests."""

import pytest
from pathlib import Path
import tempfile

pytest.importorskip("pydantic_monty")

import grail


@pytest.mark.integration
async def test_full_workflow():
    """Test complete workflow: load -> check -> run."""
    # Create a temporary .pym file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pym", delete=False) as f:
        f.write("""
from grail import external, Input
from typing import Any

budget: float = Input("budget")
department: str = Input("department", default="Engineering")

@external
async def get_team_size(dept: str) -> int:
    '''Get team size for department.'''
    ...

@external
async def calculate_budget(size: int, per_person: float) -> float:
    '''Calculate total budget.'''
    ...

size = await get_team_size(department)
total = await calculate_budget(size, budget / 10)

{
    "department": department,
    "team_size": size,
    "total_budget": total,
    "over_budget": total > budget
}
""")
        pym_path = Path(f.name)

    try:
        # Load
        script = grail.load(pym_path, grail_dir=None)

        # Check
        check_result = script.check()
        assert check_result.valid is True

        # Run
        async def get_team_size_impl(dept: str) -> int:
            return 5

        async def calculate_budget_impl(size: int, per_person: float) -> float:
            return size * per_person

        result = await script.run(
            inputs={"budget": 1000.0, "department": "Engineering"},
            externals={
                "get_team_size": get_team_size_impl,
                "calculate_budget": calculate_budget_impl,
            },
        )

        assert result["department"] == "Engineering"
        assert result["team_size"] == 5
        assert result["total_budget"] == 500.0
        assert result["over_budget"] is False

    finally:
        pym_path.unlink()


@pytest.mark.integration
def test_inline_run():
    """Test grail.run() for inline code."""
    import asyncio

    result = asyncio.run(grail.run("x + y", inputs={"x": 1, "y": 2}))
    assert result == 3


@pytest.mark.integration
async def test_with_resource_limits():
    """Test execution with resource limits."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pym", delete=False) as f:
        f.write("""
from grail import Input

x: int = Input("x")

x * 2
""")
        pym_path = Path(f.name)

    try:
        script = grail.load(pym_path, limits=grail.STRICT, grail_dir=None)

        result = await script.run(inputs={"x": 5})
        assert result == 10

    finally:
        pym_path.unlink()


@pytest.mark.integration
async def test_pause_resume_workflow():
    """Test pause/resume execution pattern."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pym", delete=False) as f:
        f.write("""
from grail import external, Input

x: int = Input("x")

@external
async def add_one(n: int) -> int:
    ...

@external
async def double(n: int) -> int:
    ...

step1 = await add_one(x)
step2 = await double(step1)
step2
""")
        pym_path = Path(f.name)

    try:

        async def add_one_impl(n: int) -> int:
            return n + 1

        async def double_impl(n: int) -> int:
            return n * 2

        externals = {
            "add_one": add_one_impl,
            "double": double_impl,
        }

        script = grail.load(pym_path, grail_dir=None)
        snapshot = script.start(inputs={"x": 5}, externals=externals)

        # Execute pause/resume loop
        while not snapshot.is_complete:
            func_name = snapshot.function_name
            args = snapshot.args
            kwargs = snapshot.kwargs

            # Call the external function
            result = await externals[func_name](*args, **kwargs)
            snapshot = snapshot.resume(return_value=result)

        final_result = snapshot.value
        assert final_result == 12  # (5 + 1) * 2

    finally:
        pym_path.unlink()


@pytest.mark.integration
def test_error_handling():
    """Test that errors are properly caught and mapped."""
    import asyncio

    with tempfile.NamedTemporaryFile(mode="w", suffix=".pym", delete=False) as f:
        f.write("""
from grail import Input

x: int = Input("x")

y = undefined_variable
""")
        pym_path = Path(f.name)

    try:
        script = grail.load(pym_path, grail_dir=None)

        with pytest.raises(grail.ExecutionError):
            asyncio.run(script.run(inputs={"x": 5}))

    finally:
        pym_path.unlink()
