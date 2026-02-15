# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 3: Resource Limits Parser

### Work to be done

Create `src/grail/limits.py`:

```python
"""Resource limits parsing and presets."""
from typing import Any
import re

# Named presets (plain dicts)
STRICT: dict[str, Any] = {
    "max_memory": "8mb",
    "max_duration": "500ms",
    "max_recursion": 120,
}

DEFAULT: dict[str, Any] = {
    "max_memory": "16mb",
    "max_duration": "2s",
    "max_recursion": 200,
}

PERMISSIVE: dict[str, Any] = {
    "max_memory": "64mb",
    "max_duration": "5s",
    "max_recursion": 400,
}

def parse_memory_string(value: str) -> int:
    """
    Parse memory string to bytes.

    Examples:
        "16mb" -> 16777216
        "1gb" -> 1073741824
        "512kb" -> 524288

    Args:
        value: Memory string (e.g., "16mb", "1GB")

    Returns:
        Number of bytes

    Raises:
        ValueError: If format is invalid
    """
    value = value.lower().strip()

    # Match number and unit
    match = re.match(r'^(\d+(?:\.\d+)?)(kb|mb|gb)$', value)
    if not match:
        raise ValueError(f"Invalid memory format: {value}. Use format like '16mb', '1gb'")

    number, unit = match.groups()
    number = float(number)

    multipliers = {
        'kb': 1024,
        'mb': 1024 * 1024,
        'gb': 1024 * 1024 * 1024,
    }

    return int(number * multipliers[unit])

def parse_duration_string(value: str) -> float:
    """
    Parse duration string to seconds.

    Examples:
        "500ms" -> 0.5
        "2s" -> 2.0
        "1.5s" -> 1.5

    Args:
        value: Duration string (e.g., "500ms", "2s")

    Returns:
        Number of seconds

    Raises:
        ValueError: If format is invalid
    """
    value = value.lower().strip()

    # Match number and unit
    match = re.match(r'^(\d+(?:\.\d+)?)(ms|s)$', value)
    if not match:
        raise ValueError(f"Invalid duration format: {value}. Use format like '500ms', '2s'")

    number, unit = match.groups()
    number = float(number)

    if unit == 'ms':
        return number / 1000.0
    else:  # 's'
        return number

def parse_limits(limits: dict[str, Any]) -> dict[str, Any]:
    """
    Parse limits dict, converting string formats to native types.

    Args:
        limits: Raw limits dict (may contain string formats)

    Returns:
        Parsed limits dict with native types

    Examples:
        {"max_memory": "16mb"} -> {"max_memory": 16777216}
        {"max_duration": "2s"} -> {"max_duration": 2.0}
    """
    parsed = {}

    for key, value in limits.items():
        if key == "max_memory" and isinstance(value, str):
            parsed[key] = parse_memory_string(value)
        elif key == "max_duration" and isinstance(value, str):
            parsed[key] = parse_duration_string(value)
        else:
            parsed[key] = value

    return parsed

def merge_limits(base: dict[str, Any] | None, override: dict[str, Any] | None) -> dict[str, Any]:
    """
    Merge two limits dicts, with override taking precedence.

    Args:
        base: Base limits (e.g., from load())
        override: Override limits (e.g., from run())

    Returns:
        Merged limits dict
    """
    if base is None and override is None:
        return parse_limits(DEFAULT.copy())

    if base is None:
        return parse_limits(override.copy())

    if override is None:
        return parse_limits(base.copy())

    # Merge: override takes precedence
    merged = base.copy()
    merged.update(override)
    return parse_limits(merged)
```

### Testing/Validation

Create `tests/unit/test_limits.py`:

```python
"""Test resource limits parsing."""
import pytest
from grail.limits import (
    parse_memory_string, parse_duration_string,
    parse_limits, merge_limits,
    STRICT, DEFAULT, PERMISSIVE
)

def test_parse_memory_string():
    """Test memory string parsing."""
    assert parse_memory_string("16mb") == 16 * 1024 * 1024
    assert parse_memory_string("1gb") == 1 * 1024 * 1024 * 1024
    assert parse_memory_string("512kb") == 512 * 1024
    assert parse_memory_string("1MB") == 1 * 1024 * 1024  # case insensitive

def test_parse_duration_string():
    """Test duration string parsing."""
    assert parse_duration_string("500ms") == 0.5
    assert parse_duration_string("2s") == 2.0
    assert parse_duration_string("1.5s") == 1.5

def test_invalid_memory_format():
    """Invalid memory format should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid memory format"):
        parse_memory_string("16")

    with pytest.raises(ValueError):
        parse_memory_string("invalid")

def test_invalid_duration_format():
    """Invalid duration format should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid duration format"):
        parse_duration_string("2")

    with pytest.raises(ValueError):
        parse_duration_string("invalid")

def test_parse_limits():
    """Test parsing full limits dict."""
    raw = {
        "max_memory": "16mb",
        "max_duration": "2s",
        "max_recursion": 200,
    }
    parsed = parse_limits(raw)

    assert parsed["max_memory"] == 16 * 1024 * 1024
    assert parsed["max_duration"] == 2.0
    assert parsed["max_recursion"] == 200

def test_merge_limits():
    """Test merging limits dicts."""
    base = {"max_memory": "16mb", "max_recursion": 200}
    override = {"max_duration": "5s"}

    merged = merge_limits(base, override)

    assert merged["max_memory"] == 16 * 1024 * 1024
    assert merged["max_duration"] == 5.0
    assert merged["max_recursion"] == 200

def test_presets_are_dicts():
    """Presets should be plain dicts."""
    assert isinstance(STRICT, dict)
    assert isinstance(DEFAULT, dict)
    assert isinstance(PERMISSIVE, dict)

    assert STRICT["max_memory"] == "8mb"
    assert DEFAULT["max_memory"] == "16mb"
    assert PERMISSIVE["max_memory"] == "64mb"
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_limits.py` passes
- [ ] All string formats parse correctly
- [ ] Merging works as expected
- [ ] Presets are accessible
