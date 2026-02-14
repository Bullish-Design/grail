# Grail Agent Guide

This directory contains agent-facing guidance and reusable skills for building the `grail` library.

## Project intent (quick summary)
- `grail` is a high-level Python wrapper around **Monty** focused on Pydantic-first ergonomics.
- Core docs in repo root:
  - `CONCEPT.md` (vision)
  - `SPEC.md` (API/feature specification)
  - `ARCHITECTURE.md` (components/data flow)

## Critical context source
A curated export of the Monty codebase is available at:
- `.context/monty-main/`

Use this export as the canonical local reference when validating assumptions about Monty behavior and APIs (Python bindings, examples, and tests).

## Working conventions
1. Confirm requirements in root docs before implementing.
2. Prefer minimal, typed APIs aligned to `MontyContext`, `StubGenerator`, and resource limits.
3. When integrating Monty features, verify parity against `.context/monty-main/` before finalizing code.
4. Use skills in `./skills/` for repeatable workflows.

## Suggested skill entry points
- `skills/repo-orientation/SKILL.md` for first-pass navigation.
- `skills/monty-alignment-check/SKILL.md` whenever checking that Grail uses Monty correctly.
