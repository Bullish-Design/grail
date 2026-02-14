# DEV GUIDE – STEP 0 (Project Setup & Foundation)

## Objective
Build a clean, reproducible development baseline so any contributor can install, lint, type-check, and run a smoke test immediately.

## Scope
- `pyproject.toml`
- `src/grail/__init__.py`
- `tests/` and pytest configuration
- Tooling config (`ruff`, `ty`, optional pre-commit)

## Implementation checklist
1. **Create base package structure**
   - Add `src/grail/__init__.py` with package docstring and version placeholder.
   - Add `tests/` with:
     - `tests/unit/`
     - `tests/integration/`
     - `tests/contracts/` (reserved for input/output visibility tests)
     - `tests/fixtures/inputs/` and `tests/fixtures/expected/`

2. **Set up packaging and tooling in `pyproject.toml`**
   - Add build-system and project metadata.
   - Add runtime dependency on `pydantic_monty`.
   - Add dev dependencies: `pytest`, `pytest-asyncio`, `ruff`, `ty`.
   - Configure pytest discovery paths and markers (`unit`, `integration`, `contract`).

3. **Add baseline lint/type settings**
   - Ruff: enable errors, style, import sorting.
   - ty: strict mode, include `src/` and `tests/`.
   - Keep settings minimal first, then tighten over time.

4. **Create smoke test**
   - Add `tests/integration/test_smoke.py`.
   - Validate import of `pydantic_monty`, Monty construction, and execution of `1 + 1`.

5. **Add visible test I/O convention now (important)**
   - Add `tests/contracts/README.md` describing this standard:
     - Contract tests load input from `tests/fixtures/inputs/<name>.json`.
     - Expected output in `tests/fixtures/expected/<name>.json`.
     - Test prints a compact diff on mismatch (or stores actual output in `tests/.artifacts/actual/<name>.json` when run locally).
   - Add helper module `tests/helpers/io_contracts.py` with `load_input`, `load_expected`, `assert_contract`.

## Testing and validation requirements
1. **Environment checks**
   - Confirm package import and smoke execution.
   - Confirm pytest discovery works for all test folders.

2. **Tool checks**
   - Lint and format checks.
   - Type checks on empty/minimal code.

3. **Visible test output checks**
   - Add one contract-style smoke case:
     - Input fixture: `{ "expr": "1 + 1" }`
     - Expected fixture: `{ "result": 2 }`
   - Ensure failure mode shows both input and expected/actual output clearly.

## Definition of done
- Fresh clone can run install + checks successfully.
- Test directory uses the standardized visible I/O layout from day one.
