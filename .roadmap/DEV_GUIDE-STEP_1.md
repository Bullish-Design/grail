# DEV GUIDE – STEP 1 (Core Foundation: Minimal `MontyContext`)

## Objective
Implement a minimal async-capable `MontyContext` that validates input models and executes code through Monty with basic limits and error handling.

## Scope
- `src/grail/context.py` (new)
- `src/grail/types.py` (ResourceLimits aliases/wrappers if needed)
- `tests/unit/` and `tests/contracts/`

## Implementation checklist
1. **Create `MontyContext[InputT]`**
   - Constructor args:
     - `input_model: type[BaseModel]`
     - optional `limits`
   - Implement `execute(code: str, inputs: InputT) -> Any`.

2. **Input validation + serialization**
   - Accept model instance or dict-like input.
   - Validate using `input_model.model_validate(...)`.
   - Serialize with `model_dump(mode="python")`.
   - Inject serialized data as `inputs` for execution.

3. **Monty call wiring**
   - Use `pydantic_monty.run_monty_async(...)`.
   - Pass code, inputs scope, and limits.
   - Keep output raw for this phase.

4. **Limits integration**
   - Provide safe defaults in one central function.
   - Merge caller-supplied limits with defaults.

5. **Error model**
   - Add clear exception wrappers (e.g., `GrailExecutionError`) while preserving original traceback.
   - Distinguish validation vs execution vs limit failures.

## Testing and validation requirements
1. **Unit tests**
   - Input validation success/failure.
   - Limits defaulting/merge logic.
   - Exception mapping behavior.

2. **Contract tests (visible I/O)**
   - Add fixtures for each scenario in `tests/fixtures/inputs/step1-*` and `tests/fixtures/expected/step1-*`:
     - arithmetic
     - nested model access
     - complex dict return
     - validation failure
   - Contract tests must log or artifact:
     - test id
     - input fixture path + payload
     - code snippet
     - expected + actual payload

3. **Boundary/negative checks**
   - recursion or long-running sample to verify limit wiring.
   - malformed code path verifies useful diagnostics.

## Definition of done
- `MontyContext.execute()` works for documented basic cases.
- Failures are categorized and easy to debug.
- Every behavior test uses standardized visible input/output fixtures.
