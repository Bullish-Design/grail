# DEV GUIDE – STEP 5 (Production Readiness: Docs, Examples, Performance, Security)

## Objective
Prepare for public release with confidence in docs accuracy, benchmark transparency, and security posture.

## Scope
- `examples/`
- `docs/`
- `benchmarks/`
- security policy files
- observability hooks

## Implementation checklist
1. **Examples program**
   - Build and maintain runnable example apps for core personas.
   - Ensure each example has README + expected outputs.

2. **Documentation site**
   - Add getting started, concepts, API reference, and migration guide.
   - Keep docs sourced from code docstrings where possible.

3. **Performance suite**
   - Implement benchmark scripts with fixed scenarios.
   - Track startup, stub generation, snapshot performance, memory overhead.

4. **Security hardening**
   - Formalize threat model.
   - Audit tool exposure, filesystem/network boundaries, and leakage risks.

5. **Production observability features**
   - Structured logs + metrics API.
   - graceful error/retry/degradation patterns.

## Testing and validation requirements
1. **Examples validation**
   - CI executes every example and validates against expected outputs stored under `tests/fixtures/expected/examples/`.

2. **Docs validation**
   - link checker and code snippet execution checks.
   - migration guide tested via scripted before/after cases.

3. **Benchmark validation**
   - enforce thresholds with machine-readable benchmark artifacts.
   - publish JSON outputs for trend tracking.

4. **Security tests**
   - explicit negative tests for unauthorized FS/network access.
   - fuzz/selective adversarial inputs for tool-call boundaries.

5. **Visible I/O policy**
   - Treat examples and benchmark scenarios as contract tests:
     - each scenario has declared input, expected output, and actual output artifact.
   - Standard directories:
     - `tests/fixtures/inputs/production/`
     - `tests/fixtures/expected/production/`
     - `tests/.artifacts/actual/production/`

## Definition of done
- Release candidate has passing docs/examples/security/benchmark gates.
- Testing outputs are inspectable and comparable across runs.
