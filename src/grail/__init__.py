"""
Grail - Transparent Python for Monty.

A minimalist library for writing Monty code with full IDE support.
"""

__version__ = "3.0.0"

# Core functions
from grail.script import load, run

# Declarations (for .pym files)
from grail._external import external
from grail._input import Input

# Limits
from grail.limits import Limits

# Errors
from grail.errors import (
    GrailError,
    ParseError,
    CheckError,
    InputError,
    ExternalError,
    ExecutionError,
    LimitError,
    OutputError,
)

# Check result types
from grail._types import CheckResult, CheckMessage

# Define public API
__all__ = [
    # Core
    "load",
    "run",
    # Declarations
    "external",
    "Input",
    # Limits
    "Limits",
    # Errors
    "GrailError",
    "ParseError",
    "CheckError",
    "InputError",
    "ExternalError",
    "ExecutionError",
    "LimitError",
    "OutputError",
    # Check results
    "CheckResult",
    "CheckMessage",
]
