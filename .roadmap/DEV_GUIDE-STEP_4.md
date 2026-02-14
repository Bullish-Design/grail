# DEV GUIDE – STEP 4 (Advanced Features: Snapshots, OSAccess, Policies)

## Objective
Add advanced execution patterns required for agents and resumable workflows while preserving safety and test clarity.

## Scope
- `src/grail/context.py`
- `src/grail/snapshots.py` (new)
- `src/grail/filesystem.py` (new)
- `src/grail/policies.py` and/or `resource_guard.py`
- broad test expansion

## Implementation checklist
1. **Snapshot lifecycle**
   - Add `start()` entry for resumable execution.
   - Add snapshot serialization/deserialization helpers.
   - Support restore in fresh context/process.

2. **OSAccess integration**
   - Add filesystem parameter and adapters.
   - Implement helper constructors for in-memory files/callback files.
   - Enforce isolation/permission boundaries.

3. **Advanced type support**
   - Extend stub generation for generics, unions, dataclasses, aliases.

4. **Resource guard + policies**
   - Implement declarative `ResourceGuard` model.
   - Create named policy presets and composition rules.

## Testing and validation requirements
1. **Snapshot tests**
   - pause/resume loop scenarios.
   - binary serialization integrity checks.
   - cross-context replay equality tests.

2. **Filesystem tests (contract-heavy)**
   - visible fixtures for initial FS state, operations, expected final state.
   - permission-denied and isolation negative cases.

3. **Type tests**
   - parameterized cases for complex annotations.
   - generated stubs compared against fixtures.

4. **Policy/guard tests**
   - policy inheritance/composition matrix.
   - invalid policy definition rejection.
   - runtime metrics and limit violation assertions.

5. **Visibility standard enforcement**
   - Add test helper that prints fixture id + resolved input + resolved output for all `contract` marker tests.
   - Add CI rule to fail if contract tests do not use fixture-based I/O format.

## Definition of done
- Advanced runtime features are stable and resumable.
- Policies and resource controls are explicit and test-proven.
- Contract tests make state transitions visible and reproducible.
