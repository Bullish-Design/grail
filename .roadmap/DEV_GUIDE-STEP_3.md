# DEV GUIDE – STEP 3 (DX: `@secure` Decorator & Error Handling)

## Objective
Improve ergonomics and diagnostics so developers can adopt Grail with minimal boilerplate and high-quality error messages.

## Scope
- `src/grail/decorators.py` (new)
- `src/grail/errors.py`
- `src/grail/context.py` (debug hooks)
- `tests/unit/`, `tests/integration/`, `tests/contracts/`

## Implementation checklist
1. **Implement `@secure` decorator**
   - Extract source with `inspect.getsource`.
   - Infer input/output models from type hints.
   - Build internal `MontyContext` with overrides (`limits`, `tools`).

2. **Error UX improvements**
   - Normalize errors with clear categories and messages.
   - Include field paths and source line references where possible.
   - Remove noisy internal frames from displayed stack traces.

3. **Debug mode**
   - Add `debug` flag.
   - Capture and expose logs: lifecycle events, tool calls, stdout/stderr.
   - Define a structured debug payload format.

4. **Docstrings and typing**
   - Add docstrings/examples for all public objects.
   - Keep strict typing consistent with prior phases.

## Testing and validation requirements
1. **Decorator tests**
   - straightforward typed functions.
   - parameterized decorator usage.
   - equivalence with direct `MontyContext` call behavior.

2. **Error tests**
   - validation path rendering (`a.b.c`).
   - line number references.
   - no internal-frame leakage in user-facing trace output.

3. **Debug mode tests (visible I/O + logs)**
   - Contract fixture must include expected debug transcript fragments.
   - Assert captured stdout/stderr and tool arguments/return values.
   - Store debug outputs in `tests/fixtures/expected/debug/`.

4. **Docs-as-tests**
   - Ensure docstring examples are executable via doctest or dedicated tests.

## Definition of done
- Decorator is practical for common usage.
- Error and debug outputs are actionable and consistent.
- Tests make runtime inputs, outputs, and debug traces visibly inspectable.
