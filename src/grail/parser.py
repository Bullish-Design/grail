"""Parser for .pym files - extracts externals and inputs from AST."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from grail._types import ExternalSpec, InputSpec, ParamSpec, ParseResult
from grail.errors import CheckError, ParseError


def get_type_annotation_str(node: ast.expr | None, lenient: bool = False) -> str:
    """Convert AST type annotation node to string.

    Args:
        node: AST annotation node.
        lenient: If True, return "<missing>" instead of raising CheckError.

    Returns:
        String representation of type (e.g., "int", "dict[str, Any]").

    Raises:
        CheckError: If annotation is missing or invalid (only when lenient=False).
    """
    if node is None:
        if lenient:
            return "<missing>"
        raise CheckError("Missing type annotation")

    return ast.unparse(node)


def _get_annotation(node: ast.expr | None) -> str:
    """Convert AST annotation node to string."""
    if node is None:
        return "<missing>"
    return ast.unparse(node)


def extract_function_params(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ParamSpec]:
    """Extract parameter specifications from function definition.

    Handles all parameter kinds: positional-only, positional-or-keyword,
    var-positional (*args), keyword-only, and var-keyword (**kwargs).

    Args:
        func_node: Function definition AST node.

    Returns:
        List of parameter specifications.
    """
    from grail._types import ParamKind

    params: list[ParamSpec] = []
    args = func_node.args

    # Defaults are right-aligned: if there are 3 args and 1 default,
    # the default applies to the 3rd arg.
    num_posonly = len(args.posonlyargs)
    num_regular = len(args.args)
    num_pos_defaults = len(args.defaults)
    # defaults apply to the LAST N of (posonlyargs + args)
    total_positional = num_posonly + num_regular
    first_default_idx = total_positional - num_pos_defaults

    # Positional-only arguments
    for i, arg in enumerate(args.posonlyargs):
        global_idx = i
        has_default = global_idx >= first_default_idx
        default_val = None
        if has_default:
            default_val = ast.dump(args.defaults[global_idx - first_default_idx])
        params.append(
            ParamSpec(
                name=arg.arg,
                type_annotation=_get_annotation(arg.annotation),
                has_default=has_default,
                default=default_val,
                kind=ParamKind.POSITIONAL_ONLY,
            )
        )

    # Regular positional-or-keyword arguments
    for i, arg in enumerate(args.args):
        if arg.arg == "self":
            continue

        global_idx = num_posonly + i
        has_default = global_idx >= first_default_idx
        default_val = None
        if has_default:
            default_val = ast.dump(args.defaults[global_idx - first_default_idx])
        params.append(
            ParamSpec(
                name=arg.arg,
                type_annotation=_get_annotation(arg.annotation),
                has_default=has_default,
                default=default_val,
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
            )
        )

    # *args
    if args.vararg:
        params.append(
            ParamSpec(
                name=args.vararg.arg,
                type_annotation=_get_annotation(args.vararg.annotation),
                has_default=False,
                kind=ParamKind.VAR_POSITIONAL,
            )
        )

    # Keyword-only arguments (kw_defaults aligns 1:1 with kwonlyargs)
    for i, arg in enumerate(args.kwonlyargs):
        kw_default = args.kw_defaults[i]  # None if no default
        params.append(
            ParamSpec(
                name=arg.arg,
                type_annotation=_get_annotation(arg.annotation),
                has_default=kw_default is not None,
                default=ast.dump(kw_default) if kw_default is not None else None,
                kind=ParamKind.KEYWORD_ONLY,
            )
        )

    # **kwargs
    if args.kwarg:
        params.append(
            ParamSpec(
                name=args.kwarg.arg,
                type_annotation=_get_annotation(args.kwarg.annotation),
                has_default=False,
                kind=ParamKind.VAR_KEYWORD,
            )
        )

    return params


def extract_externals(module: ast.Module) -> dict[str, ExternalSpec]:
    """Extract external function specifications from AST.

    Looks for functions decorated with @external.

    Args:
        module: Parsed AST module.

    Returns:
        Dictionary mapping function names to ExternalSpec.

    Raises:
        CheckError: If external declarations are malformed.
    """
    externals: dict[str, ExternalSpec] = {}

    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        has_external = False
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "external":
                has_external = True
                break
            if isinstance(decorator, ast.Attribute) and decorator.attr == "external":
                has_external = True
                break

        if not has_external:
            continue

        params = extract_function_params(node)
        docstring = ast.get_docstring(node)

        externals[node.name] = ExternalSpec(
            name=node.name,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            parameters=params,
            return_type=get_type_annotation_str(node.returns, lenient=True),
            docstring=docstring,
            lineno=node.lineno,
            col_offset=node.col_offset,
        )

    return externals


def extract_inputs(module: ast.Module) -> dict[str, InputSpec]:
    """Extract input specifications from AST.

    Looks for assignments like: x: int = Input("x").

    Args:
        module: Parsed AST module.

    Returns:
        Dictionary mapping input names to InputSpec.

    Raises:
        CheckError: If input declarations are malformed.
    """
    inputs: dict[str, InputSpec] = {}

    for node in module.body:
        # Check annotated assignments (x: int = Input("x"))
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.value, ast.Call):
                continue

            is_input_call = False
            if isinstance(node.value.func, ast.Name) and node.value.func.id == "Input":
                is_input_call = True
            elif isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "Input":
                is_input_call = True

            if not is_input_call:
                continue

            if node.annotation is None:
                annotation_str = "<missing>"
            else:
                annotation_str = get_type_annotation_str(node.annotation)

            if not isinstance(node.target, ast.Name):
                raise CheckError(
                    "Input() must be assigned to a simple variable name",
                    lineno=node.lineno,
                )

            var_name = node.target.id

            if not node.value.args:
                raise CheckError(
                    f"Input() call for '{var_name}' missing name argument",
                    lineno=node.lineno,
                )

            default = None
            for keyword in node.value.keywords:
                if keyword.arg == "default":
                    try:
                        default = ast.literal_eval(keyword.value)
                    except (ValueError, TypeError):
                        default = ast.unparse(keyword.value)
                    break

            inputs[var_name] = InputSpec(
                name=var_name,
                type_annotation=annotation_str,
                default=default,
                required=default is None,
                lineno=node.lineno,
                col_offset=node.col_offset,
            )

        # Check non-annotated assignments (x = Input("x"))
        elif isinstance(node, ast.Assign):
            if not isinstance(node.value, ast.Call):
                continue

            is_input_call = False
            if isinstance(node.value.func, ast.Name) and node.value.func.id == "Input":
                is_input_call = True
            elif isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "Input":
                is_input_call = True

            if is_input_call:
                if not isinstance(node.targets[0], ast.Name):
                    raise CheckError(
                        "Input() must be assigned to a simple variable name",
                        lineno=node.lineno,
                    )

                var_name = node.targets[0].id
                default = None
                for keyword in node.value.keywords:
                    if keyword.arg == "default":
                        try:
                            default = ast.literal_eval(keyword.value)
                        except (ValueError, TypeError):
                            default = ast.unparse(keyword.value)
                        break

                inputs[var_name] = InputSpec(
                    name=var_name,
                    type_annotation="<missing>",
                    default=default,
                    required=default is None,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                )

    return inputs


def parse_pym_file(path: Path) -> ParseResult:
    """Parse a .pym file and extract metadata.

    Args:
        path: Path to .pym file.

    Returns:
        ParseResult with externals, inputs, AST, and source lines.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ParseError: If file has syntax errors.
        CheckError: If declarations are malformed.
    """
    if not path.exists():
        raise FileNotFoundError(f".pym file not found: {path}")

    source = path.read_text()
    source_lines = source.splitlines()

    try:
        module = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ParseError(exc.msg, lineno=exc.lineno, col_offset=exc.offset) from exc

    externals = extract_externals(module)
    inputs = extract_inputs(module)

    return ParseResult(
        externals=externals,
        inputs=inputs,
        ast_module=module,
        source_lines=source_lines,
    )


def parse_pym_content(content: str, filename: str = "<string>") -> ParseResult:
    """Parse .pym content from string (useful for testing).

    Args:
        content: .pym file content.
        filename: Optional filename for error messages.

    Returns:
        ParseResult.

    Raises:
        ParseError: If content has syntax errors.
        CheckError: If declarations are malformed.
    """
    source_lines = content.splitlines()

    try:
        module = ast.parse(content, filename=filename)
    except SyntaxError as exc:
        raise ParseError(exc.msg, lineno=exc.lineno, col_offset=exc.offset) from exc

    externals = extract_externals(module)
    inputs = extract_inputs(module)

    return ParseResult(
        externals=externals,
        inputs=inputs,
        ast_module=module,
        source_lines=source_lines,
    )
