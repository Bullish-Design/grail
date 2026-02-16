"""Snapshot wrapper for pause/resume execution."""

from typing import Any, Callable

try:
    import pydantic_monty
except ImportError:
    pydantic_monty = None

from grail._types import SourceMap


class Snapshot:
    """
    Wrapper around Monty's snapshot for pause/resume execution.

    Allows inspecting external function calls and resuming with results.
    """

    def __init__(self, monty_snapshot: Any, source_map: SourceMap, externals: dict[str, Callable]):
        """
        Initialize snapshot wrapper.

        Args:
            monty_snapshot: Underlying Monty snapshot
            source_map: Line number mapping
            externals: External function implementations
        """
        self._monty_snapshot = monty_snapshot
        self._source_map = source_map
        self._externals = externals

    @property
    def function_name(self) -> str:
        """Name of the external function being called."""
        return self._monty_snapshot.function_name

    @property
    def args(self) -> tuple[Any, ...]:
        """Positional arguments for the function call."""
        return self._monty_snapshot.args

    @property
    def kwargs(self) -> dict[str, Any]:
        """Keyword arguments for the function call."""
        return self._monty_snapshot.kwargs

    @property
    def call_id(self) -> int:
        """Unique identifier for this external call."""
        return getattr(self._monty_snapshot, "call_id", 0)

    @property
    def value(self) -> Any:
        """
        Final result value (only available when is_complete=True).

        Returns:
            Final script result

        Raises:
            RuntimeError: If execution not complete
        """
        # if not self.is_complete:
        #    raise RuntimeError("Execution not complete")
        return self._monty_snapshot.value

    def resume(
        self, return_value: Any = None, exception: BaseException | None = None
    ) -> "Snapshot":
        """
        Resume execution with a return value or exception.

        Args:
            return_value: Value to return from external function
            exception: Exception to raise in Monty

        Returns:
            New Snapshot if more calls pending, or final result
        """
        if exception is not None:
            next_snapshot = self._monty_snapshot.resume(exception=exception)
        else:
            next_snapshot = self._monty_snapshot.resume(return_value=return_value)

        return Snapshot(next_snapshot, self._source_map, self._externals)

    def dump(self) -> bytes:
        """
        Serialize snapshot to bytes.

        Returns:
            Serialized snapshot data
        """
        return self._monty_snapshot.dump()

    @staticmethod
    def load(data: bytes, source_map: SourceMap, externals: dict[str, Callable]) -> "Snapshot":
        """
        Deserialize snapshot from bytes.

        Args:
            data: Serialized snapshot data
            source_map: Line number mapping
            externals: External function implementations

        Returns:
            Restored Snapshot instance
        """
        if pydantic_monty is None:
            raise RuntimeError("pydantic-monty not installed")

        monty_snapshot = pydantic_monty.MontySnapshot.load(data)
        return Snapshot(monty_snapshot, source_map, externals)
