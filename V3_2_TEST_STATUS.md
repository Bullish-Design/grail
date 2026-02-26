# V3.2 Refactoring Status Report

## Executive Summary

We have implemented all of Phases 1-5 of the V3.2 refactoring plan. Phase 6 (tests) is partially complete but has some issues that need resolution. This report details what's been done, what's failing, and proposed solutions.

---

## Completed Work

### Phase 1: Critical Bug Fixes ✅
- **1.1** `load()` now raises on check errors
- **1.2** `output_model` uses `model_validate()` (Pydantic v2 API)
- **1.3** `extract_function_params` now handles all parameter types
- **1.4** `GrailDeclarationStripper` fixed for `ast.Assign` and `ast.AnnAssign`
- **1.5** Stub generator handles typing imports correctly
- **1.6** `check()` uses cached parse result (TOCTOU fix)
- **1.7** `_map_error_to_pym` improved regex and limit detection
- **1.8** `pydantic-monty` is now a hard dependency

### Phase 2: Architecture & Deduplication ✅
- **2.1** Error handling deduplicated in `GrailScript.run()`
- **2.2** `parse_pym_file` delegates to `parse_pym_content`
- **2.3** Parser/Checker validation ownership established
- **2.4** `extract_inputs` logic deduplicated
- **2.5** Dead `__grail_external__` attribute removed
- **2.6** Module-level `run()` simplified
- **2.7** CLI error handling deduplicated with decorator
- **2.8** `.grail` directory constant centralized

### Phase 3: Data Model & Type Improvements ✅
- **3.1** `file` field added to `ParseResult`
- **3.2** `input_name` field added to `InputSpec`
- **3.3** `OutputError.validation_errors` type fixed
- **3.4** `LimitError` now extends `GrailError` directly (not `ExecutionError`)
- **3.5** `ParamSpec` renamed to `ParameterSpec`

### Phase 4: API Surface & Monty Coverage ✅
- **4.1** Import allowlist expanded to include `grail`, `typing`, `__future__`
- **4.2** Added E010 (nonlocal), E011 (del) checker rules
- **4.3** Added `environ` parameter to `load()`, `run()`, and `GrailScript`
- **4.4** Error richness improved with exception type preservation
- **4.5** Print callback stream type typed as `Literal["stdout"]`
- **4.6** Added `strict_validation` parameter (default True)

### Phase 5: CLI & Peripheral Improvements ✅
- **5.1** `cmd_watch` error handling fixed, propagates `--strict` flag
- **5.2** JSON output respects `--strict` flag
- **5.3** Added `--version` flag
- **5.4** Artifact writes wrapped in try/except (non-blocking)
- **5.5** `clean()` safety check added
- **5.6** Logging added (library-safe with NullHandler)
- **5.7** Documented `ast.unparse()` formatting loss

### Phase 6: Tests - PARTIALLY COMPLETE ❌
Created `/home/andrew/Documents/Projects/grail/tests/unit/test_v3_refactor.py` with test classes for:
- TestLoadCheckEnforcement (Phase 6.1)
- TestOutputModelValidation (Phase 6.2) 
- TestVirtualFilesystem (Phase 6.3)
- TestExternalExceptionPropagation (Phase 6.4)
- TestResourceLimitViolations (Phase 6.5)
- TestLimitErrorHierarchy (Phase 6.6)
- TestParameterExtraction (Phase 6.7)
- TestCheckTOCTOU (Phase 6.8)
- TestInputNameValidation (Phase 6.9)
- TestCodegenDeclarationStripping (Phase 6.10)
- TestStubGenerator (Phase 6.11)
- TestParserEdgeCases (Phase 6.12)
- TestCheckerEdgeCases (Phase 6.13)
- TestOnEventCallbacks (Phase 6.14)
- TestDataclassRegistry (Phase 6.15)
- TestAdditionalEdgeCases (Phase 6.16)

Also updated `tests/unit/test_errors.py` to reflect new LimitError hierarchy.

---

## Current Issues

### Issue 1: Monty `inputs` Parameter Semantics

**Problem**: Monty requires `inputs=None` when a script has no declared inputs, but grail converts `inputs or {}` which converts `None` to `{}`. This causes errors:
```
TypeError: No input variables declared but inputs dict was provided
```

**Affected Tests**: 
- `TestOutputModelValidation` (both tests)
- `TestVirtualFilesystem` (both tests)  
- `TestResourceLimitViolations.test_duration_limit_exceeded`
- `TestResourceLimitViolations.test_recursion_limit_exceeded`
- `TestLimitErrorHierarchy.test_except_execution_error_does_not_catch_limit_error`
- All tests in `TestAdditionalEdgeCases`

**Root Cause**: In `src/grail/script.py` line 456:
```python
inputs = inputs or {}  # This converts None to {}
```

When `inputs=None` is passed, Monty expects `None` (not an empty dict) when there are no declared inputs in the script.

### Issue 2: External Function Tests Need Proper Inputs

**Problem**: Tests using `@external` functions fail because:
1. They don't declare inputs via `Input()`
2. Passing `externals=` without inputs triggers the "no input variables declared" error

**Example**:
```python
# This fails because no Input() declaration exists
script.run(externals={"fail": failing_external})
```

### Issue 3: Type Checking Errors in script.py

The codebase has pre-existing type checking errors that aren't related to our changes:
```
ERROR: Cannot access attribute "exception" for class "Exception"
ERROR: Cannot access attribute "limit_type" for class "Exception"  
ERROR: Cannot access attribute "traceback" for class "Exception"
ERROR: Argument of type "dict[str, Any]" cannot be assigned to parameter "limits"
```

These are type stub issues with Monty-specific exception types and can be addressed separately.

---

## Proposed Solutions

### Solution A: Fix `inputs` Handling in `run()`

**Option 1**: Only convert to `{}` if there are declared inputs in the script:
```python
# In GrailScript.run()
if inputs is None:
    inputs = {} if self.inputs else None
```

**Option 2**: Add a separate code path for `inputs=None` that passes through to Monty:
```python
if inputs is None:
    # Pass None to Monty when no inputs are declared
    inputs_to_monty = None
else:
    inputs_to_monty = inputs
```

**Recommendation**: Option 1 is cleaner - it preserves the intent while fixing the Monty behavior.

### Solution B: Update Tests to Use Declared Inputs

For tests that use `@external` functions, ensure they declare inputs:
```python
# Before (fails)
pym.write_text("""
from grail import external
@external
async def fail() -> str: ...
result = await fail()
""")

# After (works)  
pym.write_text("""
from grail import external, Input
x = Input("x")
@external
async def fail(val: int) -> str: ...
result = await fail(x)
""")
script.run(inputs={"x": 1}, externals={"fail": my_func})
```

### Solution C: Accept that Some Tests Are Integration Tests

Move tests that require full Monty execution to the integration test suite where they can properly test with real Monty execution.

---

## Test Results Summary

**Current**: 38 tests collected, ~15 passing, ~13 failing, ~10 errors

**Passing Tests** (working correctly):
- TestLoadCheckEnforcement (both)
- TestParameterExtraction (both)
- TestCheckTOCTOU
- TestInputNameValidation (both)
- TestCodegenDeclarationStripping (all 4)
- TestStubGenerator (all 3)
- TestParserEdgeCases (all 4)
- TestCheckerEdgeCases (all 4)
- TestOnEventCallbacks (both)
- TestDataclassRegistry
- TestLimitErrorHierarchy (2 unit tests)

**Failing Tests** (need fixes from above):
- TestOutputModelValidation (2) - needs declared inputs
- TestVirtualFilesystem (2) - needs declared inputs  
- TestResourceLimitViolations (2) - needs `inputs=None` fix
- TestLimitErrorHierarchy.test_except_execution_error_does_not_catch_limit_error - needs `inputs=None` fix
- TestAdditionalEdgeCases (2) - needs `inputs=None` fix
- TestExternalExceptionPropagation (1) - needs proper input handling

---

## Next Steps

1. **Fix `inputs` handling** in `GrailScript.run()` to preserve `None` when no inputs are declared
2. **Re-run tests** to verify the fix
3. **Verify all existing tests still pass** with the change
4. **Address type checking warnings** if time permits

---

## Files Modified

| File | Changes |
|------|---------|
| `src/grail/_types.py` | Added `file`, `input_name`, renamed `ParamSpec` → `ParameterSpec` |
| `src/grail/errors.py` | `LimitError` hierarchy, `OutputError` type |
| `src/grail/parser.py` | Added logging, updated InputSpec |
| `src/grail/checker.py` | Import allowlist, E010/E011 rules |
| `src/grail/script.py` | Many changes (environ, strict_validation, logging, etc.) |
| `src/grail/cli.py` | Watch fix, JSON strict, --version |
| `src/grail/artifacts.py` | Clean safety check |
| `src/grail/codegen.py` | Added logging, documentation |
| `src/grail/stubs.py` | Added logging |
| `src/grail/__init__.py` | Added logging NullHandler, exports |
| `tests/unit/test_errors.py` | Updated LimitError tests |
| `tests/unit/test_v3_refactor.py` | **NEW** - Phase 6 tests |
