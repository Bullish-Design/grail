# Threat Model

## Assets
- Host filesystem integrity
- Host network boundary
- Tool invocation boundary
- Input/output data confidentiality

## Threats
- Unauthorized file reads/writes
- Unauthorized network egress
- Tool abuse via untyped/unchecked arguments
- Error/log leakage of sensitive data

## Controls
- Explicit `GrailFilesystem` permission model
- Monty sandbox restrictions and whitelisted tools
- Pydantic validation for inputs/outputs
- Structured logging hooks for auditable events
- Contract tests for negative filesystem cases
