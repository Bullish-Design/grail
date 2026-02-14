"""Grail: a Pydantic-native wrapper around Monty for secure code execution."""

from .context import MontyContext
from .decorators import secure
from .errors import (
    GrailExecutionError,
    GrailLimitError,
    GrailOutputValidationError,
    GrailValidationError,
)
from .filesystem import FilePermission, GrailFilesystem, callback_filesystem, memory_filesystem
from .snapshots import (
    MontySnapshot,
    deserialize_snapshot_payload,
    serialize_snapshot_payload,
    snapshot_payload_from_base64,
    snapshot_payload_to_base64,
)
from .stubs import StubGenerator
from .tools import ToolRegistry
from .types import ResourceLimits, merge_resource_limits

__all__ = [
    "GrailExecutionError",
    "GrailLimitError",
    "GrailOutputValidationError",
    "GrailValidationError",
    "FilePermission",
    "GrailFilesystem",
    "memory_filesystem",
    "callback_filesystem",
    "MontyContext",
    "ResourceLimits",
    "snapshot_payload_to_base64",
    "snapshot_payload_from_base64",
    "serialize_snapshot_payload",
    "deserialize_snapshot_payload",
    "MontySnapshot",
    "StubGenerator",
    "ToolRegistry",
    "merge_resource_limits",
    "secure",
]

__version__ = "0.0.0"
