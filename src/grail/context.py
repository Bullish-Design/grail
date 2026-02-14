"""MontyContext orchestration for validated sandbox execution."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .stubs import StubGenerator
from .tools import ToolRegistry
from .types import ResourceLimits, merge_resource_limits

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class GrailExecutionError(RuntimeError):
    """Raised when Monty fails during code execution."""


class GrailValidationError(ValueError):
    """Raised when Grail input validation fails."""


class GrailLimitError(GrailExecutionError):
    """Raised when execution appears to violate configured limits."""


class GrailOutputValidationError(GrailValidationError):
    """Raised when output validation against the configured output model fails."""


class MontyContext(Generic[InputT, OutputT]):
    """Context for validated execution in Monty with optional tools and typed output."""

    def __init__(
        self,
        input_model: type[InputT],
        limits: ResourceLimits | None = None,
        output_model: type[OutputT] | None = None,
        tools: list[Callable[..., Any]] | None = None,
    ) -> None:
        self.input_model = input_model
        self.output_model = output_model
        self.limits = merge_resource_limits(limits)
        self.tools = ToolRegistry(tools)
        self.stub_generator = StubGenerator()

    async def execute_async(self, code: str, inputs: InputT | dict[str, Any]) -> Any | OutputT:
        """Validate input data and execute code in Monty."""
        validated_inputs = self._validate_inputs(inputs)
        serialized_inputs = validated_inputs.model_dump(mode="python")
        type_stubs = self.stub_generator.generate(
            input_model=self.input_model,
            output_model=self.output_model,
            tools=[self.tools.as_mapping()[name] for name in self.tools.names],
        )

        from pydantic_monty import Monty, MontyError, MontyRuntimeError, run_monty_async

        monty_kwargs = self._supported_kwargs(
            Monty,
            {
                "inputs": ["inputs"],
                "type_definitions": type_stubs,
                "type_check_stubs": type_stubs,
                "stubs": type_stubs,
            },
            drop_required=("code",),
        )

        run_kwargs = self._supported_kwargs(
            run_monty_async,
            {
                "inputs": {"inputs": serialized_inputs},
                "limits": self.limits,
                "tools": self.tools.as_mapping(),
                "external_functions": self.tools.as_mapping(),
                "functions": self.tools.as_mapping(),
                "globals": self.tools.as_mapping(),
            },
            drop_required=("runner", "monty"),
        )

        try:
            runner = Monty(code, **monty_kwargs)
            result = await run_monty_async(runner, **run_kwargs)
            return self._validate_output(result)
        except ValidationError as exc:
            raise GrailOutputValidationError(self._output_validation_message(exc)) from exc
        except MontyRuntimeError as exc:
            if "limit" in str(exc).lower() or "recursion" in str(exc).lower():
                raise GrailLimitError(f"Monty resource limit hit: {exc}") from exc
            raise GrailExecutionError(f"Monty runtime error: {exc}") from exc
        except MontyError as exc:
            raise GrailExecutionError(f"Monty execution failed: {exc}") from exc

    def execute(self, code: str, inputs: InputT | dict[str, Any]) -> Any | OutputT:
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

    def _validate_output(self, output: Any) -> Any | OutputT:
        if self.output_model is None:
            return output
        return self.output_model.model_validate(output)

    def _output_validation_message(self, exc: ValidationError) -> str:
        model_name = self.output_model.__name__ if self.output_model else "OutputModel"
        return f"Output validation failed for {model_name}: {exc}"

    def _supported_kwargs(
        self,
        callable_obj: Callable[..., Any],
        candidates: dict[str, Any],
        drop_required: tuple[str, ...],
    ) -> dict[str, Any]:
        signature = inspect.signature(callable_obj)
        parameters = signature.parameters

        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()):
            return candidates

        supported: dict[str, Any] = {}
        for key, value in candidates.items():
            if key in parameters:
                supported[key] = value

        for required in drop_required:
            supported.pop(required, None)

        return supported
