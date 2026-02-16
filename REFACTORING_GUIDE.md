# Grail Refactoring Guide (Junior Developer Playbook)

This guide turns the findings in `CODE_REVIEW.md` into a practical implementation plan.

## How to Use This Guide

- Work through steps in order.
- Keep each step in its own pull request when possible.
- Do not start the next step until tests for the current step pass.
- Prefer small, reviewable commits.

---

## Step 0: Establish Baseline and Safety Nets

### Goal
Create a stable baseline before changing behavior.

### Tasks
1. Run the existing test suite and record failures.
2. Create a tracking issue or checklist covering every item in this guide.
3. Add a short `tests/README.md` section (or update it) explaining how to run unit vs integration tests.

### Tests to Implement/Run
- No new product behavior tests yet; this is baseline setup.
- Add a smoke CI command set if missing:
  - `pytest -q`
  - `pytest tests/unit -q`
  - `pytest tests/integration -q`

### Validation Criteria
- You can clearly distinguish pre-existing failures from regressions introduced by refactoring.

---

## Step 1: Fix Async Test Configuration (Unblock Confidence)

### Goal
Resolve async test execution issues so core runtime paths can be verified.

### Tasks
1. Confirm `pytest-asyncio` is installed and correctly configured.
2. Set pytest async mode explicitly in `pyproject.toml` or `pytest.ini` (for example, `asyncio_mode = auto` or project-preferred setting).
3. Update any broken async tests to match modern `pytest-asyncio` patterns.

### Tests to Implement
1. **Regression test for async execution path**
   - Ensure a simple `.pym` script that awaits an external async function runs successfully.
2. **Configuration test/documentation check**
   - Add a short test note or config assertion proving async plugin is active (can be done by ensuring an async test runs without plugin errors).

### Validation Criteria
- Formerly failing async test(s) pass.
- Running `pytest -q` no longer fails because async support is missing.

---

## Step 2: Replace Naive Source Mapping with AST-Based Mapping

### Goal
Make `.pym` ↔ generated code line mapping accurate and reliable.

### Tasks
1. Refactor `codegen.py` to build source maps during AST transformation instead of line-content heuristics.
2. Preserve and track source line metadata as nodes are removed/transformed.
3. Support multiline statements and shifted offsets.
4. Parse generated code once before returning artifacts to ensure output is valid Python.

### Tests to Implement
1. **Unit: exact line mapping after removing declarations**
   - Inputs with `@external` and `Input()` declarations.
   - Assert source map points runtime lines back to original `.pym` lines.
2. **Unit: multiline statement mapping**
   - Include multiline comprehensions/calls and assert accurate mappings.
3. **Unit: transformed output validity**
   - Assert generated source can be parsed by `ast.parse`.
4. **Edge-case test**
   - Empty line blocks/comments/docstrings should not break mapping.

### Validation Criteria
- Source maps are deterministic and correct for common and multiline scenarios.
- Invalid transformed output is caught before runtime.

---

## Step 3: Integrate Source Map into Runtime Error Translation

### Goal
Surface `.pym` line numbers (not Monty/internal line numbers) in runtime errors.

### Tasks
1. Refactor `_map_error_to_pym()` in `script.py` to parse runtime traceback/error payload robustly.
2. Use source map generated in Step 2 to translate line numbers.
3. Remove stale comments indicating API uncertainty; replace with stable internal adapter helpers if needed.
4. Add fallback behavior when line mapping is unavailable.

### Tests to Implement
1. **Unit: error line remapping**
   - Simulate runtime failure at known generated line and assert mapped `.pym` line in `ExecutionError`.
2. **Unit: fallback behavior**
   - When no map entry exists, assert graceful message still returned.
3. **Integration: real runtime error**
   - Execute script that raises during runtime and assert final error references original `.pym` line.

### Validation Criteria
- Runtime errors consistently cite `.pym` lines when mapping exists.
- No crashes in error mapper for unknown traceback shapes.

---

## Step 4: Implement Rich Error Context Display

### Goal
Upgrade error output to include surrounding code context as promised by the spec.

### Tasks
1. Extend `ExecutionError` formatting in `errors.py` to include:
   - preceding line,
   - failing line with marker,
   - following line.
2. Include filename/path where available.
3. Keep formatting compact and readable in both CLI and API contexts.

### Tests to Implement
1. **Unit: formatted context block**
   - Assert output contains the expected line window and marker (`>` or equivalent).
2. **Unit: boundary conditions**
   - Failing line at top or bottom of file should still format correctly.
3. **Integration: runtime exception formatting**
   - Ensure real execution path emits enriched context.

### Validation Criteria
- Error messages match documented contextual format.
- Context rendering works at file boundaries.

---

## Step 5: Implement `grail run --input` Support

### Goal
Match CLI behavior promised in spec by accepting `--input key=value` entries.

### Tasks
1. Add `--input` argument parsing in `cli.py` (allow repeated values).
2. Parse and validate key/value pairs; provide clear user errors for malformed input.
3. Merge CLI inputs with host-provided values using documented precedence.
4. Pass parsed inputs into `script.run()`.

### Tests to Implement
1. **CLI unit test: single input**
   - `--input budget_limit=5000` reaches runtime correctly.
2. **CLI unit test: repeated inputs**
   - Multiple `--input` flags build expected dict.
3. **CLI unit test: malformed input handling**
   - Missing `=` returns non-zero exit and helpful message.
4. **Integration test: full run command**
   - Validate end-to-end run with host + inputs.

### Validation Criteria
- `grail run ... --input ...` works as documented.
- Invalid input syntax produces actionable errors.

---

## Step 6: Harden and Polish CLI UX

### Goal
Improve usability and robustness for command-line users.

### Tasks
1. Improve top-level exception handling so users see friendly errors.
2. Document optional `watchfiles` dependency in README and package extras.
3. Add/confirm optional dependency group in `pyproject.toml` for watch support.
4. Revisit `grail run` UX (host file requirement):
   - either improve flow/documentation,
   - or plan deprecation path with clear messaging.

### Tests to Implement
1. **CLI test: watch command without dependency**
   - Should fail gracefully with install guidance.
2. **CLI test: user-friendly error formatting**
   - Internal exceptions should map to readable CLI output.
3. **Packaging/config test**
   - Optional extras include watch dependency.

### Validation Criteria
- CLI failures are understandable and actionable.
- Optional watch mode is clearly documented and discoverable.

---

## Step 7: Parser Robustness (Top-Level Declarations Only)

### Goal
Ensure parser only processes intended top-level `@external` declarations.

### Tasks
1. Replace broad `ast.walk()` use (for declaration collection paths) with controlled top-level iteration via `module.body`.
2. Explicitly ignore nested functions/classes for declaration extraction.
3. Add comments/docstrings clarifying top-level-only rule.

### Tests to Implement
1. **Unit: nested function should not register external**
   - External-like decorator inside function body must be ignored.
2. **Unit: top-level declarations still work**
   - Existing valid declarations continue to be discovered.
3. **Regression test: mixed module content**
   - Ensure behavior is stable with nested and top-level items.

### Validation Criteria
- No false-positive external/input extraction from nested scopes.

---

## Step 8: Improve Stub Generator `Any` Detection

### Goal
Remove fragile substring matching and detect `typing.Any` safely.

### Tasks
1. Replace `"Any" in ...` checks with token-aware matching (AST parse, typing parser, or conservative regex with boundaries).
2. Recheck import generation logic to avoid false positives.
3. Keep implementation minimal and maintainable.

### Tests to Implement
1. **Unit: true Any annotations trigger import**
   - `Any`, `list[Any]`, etc.
2. **Unit: false positives avoided**
   - Types like `Company` should not trigger `Any` import.
3. **Unit: mixed annotations**
   - Import appears once when needed across externals/inputs.

### Validation Criteria
- `Any` import behavior is correct and deterministic.

---

## Step 9: Snapshot Runtime Cleanup and Documentation

### Goal
Make snapshot behavior safer and easier to understand.

### Tasks
1. Clean up commented-out logic in `snapshot.py`.
2. Decide and enforce policy for accessing `output` before completion (raise vs documented behavior).
3. Add clear docstrings and developer docs for async resume protocol.
4. Document `Snapshot.load()` limitations (required source map + externals context).

### Tests to Implement
1. **Unit: output access policy**
   - Verify expected behavior when snapshot is incomplete.
2. **Unit: async external resume flow**
   - Confirm handoff/resume protocol for async externals.
3. **Doc test or integration example**
   - Ensure documented load constraints are realistic and accurate.

### Validation Criteria
- Snapshot API behavior is explicit, tested, and documented.

---

## Step 10: Populate and Surface Limit Metadata

### Goal
Make `LimitError` more actionable by recording which limit was exceeded.

### Tasks
1. Ensure `limit_type` is set consistently when raising `LimitError`.
2. Include this metadata in formatted error messages and/or structured fields.
3. Keep backward compatibility for existing catch blocks.

### Tests to Implement
1. **Unit: each limit path sets `limit_type`**
   - CPU, memory, output size, duration, etc. (as supported).
2. **Unit: message formatting includes limit type**
   - Assert useful user-facing output.

### Validation Criteria
- Users can identify exceeded limit without guesswork.

---

## Step 11: Remove Commented-Out / Uncertain Code Paths

### Goal
Reduce technical debt and remove ambiguity.

### Tasks
1. Remove stale commented code from `script.py`, `snapshot.py`, and other touched files.
2. Convert essential historical context into concise comments or docs.
3. Ensure public behavior is unchanged (unless intentionally updated in prior steps).

### Tests to Implement
1. **Regression suite run**
   - Full unit/integration test pass required.
2. **Lint/static checks**
   - Ensure no dead/commented-out logic patterns reintroduced.

### Validation Criteria
- Codebase is cleaner without behavior regressions.

---

## Step 12: Expand Integration Coverage (End-to-End Confidence)

### Goal
Cover real workflows, artifacts, and CLI behavior end to end.

### Tasks
1. Add integration tests for:
   - `grail check` workflow,
   - `grail run` workflow with inputs,
   - artifact generation and contents (`.grail/` outputs),
   - runtime error mapping/context output.
2. Add fixture scenarios for both success and failure paths.

### Tests to Implement
1. **E2E success path**
   - Load, validate, run script with externals/inputs.
2. **E2E failure path**
   - Controlled runtime error should map line + context correctly.
3. **Artifact verification**
   - Assert generated files exist and contain expected schema/content.

### Validation Criteria
- Critical user journeys are covered by repeatable automated tests.

---

## Step 13: Performance and Regression Guardrails

### Goal
Protect performance claims and prevent future regressions.

### Tasks
1. Add lightweight benchmark tests/scripts for:
   - parse + transform overhead,
   - artifact write overhead,
   - source map generation cost.
2. Record target budgets and fail/warn thresholds.
3. Add regression checks in CI (can be periodic if too noisy for every PR).

### Tests to Implement
1. **Benchmark smoke tests**
   - Ensure overhead remains near stated expectations.
2. **Large-file scenario test**
   - Validate parser/codegen behavior on bigger `.pym` files.

### Validation Criteria
- Performance targets are measured, tracked, and defended.

---

## Step 14: Documentation and Developer Enablement

### Goal
Make the refactored system easy to use and maintain.

### Tasks
1. Update README with:
   - `--input` examples,
   - optional watch dependency installation,
   - improved error output examples.
2. Add snapshot usage section with limitations.
3. Add troubleshooting notes for async tests and common CLI errors.
4. (Optional) Start a short user guide/tutorial.

### Tests to Implement
1. **Docs consistency checks**
   - Commands in docs should match actual CLI behavior.
2. **Example execution tests (where feasible)**
   - Run documented examples in CI or doctest-like script.

### Validation Criteria
- Documentation reflects actual behavior and reduces onboarding friction.

---

## Recommended Delivery Plan (Milestones)

1. **Milestone A (Stability):** Steps 0-2
2. **Milestone B (Error Quality + Spec Compliance):** Steps 3-5
3. **Milestone C (CLI + Core Robustness):** Steps 6-8
4. **Milestone D (Runtime Cleanup + Limits):** Steps 9-11
5. **Milestone E (Coverage + Performance + Docs):** Steps 12-14

Each milestone should end with a full test run and a short release note.

---

## Definition of Done (Project-Level)

All items below should be true before declaring the refactor complete:

- Async tests run reliably in CI.
- Source mapping is AST-based and verified.
- Runtime errors report correct `.pym` lines with context.
- `grail run --input` is implemented and documented.
- CLI gracefully handles optional dependencies and user errors.
- Snapshot behavior and limitations are tested and documented.
- Integration and artifact tests cover key workflows.
- Performance checks exist for core overhead claims.
- No stale commented-out code remains in touched modules.

