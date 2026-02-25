"""GrailScript - Main API for loading and executing .pym files."""

import asyncio
import warnings
from pathlib import Path
from typing import Any, Callable
import time
import re

try:
    import pydantic_monty
except ImportError:
    pydantic_monty = None

from grail._types import ExternalSpec, InputSpec, CheckResult, CheckMessage, SourceMap, ScriptEvent
from grail.parser import parse_pym_file
from grail.checker import check_pym
from grail.stubs import generate_stubs
from grail.codegen import generate_monty_code
from grail.artifacts import ArtifactsManager
from grail.limits import Limits
from grail.errors import InputError, ExternalError, ExecutionError, LimitError, OutputError


class GrailScript:
    """
    Main interface for loading and executing .pym files.

    This class encapsulates:
    - Parsed .pym file metadata
    - Generated Monty code and stubs
    - Validation results
    - Execution interface
    """

    def __init__(
        self,
        path: Path,
        externals: dict[str, ExternalSpec],
        inputs: dict[str, InputSpec],
        monty_code: str,
        stubs: str,
        source_map: SourceMap,
        source_lines: list[str],
        limits: Limits | None = None,
        files: dict[str, str | bytes] | None = None,
        grail_dir: Path | None = None,
        dataclass_registry: list[type] | None = None,
    ):
        """
        Initialize GrailScript.

        Args:
            path: Path to original .pym file
            externals: External function specifications
            inputs: Input specifications
            monty_code: Generated Monty code
            stubs: Generated type stubs
            source_map: Line number mapping
            source_lines: .pym source lines
            limits: Resource limits
            files: Virtual filesystem files
            grail_dir: Directory for artifacts (None disables)
            dataclass_registry: List of dataclass types for isinstance() checks
        """
        self.path = path
        self.name = path.stem
        self.externals = externals
        self.inputs = inputs
        self.monty_code = monty_code
        self.stubs = stubs
        self.source_map = source_map
        self.source_lines = source_lines
        self.limits = limits
        self.files = files
        self.grail_dir = grail_dir
        self.dataclass_registry = dataclass_registry

        # Initialize artifacts manager if grail_dir is set
        self._artifacts = ArtifactsManager(grail_dir) if grail_dir else None

    def check(self, on_event: Callable[..., None] | None = None) -> CheckResult:
        """
        Run validation checks on the script.

        Args:
            on_event: Optional callback for structured events

        Returns:
            CheckResult with errors, warnings, and info
        """
        if on_event is not None:
            on_event(
                ScriptEvent(
                    type="check_start",
                    script_name=self.name,
                    timestamp=time.time(),
                )
            )

        # Re-parse and check
        parse_result = parse_pym_file(self.path)
        check_result = check_pym(parse_result)
        check_result.file = str(self.path)

        # Run Monty type checker if available
        if pydantic_monty is not None:
            try:
                pydantic_monty.Monty(
                    self.monty_code,
                    script_name=f"{self.name}.pym",
                    type_check=True,
                    type_check_stubs=self.stubs,
                    inputs=list(self.inputs.keys()),
                    external_functions=list(self.externals.keys()),
                )
            except pydantic_monty.MontyTypingError as e:
                check_result.errors.append(
                    CheckMessage(
                        code="E100",
                        lineno=0,
                        col_offset=0,
                        end_lineno=None,
                        end_col_offset=None,
                        severity="error",
                        message=f"Type error: {str(e)}",
                        suggestion="Fix the type error indicated above",
                    )
                )
                check_result.valid = False

        # Write check results to artifacts if enabled
        if self._artifacts:
            self._artifacts.write_script_artifacts(
                self.name, self.stubs, self.monty_code, check_result, self.externals, self.inputs
            )

        if on_event is not None:
            on_event(
                ScriptEvent(
                    type="check_complete",
                    script_name=self.name,
                    timestamp=time.time(),
                    result_summary=f"{'valid' if check_result.valid else 'invalid'}: {len(check_result.errors)} errors, {len(check_result.warnings)} warnings",
                )
            )

        return check_result

    def _validate_inputs(self, inputs: dict[str, Any]) -> None:
        """
        Validate that provided inputs match declarations.

        Args:
            inputs: Runtime input values

        Raises:
            InputError: If validation fails
        """
        # Check for missing required inputs
        for name, spec in self.inputs.items():
            if spec.required and name not in inputs:
                raise InputError(
                    f"Missing required input: '{name}' (type: {spec.type_annotation})",
                    input_name=name,
                )

        # Check for extra inputs (warn but don't fail)
        for name in inputs:
            if name not in self.inputs:
                warnings.warn(
                    f"Extra input '{name}' not declared in script",
                    stacklevel=2,
                )

    def _validate_externals(self, externals: dict[str, Callable]) -> None:
        """
        Validate that provided externals match declarations.

        Args:
            externals: Runtime external function implementations

        Raises:
            ExternalError: If validation fails
        """
        # Check for missing externals
        for name in self.externals:
            if name not in externals:
                raise ExternalError(f"Missing external function: '{name}'", function_name=name)

        # Check for extra externals (warn but don't fail)
        for name in externals:
            if name not in self.externals:
                warnings.warn(
                    f"Extra external '{name}' not declared in script",
                    stacklevel=2,
                )

    def _prepare_monty_limits(self, override_limits: Limits | None) -> dict[str, Any]:
        """
        Merge load-time and run-time limits into a Monty-native dict.

        Falls back to Limits.default() if no limits are provided anywhere.
        """
        base = self.limits
        if base is None and override_limits is None:
            return Limits.default().to_monty()
        if base is None:
            assert override_limits is not None
            return override_limits.to_monty()
        if override_limits is None:
            return base.to_monty()
        return base.merge(override_limits).to_monty()

    def _prepare_monty_files(self, override_files: dict[str, str | bytes] | None):
        """
        Prepare files for Monty's OSAccess.

        Args:
            override_files: Runtime file overrides

        Returns:
            OSAccess object or None
        """
        if pydantic_monty is None:
            return None

        files = override_files if override_files is not None else self.files
        if not files:
            return None

        # Convert dict to Monty's MemoryFile + OSAccess
        memory_files = []
        for path, content in files.items():
            memory_files.append(pydantic_monty.MemoryFile(path, content))

        return pydantic_monty.OSAccess(memory_files)

    def _map_error_to_pym(self, error: Exception) -> ExecutionError:
        """
        Map Monty error to .pym file line numbers.

        Uses structured traceback data from MontyRuntimeError when available,
        falling back to message parsing for other error types.

        Args:
            error: Original error from Monty

        Returns:
            ExecutionError with mapped line numbers
        """
        error_msg = str(error)
        error_msg_lower = error_msg.lower()
        lineno = None
        col_offset = None

        # Use structured traceback if available (MontyRuntimeError)
        if pydantic_monty is not None and isinstance(error, pydantic_monty.MontyRuntimeError):
            frames = error.traceback()
            if frames:
                # Use the innermost frame (last in the list)
                frame = frames[-1]
                monty_line = frame.line
                lineno = self.source_map.monty_to_pym.get(monty_line, monty_line)
                col_offset = getattr(frame, "column", None)
        else:
            # Fallback: try to extract line number from error message
            match = re.search(r"line (\d+)", error_msg, re.IGNORECASE)
            if match:
                monty_line = int(match.group(1))
                lineno = self.source_map.monty_to_pym.get(monty_line, monty_line)

        # Detect limit errors by type or message heuristics
        limit_type = None
        if "memory" in error_msg_lower:
            limit_type = "memory"
        elif "duration" in error_msg_lower:
            limit_type = "duration"
        elif "recursion" in error_msg_lower:
            limit_type = "recursion"

        if "limit" in error_msg_lower or limit_type is not None:
            return LimitError(error_msg, limit_type=limit_type)

        source_context = "\n".join(self.source_lines) if self.source_lines else None
        return ExecutionError(
            error_msg,
            lineno=lineno,
            col_offset=col_offset,
            source_context=source_context,
            suggestion=None,
        )

    async def run(
        self,
        inputs: dict[str, Any] | None = None,
        externals: dict[str, Callable] | None = None,
        output_model: type | None = None,
        files: dict[str, str | bytes] | None = None,
        limits: Limits | None = None,
        print_callback: Callable[[str, str], None] | None = None,
        on_event: Callable[[ScriptEvent], None] | None = None,
    ) -> Any:
        """
        Execute the script in Monty.

        Args:
            inputs: Input values
            externals: External function implementations
            output_model: Optional Pydantic model for output validation
            files: Override files from load()
            limits: Override limits from load()
            print_callback: Optional callback for print() output from the script.
                Signature: (stream: str, text: str) -> None
            on_event: Optional callback for structured lifecycle events.

        Returns:
            Result of script execution

        Raises:
            InputError: Missing or invalid inputs
            ExternalError: Missing external functions
            ExecutionError: Monty runtime error
            OutputError: Output validation failed
        """
        if pydantic_monty is None:
            raise RuntimeError("pydantic-monty not installed")

        inputs = inputs or {}
        externals = externals or {}

        captured_output: list[str] = []

        def _monty_print_callback(stream: str, text: str) -> None:
            captured_output.append(text)
            if print_callback is not None:
                print_callback(stream, text)
            if on_event is not None:
                on_event(
                    ScriptEvent(
                        type="print",
                        script_name=self.name,
                        timestamp=time.time(),
                        text=text,
                    )
                )

        if on_event is not None:
            on_event(
                ScriptEvent(
                    type="run_start",
                    script_name=self.name,
                    timestamp=time.time(),
                    input_count=len(inputs),
                    external_count=len(externals),
                )
            )

        # Validate inputs and externals
        self._validate_inputs(inputs)
        self._validate_externals(externals)

        # Prepare Monty configuration
        parsed_limits = self._prepare_monty_limits(limits)
        os_access = self._prepare_monty_files(files)

        # Create Monty instance - catch type errors during construction
        try:
            monty = pydantic_monty.Monty(
                self.monty_code,
                script_name=f"{self.name}.pym",
                type_check=True,
                type_check_stubs=self.stubs,
                inputs=list(self.inputs.keys()),
                external_functions=list(self.externals.keys()),
                dataclass_registry=self.dataclass_registry,
            )
        except pydantic_monty.MontyTypingError as e:
            # Convert type errors to ExecutionError
            raise ExecutionError(
                f"Type checking failed: {str(e)}",
                lineno=None,
                source_context=None,
                suggestion="Fix type errors in your code",
            ) from e

        # Execute
        start_time = time.time()
        try:
            result = await pydantic_monty.run_monty_async(
                monty,
                inputs=inputs,
                external_functions=externals,
                os=os_access,
                limits=parsed_limits,
                print_callback=_monty_print_callback,
            )
            success = True
            error_msg = None
        except (pydantic_monty.MontyRuntimeError, pydantic_monty.MontyTypingError) as e:
            success = False
            error_msg = str(e)
            mapped_error = self._map_error_to_pym(e)

            if on_event is not None:
                duration_ms = (time.time() - start_time) * 1000
                on_event(
                    ScriptEvent(
                        type="run_error",
                        script_name=self.name,
                        timestamp=time.time(),
                        duration_ms=duration_ms,
                        error=str(mapped_error),
                    )
                )

            # Write error log
            if self._artifacts:
                duration_ms = (time.time() - start_time) * 1000
                stdout_text = "".join(captured_output)
                self._artifacts.write_run_log(
                    self.name,
                    stdout=stdout_text,
                    stderr=str(mapped_error),
                    duration_ms=duration_ms,
                    success=False,
                )

            raise mapped_error
        except Exception as e:
            # Catch unexpected errors (MontySyntaxError, etc.)
            success = False
            error_msg = str(e)
            mapped_error = self._map_error_to_pym(e)

            if on_event is not None:
                duration_ms = (time.time() - start_time) * 1000
                on_event(
                    ScriptEvent(
                        type="run_error",
                        script_name=self.name,
                        timestamp=time.time(),
                        duration_ms=duration_ms,
                        error=str(mapped_error),
                    )
                )

            # Write error log
            if self._artifacts:
                duration_ms = (time.time() - start_time) * 1000
                stdout_text = "".join(captured_output)
                self._artifacts.write_run_log(
                    self.name,
                    stdout=stdout_text,
                    stderr=str(mapped_error),
                    duration_ms=duration_ms,
                    success=False,
                )

            raise mapped_error

        duration_ms = (time.time() - start_time) * 1000
        stdout_text = "".join(captured_output)

        # Write success log
        if self._artifacts:
            self._artifacts.write_run_log(
                self.name,
                stdout=stdout_text,
                stderr="",
                duration_ms=duration_ms,
                success=True,
            )

        if on_event is not None:
            on_event(
                ScriptEvent(
                    type="run_complete",
                    script_name=self.name,
                    timestamp=time.time(),
                    duration_ms=duration_ms,
                    result_summary=f"{type(result).__name__}",
                )
            )

        # Validate output if model provided
        if output_model is not None:
            try:
                result = (
                    output_model(**result) if isinstance(result, dict) else output_model(result)
                )
            except Exception as e:
                raise OutputError(f"Output validation failed: {e}", validation_errors=e)

        return result

    def run_sync(
        self,
        inputs: dict[str, Any] | None = None,
        externals: dict[str, Callable] | None = None,
        **kwargs,
    ) -> Any:
        """
        Synchronous wrapper around run().

        Args:
            inputs: Input values
            externals: External function implementations
            **kwargs: Additional arguments for run()

        Returns:
            Result of script execution

        Raises:
            RuntimeError: If called from within an async context where a new
                event loop cannot be created. Use `await script.run()` instead.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run(inputs, externals, **kwargs))
        else:
            raise RuntimeError(
                "run_sync() cannot be used inside an async context "
                "(e.g., Jupyter, FastAPI). Use 'await script.run()' instead."
            )


def load(
    path: str | Path,
    limits: Limits | None = None,
    files: dict[str, str | bytes] | None = None,
    grail_dir: str | Path | None = ".grail",
    dataclass_registry: list[type] | None = None,
) -> GrailScript:
    """
    Load and parse a .pym file.

    Args:
        path: Path to .pym file
        limits: Resource limits
        files: Virtual filesystem files
        grail_dir: Directory for artifacts (None disables)
        dataclass_registry: List of dataclass types for isinstance() checks

    Returns:
        GrailScript instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If file has syntax errors
        CheckError: If declarations are malformed
    """
    path = Path(path)

    # Parse the file
    parse_result = parse_pym_file(path)

    # Run validation checks
    check_result = check_pym(parse_result)
    check_result.file = str(path)

    # Generate stubs
    stubs = generate_stubs(parse_result.externals, parse_result.inputs)

    # Generate Monty code
    monty_code, source_map = generate_monty_code(parse_result)

    # Setup grail_dir
    grail_dir_path = Path(grail_dir) if grail_dir else None

    # Write artifacts
    if grail_dir_path:
        artifacts = ArtifactsManager(grail_dir_path)
        artifacts.write_script_artifacts(
            path.stem, stubs, monty_code, check_result, parse_result.externals, parse_result.inputs
        )

    return GrailScript(
        path=path,
        externals=parse_result.externals,
        inputs=parse_result.inputs,
        monty_code=monty_code,
        stubs=stubs,
        source_map=source_map,
        source_lines=parse_result.source_lines,
        limits=limits,
        files=files,
        grail_dir=grail_dir_path,
        dataclass_registry=dataclass_registry,
    )


async def run(
    code: str,
    inputs: dict[str, Any] | None = None,
    print_callback: Callable[[str, str], None] | None = None,
) -> Any:
    """
    Execute inline Monty code (escape hatch for simple cases).

    Args:
        code: Monty code to execute
        inputs: Input values
        print_callback: Optional callback for print() output from the script.
            Signature: (stream: str, text: str) -> None

    Returns:
        Result of code execution
    """
    if pydantic_monty is None:
        raise RuntimeError("pydantic-monty not installed")

    input_names: list[str] = []
    input_values: dict[str, Any] = {}
    if inputs:
        input_names = list(inputs.keys())
        input_values = inputs

    if input_names:
        monty = pydantic_monty.Monty(code, inputs=input_names)
    else:
        monty = pydantic_monty.Monty(code)

    if print_callback:
        result = await pydantic_monty.run_monty_async(
            monty, inputs=input_values or None, print_callback=print_callback
        )
    elif input_values:
        result = await pydantic_monty.run_monty_async(monty, inputs=input_values)
    else:
        result = await pydantic_monty.run_monty_async(monty)
    return result


def run_sync(
    code: str,
    inputs: dict[str, Any] | None = None,
    print_callback: Callable[[str, str], None] | None = None,
) -> Any:
    """
    Synchronous wrapper for inline Monty code execution.

    Args:
        code: Monty code to execute
        inputs: Input values
        print_callback: Optional callback for print() output

    Returns:
        Result of code execution

    Raises:
        RuntimeError: If called from within an async context.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run(code, inputs, print_callback=print_callback))
    else:
        raise RuntimeError(
            "run_sync() cannot be used inside an async context. Use 'await grail.run()' instead."
        )
