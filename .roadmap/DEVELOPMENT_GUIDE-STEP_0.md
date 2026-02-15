# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 0: Grail Declarations (external & Input)

**Why this comes first**: The parser needs these to exist, and `.pym` files won't work in IDEs without them.

### Work to be done

1. **Create `src/grail/_external.py`**:

```python
"""External function decorator for .pym files."""
from typing import Any, Callable, TypeVar

F = TypeVar('F', bound=Callable[..., Any])

def external(func: F) -> F:
    """
    Decorator to mark a function as externally provided.

    This is a no-op at runtime - it exists purely for grail's parser
    to extract function signatures and generate type stubs.

    Usage:
        @external
        async def fetch_data(url: str) -> dict[str, Any]:
            '''Fetch data from URL.'''
            ...

    Requirements:
    - Function must have complete type annotations
    - Function body must be ... (Ellipsis)
    """
    # Store metadata on the function for introspection
    func.__grail_external__ = True
    return func
```

2. **Create `src/grail/_input.py`**:

```python
"""Input declaration for .pym files."""
from typing import TypeVar, overload, Any

T = TypeVar('T')

# Overloads for type checker to understand Input() properly
@overload
def Input(name: str) -> Any: ...

@overload
def Input(name: str, default: T) -> T: ...

def Input(name: str, default: Any = None) -> Any:
    """
    Declare an input variable that will be provided at runtime.

    This is a no-op at runtime - it exists for grail's parser to extract
    input declarations. At Monty runtime, these become actual variable bindings.

    Usage:
        budget_limit: float = Input("budget_limit")
        department: str = Input("department", default="Engineering")

    Requirements:
    - Must have a type annotation

    Args:
        name: The input variable name
        default: Optional default value if not provided at runtime

    Returns:
        The default value if provided, otherwise None (at parse time)
    """
    return default
```

3. **Create `src/grail/_types_stubs.pyi`** (type stubs for IDEs):

```python
"""Type stubs for grail declarations."""
from typing import TypeVar, Callable, Any, overload

F = TypeVar('F', bound=Callable[..., Any])
T = TypeVar('T')

def external(func: F) -> F:
    """Mark a function as externally provided."""
    ...

@overload
def Input(name: str) -> Any: ...

@overload
def Input(name: str, default: T) -> T: ...

def Input(name: str, default: Any = None) -> Any:
    """Declare an input variable."""
    ...
```

4. **Create `src/grail/py.typed`** (empty marker file for PEP 561)

### Testing/Validation

Create `tests/unit/test_declarations.py`:

```python
"""Test grail declarations (external, Input)."""
import pytest
from grail._external import external
from grail._input import Input

def test_external_decorator_is_noop():
    """External decorator should not modify function behavior."""
    @external
    def dummy(x: int) -> int:
        ...

    assert hasattr(dummy, '__grail_external__')
    assert dummy.__grail_external__ is True

def test_input_returns_default():
    """Input should return the default value."""
    result = Input("test_var", default="default_value")
    assert result == "default_value"

def test_input_without_default_returns_none():
    """Input without default should return None."""
    result = Input("test_var")
    assert result is None

def test_can_import_from_grail():
    """Should be able to import from grail package."""
    from grail._external import external
    from grail._input import Input

    assert external is not None
    assert Input is not None
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_declarations.py` passes
- [ ] Can import `from grail._external import external`
- [ ] Can import `from grail._input import Input`
- [ ] IDE recognizes these imports (no red squiggles)
