
## Overall Assessment

The guide shows **good structural thinking** with incremental development and testing at each step, which aligns with your requirements. However, there are **significant gaps and issues** that would cause problems during implementation. This is understandable from a junior developer, but needs correction before proceeding.

## Critical Issues

### 1. **Missing Foundation: grail Declarations (HIGH PRIORITY)**

The guide jumps into parsing without implementing the fundamental building blocks that make `.pym` files work:

**Problem:** Step 12 imports `from grail._external import external` and `from grail._input import Input`, but these are never created!

**Impact:** The parser (Step 4) needs these to exist, and `.pym` files won't work in IDEs without them.

**Fix Needed:** Add **Step 0** (before current Step 1):
- Create `src/grail/_external.py` with the `external` decorator (no-op at runtime)
- Create `src/grail/_input.py` with the `Input()` function (no-op at runtime)
- These need proper type stubs so IDEs understand them
- Test that they can be imported and used in a `.pym` file

### 2. **Parser Implementation Too Vague (HIGH PRIORITY)**

**Problems in Step 4:**
- "Walk AST to find `@external` decorated functions" - HOW? Need to check `decorator_list` on `FunctionDef` nodes
- "Extract `Input()` calls" - FROM WHERE? Need to find `AnnAssign` nodes with `Input()` call on RHS
- No explanation of how to validate function body is `...` (need to check `body[0]` is `Expr` containing `Constant(...)`
- Missing async detection (check `isinstance(node, ast.AsyncFunctionDef)`)

**Fix Needed:** Add detailed algorithm:
```python
# Example of what Step 4 should explain:
for node in ast.walk(module):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == 'external':
                # Extract ExternalSpec...
                # Validate body is single Ellipsis...
```

### 3. **Code Generator Missing Algorithm (HIGH PRIORITY)**

**Problems in Step 7:**
- "Strip grail imports" - String manipulation or AST? (Answer: Should use AST filtering)
- "Remove `@external` functions" - Which AST nodes exactly?
- "Source map building" - No algorithm provided
- **Critical:** Doesn't explain how to preserve the final expression as return value

**Fix Needed:** Specify that codegen should:
1. Filter AST nodes (remove certain `Import`, `ImportFrom`, decorated `FunctionDef`, `AnnAssign` with Input calls)
2. Use `ast.unparse()` to generate code
3. Build line mapping during AST traversal
4. Ensure final `Expr` node becomes the return value

### 4. **Monty Integration Details Missing (HIGH PRIORITY)**

**Problems in Step 9:**
- How to call `pydantic_monty.Monty()`? What parameters?
- How to create `OSAccess` and `MemoryFile` objects?
- How to map `{"max_memory": "16mb"}` to Monty's expected format?
- How to extract errors from Monty and map line numbers?

**Fix Needed:** Add explicit integration details or a separate step dedicated to Monty integration testing.

### 5. **Wrong Module for `grail.run()` (MEDIUM PRIORITY)**

Step 12 shows `from grail.codegen import run` but `run()` should be in `script.py`, not `codegen.py`. Codegen is for transforming code, not executing it.

### 6. **Type Checking Integration Missing (MEDIUM PRIORITY)**

Step 5 mentions E1xx errors from Monty's `ty` type checker but never explains:
- How to invoke the type checker
- How to parse its output
- How to convert its errors to `CheckMessage` format

### 7. **Test Fixtures Not Created (MEDIUM PRIORITY)**

The guide references `fixtures/simple.pym` and `fixtures/with_external.pym` but never creates them. These should be created early and reused across tests.

### 8. **CLI Host File Protocol Undefined (MEDIUM PRIORITY)**

Step 11 mentions `grail run <file.pym> --host <host.py>` but never explains:
- What interface the host file must export
- How to dynamically import and execute it
- How `--input` flags map to the inputs dict

## Suggested Order Issues

The current order is mostly good, but I'd recommend these changes:

1. **Add Step 0**: Implement `external` and `Input` declarations BEFORE types (they're simpler and needed first)
2. **Split Step 9**: Separate Monty integration testing from full Script API
   - Step 9a: Basic Monty integration (call Monty with hand-written code/stubs)
   - Step 9b: Full GrailScript class
3. **Move Snapshot later**: It's less critical than CLI for basic functionality
4. **Add intermediate validation**: Test generated stubs and monty_code are valid Python before using them

## Recommended Order:

```
Step 0: Grail Declarations (external, Input) 
Step 1: Type Definitions
Step 2: Error Hierarchy
Step 3: Resource Limits
Step 4: Test Fixtures (create reusable .pym examples)
Step 5: Parser (with detailed AST algorithms)
Step 6: Checker (with type checker integration)
Step 7: Stubs Generator
Step 8: Code Generator (with detailed AST algorithm)
Step 9: Artifacts Manager
Step 10: Basic Monty Integration (test calling Monty directly)
Step 11: GrailScript Class (load/run with full validation)
Step 12: CLI Commands
Step 13: Snapshot (pause/resume)
Step 14: Public API (__init__.py)
Step 15: Integration & E2E Tests
Step 16: Final Validation
```

## Missing from Guide

1. **Output model validation** (Pydantic validation mentioned in spec)
2. **Error context formatting** (showing surrounding lines)
3. **Limit merging logic** (load-time + run-time overrides)
4. **Watch command implementation** (needs `watchfiles` library)
5. **JSON output format for CI** (spec mentions `--format json`)

## Strengths to Keep

✅ Incremental approach with testing at each step
✅ Unit tests before integration tests  
✅ Clear separation between parser, checker, stubs, codegen
✅ Artifacts manager as separate concern
✅ Final validation step

## Verdict

**The guide needs significant revision before use.** The core structure is sound, but critical implementation details are missing or wrong. A junior developer following this guide would get stuck at multiple points.
