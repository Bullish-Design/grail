# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 13: Snapshot - Pause/Resume Wrapper

**Purpose**: Thin wrapper over Monty's snapshot mechanism for pause/resume execution.

### Work to be done

Create `src/grail/snapshot.py`:

```python
"""Snapshot wrapper for pause/resume execution."""
from typing import Any, Callable

try:
    import pydantic_monty
except ImportError:
    pydantic_monty = None

from grail._types import SourceMap


class Snapshot:
    """
    Wrapper around Monty's snapshot for pause/resume execution.

    Allows inspecting external function calls and resuming with results.
    """

    def __init__(
        self,
        monty_snapshot: Any,
        source_map: SourceMap,
        externals: dict[str, Callable]
    ):
        """
        Initialize snapshot wrapper.

        Args:
            monty_snapshot: Underlying Monty snapshot
            source_map: Line number mapping
            externals: External function implementations
        """
        self._monty_snapshot = monty_snapshot
        self._source_map = source_map
        self._externals = externals

    @property
    def function_name(self) -> str:
        """Name of the external function being called."""
        return self._monty_snapshot.function_name

    @property
    def args(self) -> tuple[Any, ...]:
        """Positional arguments for the function call."""
        return self._monty_snapshot.args

    @property
    def kwargs(self) -> dict[str, Any]:
        """Keyword arguments for the function call."""
        return self._monty_snapshot.kwargs

    @property
    def is_complete(self) -> bool:
        """Whether execution has finished."""
        return self._monty_snapshot.is_complete

    @property
    def call_id(self) -> int:
        """Unique identifier for this external call."""
        return getattr(self._monty_snapshot, "call_id", 0)

    @property
    def value(self) -> Any:
        """
        Final result value (only available when is_complete=True).

        Returns:
            Final script result

        Raises:
            RuntimeError: If execution not complete
        """
        if not self.is_complete:
            raise RuntimeError("Execution not complete")
        return self._monty_snapshot.value

    def resume(
        self,
        return_value: Any = None,
        exception: BaseException | None = None
    ) -> "Snapshot":
        """
        Resume execution with a return value or exception.

        Args:
            return_value: Value to return from external function
            exception: Exception to raise in Monty

        Returns:
            New Snapshot if more calls pending, or final result
        """
        if exception is not None:
            next_snapshot = self._monty_snapshot.resume(exception=exception)
        else:
            next_snapshot = self._monty_snapshot.resume(return_value=return_value)

        return Snapshot(next_snapshot, self._source_map, self._externals)

    def dump(self) -> bytes:
        """
        Serialize snapshot to bytes.

        Returns:
            Serialized snapshot data
        """
        return self._monty_snapshot.dump()

    @staticmethod
    def load(data: bytes, source_map: SourceMap, externals: dict[str, Callable]) -> "Snapshot":
        """
        Deserialize snapshot from bytes.

        Args:
            data: Serialized snapshot data
            source_map: Line number mapping
            externals: External function implementations

        Returns:
            Restored Snapshot instance
        """
        if pydantic_monty is None:
            raise RuntimeError("pydantic-monty not installed")

        monty_snapshot = pydantic_monty.MontySnapshot.load(data)
        return Snapshot(monty_snapshot, source_map, externals)
```

### Testing/Validation

Create `tests/unit/test_snapshot.py`:

```python
"""Test snapshot pause/resume functionality."""
import pytest

pytest.importorskip("pydantic_monty")

from pathlib import Path
from grail.script import load

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.mark.integration
def test_snapshot_basic_properties():
    """Should expose snapshot properties."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    async def double_impl(n: int) -> int:
        return n * 2

    snapshot = script.start(
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    # Should be paused on first external call
    assert snapshot.function_name == "double"
    assert snapshot.args == () or 5 in snapshot.args or snapshot.kwargs.get("n") == 5
    assert snapshot.is_complete is False


@pytest.mark.integration
def test_snapshot_resume():
    """Should resume execution with return value."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    async def double_impl(n: int) -> int:
        return n * 2

    snapshot = script.start(
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    # Resume with return value
    result_snapshot = snapshot.resume(return_value=10)

    # Should be complete now
    assert result_snapshot.is_complete is True
    assert result_snapshot.value == 10


@pytest.mark.integration
def test_snapshot_serialization():
    """Should serialize and deserialize snapshots."""
    script = load(FIXTURES_DIR / "simple.pym", grail_dir=None)

    async def double_impl(n: int) -> int:
        return n * 2

    snapshot = script.start(
        inputs={"x": 5},
        externals={"double": double_impl}
    )

    # Serialize
    data = snapshot.dump()
    assert isinstance(data, bytes)

    # Deserialize
    from grail.snapshot import Snapshot
    restored = Snapshot.load(data, script.source_map, {"double": double_impl})

    assert restored.function_name == snapshot.function_name
    assert restored.is_complete == snapshot.is_complete
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_snapshot.py -m integration` passes
- [ ] Snapshot properties are accessible
- [ ] Resume works correctly
- [ ] Serialization/deserialization works
