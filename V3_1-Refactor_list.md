# Grail V3.1 — Refactoring Issues List

**Based on:** CODE_REVIEW_V3.md (2026-02-25)

---

## 1. Critical Issues (Fix Before v3 GA)

| # | Issue | Location | Effort |
|---|---|---|---|
| 1 | `load()` silently ignores check errors | `script.py:560-561` | Low |
| 2 | `extract_function_params` drops `*args`/`**kwargs` silently | `parser.py:46` | Medium |
| 3 | `GrailDeclarationStripper` doesn't strip `ast.Assign` Input() | `codegen.py:49-53` | Low |
| 4 | Stub generator doesn't import `typing` names beyond `Any` | `stubs.py:30-45` | Low |
| 5 | `output_model` uses wrong Pydantic v2 API | `script.py:487-493` | Low |
| 6 | Bare `assert` stripped by `python -O` | `script.py:209` | Trivial |

---

## 2. High Priority Design Issues

| # | Issue | Location | Effort |
|---|---|---|---|
| 7 | Export `GrailScript` from `__init__.py` | `__init__.py` | Trivial |
| 8 | `Input()` name parameter silently ignored | `parser.py:222` | Medium |
| 9 | Import allowlist too restrictive (`{"grail", "typing"}` only) | `checker.py:129` | Low |
| 10 | ~60 lines duplicated error handling | `script.py:400-460` | Low |
| 11 | Regex line extraction has false positives | `script.py:266-271` | Low |
| 12 | Limit detection by string matching | `script.py:273-283` | Medium |
| 13 | `check()` re-parses from disk (TOCTOU) | `script.py:102` | Medium |
| 14 | Zero logging anywhere in `src/grail/` | All modules | Medium |
| 15 | Export `STRICT`, `DEFAULT`, `PERMISSIVE` constants | `__init__.py` | Trivial |
| 16 | Export `ExternalSpec` and `InputSpec` types | `__init__.py` | Trivial |

---

## 3. Medium Priority Cleanup

| # | Issue | Location | Effort |
|---|---|---|---|
| 17 | Remove dead `validate_external_function()` | `parser.py:77-129` | Trivial |
| 18 | Remove legacy limits API | `limits.py:176-201` | Trivial |
| 19 | `pydantic-monty` — pick hard or optional dep | `pyproject.toml` + `script.py:10-13` | Low |
| 20 | `LimitError` hierarchy — sibling not child of `ExecutionError` | `errors.py:113-118` | Medium |
| 21 | `spec.loader` null check in CLI | `cli.py:217-219` | Trivial |
| 22 | `cmd_watch` missing error handling + KeyboardInterrupt | `cli.py:254` | Low |
| 23 | Artifact writes should not block `load()` | `artifacts.py:47` | Low |
| 24 | `MontySyntaxError` should map to `ParseError` | `script.py:430` | Low |
| 25 | Decorator aliased imports fail silently (`@ext` for `@external`) | `parser.py:148-177` | Medium |

---

## 4. Data Type Enhancements

| # | Issue | Location |
|---|---|---|
| 26 | `ParamSpec` missing `kind` field for positional-only, keyword-only, `*args`, `**kwargs` | `_types.py` |
| 27 | `ParseResult` doesn't store source file path | `_types.py:44-51` |
| 28 | `InputSpec` doesn't capture the `Input()` name argument | `_types.py` |

---

## 5. Monty API Coverage Gaps

| # | Issue | Priority |
|---|---|---|
| 29 | OS Access enrichment — allow `AbstractOS` or env vars | High |
| 30 | Error richness — use `MontyError.exception()`, `Frame` fields | High |
| 31 | Type checking diagnostics — expose `display(format='full')` | Medium |
| 32 | Threading docs — document concurrent `run()` safety | Low |
| 33 | Serialization — document intentional omission | Low |

---

## 6. CLI Issues

| # | Issue | Location |
|---|---|---|
| 34 | `spec.loader` null dereference | `cli.py:217-219` |
| 35 | `cmd_watch` no exit code / KeyboardInterrupt handling | `cli.py:254` |
| 36 | `cmd_check` JSON output ignores `--strict` flag | `cli.py` |
| 37 | No `--version` flag | `cli.py` |
| 38 | Error handling boilerplate duplicated 5 times | `cli.py` |
| 39 | `--host` flag security not documented | `cli.py:219` |

---

## 7. Test Gaps (Write These Tests)

### Critical — Zero Test Coverage

| # | Test | Description |
|---|---|---|
| 1 | `test_output_model_valid` | Result validated against Pydantic model — success |
| 2 | `test_output_model_invalid_raises_output_error` | Mismatched result → `OutputError` |
| 3 | `test_run_with_dataclass_input` | Pass dataclass instance as input |
| 4 | `test_run_with_dataclass_output` | Script returns dataclass instance |
| 5 | `test_dataclass_registry_passed_to_monty` | Registry forwarded to Monty constructor |
| 6 | `test_run_with_virtual_file_read` | Script reads from virtual file via `open()` |
| 7 | `test_run_with_virtual_file_write` | Script writes to virtual file |
| 8 | `test_files_override_at_runtime` | `files` at `run()` overrides `files` from `load()` |
| 9 | `test_external_raises_value_error` | External raises `ValueError` → should propagate |
| 10 | `test_external_raises_with_try_except_in_script` | Script wraps external in try/except |
| 11 | `test_memory_limit_exceeded` | Allocate beyond `max_memory` → `LimitError` |
| 12 | `test_duration_limit_exceeded` | Infinite loop with `max_duration` → `LimitError` |
| 13 | `test_recursion_limit_exceeded` | Deep recursion → `LimitError` |

### High — Important Paths Partially Covered

| # | Test | Description |
|---|---|---|
| 14 | `test_integration_sync_external` | Sync (non-async) external — all tests use async |
| 15 | `test_integration_external_raises_exception` | External that raises during execution |
| 16 | `test_integration_default_input_used` | Required input omitted but default provided |
| 17 | `test_on_event_error` | `run_error` event |
| 18 | `test_on_event_print` | `print` event |
| 19 | `test_check_type_error_e100` | E100 path in `check()` |
| 20 | `test_parse_grail_dot_external_style` | `@grail.external` (Attribute-style) |
| 21 | `test_parse_grail_dot_input_style` | `grail.Input("x")` (Attribute-style) |
| 22 | `test_run_sync_in_async_context_raises` | `run_sync()` inside async context |
| 23 | `test_prepare_monty_limits_merge` | Both load-time and run-time limits |

### Medium — Edge Cases

| # | Test | Description |
|---|---|---|
| 24 | `test_e004_match_statement` | E004 implemented but untested |
| 25 | `test_w004_long_script` | W004 (>200 lines) never tested |
| 26 | `test_yield_from_detected` | `visit_YieldFrom` — only `visit_Yield` exercised |
| 27 | `test_multiple_errors_accumulated` | Multiple simultaneous violations |
| 28 | `test_stub_complex_type_annotations` | `list[dict[str, Any]]`, `Optional[int]`, etc. |
| 29 | `test_stub_any_in_parameter_type` | `Any` in parameter types |
| 30 | `test_empty_script` | Empty `.pym` file through full pipeline |
| 31 | `test_unicode_in_script` | Unicode variables, strings, comments |

---

## 8. Summary Statistics

| Category | Count |
|----------|-------|
| Critical Issues | 6 |
| High Priority Design | 10 |
| Medium Priority Cleanup | 9 |
| Data Type Enhancements | 3 |
| Monty API Coverage | 5 |
| CLI Issues | 6 |
| **Total Issues** | **39** |
| Tests to Write | 31 |
