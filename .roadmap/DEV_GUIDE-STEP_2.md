# DEV GUIDE – STEP 2 (MVP: Output Validation & External Functions)

## Objective
Complete the first production-usable API: typed output validation, tools support, and minimal stub generation.

## Scope
- `src/grail/context.py`
- `src/grail/stubs.py` (new)
- `src/grail/tools.py` (optional helper layer)
- `tests/unit/`, `tests/integration/`, `tests/contracts/`

## Implementation checklist
1. **Output model support**
   - Extend `MontyContext[InputT, OutputT]`.
   - Add `output_model` parameter.
   - Parse raw result into `output_model.model_validate(...)`.

2. **Tool registration and execution**
   - Add `tools: list[Callable]`.
   - Register sync+async tools for Monty access.
   - Keep deterministic naming for tools (explicit map recommended).

3. **Stub generation (minimal)**
   - Implement `StubGenerator` for:
     - input model shape
     - output model shape
     - tool signatures
   - Pass generated stubs to Monty type-check config.

4. **Async behavior**
   - Ensure external async tools can be awaited.
   - Define behavior for concurrent tool calls and snapshot/future states.

## Testing and validation requirements
1. **Output validation tests**
   - valid payload -> output model instance.
   - invalid payload -> structured validation details.
   - nested model success/failure.

2. **Tooling tests**
   - sync tool invocation.
   - async tool invocation.
   - tool exception propagation.
   - unknown tool access error.

3. **Type-stub tests**
   - snapshot tests for generated stub text (store under `tests/fixtures/expected/stubs/`).
   - type misuse caught before runtime where possible.

4. **Visible I/O contract tests**
   - One fixture pair per tool scenario.
   - Include explicit `inputs`, `tool_calls`, `expected_output`, and optional `expected_error` fields in fixture schema.
   - Standardize JSON keys and ordering to make diffs readable.

## Definition of done
- End-to-end async execution with tools + typed output works.
- Stub generation is tested and deterministic.
- Contract fixtures clearly expose execution inputs and outputs.
