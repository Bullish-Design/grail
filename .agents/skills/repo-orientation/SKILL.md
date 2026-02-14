# Skill: repo-orientation

## Purpose
Fast, low-noise orientation for contributors/agents working in this repository.

## When to use
- At the start of a task.
- When requirements seem ambiguous.
- Before proposing architecture changes.

## Inputs
- User task/request.
- Root docs: `CONCEPT.md`, `SPEC.md`, `ARCHITECTURE.md`.

## Workflow
1. Read root docs in this order: concept -> spec -> architecture.
2. Extract three things: product goal, required APIs, and constraints.
3. Locate candidate implementation paths in `src/` and tests in `tests/`.
4. Summarize gaps between current code and documented target behavior.
5. Only then propose implementation steps.

## Output checklist
- Goal statement in one sentence.
- APIs/components impacted.
- Any dependency on Monty details explicitly called out.
