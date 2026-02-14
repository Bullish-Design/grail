# Contract Test I/O Convention

Contract tests in this repository follow a visible input/output pattern:

- Input fixtures live in `tests/fixtures/inputs/<name>.json`.
- Expected output fixtures live in `tests/fixtures/expected/<name>.json`.
- Tests should report clear mismatch diagnostics with:
  - fixture name/path,
  - input payload,
  - expected payload,
  - actual payload.

When run locally, helpers may persist actual payloads to `tests/.artifacts/actual/<name>.json`
so failures can be inspected and diffed outside the test runner.
