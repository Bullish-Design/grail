"""MontyContext orchestration for validated sandbox execution."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
from collections.abc import Callable
from typing import Any, Generic, TypedDict, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import (
    GrailExecutionError,
    GrailLimitError,
    GrailOutputValidationError,
    GrailValidationError,
    extract_location,
    format_runtime_error,
    format_validation_error,
)
from .snapshots import MontySnapshot
from .stubs import StubGenerator
from .tools import ToolRegistry
from .types import ResourceLimits, merge_resource_limits

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class DebugToolCall(TypedDict):
    name: str
    args: list[Any]
    kwargs: dict[str, Any]
    result: Any


class DebugPayload(TypedDict):
    events: list[str]
    stdout: str
    stderr: str
    tool_calls: list[DebugToolCall]


class MontyContext(Generic[InputT, OutputT]):
    """Context for validated execution in Monty with optional tools and typed output."""

    def __init__(
        self,
        input_model: type[InputT],
        limits: ResourceLimits | None = None,
        output_model: type[OutputT] | None = None,
        tools: list[Callable[..., Any]] | None = None,
        debug: bool = False,
    ) -> None:
        self.input_model = input_model
        self.output_model = output_model
        self.limits = merge_resource_limits(limits)
        self.tools = ToolRegistry(tools)
        self.stub_generator = StubGenerator()
        self.debug = debug
        self._debug_payload: DebugPayload = {
            "events": [],
            "stdout": "",
            "stderr": "",
            "tool_calls": [],
        }

    @property
    def debug_payload(self) -> DebugPayload:
        return self._debug_payload

    async def execute_async(self, code: str, inputs: InputT | dict[str, Any]) -> Any | OutputT:
        """Validate input data and execute code in Monty."""
        self._debug_payload = {"events": [], "stdout": "", "stderr": "", "tool_calls": []}
        self._event("validate-inputs")
        validated_inputs = self._validate_inputs(inputs)
        serialized_inputs = validated_inputs.model_dump(mode="python")
        type_stubs = self.stub_generator.generate(
            input_model=self.input_model,
            output_model=self.output_model,
            tools=[self.tools.as_mapping()[name] for name in self.tools.names],
        )

        from pydantic_monty import Monty, run_monty_async

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
                "tools": self._debug_tools_mapping(),
                "external_functions": self._debug_tools_mapping(),
                "functions": self._debug_tools_mapping(),
                "globals": self._debug_tools_mapping(),
            },
            drop_required=("runner", "monty"),
        )

        out = io.StringIO()
        err = io.StringIO()
        try:
            self._event("build-runner")
            runner = Monty(code, **monty_kwargs)
            self._event("execute")
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                result = await run_monty_async(runner, **run_kwargs)
            return self._validated_output_with_event(result)
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_monty_exception(exc) from exc
        finally:
            self._debug_payload["stdout"] += out.getvalue()
            self._debug_payload["stderr"] += err.getvalue()
            self._event("finished")

    async def start(self, code: str, inputs: InputT | dict[str, Any]) -> MontySnapshot:
        """Validate input data and begin execution in resumable mode."""
        self._debug_payload = {"events": [], "stdout": "", "stderr": "", "tool_calls": []}
        self._event("validate-inputs")
        validated_inputs = self._validate_inputs(inputs)
        serialized_inputs = validated_inputs.model_dump(mode="python")
        type_stubs = self.stub_generator.generate(
            input_model=self.input_model,
            output_model=self.output_model,
            tools=[self.tools.as_mapping()[name] for name in self.tools.names],
        )

        from pydantic_monty import Monty

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

        start_kwargs = self._supported_kwargs(
            Monty.start,
            {
                "inputs": {"inputs": serialized_inputs},
                "limits": self.limits,
                "tools": self._debug_tools_mapping(),
                "external_functions": self._debug_tools_mapping(),
                "functions": self._debug_tools_mapping(),
                "globals": self._debug_tools_mapping(),
                "print_callback": self._print_callback,
            },
            drop_required=("self",),
        )
        try:
            self._event("build-runner")
            runner = Monty(code, **monty_kwargs)
            return await self._run_start(runner, start_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_monty_exception(exc) from exc

    def load_snapshot(self, serialized: bytes, **kwargs: Any) -> MontySnapshot:
        """Restore a paused snapshot in this context from a serialized payload."""
        from pydantic_monty import MontySnapshot as NativeMontySnapshot

        load_kwargs = self._supported_kwargs(
            NativeMontySnapshot.load,
            {
                "print_callback": self._print_callback,
                **kwargs,
            },
            drop_required=(),
        )
        try:
            snapshot = NativeMontySnapshot.load(serialized, **load_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_monty_exception(exc) from exc

        self._event("restore-snapshot")
        return MontySnapshot(
            snapshot,
            validate_output=self._validated_output_with_event,
            normalize_exception=self._normalize_monty_exception,
        )

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
            message = format_validation_error(
                f"Input validation failed for {self.input_model.__name__}",
                exc,
            )
            raise GrailValidationError(message) from exc

    def _validate_output(self, output: Any) -> Any | OutputT:
        if self.output_model is None:
            return output
        return self.output_model.model_validate(output)

    async def _run_start(self, runner: Any, start_kwargs: dict[str, Any]) -> MontySnapshot:
        out = io.StringIO()
        err = io.StringIO()
        self._event("execute")
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                state = runner.start(**start_kwargs)
                if inspect.isawaitable(state):
                    state = await state
        finally:
            self._debug_payload["stdout"] += out.getvalue()
            self._debug_payload["stderr"] += err.getvalue()
            self._event("finished")

        return MontySnapshot(
            state,
            validate_output=self._validated_output_with_event,
            normalize_exception=self._normalize_monty_exception,
        )

    def _validated_output_with_event(self, output: Any) -> Any | OutputT:
        self._event("validate-output")
        try:
            return self._validate_output(output)
        except ValidationError as exc:
            output_name = self.output_model.__name__ if self.output_model else "OutputModel"
            raise GrailOutputValidationError(
                format_validation_error(
                    f"Output validation failed for {output_name}",
                    exc,
                )
            ) from exc

    def _normalize_monty_exception(self, exc: Exception) -> Exception:
        from pydantic_monty import MontyError, MontyRuntimeError

        if isinstance(exc, ValidationError):
            output_name = self.output_model.__name__ if self.output_model else "OutputModel"
            return GrailOutputValidationError(
                format_validation_error(
                    f"Output validation failed for {output_name}",
                    exc,
                )
            )
        if isinstance(exc, MontyRuntimeError):
            location = extract_location(exc)
            message = format_runtime_error(
                category="Monty runtime error",
                exc=exc,
                location=location,
            )
            if "limit" in str(exc).lower() or "recursion" in str(exc).lower():
                return GrailLimitError(message)
            return GrailExecutionError(message)
        if isinstance(exc, MontyError):
            location = extract_location(exc)
            message = format_runtime_error(
                category="Monty execution failed",
                exc=exc,
                location=location,
            )
            return GrailExecutionError(message)
        return exc

    def _print_callback(self, stream: str, text: str) -> None:
        if stream == "stdout":
            self._debug_payload["stdout"] += text
        elif stream == "stderr":
            self._debug_payload["stderr"] += text

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

    def _event(self, value: str) -> None:
        if self.debug:
            self._debug_payload["events"].append(value)

    def _debug_tools_mapping(self) -> dict[str, Callable[..., Any]]:
        tools = self.tools.as_mapping()
        if not self.debug:
            return tools

        wrapped: dict[str, Callable[..., Any]] = {}
        for name, fn in tools.items():
            wrapped[name] = self._wrap_tool(name, fn)
        return wrapped

    def _wrap_tool(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        async def _inner(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            self._debug_payload["tool_calls"].append(
                {"name": name, "args": list(args), "kwargs": kwargs, "result": result}
            )
            return result

        return _inner
