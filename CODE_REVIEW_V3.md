# Grail V3 — Code Review

**Date:** 2026-02-25
**Scope:** Full codebase review of `src/grail/` (14 source files, ~2,600 LOC), test suite (21 test files), and Monty API coverage analysis.

---

## Executive Summary

Grail V3 is a well-structured library with a clean public API (~15 symbols), sensible module decomposition, and a solid core pipeline (parse → check → codegen → run). The `.pym` format is a pragmatic design choice that leverages existing Python tooling.

However, the review identified several issues across three severity tiers:

**Critical (will bite users):**
- `load()` silently ignores check errors — users think their script is validated, but it isn't
- `extract_function_params` silently drops `*args`, `**kwargs`, keyword-only parameters
- `GrailDeclarationStripper` doesn't handle `ast.Assign` for `Input()` — leaves `Input()` calls in generated Monty code
- Stub generator doesn't import `typing` names other than `Any` (e.g., `Optional`, `Union`)
- `output_model` validation uses wrong Pydantic v2 API (`model(**result)` vs `model.model_validate(result)`)
- Bare `assert` in production code (`script.py:209`) — stripped by `python -O`

**Design Issues (should be addressed before v3 GA):**
- `GrailScript` not exported from `__init__.py` — users can't type-annotate the main object
- `Input()` name parameter is silently ignored — mismatch risk
- Import allowlist restricted to `{grail, typing}` — may be too restrictive for Monty's capabilities
- Error handling duplication in `script.py:400-460` (~60 lines copy-pasted)
- Legacy API in `limits.py` ships deprecated code in a v3 clean-break
- Zero logging — no `logging` module usage anywhere in source

**Test Gaps (5 features with zero test coverage):**
- `output_model` validation, `dataclass_registry`, virtual filesystem execution, exception propagation from externals, resource limit violation scenarios

---

## 1. Architecture & Design

### 1.1 Public API Surface

The `__init__.py` exports 15 symbols (`__init__.py:35-58`), which aligns precisely with the spec's stated goal of "~15 public symbols" (`GRAIL_CONCEPT.md:25`). The grouping is coherent: 3 core functions, 2 declaration markers, 1 limits type, 7 errors, and 3 result/event types.

**`GrailScript` is intentionally not exported — but should it be.** The class is the central object users interact with after `load()`, yet it cannot be referenced by name for type annotations. A user writing `def process(script: grail.GrailScript)` must instead do `from grail.script import GrailScript`, reaching into an internal module. This is a real gap. The class is already fully public in behavior (it's the return type of `load()`), so not exporting it from `__init__.py` is an artificial constraint. It should be added to `__all__`.

**`ParseResult` is not exported, and correctly so.** It's an internal pipeline type. Same for `SourceMap`, `ParamSpec`, `ExternalSpec`, and `InputSpec` — these are consumed internally. However, `ExternalSpec` and `InputSpec` *are* exposed as the value types of `GrailScript.externals` and `GrailScript.inputs` (public properties, `script.py:68-69`). Users who inspect a loaded script will receive objects they cannot type-annotate without an internal import. If these properties are meant to be public, their types should be exported. If they're not, the properties should return simpler types (dicts, named tuples).

**Spec-implementation inconsistency:** The SPEC.md documents `STRICT`, `DEFAULT`, and `PERMISSIVE` as public API constants, and `limits.py:199-201` defines them, but `__init__.py` does not export them. They should be exported

**`ScriptEvent` is exported** (`__init__.py:32`) — this is correct for typed callback signatures. Not superfluous.

### 1.2 Module Decomposition

The module split is largely sensible and follows a clean pipeline model:

| Module | Responsibility | Verdict |
|---|---|---|
| `parser.py` (354 lines) | AST extraction of externals/inputs | Clean, single-purpose |
| `checker.py` (417 lines) | Monty compatibility validation | Clean, single-purpose |
| `codegen.py` (132 lines) | AST stripping + code generation | Clean, small |
| `stubs.py` (77 lines) | Type stub generation | Clean, small |
| `script.py` (663 lines) | `GrailScript` class + `load()`/`run()`/`run_sync()` | **Too large, doing too much** |
| `errors.py` (128 lines) | Error hierarchy | Clean |
| `limits.py` (202 lines) | Resource limits + parsing | Clean |
| `artifacts.py` (149 lines) | `.grail/` directory management | Clean |
| `cli.py` (376 lines) | CLI commands | Clean |
| `_types.py` (120 lines) | Internal data types | Clean |
| `_external.py` (27 lines) | `@external` decorator | Clean, minimal |
| `_input.py` (38 lines) | `Input()` sentinel | Clean, minimal |

**`script.py` is doing triple duty.** It contains: (1) the `GrailScript` class, (2) the `load()` entry point, and (3) the standalone `run()`/`run_sync()` escape hatches. At 663 lines it's the largest module and the only one with multiple responsibilities.

**`parser.py` contains dead code.** `validate_external_function()` (`parser.py:77-129`) exists but is never called — `extract_externals()` does not invoke it. The actual validation happens only in `checker.py`. This dead function should be removed.

**`limits.py` has legacy API cruft.** Lines 173-201 define `parse_limits()`, `merge_limits()`, and `STRICT`/`DEFAULT`/`PERMISSIVE` dict constants, all deprecated in favor of the `Limits` class. For a v3 "clean-break redesign," shipping deprecated API on day one is contradictory.

### 1.3 The .pym Format

The "valid Python with decorators and sentinel functions" approach is the best design choice available:

- **vs. Custom DSL:** Would require a custom parser, custom IDE extension, and fragment the developer experience. `.pym` gets syntax highlighting, autocomplete, and type checking from Python tooling for free.
- **vs. YAML/TOML config + inline code:** Would force maintaining two files per script with inevitable drift.
- **vs. Magic comments:** Would lose type information entirely.

**Where the format gets tricky:** The `.pym` extension creates minor IDE friction — VS Code/PyCharm won't treat `.pym` files as Python out of the box. Users need to configure file associations. This should be prominently documented.

The `from grail import external, Input` line creates a dependency paradox: the `.pym` file imports `grail`, but runs in Monty where `grail` doesn't exist. The parser strips this import during codegen, so it works, but the `.pym` file is not actually executable as Python — running `python analysis.pym` would silently produce `None`. This is the intended use, but it should be noted in the documentation. 

### 1.4 The load → check → run Workflow

**`load()` runs `check_pym()` but ignores the result.** This is the most significant design issue. At `script.py:560-561`, `load()` calls `check_pym(parse_result)` but **never inspects `check_result.valid`**. Invalid scripts are silently loaded. The docstring says `load()` raises `CheckError: If declarations are malformed`, but this only happens for parse-level errors — the checker's E001-E008 errors are collected and silently swallowed.

A `.pym` file with a class definition (E001) or a `with` statement (E003) will load successfully and only fail at Monty runtime. This is a foot-gun.

**`check()` re-parses from disk.** `GrailScript.check()` (`script.py:102`) re-parses the file from disk, which is wasteful and introduces a TOCTOU issue: if the file changed between `load()` and `check()`, the check validates different code than what was loaded.

**`run()` redundantly type-checks.** At `script.py:369-377`, `run()` creates a `Monty()` with `type_check=True`. But `check()` also does this at `script.py:109-116`. Users who call both pay the type-checking cost twice with no way to skip the redundant check.

### 1.5 The `_external.py` and `_input.py` Sentinel Modules

**`_external.py`:** The decorator sets `__grail_external__ = True` on the function (`_external.py:25`), but this attribute is **never read anywhere** in the codebase. The parser identifies externals by matching the decorator name in the AST. The `setattr` is dead code.

**`_input.py`:** `Input()` returns `default` (or `None`). The `@overload` signatures are a nice touch for IDE support. However, the `name` parameter is redundant and ignored — the parser at `parser.py:222` uses the variable name, not the string argument. So `budget: float = Input("totally_wrong")` silently uses `budget` as the input name. This should be reconciled —  validate that the string matches the variable name.

### 1.6 Dependency Management

**`pydantic-monty` is a hard dependency but treated as optional.** `pyproject.toml:16` lists it as required, but `script.py:10-13` wraps the import in `try/except ImportError`. These contradict each other. It needs to be treated as a hard dependency. 

### 1.7 Summary of Priority Issues

1. **`load()` silently ignores check errors** — `script.py:560-561`
2. **`GrailScript` not exported** — users can't type-annotate the most important object
3. **`Input()` name parameter is ignored** — `parser.py:222` vs string argument
4. **`pydantic-monty` listed as required but imported as optional** — pick one
5. **`validate_external_function()` is dead code** — `parser.py:77-129`
6. **`check()` re-parses from disk** — TOCTOU risk
7. **Legacy API shipped in a v3 clean-break** — `limits.py:173-201`

---

## 2. Core Pipeline — Parser, Checker, Codegen, Stubs

### 2.1 Parser (`parser.py`)

**Decorator recognition is partial.** `extract_externals` (`parser.py:148-177`) checks for both `ast.Name` (`@external`) and `ast.Attribute` (`@grail.external`). However, aliased imports like `from grail import external as ext` will silently fail — `@ext` produces `ast.Name(id="ext")`, which doesn't match `decorator.id == "external"`. This is a **latent bug** if anyone uses aliased imports. This needs to be flagged for investigation to determine a solution. In the meantime, document it as unsupported.

**`extract_function_params` silently drops `*args`, `**kwargs`, and keyword-only parameters.** The function at `parser.py:34-74` only iterates over `func_node.args.args` (positional arguments). It completely ignores `func_node.args.vararg`, `func_node.args.kwarg`, `func_node.args.kwonlyargs`, and `func_node.args.posonlyargs`. If a user writes `@external async def fetch(*args, **kwargs) -> str: ...`, the extracted `ParamSpec` list will be empty. This is **silent data loss** — no error raised, params are just gone.

**Recommendation:** Raise an error for unsupported parameter kinds (if Monty doesn't support them) and extract them properly. Silent omission is the worst option.

**`extract_inputs` has duplicated logic.** The `ast.AnnAssign` branch (`parser.py:198-246`) and the `ast.Assign` branch (`parser.py:249-283`) contain nearly identical `is_input_call` detection and `default` extraction logic. Should be refactored into a helper.

**`parse_pym_file` vs `parse_pym_content` is near-duplicate.** `parse_pym_file` should call `parse_pym_content` internally — the only difference is file I/O vs string input.

**Error handling is inconsistent between parser and checker.** The parser raises `CheckError` (hard failures) for malformed declarations, while the checker re-validates the same conditions but emits `CheckMessage` objects (soft failures). The two systems need to agree on which layer owns validation. Give recommendations. 

### 2.2 Checker (`checker.py`)

**The import allowlist is too restrictive — likely a bug.** `visit_ImportFrom` at `checker.py:129` hardcodes `{"grail", "typing"}` as the only allowed modules. However, Monty supports standard library modules like `sys`, `asyncio`, `dataclasses`, `pathlib`, `os`. If a `.pym` file needs `from dataclasses import dataclass`, the checker will flag it as E005 even though Monty executes it fine.

**`visit_Import` has an asymmetry with `visit_ImportFrom`:** `import grail` would trigger E005 (only `typing` is exempted), but `from grail import ...` is correctly allowed. The error message says "Import 'grail' is not allowed in Monty" which is misleading.

**`check_declarations` duplicates parser validation.** `check_declarations` (`checker.py:183-284`) re-walks the AST to check external function bodies (E007), which is the same validation `validate_external_function` does at `parser.py:77-129`. The parser check raises eagerly, the checker emits messages. Contradictory pattern.

**Missing Monty compatibility checks:** The checker catches classes (E001), generators (E002), `with` (E003), `match` (E004), and bad imports (E005). Notably absent: `global`/`nonlocal`, `del` statements, nested closures, and lambda expressions. Whether these matter depends on Monty's actual capabilities, but the checker should be explicit.

**W002/W003 reference tracking has a subtle edge case.** The `referenced_names` set at `checker.py:344-349` adds `node.attr` for `ast.Attribute(Load)`, meaning `obj.fetch` would suppress W002 for an external named `fetch` even when they're unrelated. Minor false-negative risk.

**`check_pym` hardcodes `file="<unknown>"` at `checker.py:411`.** The callers don't override it, making the `file` field meaningless.

### 2.3 Codegen (`codegen.py`)

**`ast.unparse()` destroys all formatting, comments, and blank lines — this is not documented.** At `codegen.py:117`, all comments are lost, all blank lines gone, all formatting replaced with `ast.unparse`'s canonical output. This is a significant UX issue for debugging. Should be documented prominently.

**`GrailDeclarationStripper` does NOT handle `ast.Assign` for Input() — confirmed bug.** The stripper handles `visit_AnnAssign` at `codegen.py:49-53` but has no `visit_Assign` method. The parser correctly extracts inputs from `x = Input("x")`, but codegen fails to strip them, leaving `Input("x")` in generated Monty code where `Input` is not defined.

**`build_source_map` relies on `ast.walk` BFS order being identical across two ASTs.** This works by accident because the AST transformation only removes nodes without restructuring. If the transformation ever changes structure, the zip at `codegen.py:89` would silently produce wrong mappings. The docstring reasoning is inaccurate about why this works. Needs a fix. 

**`copy.deepcopy` of the AST is necessary and correct.** Prevents mutating the original `ParseResult.ast_module`. Performance is fine for the file sizes Grail processes.

### 2.4 Stubs (`stubs.py`)

**`_needs_any_import` regex is correct.** `\bAny\b` at `stubs.py:10` handles word boundaries properly — `AnyThing`, `MyAny` will NOT match.

**Missing imports beyond `Any`.** The generator at `stubs.py:30-45` only checks for `Any`. If annotations use `Optional`, `Union`, `Dict`, `List`, or other `typing` constructs, the generated stub will reference them without importing them. **This produces invalid stubs.**

**Docstrings in stubs are not escaped.** At `stubs.py:71`, if the docstring contains triple quotes, the generated stub has a syntax error.

### 2.5 Data Types (`_types.py`)

**`ParamSpec` is missing a `kind` field.** It has no way to represent positional-only, keyword-only, `*args`, or `**kwargs` parameters. If `extract_function_params` is fixed, `ParamSpec` needs this.

**`ParseResult` doesn't store the source file path.** This contributes to the `file="<unknown>"` issue in `check_pym`.

**`InputSpec` doesn't capture the `Input()` name argument.** Only the variable name is stored, making it impossible to detect mismatches like `x: int = Input("y")`.

### 2.6 Summary of Critical Issues

| Severity | Issue | Location |
|----------|-------|----------|
| **Bug** | `GrailDeclarationStripper` doesn't handle `ast.Assign` Input() | `codegen.py:49-53` (missing `visit_Assign`) |
| **Bug** | `extract_function_params` silently drops `*args`, `**kwargs`, keyword-only params | `parser.py:46` |
| **Bug** | Stub generator doesn't import `typing` names other than `Any` | `stubs.py:30-45` |
| **Design** | Import allowlist is `{"grail", "typing"}` only | `checker.py:129` |
| **Design** | Parser and checker duplicate validation | `parser.py:77-129` vs `checker.py:228-267` |
| **Design** | `ParseResult` doesn't store file path | `_types.py:44-51` |
| **Fragile** | `build_source_map` relies on `ast.walk` BFS order | `codegen.py:75-92` |

---

## 3. Runtime & Execution

### 3.1 Duplicated Error Handling (`script.py:400-460`)

Lines 400-429 and 430-460 are structurally identical. Both catch an exception, set `success = False` and `error_msg`, call `self._map_error_to_pym(e)`, conditionally fire `on_event`, conditionally write artifact logs, and `raise mapped_error`. The *only* difference is the exception type in the `except` clause. This is ~30 lines of pure copy-paste duplication.

Additionally:
- `success` (line 401/432) and `error_msg` (line 402/433) are assigned but **never read** — dead stores.
- `duration_ms` is computed twice within each block — once for the event callback and again for artifacts. The two values differ by the time spent in `on_event()`.

**Recommendation:** Collapse to a single `except Exception as e:` block, or extract a `_handle_run_error()` method. Remove dead stores. Compute `duration_ms` once.

### 3.2 Bare `assert` in Production Code (`script.py:209`)

```python
if base is None:
    assert override_limits is not None
    return override_limits.to_monty()
```

When Python runs with `-O`, all `assert` statements are stripped. This assert narrows `Limits | None` to `Limits` for the type checker. With `-O`, if `override_limits` were `None`, it would produce `None.to_monty()` — an inscrutable `AttributeError`.

In practice, the guard on line 206 guarantees `override_limits is not None` here, so the assert is logically unreachable. Replace with `# type: ignore[union-attr]` or restructure the logic.

### 3.3 Input/External Validation — Warnings vs. Errors (`script.py:150-197`)

Both `_validate_inputs` and `_validate_externals` issue `warnings.warn()` for extra (undeclared) keys. This creates a real risk:

- **Typos become silent failures.** Passing `{"nme": "Alice"}` when the script declares `name = Input(str)` produces a warning (easily missed) and the script runs with `name` at its default or raises for the missing required input.
- **`stacklevel=2` is fragile** — it points at `run()`, not the user's code. Should be `stacklevel=3` or higher.

**Recommendation:** Consider making extra inputs/externals a hard error by default, with opt-in `strict=False`.

### 3.4 `_prepare_monty_files` — Only `MemoryFile` (`script.py:215-237`)

Only supports `dict[str, str | bytes]` → `MemoryFile`. No `CallbackFile`, no `environ`, no `AbstractOS`. Users needing these must bypass `GrailScript` entirely. Consider accepting `pydantic_monty.OSAccess` directly as an alternative parameter in a future release.

### 3.5 `_map_error_to_pym` — Regex Fragility (`script.py:266-271`)

The regex fallback `re.search(r"line (\d+)", error_msg, re.IGNORECASE)` has problems:

1. **False positives:** `"Error processing inline 42 data"` extracts `42` as a line number.
2. **No word boundary.** `"deadline 3"` extracts `3`.
3. **Unmapped line numbers leak through.** `source_map.monty_to_pym.get(monty_line, monty_line)` falls back to the raw Monty line number, which will be meaningless to the user.

**Recommendation:** Add `\b` word boundaries. Better yet, set `lineno = None` when structured traceback is unavailable rather than guessing.

### 3.6 Limit Detection by String Matching (`script.py:273-283`)

```python
if "memory" in error_msg_lower:
    limit_type = "memory"
```

Any error message containing "memory" (e.g., `"Failed to access memory address"`) will be classified as a `LimitError`. The check on line 282 means if *any* keyword matched, the error becomes a `LimitError` even without "limit" in the message.

**Recommendation:** Check the exception *type* first. At minimum require *both* a keyword and `"limit"` in the message.

### 3.7 `output_model` Validation (`script.py:487-493`)

```python
result = output_model(**result) if isinstance(result, dict) else output_model(result)
```

Problems:
1. **Wrong Pydantic v2 API.** `MyModel(42)` passes `42` as the first positional arg, which maps to the first declared field. The correct call is `output_model.model_validate(result)`.
2. **Non-Pydantic models.** The parameter is typed as `type`, not `type[BaseModel]`. Behavior is unpredictable for dataclasses or TypedDicts.
3. **`isinstance(result, dict)` is too narrow.** Consider `isinstance(result, Mapping)`.

### 3.8 Inline `run()` — Missing Features (`script.py:594-633`)

The module-level `run()` has no limits, no type checking, no externals, no files, no error mapping, and no event callbacks. Documented as "escape hatch for simple cases," but:

1. **No limits is dangerous.** An infinite loop hangs indefinitely. Add a `limits` parameter with a default of `Limits.default()`.
2. **The conditional branching is unnecessary.** Lines 620-633 create a 2×3 matrix of code paths to avoid passing `None`/`{}` to Monty. This can collapse to 2-3 lines.

### 3.9 `run_sync()` — Acceptable (`script.py:497-526`)

The async context detection pattern is correct and standard. The one unhandled edge case is `nest_asyncio` (common in Jupyter), but this is an acceptable trade-off.

Note: `GrailScript.run_sync()` stores the loop in `loop` (line 519) but never uses it — minor dead variable.

### 3.10 Error Hierarchy (`errors.py`)

**`LimitError.__init__` drops most `ExecutionError` fields.** It only passes `message` — `lineno`, `col_offset`, `source_context`, and `suggestion` all default to `None`. The subclass relationship is misleading — `LimitError` doesn't behave like an `ExecutionError` with location information.

**Should `LimitError` extend `ExecutionError`?** Limits are a resource concern, not a code execution error. A user catching `ExecutionError` will also catch `LimitError`, which may not be intended. Consider making it a sibling under `GrailError`.

**`_build_context_display` line indexing is correct** but undocumented — no note explaining the 1-indexed convention.

**`OutputError.validation_errors` is typed as `Any`.** Should be `Exception | None` at minimum.

### 3.11 Limits Model (`limits.py`)

The `Limits` model is well-designed. Coverage is complete for all 5 Monty resource limits:

| Grail field | Monty field | Covered? |
|---|---|---|
| `max_memory` | `max_memory` | Yes |
| `max_duration` | `max_duration_secs` | Yes (renamed) |
| `max_recursion` | `max_recursion_depth` | Yes (renamed) |
| `max_allocations` | `max_allocations` | Yes |
| `gc_interval` | `gc_interval` | Yes |

`to_monty()`, `merge()`, and presets (`strict`/`default`/`permissive`) all work correctly.

### 3.12 Legacy API — Should Be Removed (`limits.py:176-201`)

`parse_limits()`, `merge_limits()`, `STRICT`, `DEFAULT`, `PERMISSIVE` are defined but:
- Not imported anywhere in the codebase
- Not exported from `__init__.py`
- Not used in any test
- Have no `warnings.warn("deprecated")` call

For a v3 library, remove entirely.

### 3.13 Summary of Recommendations

| # | Issue | Severity | Effort |
|---|---|---|---|
| 3.1 | Duplicate error handling blocks | Medium | Low |
| 3.2 | Bare `assert` | High | Trivial |
| 3.3 | Extra inputs/externals should be errors | Medium | Low |
| 3.5 | Regex line extraction false positives | High | Low |
| 3.6 | Limit detection by string matching | Medium | Medium |
| 3.7 | `output_model` wrong Pydantic v2 API | Medium | Low |
| 3.8 | Inline `run()` has no limits | Medium | Low |
| 3.10 | `LimitError` hierarchy questionable | Medium | Medium |
| 3.12 | Legacy API is dead code | Medium | Trivial |

---

## 4. Monty API Coverage Gaps

### Coverage Summary

| # | Capability | Verdict | Key Gap |
|---|---|---|---|
| 4.1 | Async execution | **COVERED** | — |
| 4.2 | External functions | **COVERED** | — |
| 4.3 | Inputs | **COVERED** | — |
| 4.4 | Print callback | **PARTIALLY COVERED** | Stream type hint is `str` not `Literal['stdout']` |
| 4.5 | OS Access / VFS | **PARTIALLY COVERED** | No `CallbackFile`, no custom `AbstractOS`, no env vars, no `root_dir` |
| 4.6 | Type checking | **PARTIALLY COVERED** | 9 display formats unused; `str(e)` only |
| 4.7 | Resource limits | **COVERED** | — |
| 4.8 | Dataclass support | **COVERED** | — |
| 4.9 | Error types | **PARTIALLY COVERED** | `display()` methods unused; `MontySyntaxError` not specifically caught; `Frame` fields mostly ignored |
| 4.10 | Serialization | **NOT COVERED** | `dump()`/`load()` not wrapped (likely intentional) |
| 4.11 | Bidirectional types | **COVERED** | — |
| 4.12 | Threading/GIL | **NOT COVERED** | Works implicitly but undocumented/untested |

### 4.1 Async Execution — COVERED

Grail calls `pydantic_monty.run_monty_async()` at `script.py:390-397` for `.pym` execution and `script.py:626-632` for inline `grail.run()`. Monty's implementation handles both sync and async external functions transparently. `asyncio.gather()` inside Monty code works correctly through Grail.

### 4.2 External Functions — COVERED

Grail validates declared externals are provided (`script.py:176-197`) then passes the raw `externals` dict straight through to `run_monty_async(external_functions=externals)` at `script.py:392`. Monty handles args/kwargs passthrough, exception propagation, and try/except catching.

### 4.3 Inputs — COVERED

All Monty-supported input types flow through unmodified since Grail passes the raw dict. Validation at `script.py:150-174` checks for missing required inputs and warns on extras.

### 4.4 Print Callback — PARTIALLY COVERED

Grail wraps the print callback at `script.py:334-346`. Minor issue: Grail's type hint uses `str` for the stream parameter rather than `Literal['stdout']`, slightly misrepresenting what Monty actually emits (Monty only ever sends `'stdout'`).

### 4.5 OS Access / Virtual Filesystem — PARTIALLY COVERED

Grail wraps OS access at `script.py:215-237`, converting `dict[str, str|bytes]` to `MemoryFile` + `OSAccess`.

**What's NOT covered:**
1. **`CallbackFile`** — Users cannot provide callback-backed files through the Grail API
2. **`AbstractOS` subclassing** — Users cannot provide a custom OS implementation
3. **Environment variables** — `OSAccess` accepts an `environ` dict, but Grail never passes one. Scripts using `os.getenv()` get empty results
4. **`root_dir` parameter** — Not exposed
5. **Inline `grail.run()`** — Doesn't accept `files` or `os` at all

### 4.6 Type Checking — PARTIALLY COVERED

Grail integrates Monty's type checker at check time (`script.py:107-130`) and run time (`script.py:368-385`). But:

- **`MontyTypingError.display()` formats** — Monty provides 9 output formats (`'full'`, `'concise'`, `'azure'`, `'json'`, `'jsonlines'`, `'rdjson'`, `'pylint'`, `'gitlab'`, `'github'`) with optional color. Grail uses only `str(e)`, discarding all structured diagnostic information. IDE-friendly formats are lost.
- **`MontySyntaxError.display()`** — Has `'type-msg'` and `'msg'` formats. Grail uses `str(e)` only.

### 4.7 Resource Limits — COVERED

All 5 Monty resource limits are mapped correctly by `Limits.to_monty()` (`limits.py:150-170`).

### 4.8 Dataclass Support — COVERED

`dataclass_registry` is accepted at `load()` (`script.py:534`) and passed to `Monty()` at `script.py:376`.

### 4.9 Error Types — PARTIALLY COVERED

| Monty error | Grail handling | Quality |
|---|---|---|
| `MontyRuntimeError` | Caught at `script.py:400`, mapped via `_map_error_to_pym()` | Good — uses `traceback()` |
| `MontyTypingError` | Caught at `script.py:378,400` | Loses structured diagnostics |
| `MontySyntaxError` | Generic `except Exception` at `script.py:430` | Not specifically handled |

**Specific gaps:**
1. `MontyRuntimeError.display()` — provides `'traceback'`, `'type-msg'`, `'msg'` formats. Grail only uses `str(e)` and `traceback()`.
2. `MontyError.exception()` — returns the inner Python exception. Grail never calls this, so original exception types are lost.
3. `Frame` properties — Grail reads `frame.line` and `frame.column` but ignores `frame.filename`, `frame.end_line`, `frame.end_column`, `frame.function_name`, and `frame.source_line`.
4. `MontySyntaxError` — should be caught and mapped to `ParseError`, not generic `ExecutionError`.

### 4.10 Serialization — NOT COVERED

Monty provides `dump()` → `bytes` and `load(bytes)` → `Monty`. Every `grail.load()` call re-parses and re-compiles. For repeated execution of the same script, this is a performance gap. Likely intentional for v3, but should be documented.

### 4.11 Bidirectional Types — COVERED

Grail performs no type conversion — all Monty-supported types pass through.

### 4.12 Threading / GIL Release — NOT COVERED

Monty releases the GIL during execution, enabling true parallel execution. Grail doesn't expose, document, or test this. Users have no way to know concurrent `run()` calls are safe without reading Monty's internals.

### Priority Recommendations

1. **High — OS Access enrichment** (4.5): Allow `AbstractOS` or at minimum env vars
2. **High — Error richness** (4.9): Use `MontyError.exception()`, `Frame.function_name`/`source_line`, catch `MontySyntaxError` explicitly
3. **Medium — Type checking diagnostics** (4.6): Expose `display(format='full')` for richer diagnostics
4. **Low — Serialization** (4.10): Document intentional omission
5. **Low — Threading docs** (4.12): Document that concurrent `run()` calls are safe

---

## 5. Test Suite Completeness

### Overview

The test suite contains 14 unit test files, 5 integration test files, and 7 fixture files. Coverage is generally good for the core pipeline (parse → check → codegen → stubs) but has significant gaps in runtime execution paths, edge cases, and several features that exist in `script.py` but are never exercised.

### 5.1 Parser Tests — Well Covered, Minor Gaps

**Covered:** Basic parsing, multiple externals, missing annotations, non-ellipsis body, syntax errors, docstrings, defaults, nested scope filtering.

**Missing:**
| Test | Description |
|---|---|
| `test_parse_grail_dot_external_style` | `@grail.external` (Attribute-style) handled in `parser.py:157` but never tested |
| `test_parse_grail_dot_input_style` | `grail.Input("x")` (Attribute-style) handled in `parser.py:205,256` but never tested |
| `test_parse_sync_external` | All fixtures use `async def`. Sync `@external def foo(x: int) -> int: ...` never parsed |
| `test_parse_input_no_args_raises` | `Input()` with no positional arg should raise `CheckError` — untested |
| `test_parse_empty_file` | Empty `.pym` file — untested edge case |

### 5.2 Checker Tests — Good, Gaps in E004/W004

**Covered:** E001-E003, E005-E008, W001-W003, info collection, feature tracking.

**Missing:**
| Test | Description |
|---|---|
| `test_e004_match_statement` | E004 implemented in `checker.py:91` but has no test |
| `test_w004_long_script` | W004 (>200 lines) implemented in `checker.py:323` but never tested |
| `test_yield_from_detected` | `visit_YieldFrom` at `checker.py:59` — only `visit_Yield` exercised |
| `test_multiple_errors_accumulated` | Multiple simultaneous violations — never tested |

### 5.3 Codegen Tests — Good Coverage

**Covered:** Import stripping, external stripping, input stripping, code preservation, source map accuracy, AST immutability.

**Missing:**
| Test | Description |
|---|---|
| `test_codegen_preserves_comments` | Whether comments survive (they don't — should document) |
| `test_codegen_multiple_external_stripping` | Source map gap accumulation with multiple externals |
| `test_codegen_empty_script` | Empty source input |

### 5.4 Stubs Tests — Partial

**Covered:** Simple stubs, `Any` import, defaults, multiple declarations, `Any` boundary detection.

**Missing:**
| Test | Description |
|---|---|
| `test_stub_complex_type_annotations` | `list[dict[str, Any]]`, `Optional[int]`, `tuple[str, ...]` — untested |
| `test_stub_any_in_parameter_type` | `Any` in parameter types (not just return type) — untested |
| `test_stub_no_externals_no_inputs` | Empty stubs — untested |

### 5.5 Script/run Tests — Partially Covered

**Covered (unit):** Load, check, input validation, external validation, limits, files, artifacts, error mapping.

**Missing:**
| Test | Description |
|---|---|
| `test_run_without_pydantic_monty_raises` | `pydantic_monty is None` path — untested |
| `test_run_sync_in_async_context_raises` | `run_sync()` inside async context — untested |
| `test_prepare_monty_limits_merge` | Both load-time and run-time limits — untested |
| `test_load_with_dataclass_registry` | `dataclass_registry` parameter — untested |

### 5.6 Integration Tests — Good but Runtime-Heavy Gaps

**Covered:** Full load → check → run workflow, artifacts, inline run, limits (within bounds), print callback, on_event (success path), external functions, type checking, error handling.

**Missing:**
| Test | Description |
|---|---|
| `test_integration_sync_external` | Sync (non-async) external — all tests use async |
| `test_integration_external_raises_exception` | External that raises during execution — untested |
| `test_integration_default_input_used` | Required input omitted but default provided — untested |

### 5.7-5.16: Features with Zero or Near-Zero Test Coverage

**OS Access / Files (Zero Coverage):**
`_prepare_monty_files()` is never exercised with actual file I/O. `test_load_with_files` only checks the dict is stored.

| Test Needed | Description |
|---|---|
| `test_run_with_virtual_file_read` | Script reads from virtual file via `open()` |
| `test_run_with_virtual_file_write` | Script writes to virtual file |
| `test_files_override_at_runtime` | `files` at `run()` overrides `files` from `load()` |

**Exception Propagation from Externals (Zero Coverage):**
| Test Needed | Description |
|---|---|
| `test_external_raises_value_error` | External raises `ValueError` → should propagate as `ExecutionError` |
| `test_external_raises_with_try_except_in_script` | Script wraps external in try/except |

**Resource Limit Violations (Zero Coverage):**
`test_with_resource_limits` runs within limits. No test triggers an actual violation.

| Test Needed | Description |
|---|---|
| `test_memory_limit_exceeded` | Allocate beyond `max_memory` → `LimitError(limit_type="memory")` |
| `test_duration_limit_exceeded` | Infinite loop with `max_duration="100ms"` → `LimitError(limit_type="duration")` |
| `test_recursion_limit_exceeded` | Deep recursion → `LimitError(limit_type="recursion")` |

**`output_model` Validation (Zero Coverage):**
| Test Needed | Description |
|---|---|
| `test_output_model_valid` | Result validated against Pydantic model — success |
| `test_output_model_invalid_raises_output_error` | Mismatched result → `OutputError` |

**Dataclass Round-trips (Zero Coverage):**
| Test Needed | Description |
|---|---|
| `test_run_with_dataclass_input` | Pass dataclass instance as input |
| `test_run_with_dataclass_output` | Script returns dataclass instance |
| `test_dataclass_registry_passed_to_monty` | Registry forwarded to Monty constructor |

**Print Callback on `GrailScript.run()` (Zero Coverage):**
`test_print_callback_captures_output` tests `grail.run()` (inline), not `GrailScript.run()`.

**on_event Error/Print Events (Partial):**
Only success path (`run_start`/`run_complete`) tested. `run_error`, `print`, `check_start`/`check_complete` events untested.

**Type Error Reporting (Partial):**
`GrailScript.check()` catches `MontyTypingError` → E100 at `script.py:117-130`, but this path is never triggered in tests.

### 5.17 Edge Cases — Mostly Untested

| Test Needed | Description |
|---|---|
| `test_empty_script` | Empty `.pym` file through full pipeline |
| `test_unicode_in_script` | Unicode variables, strings, comments |
| `test_large_output` | Script returning very large dict/list |
| `test_script_with_only_imports` | Only `from grail import external` — no code |
| `test_script_result_is_none` | Script with no final expression |

### 5.18 Priority Gaps

**Critical (features with zero test coverage):**
1. `output_model` validation — fully implemented, completely untested
2. `dataclass_registry` — accepted, forwarded, completely untested
3. Virtual filesystem execution — `_prepare_monty_files()` never exercises actual file I/O
4. Exception propagation from externals — no test for external functions that throw
5. Resource limit violations — no test actually triggers a limit exceeded scenario

**High (important paths partially covered):**
6. on_event error/print events
7. Type error reporting (E100)
8. `@grail.external` / `grail.Input()` style
9. Sync external execution
10. Legacy limits API

---

## 6. CLI, Artifacts & Peripheral Modules

### 6.1 CLI (`cli.py`)

**Bug: `spec.loader` null dereference in `cmd_run`.** At `cli.py:217-219`, `spec_from_file_location` can return `None`, and `spec.loader` can be `None`. Both produce `AttributeError` — an ugly traceback that leaks implementation details. The `host_path.exists()` check at `cli.py:213` guards the most common case, but edge cases remain. Add null checks:

```python
spec = importlib.util.spec_from_file_location("host", host_path)
if spec is None or spec.loader is None:
    print(f"Error: Cannot load host file {host_path}", file=sys.stderr)
    return 1
```

**Security: `cmd_run` executes arbitrary Python in-process.** At `cli.py:219`, `spec.loader.exec_module(host_module)` runs arbitrary code from the `--host` file with full process privileges. This is architecturally intentional but undocumented — the `--host` flag description just says `"Host Python file with main() function"`.

**Error handling boilerplate.** Every `cmd_*` function repeats the same `try/except` pattern for `ParseError`, `GrailError`, `FileNotFoundError`. Copy-pasted 5 times. Should be a decorator.

**`cmd_watch` is the only command without error handling.** If `cmd_check` throws during watch, it produces an unhandled traceback instead of the friendly error message every other command provides.

**`cmd_watch` never returns an exit code.** No `return` on any success path. Ctrl+C produces an uncaught `KeyboardInterrupt` traceback instead of a clean exit.

**`cmd_check` JSON output ignores `--strict` flag.** In text mode, `--strict` causes warnings to be treated as failures. In JSON mode, the flag is silently ignored.

**Missing CLI features:**
- No `--version` flag
- All `--input` values are strings — no type coercion. `x: int = Input("x")` receives `"5"` not `5`
- `RuntimeError("pydantic-monty not installed")` is not a `GrailError` subclass — produces raw traceback instead of friendly error

### 6.2 Artifacts (`artifacts.py`)

**No atomic writes.** All writes use `Path.write_text()` directly. Concurrent processes or crashes can corrupt files.

**No error handling for unwritable directories.** `mkdir(parents=True, exist_ok=True)` on a read-only filesystem raises `PermissionError`, which propagates from `load()`. Artifact writing is a side effect — a read-only filesystem should not prevent loading.

**`clean()` uses `shutil.rmtree` without safeguards.** At `artifacts.py:145-148`, if a caller accidentally passes `/` or a critical path, this deletes it recursively. A sanity check (verify basename is `.grail`) would be prudent.

**Duplicate serialization logic.** The `check.json` serialization at `artifacts.py:58-76` duplicates the JSON structure in `cli.py:101-126`. Should be a method on `CheckResult`.

**No schema versioning.** JSON artifacts have no version field for format compatibility detection.

### 6.3 Sentinel Modules

**`_external.py`:** The `__grail_external__ = True` attribute at `_external.py:25` is dead code — never read by any module. The decorator is a pure identity function in practice. The docstring states requirements it doesn't enforce.

**`_input.py`:** `Input()` returns `default` (or `None`). No way to distinguish "no default" from "default is None" — the parser handles this at the AST level, but runtime introspection can't differentiate `Input("x")` from `Input("x", default=None)`.

### 6.4 Cross-cutting Concerns

**Logging: completely absent.** Zero use of Python's `logging` module anywhere in `src/grail/`. All diagnostic output is `print()` to stdout/stderr. Library consumers cannot adjust verbosity programmatically. For a v3 library, this is a significant gap.

**Path handling inconsistency.** `load()` accepts `str | Path`, `ArtifactsManager.__init__` accepts only `Path`. Minor but inconsistent.

**Hardcoded values.** The `.grail` directory name appears in `cli.py:19`, `cli.py:287`, and `script.py:533` with no central constant.

---

## 7. Consolidated Recommendations

### Critical — Fix Before v3 GA

| # | Issue | Location | Effort |
|---|---|---|---|
| 1 | `load()` silently ignores check errors | `script.py:560-561` | Low |
| 2 | `extract_function_params` drops `*args`/`**kwargs` silently | `parser.py:46` | Medium |
| 3 | `GrailDeclarationStripper` doesn't strip `ast.Assign` Input() | `codegen.py:49-53` | Low |
| 4 | Stub generator doesn't import `typing` names beyond `Any` | `stubs.py:30-45` | Low |
| 5 | `output_model` uses wrong Pydantic v2 API | `script.py:487-493` | Low |
| 6 | Bare `assert` stripped by `python -O` | `script.py:209` | Trivial |

### High — Design Issues

| # | Issue | Location | Effort |
|---|---|---|---|
| 7 | Export `GrailScript` from `__init__.py` | `__init__.py` | Trivial |
| 8 | `Input()` name parameter silently ignored | `parser.py:222` | Medium |
| 9 | Import allowlist too restrictive | `checker.py:129` | Low |
| 10 | ~60 lines duplicated error handling | `script.py:400-460` | Low |
| 11 | Regex line extraction has false positives | `script.py:266-271` | Low |
| 12 | Limit detection by string matching | `script.py:273-283` | Medium |
| 13 | `check()` re-parses from disk (TOCTOU) | `script.py:102` | Medium |
| 14 | No logging anywhere | All of `src/grail/` | Medium |

### Medium — Cleanup

| # | Issue | Location | Effort |
|---|---|---|---|
| 15 | Remove dead `validate_external_function()` | `parser.py:77-129` | Trivial |
| 16 | Remove legacy limits API | `limits.py:176-201` | Trivial |
| 17 | `pydantic-monty` — pick hard or optional dep | `pyproject.toml` + `script.py:10-13` | Low |
| 18 | `LimitError` hierarchy — sibling not child | `errors.py:113-118` | Medium |
| 19 | `spec.loader` null check in CLI | `cli.py:217-219` | Trivial |
| 20 | `cmd_watch` missing error handling + KeyboardInterrupt | `cli.py:254` | Low |
| 21 | Artifact writes should not block `load()` | `artifacts.py:47` | Low |
| 22 | `MontySyntaxError` should map to `ParseError` | `script.py:430` | Low |

### Test Gaps — Write These Tests

1. `output_model` validation (valid, invalid, dict, scalar)
2. `dataclass_registry` round-trip
3. Virtual filesystem read/write execution
4. External function exception propagation
5. Resource limit violation scenarios (memory, duration, recursion)
6. `on_event` error and print events
7. Type error E100 path in `check()`
8. `@grail.external` and `grail.Input()` attribute-style declarations
9. Sync external execution end-to-end
10. `run_sync()` in async context error
