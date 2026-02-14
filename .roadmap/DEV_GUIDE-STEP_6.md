# DEV GUIDE – STEP 6 (Ecosystem Integration: Pydantic AI, FastAPI, Distributed, JS, Plugins)

## Objective
Integrate Grail into adjacent ecosystems with clear compatibility contracts and robust integration testing.

## Scope
- integration packages/modules for AI, web, distributed workers, monitoring, JS bindings, plugin APIs
- corresponding examples and conformance tests

## Implementation checklist
1. **Pydantic AI integration**
   - Add adapter APIs for code-mode and tool-calling workflows.
   - Support snapshot-backed state persistence.

2. **FastAPI integration**
   - Build endpoint helper/decorator for request->execute->response lifecycle.
   - Include streaming and error mapping support.

3. **Distributed execution**
   - Define portable context/snapshot serialization contracts.
   - Provide worker-queue reference implementation.

4. **Monitoring integrations**
   - Add OpenTelemetry trace hooks and Prometheus exporter.
   - Define stable metric names and labels.

5. **JavaScript/TypeScript layer**
   - Provide bindings, type definitions, and package build/publish flow.

6. **Plugin framework**
   - Add plugin lifecycle hooks and conflict detection.
   - Provide plugin authoring guide and validation harness.

## Testing and validation requirements
1. **Cross-integration suites**
   - dedicated `tests/integration/<surface>/` per ecosystem.
   - each suite includes happy-path + failure-path + compatibility-version tests.

2. **Conformance fixtures (visible I/O)**
   - shared fixture schema across ecosystems:
     - `input`
     - `execution_config`
     - `expected_output`
     - `expected_events` (traces/metrics/tool calls)
   - store in `tests/fixtures/inputs/ecosystem/` and `tests/fixtures/expected/ecosystem/`.

3. **Parity tests**
   - same scenario executed via Python API, FastAPI API, and JS binding should produce equivalent outputs/events.

4. **Load and resilience tests**
   - API throughput and distributed worker reliability tests.
   - plugin conflict and failure isolation tests.

5. **Release gates**
   - ecosystem adapters require matrix CI runs and published compatibility table.

## Definition of done
- Integrations are documented, tested, and versioned with explicit compatibility guarantees.
- Inputs/outputs/events for integration tests are fully visible via shared contract artifacts.
