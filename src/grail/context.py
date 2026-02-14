"""MontyContext orchestration for validated sandbox execution."""

from __future__ import annotations

import asyncio
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .types import ResourceLimits, merge_resource_limits

InputT = TypeVar("InputT", bound=BaseModel)


class GrailExecutionError(RuntimeError):
    """Raised when Monty fails during code execution."""


class GrailValidationError(ValueError):
    """Raised when Grail input validation fails."""


class GrailLimitError(GrailExecutionError):
    """Raised when execution appears to violate configured limits."""


class MontyContext(Generic[InputT]):
    """Minimal context for validated execution in Monty."""

    def __init__(self, input_model: type[InputT], limits: ResourceLimits | None = None) -> None:
        self.input_model = input_model
        self.limits = merge_resource_limits(limits)

    async def execute_async(self, code: str, inputs: InputT | dict[str, Any]) -> Any:
        """Validate input data and execute code in Monty."""
        validated_inputs = self._validate_inputs(inputs)
        serialized_inputs = validated_inputs.model_dump(mode="python")

        from pydantic_monty import Monty, MontyError, MontyRuntimeError, run_monty_async

        try:
            runner = Monty(code, inputs=["inputs"])
            return await run_monty_async(
                runner,
                inputs={"inputs": serialized_inputs},
                limits=self.limits,
            )
        except MontyRuntimeError as exc:
            if "limit" in str(exc).lower() or "recursion" in str(exc).lower():
                raise GrailLimitError(f"Monty resource limit hit: {exc}") from exc
            raise GrailExecutionError(f"Monty runtime error: {exc}") from exc
        except MontyError as exc:
            raise GrailExecutionError(f"Monty execution failed: {exc}") from exc

    def execute(self, code: str, inputs: InputT | dict[str, Any]) -> Any:
        """Synchronous wrapper around :meth:`execute_async`."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.execute_async(code, inputs))
        raise RuntimeError(
            "MontyContext.execute() cannot be called from an active event loop; "
            "use MontyContext.execute_async() instead."
        ) from None

    def _validate_inputs(self, inputs: InputT | dict[str, Any]) -> InputT:
        if isinstance(inputs, self.input_model):
            return inputs

        try:
            return self.input_model.model_validate(inputs)
        except ValidationError as exc:
            message = f"Input validation failed for {self.input_model.__name__}: {exc}"
            raise GrailValidationError(message) from exc
