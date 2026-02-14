# Skill: monty-alignment-check

## Purpose
Efficiently verify that Grail's implementation and assumptions align with Monty's actual Python API and behavior.

## Use this skill when
- Adding/changing any Grail wrapper around Monty execution, snapshots, type checking, external functions, or limits.
- Validating names/signatures for `pydantic_monty` classes/functions.
- Confirming runtime semantics for `run`, `start/resume`, async execution, serialization, and resource limits.

## Canonical reference location
- `.context/monty-main/`

## High-value files to inspect first
1. `.context/monty-main/crates/monty-python/python/pydantic_monty/__init__.py`
2. `.context/monty-main/crates/monty-python/python/pydantic_monty/_monty.pyi`
3. `.context/monty-main/crates/monty-python/README.md`
4. `.context/monty-main/crates/monty-python/tests/`
5. `.context/monty-main/README.md` (broader capability/limitations)

## Search strategy (fast path)
Prefer targeted ripgrep queries:

```bash
# API symbols and constructors
rg -n "class Monty|class MontySnapshot|class MontyComplete|def run_monty_async|ResourceLimits" \
  .context/monty-main/crates/monty-python

# Start/resume and serialization semantics
rg -n "start\(|resume\(|dump\(|load\(" \
  .context/monty-main/crates/monty-python/{README.md,tests,python/pydantic_monty}

# Type-check integration and stubs
rg -n "type_check|type_check_stubs|ty" \
  .context/monty-main/{README.md,crates/monty-python,crates/monty-type-checking}

# External function calling patterns
rg -n "external_functions|function_name|args" \
  .context/monty-main/crates/monty-python/{README.md,tests,python/pydantic_monty}
```

## Alignment checklist
Before finalizing Grail changes, confirm:
1. Symbol names and signatures match Monty's exported Python API.
2. Execution mode assumptions (sync/async, start/resume behavior) match tests/docs.
3. Resource limit fields mapped by Grail correspond to actual Monty fields.
4. Serialization methods (`dump/load`) are used on the correct objects (`Monty`, `MontySnapshot`, etc.).
5. Type-checking behavior uses the correct flags/stub inputs accepted by Monty.

## Deliverable template
When done, provide a short "Monty alignment summary" with:
- Verified APIs
- Any mismatches found
- File paths in Grail that must be updated
