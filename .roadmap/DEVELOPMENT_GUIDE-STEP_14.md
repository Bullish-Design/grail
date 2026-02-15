# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 14: Public API - __init__.py Exports

**Purpose**: Define the public API surface (~15 symbols).

### Work to be done

Create `src/grail/__init__.py`:

```python
"""
Grail - Transparent Python for Monty.

A minimalist library for writing Monty code with full IDE support.
"""

__version__ = "2.0.0"

# Core functions
from grail.script import load, run

# Declarations (for .pym files)
from grail._external import external
from grail._input import Input

# Snapshot
from grail.snapshot import Snapshot

# Limits presets
from grail.limits import STRICT, DEFAULT, PERMISSIVE

# Errors
from grail.errors import (
    GrailError,
    ParseError,
    CheckError,
    InputError,
    ExternalError,
    ExecutionError,
    LimitError,
    OutputError,
)

# Check result types
from grail._types import CheckResult, CheckMessage

# Define public API
__all__ = [
    # Core
    "load",
    "run",
    # Declarations
    "external",
    "Input",
    # Snapshot
    "Snapshot",
    # Limits
    "STRICT",
    "DEFAULT",
    "PERMISSIVE",
    # Errors
    "GrailError",
    "ParseError",
    "CheckError",
    "InputError",
    "ExternalError",
    "ExecutionError",
    "LimitError",
    "OutputError",
    # Check results
    "CheckResult",
    "CheckMessage",
]
```

### Testing/Validation

Create `tests/unit/test_public_api.py`:

```python
"""Test public API surface."""
import grail


def test_public_api_symbols():
    """Verify all public symbols are exported."""
    expected = {
        # Core
        "load",
        "run",
        # Declarations
        "external",
        "Input",
        # Snapshot
        "Snapshot",
        # Limits
        "STRICT",
        "DEFAULT",
        "PERMISSIVE",
        # Errors
        "GrailError",
        "ParseError",
        "CheckError",
        "InputError",
        "ExternalError",
        "ExecutionError",
        "LimitError",
        "OutputError",
        # Check results
        "CheckResult",
        "CheckMessage",
    }

    for symbol in expected:
        assert hasattr(grail, symbol), f"Missing public symbol: {symbol}"


def test_version_exists():
    """Should have __version__ attribute."""
    assert hasattr(grail, "__version__")
    assert isinstance(grail.__version__, str)


def test_all_list():
    """Should have __all__ list."""
    assert hasattr(grail, "__all__")
    assert isinstance(grail.__all__, list)
    assert len(grail.__all__) >= 15


def test_can_import_all():
    """Should be able to import all public symbols."""
    from grail import (
        load, run, external, Input, Snapshot,
        STRICT, DEFAULT, PERMISSIVE,
        GrailError, ParseError, CheckError, InputError,
        ExternalError, ExecutionError, LimitError, OutputError,
        CheckResult, CheckMessage
    )

    assert load is not None
    assert run is not None
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_public_api.py` passes
- [ ] All 15+ public symbols are exported
- [ ] __version__ is defined
- [ ] __all__ list is correct
