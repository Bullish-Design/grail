# Limits Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the entire `parse_limits`/`merge_limits`/`ResourceLimits` TypedDict system with a single frozen Pydantic `Limits` model that parses once at construction, validates input, and converts to Monty format via `.to_monty()`.

**Architecture:** A single `Limits` class (Pydantic `BaseModel`, frozen) becomes the only representation of resource limits throughout the system. User-facing string formats (`"16mb"`, `"2s"`) are accepted as constructor arguments and parsed via `field_validator(mode="before")`. The class exposes `.strict()`, `.default()`, `.permissive()` class methods for presets, a `.merge(overrides)` method for combining limits, and a `.to_monty()` method that produces the `dict` Monty's `run_monty_async()` expects. All other limits infrastructure (`parse_limits`, `merge_limits`, `ResourceLimits` TypedDict, module-level preset dicts) is deleted.

**Tech Stack:** Python 3.13, Pydantic v2 (already a dependency), pytest, pytest-asyncio

---

## Current State Summary

**Files involved:**

| File | Role |
|------|------|
| `src/grail/limits.py` (151 lines) | `parse_memory_string`, `parse_duration_string`, `parse_limits`, `merge_limits`, preset dicts `STRICT`/`DEFAULT`/`PERMISSIVE` |
| `src/grail/_types.py:96-104` | `ResourceLimits` TypedDict |
| `src/grail/script.py` | `GrailScript.__init__` stores `self.limits`, `_prepare_monty_limits()` calls `merge_limits`, `load()` calls `parse_limits`, `run()` accepts limits |
| `src/grail/__init__.py` | Exports `STRICT`, `DEFAULT`, `PERMISSIVE` |
| `src/grail/errors.py:113-118` | `LimitError` (unchanged by this refactor) |
| `src/grail/cli.py:13` | Imports `DEFAULT` (unused in practice) |
| `tests/unit/test_limits.py` (84 lines) | Tests for parse/merge/presets |
| `tests/unit/test_script.py:97-101` | `test_load_with_limits` |
| `tests/unit/test_public_api.py` | Asserts `STRICT`/`DEFAULT`/`PERMISSIVE` in public API |
| `tests/integration/test_end_to_end.py:162-182` | `test_with_resource_limits` uses `grail.STRICT` |

**Monty contract** (from `pydantic_monty.ResourceLimits`):
```python
class ResourceLimits(TypedDict, total=False):
    max_allocations: int
    max_duration_secs: float
    max_memory: int
    gc_interval: int
    max_recursion_depth: int
```
Monty's `run_monty_async(..., limits=dict)` accepts this dict. Omitted keys disable that limit.

**Known bugs in current code:**
1. Double-parsing: `load()` parses at line 406, `merge_limits()` re-parses at line 150
2. Catch-all `else` in `parse_limits()` silently accepts unknown/typo'd keys
3. `max_allocations`/`gc_interval` not explicitly handled (fall through catch-all)
4. Inconsistent types: `load()` accepts `dict[str, Any]`, `run()` accepts `ResourceLimits | dict[str, Any]`
5. Presets are raw dicts — no type safety, wrong key names until parsed

---

## Task 1: Create the `Limits` Pydantic Model with Tests

**Files:**
- Create: `tests/unit/test_limits.py` (full rewrite)
- Create: `src/grail/limits.py` (full rewrite)

### Step 1: Write failing tests for the new `Limits` model

Replace the entire contents of `tests/unit/test_limits.py` with:

```python
"""Test Limits model."""

import pytest
from pydantic import ValidationError

from grail.limits import Limits


# --- Construction & Parsing ---

class TestLimitsConstruction:
    """Test creating Limits instances with various input formats."""

    def test_create_with_string_memory(self):
        """String memory values should be parsed to bytes."""
        limits = Limits(max_memory="16mb")
        assert limits.max_memory == 16 * 1024 * 1024

    def test_create_with_string_memory_kb(self):
        limits = Limits(max_memory="512kb")
        assert limits.max_memory == 512 * 1024

    def test_create_with_string_memory_gb(self):
        limits = Limits(max_memory="1gb")
        assert limits.max_memory == 1024 * 1024 * 1024

    def test_create_with_string_memory_case_insensitive(self):
        limits = Limits(max_memory="16MB")
        assert limits.max_memory == 16 * 1024 * 1024

    def test_create_with_string_duration_ms(self):
        """String duration in ms should be parsed to seconds."""
        limits = Limits(max_duration="500ms")
        assert limits.max_duration == 0.5

    def test_create_with_string_duration_s(self):
        limits = Limits(max_duration="2s")
        assert limits.max_duration == 2.0

    def test_create_with_string_duration_fractional(self):
        limits = Limits(max_duration="1.5s")
        assert limits.max_duration == 1.5

    def test_create_with_int_recursion(self):
        limits = Limits(max_recursion=200)
        assert limits.max_recursion == 200

    def test_create_with_int_allocations(self):
        limits = Limits(max_allocations=10000)
        assert limits.max_allocations == 10000

    def test_create_with_int_gc_interval(self):
        limits = Limits(gc_interval=500)
        assert limits.gc_interval == 500

    def test_all_fields_none_by_default(self):
        """Omitted fields should be None."""
        limits = Limits()
        assert limits.max_memory is None
        assert limits.max_duration is None
        assert limits.max_recursion is None
        assert limits.max_allocations is None
        assert limits.gc_interval is None

    def test_create_with_all_fields(self):
        limits = Limits(
            max_memory="16mb",
            max_duration="2s",
            max_recursion=200,
            max_allocations=10000,
            gc_interval=500,
        )
        assert limits.max_memory == 16 * 1024 * 1024
        assert limits.max_duration == 2.0
        assert limits.max_recursion == 200
        assert limits.max_allocations == 10000
        assert limits.gc_interval == 500


# --- Validation & Errors ---

class TestLimitsValidation:
    """Test that invalid inputs are rejected."""

    def test_invalid_memory_format(self):
        with pytest.raises(ValidationError):
            Limits(max_memory="16")

    def test_invalid_memory_string(self):
        with pytest.raises(ValidationError):
            Limits(max_memory="not_a_size")

    def test_invalid_duration_format(self):
        with pytest.raises(ValidationError):
            Limits(max_duration="2")

    def test_invalid_duration_string(self):
        with pytest.raises(ValidationError):
            Limits(max_duration="not_a_duration")

    def test_unknown_field_rejected(self):
        """Unknown fields should raise ValidationError, not silently pass through."""
        with pytest.raises(ValidationError):
            Limits(max_mmeory="16mb")  # typo

    def test_frozen(self):
        """Limits should be immutable after creation."""
        limits = Limits(max_memory="16mb")
        with pytest.raises(ValidationError):
            limits.max_memory = 0


# --- Presets ---

class TestLimitsPresets:
    """Test preset class methods."""

    def test_strict_preset(self):
        limits = Limits.strict()
        assert limits.max_memory == 8 * 1024 * 1024
        assert limits.max_duration == 0.5
        assert limits.max_recursion == 120

    def test_default_preset(self):
        limits = Limits.default()
        assert limits.max_memory == 16 * 1024 * 1024
        assert limits.max_duration == 2.0
        assert limits.max_recursion == 200

    def test_permissive_preset(self):
        limits = Limits.permissive()
        assert limits.max_memory == 64 * 1024 * 1024
        assert limits.max_duration == 5.0
        assert limits.max_recursion == 400

    def test_presets_return_limits_instances(self):
        assert isinstance(Limits.strict(), Limits)
        assert isinstance(Limits.default(), Limits)
        assert isinstance(Limits.permissive(), Limits)


# --- Merging ---

class TestLimitsMerge:
    """Test merging two Limits instances."""

    def test_merge_override_takes_precedence(self):
        base = Limits(max_memory="16mb", max_recursion=200)
        override = Limits(max_memory="32mb")
        merged = base.merge(override)

        assert merged.max_memory == 32 * 1024 * 1024
        assert merged.max_recursion == 200

    def test_merge_preserves_base_when_override_is_none(self):
        base = Limits(max_memory="16mb", max_duration="2s")
        override = Limits()  # all None
        merged = base.merge(override)

        assert merged.max_memory == 16 * 1024 * 1024
        assert merged.max_duration == 2.0

    def test_merge_returns_new_instance(self):
        base = Limits(max_memory="16mb")
        override = Limits(max_duration="5s")
        merged = base.merge(override)

        assert merged is not base
        assert merged is not override
        assert merged.max_memory == 16 * 1024 * 1024
        assert merged.max_duration == 5.0

    def test_merge_all_fields(self):
        base = Limits(max_memory="16mb", max_duration="2s", max_recursion=200,
                      max_allocations=10000, gc_interval=500)
        override = Limits(max_memory="32mb", max_allocations=20000)
        merged = base.merge(override)

        assert merged.max_memory == 32 * 1024 * 1024
        assert merged.max_duration == 2.0
        assert merged.max_recursion == 200
        assert merged.max_allocations == 20000
        assert merged.gc_interval == 500


# --- Monty Conversion ---

class TestLimitsToMonty:
    """Test conversion to Monty-native dict format."""

    def test_to_monty_renames_keys(self):
        limits = Limits(max_memory="16mb", max_duration="2s", max_recursion=200)
        monty = limits.to_monty()

        assert monty == {
            "max_memory": 16 * 1024 * 1024,
            "max_duration_secs": 2.0,
            "max_recursion_depth": 200,
        }

    def test_to_monty_omits_none_fields(self):
        limits = Limits(max_memory="16mb")
        monty = limits.to_monty()

        assert monty == {"max_memory": 16 * 1024 * 1024}
        assert "max_duration_secs" not in monty
        assert "max_recursion_depth" not in monty

    def test_to_monty_all_fields(self):
        limits = Limits(
            max_memory="16mb",
            max_duration="2s",
            max_recursion=200,
            max_allocations=10000,
            gc_interval=500,
        )
        monty = limits.to_monty()

        assert monty == {
            "max_memory": 16 * 1024 * 1024,
            "max_duration_secs": 2.0,
            "max_recursion_depth": 200,
            "max_allocations": 10000,
            "gc_interval": 500,
        }

    def test_to_monty_empty_limits(self):
        limits = Limits()
        monty = limits.to_monty()

        assert monty == {}


# --- String Parsing Functions (preserved as internal helpers) ---

class TestParseMemoryString:
    """Test the memory string parser (used by Limits internally)."""

    def test_megabytes(self):
        from grail.limits import parse_memory_string
        assert parse_memory_string("16mb") == 16 * 1024 * 1024

    def test_gigabytes(self):
        from grail.limits import parse_memory_string
        assert parse_memory_string("1gb") == 1024 * 1024 * 1024

    def test_kilobytes(self):
        from grail.limits import parse_memory_string
        assert parse_memory_string("512kb") == 512 * 1024

    def test_case_insensitive(self):
        from grail.limits import parse_memory_string
        assert parse_memory_string("1MB") == 1024 * 1024

    def test_invalid_raises(self):
        from grail.limits import parse_memory_string
        with pytest.raises(ValueError, match="Invalid memory format"):
            parse_memory_string("16")


class TestParseDurationString:
    """Test the duration string parser (used by Limits internally)."""

    def test_milliseconds(self):
        from grail.limits import parse_duration_string
        assert parse_duration_string("500ms") == 0.5

    def test_seconds(self):
        from grail.limits import parse_duration_string
        assert parse_duration_string("2s") == 2.0

    def test_fractional_seconds(self):
        from grail.limits import parse_duration_string
        assert parse_duration_string("1.5s") == 1.5

    def test_invalid_raises(self):
        from grail.limits import parse_duration_string
        with pytest.raises(ValueError, match="Invalid duration format"):
            parse_duration_string("2")
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/unit/test_limits.py -v`
Expected: FAIL — `Limits` class does not exist yet; `parse_limits`, `merge_limits`, `STRICT`, etc. still exist but tests no longer import them.

### Step 3: Implement the `Limits` model

Replace the entire contents of `src/grail/limits.py` with:

```python
"""Resource limits for script execution."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def parse_memory_string(value: str) -> int:
    """
    Parse memory string to bytes.

    Examples:
        "16mb" -> 16777216
        "1gb"  -> 1073741824
        "512kb" -> 524288

    Raises:
        ValueError: If format is invalid.
    """
    value = value.lower().strip()
    match = re.match(r"^(\d+(?:\.\d+)?)(kb|mb|gb)$", value)
    if not match:
        raise ValueError(f"Invalid memory format: {value}. Use format like '16mb', '1gb'")

    number, unit = match.groups()
    multipliers = {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}
    return int(float(number) * multipliers[unit])


def parse_duration_string(value: str) -> float:
    """
    Parse duration string to seconds.

    Examples:
        "500ms" -> 0.5
        "2s"    -> 2.0

    Raises:
        ValueError: If format is invalid.
    """
    value = value.lower().strip()
    match = re.match(r"^(\d+(?:\.\d+)?)(ms|s)$", value)
    if not match:
        raise ValueError(f"Invalid duration format: {value}. Use format like '500ms', '2s'")

    number, unit = match.groups()
    number = float(number)
    return number / 1000.0 if unit == "ms" else number


class Limits(BaseModel, frozen=True):
    """
    Resource limits for script execution.

    All fields are optional. Omit a field (or pass None) to leave that
    limit unconstrained.

    Memory and duration accept human-readable strings:
        Limits(max_memory="16mb", max_duration="2s")

    Use presets for common configurations:
        Limits.strict()
        Limits.default()
        Limits.permissive()
    """

    model_config = ConfigDict(extra="forbid")

    max_memory: int | None = None
    """Maximum heap memory in bytes. Accepts strings like '16mb', '1gb'."""

    max_duration: float | None = None
    """Maximum execution time in seconds. Accepts strings like '500ms', '2s'."""

    max_recursion: int | None = None
    """Maximum function call stack depth."""

    max_allocations: int | None = None
    """Maximum number of heap allocations allowed."""

    gc_interval: int | None = None
    """Run garbage collection every N allocations."""

    @field_validator("max_memory", mode="before")
    @classmethod
    def _parse_memory(cls, v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, str):
            return parse_memory_string(v)
        return v

    @field_validator("max_duration", mode="before")
    @classmethod
    def _parse_duration(cls, v: Any) -> float | None:
        if v is None:
            return None
        if isinstance(v, str):
            return parse_duration_string(v)
        return v

    # --- Presets ---

    @classmethod
    def strict(cls) -> Limits:
        """Tight limits for untrusted code."""
        return cls(max_memory="8mb", max_duration="500ms", max_recursion=120)

    @classmethod
    def default(cls) -> Limits:
        """Balanced defaults for typical scripts."""
        return cls(max_memory="16mb", max_duration="2s", max_recursion=200)

    @classmethod
    def permissive(cls) -> Limits:
        """Relaxed limits for trusted or heavy workloads."""
        return cls(max_memory="64mb", max_duration="5s", max_recursion=400)

    # --- Merging ---

    def merge(self, overrides: Limits) -> Limits:
        """
        Return a new Limits with override values taking precedence.

        Only non-None fields in `overrides` replace the base values.
        """
        return Limits(
            max_memory=overrides.max_memory if overrides.max_memory is not None else self.max_memory,
            max_duration=overrides.max_duration if overrides.max_duration is not None else self.max_duration,
            max_recursion=overrides.max_recursion if overrides.max_recursion is not None else self.max_recursion,
            max_allocations=overrides.max_allocations if overrides.max_allocations is not None else self.max_allocations,
            gc_interval=overrides.gc_interval if overrides.gc_interval is not None else self.gc_interval,
        )

    # --- Monty Conversion ---

    def to_monty(self) -> dict[str, Any]:
        """
        Convert to the dict format expected by ``pydantic_monty.run_monty_async()``.

        Key renames:
            max_duration  -> max_duration_secs
            max_recursion -> max_recursion_depth
        """
        mapping: list[tuple[str, str]] = [
            ("max_memory", "max_memory"),
            ("max_duration", "max_duration_secs"),
            ("max_recursion", "max_recursion_depth"),
            ("max_allocations", "max_allocations"),
            ("gc_interval", "gc_interval"),
        ]
        result: dict[str, Any] = {}
        for attr, monty_key in mapping:
            value = getattr(self, attr)
            if value is not None:
                result[monty_key] = value
        return result
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/unit/test_limits.py -v`
Expected: ALL PASS

### Step 5: Commit

```bash
git add src/grail/limits.py tests/unit/test_limits.py
git commit -m "refactor: replace limits system with frozen Pydantic Limits model"
```

---

## Task 2: Remove `ResourceLimits` TypedDict from `_types.py`

**Files:**
- Modify: `src/grail/_types.py:96-104` (delete `ResourceLimits`)
- Modify: `tests/unit/test_types.py` (no changes needed — it doesn't test `ResourceLimits`)

### Step 1: Verify no other file imports `ResourceLimits` from `_types.py`

Run: `rg "from grail._types import.*ResourceLimits" src/`
Expected output (these are the files we'll fix in later tasks):
- `src/grail/script.py`

The old `limits.py` used to import it, but Task 1 already rewrote `limits.py`.

### Step 2: Delete the `ResourceLimits` TypedDict

In `src/grail/_types.py`, delete lines 96-103 (the entire `ResourceLimits` class and its fields). Also remove `TypedDict` from the `typing` import on line 7 if it's no longer used.

After editing, `_types.py` line 7 should read:
```python
from typing import Any, Literal
```

And lines 94+ should just be the end of `CheckResult` followed by end-of-file.

### Step 3: Run tests to verify nothing breaks

Run: `pytest tests/unit/test_types.py -v`
Expected: ALL PASS (these tests never tested `ResourceLimits`)

Run: `pytest tests/unit/test_limits.py -v`
Expected: ALL PASS (new tests don't reference `ResourceLimits`)

Note: `test_script.py` will fail at this point because `script.py` still imports `ResourceLimits`. That's expected and fixed in Task 3.

### Step 4: Commit

```bash
git add src/grail/_types.py
git commit -m "refactor: remove ResourceLimits TypedDict from _types.py"
```

---

## Task 3: Update `script.py` to Use `Limits`

This is the largest task. Every limits-related line in `script.py` changes.

**Files:**
- Modify: `src/grail/script.py`
- Modify: `tests/unit/test_script.py`

### Step 1: Write the updated test for `test_load_with_limits`

In `tests/unit/test_script.py`, replace lines 97-101:

**Before:**
```python
def test_load_with_limits():
    """Should accept limits parameter."""
    script = load(FIXTURES_DIR / "simple.pym", limits={"max_memory": "8mb"}, grail_dir=None)

    assert script.limits == {"max_memory": 8388608}
```

**After:**
```python
def test_load_with_limits():
    """Should accept Limits parameter."""
    from grail.limits import Limits

    script = load(
        FIXTURES_DIR / "simple.pym",
        limits=Limits(max_memory="8mb"),
        grail_dir=None,
    )

    assert isinstance(script.limits, Limits)
    assert script.limits.max_memory == 8 * 1024 * 1024
```

### Step 2: Run the test to verify it fails

Run: `pytest tests/unit/test_script.py::test_load_with_limits -v`
Expected: FAIL — `load()` still accepts `dict[str, Any]`

### Step 3: Update `script.py`

Apply these changes to `src/grail/script.py`:

**3a. Update imports (line 14 and 20):**

Replace:
```python
from grail._types import ExternalSpec, InputSpec, CheckResult, SourceMap, ResourceLimits
```
With:
```python
from grail._types import ExternalSpec, InputSpec, CheckResult, SourceMap
```

Replace:
```python
from grail.limits import merge_limits, parse_limits
```
With:
```python
from grail.limits import Limits
```

**3b. Update `GrailScript.__init__` (line 44):**

Replace:
```python
        limits: ResourceLimits | None = None,
```
With:
```python
        limits: Limits | None = None,
```

**3c. Update `_prepare_monty_limits` (lines 141-153):**

Replace the entire method:
```python
    def _prepare_monty_limits(
        self, override_limits: ResourceLimits | dict[str, Any] | None
    ) -> ResourceLimits:
        """
        Merge and parse limits for Monty.

        Args:
            override_limits: Runtime limit overrides

        Returns:
            Parsed limits dict ready for Monty
        """
        return merge_limits(self.limits, override_limits)
```

With:
```python
    def _prepare_monty_limits(self, override_limits: Limits | None) -> dict[str, Any]:
        """
        Merge load-time and run-time limits into a Monty-native dict.

        Falls back to Limits.default() if no limits are provided anywhere.
        """
        base = self.limits
        if base is None and override_limits is None:
            return Limits.default().to_monty()
        if base is None:
            return override_limits.to_monty()
        if override_limits is None:
            return base.to_monty()
        return base.merge(override_limits).to_monty()
```

**3d. Update `run()` signature (line 224):**

Replace:
```python
        limits: ResourceLimits | dict[str, Any] | None = None,
```
With:
```python
        limits: Limits | None = None,
```

**3e. Update `load()` function (lines 351-409):**

Replace the signature and the `limits` argument in the constructor call:

Replace:
```python
def load(
    path: str | Path,
    limits: dict[str, Any] | None = None,
    files: dict[str, str | bytes] | None = None,
    grail_dir: str | Path | None = ".grail",
) -> GrailScript:
```
With:
```python
def load(
    path: str | Path,
    limits: Limits | None = None,
    files: dict[str, str | bytes] | None = None,
    grail_dir: str | Path | None = ".grail",
) -> GrailScript:
```

Replace line 406:
```python
        limits=parse_limits(cast(dict[str, Any], limits)) if limits else None,
```
With:
```python
        limits=limits,
```

**3f. Remove unused imports:**

Remove `cast` from the `typing` import on line 5 (keep `Any` and `Callable`):
```python
from typing import Any, Callable
```

### Step 4: Run all script tests

Run: `pytest tests/unit/test_script.py -v`
Expected: ALL PASS

### Step 5: Run the full limits test suite too

Run: `pytest tests/unit/test_limits.py tests/unit/test_script.py -v`
Expected: ALL PASS

### Step 6: Commit

```bash
git add src/grail/script.py tests/unit/test_script.py
git commit -m "refactor: update script.py to use Limits model instead of raw dicts"
```

---

## Task 4: Update Public API Exports (`__init__.py`)

**Files:**
- Modify: `src/grail/__init__.py`
- Modify: `tests/unit/test_public_api.py`

### Step 1: Update the test first

In `tests/unit/test_public_api.py`:

**Replace** the `"STRICT"`, `"DEFAULT"`, `"PERMISSIVE"` entries in `expected` set (lines 17-18) with `"Limits"`:

```python
    expected = {
        # Core
        "load",
        "run",
        # Declarations
        "external",
        "Input",
        # Limits
        "Limits",
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
```

**Update** the `test_can_import_all` function — replace the preset imports with `Limits`:

```python
def test_can_import_all():
    """Should be able to import all public symbols."""
    from grail import (
        load,
        run,
        external,
        Input,
        Limits,
        GrailError,
        ParseError,
        CheckError,
        InputError,
        ExternalError,
        ExecutionError,
        LimitError,
        OutputError,
        CheckResult,
        CheckMessage,
    )

    assert load is not None
    assert run is not None
```

**Update** the `test_all_list` function to check for `>= 14` (was 15, now one fewer since 3 presets became 1 class):

```python
def test_all_list():
    """Should have __all__ list."""
    assert hasattr(grail, "__all__")
    assert isinstance(grail.__all__, list)
    assert len(grail.__all__) >= 14
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/unit/test_public_api.py -v`
Expected: FAIL — `Limits` not exported yet, `STRICT`/`DEFAULT`/`PERMISSIVE` still exported

### Step 3: Update `__init__.py`

Replace lines 17-17:
```python
from grail.limits import STRICT, DEFAULT, PERMISSIVE
```
With:
```python
from grail.limits import Limits
```

Replace the `__all__` list (lines 35-58):
```python
__all__ = [
    # Core
    "load",
    "run",
    # Declarations
    "external",
    "Input",
    # Limits
    "Limits",
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

### Step 4: Run tests

Run: `pytest tests/unit/test_public_api.py -v`
Expected: ALL PASS

### Step 5: Commit

```bash
git add src/grail/__init__.py tests/unit/test_public_api.py
git commit -m "refactor: export Limits class instead of preset dicts in public API"
```

---

## Task 5: Update Integration Tests

**Files:**
- Modify: `tests/integration/test_end_to_end.py`

### Step 1: Update `test_with_resource_limits`

In `tests/integration/test_end_to_end.py`, replace lines 162-182:

**Before:**
```python
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
```

**After:**
```python
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
        script = grail.load(pym_path, limits=grail.Limits.strict(), grail_dir=None)

        result = await script.run(inputs={"x": 5})
        assert result == 10

    finally:
        pym_path.unlink()
```

The only change is `limits=grail.STRICT` -> `limits=grail.Limits.strict()`.

### Step 2: Run integration tests

Run: `pytest tests/integration/test_end_to_end.py -v`
Expected: ALL PASS

### Step 3: Commit

```bash
git add tests/integration/test_end_to_end.py
git commit -m "refactor: update integration tests to use Limits.strict()"
```

---

## Task 6: Update CLI

**Files:**
- Modify: `src/grail/cli.py`

### Step 1: Remove unused `DEFAULT` import

In `src/grail/cli.py`, line 13:

**Before:**
```python
from grail.limits import DEFAULT
```

**After:**
```python
from grail.limits import Limits
```

Note: `DEFAULT` is imported but never actually used in any CLI command. The import of `Limits` is for future use and to verify the import works. If you prefer, you can simply delete the line entirely. But keeping `Limits` imported is forward-looking for when CLI limits support is added.

### Step 2: Run CLI-related tests (if any)

Run: `pytest tests/ -v -k "cli"`
Expected: PASS (or no tests collected — CLI tests may not exist yet)

### Step 3: Run the full test suite

Run: `pytest tests/ -v`
Expected: ALL PASS

### Step 4: Commit

```bash
git add src/grail/cli.py
git commit -m "refactor: update CLI to import Limits instead of DEFAULT"
```

---

## Task 7: Final Verification

### Step 1: Run the full test suite

Run: `pytest tests/ -v`
Expected: ALL PASS (107+ tests)

### Step 2: Run type checking

Run: `ruff check src/ tests/`
Expected: No errors

### Step 3: Verify no stale references remain

Run these searches — each should return zero results:

```bash
rg "ResourceLimits" src/ tests/
rg "parse_limits" src/ tests/
rg "merge_limits" src/ tests/
rg "from grail.limits import.*STRICT" src/ tests/
rg "from grail.limits import.*DEFAULT" src/ tests/
rg "from grail.limits import.*PERMISSIVE" src/ tests/
rg "grail\.STRICT" src/ tests/
rg "grail\.DEFAULT" src/ tests/
rg "grail\.PERMISSIVE" src/ tests/
```

If any stale references are found, fix them before proceeding.

### Step 4: Commit (if any fixes were needed)

```bash
git add -A
git commit -m "refactor: clean up stale limits references"
```

---

## Summary of Changes

| File | Action | Description |
|------|--------|-------------|
| `src/grail/limits.py` | **Rewrite** | `Limits` Pydantic model replaces `parse_limits`, `merge_limits`, preset dicts |
| `src/grail/_types.py` | **Edit** | Delete `ResourceLimits` TypedDict |
| `src/grail/script.py` | **Edit** | Use `Limits` type everywhere, remove `cast`/`parse_limits` imports |
| `src/grail/__init__.py` | **Edit** | Export `Limits` instead of `STRICT`/`DEFAULT`/`PERMISSIVE` |
| `src/grail/cli.py` | **Edit** | Import `Limits` instead of `DEFAULT` |
| `tests/unit/test_limits.py` | **Rewrite** | Comprehensive tests for `Limits` model |
| `tests/unit/test_script.py` | **Edit** | `test_load_with_limits` uses `Limits()` |
| `tests/unit/test_public_api.py` | **Edit** | Assert `Limits` exported, not preset dicts |
| `tests/integration/test_end_to_end.py` | **Edit** | `grail.STRICT` -> `grail.Limits.strict()` |

**Deleted concepts:** `ResourceLimits` TypedDict, `parse_limits()`, `merge_limits()`, `STRICT`/`DEFAULT`/`PERMISSIVE` module-level dicts

**New concept:** `Limits` — single frozen Pydantic model that owns parsing, validation, merging, and Monty conversion

**Bugs fixed:**
1. Double-parsing (parsing happens once, at `Limits()` construction)
2. Unknown keys silently accepted (Pydantic `extra="forbid"`)
3. `max_allocations`/`gc_interval` not handled (explicit fields now)
4. Inconsistent types across the API (everything is `Limits | None`)
5. Presets using wrong key names (presets are `Limits` instances)
