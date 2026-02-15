# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 5: Parser - Extract Externals and Inputs from AST

**Critical step**: This is where we extract `@external` functions and `Input()` calls from `.pym` files.

### Work to be done

Create `src/grail/parser.py`:

```python
"""Parser for .pym files - extracts externals and inputs from AST."""
import ast
from pathlib import Path
from typing import Any

from grail._types import (
    ExternalSpec, InputSpec, ParamSpec, ParseResult
)
from grail.errors import ParseError, CheckError


def get_type_annotation_str(node: ast.expr | None) -> str:
    """
    Convert AST type annotation node to string.

    Args:
        node: AST annotation node

    Returns:
        String representation of type (e.g., "int", "dict[str, Any]")

    Raises:
        CheckError: If annotation is missing or invalid
    """
    if node is None:
        raise CheckError("Missing type annotation")

    return ast.unparse(node)


def extract_function_params(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ParamSpec]:
    """
    Extract parameter specifications from function definition.

    Args:
        func_node: Function definition AST node

    Returns:
        List of parameter specifications

    Raises:
        CheckError: If parameters lack type annotations
    """
    params = []

    for arg in func_node.args.args:
        # Skip 'self' if present (shouldn't be in external funcs but be defensive)
        if arg.arg == 'self':
            continue

        if arg.annotation is None:
            raise CheckError(
                f"Parameter '{arg.arg}' in function '{func_node.name}' missing type annotation",
                lineno=func_node.lineno
            )

        # Check for default value
        default = None
        # Defaults are stored separately in args.defaults
        # They align with the last N args
        num_defaults = len(func_node.args.defaults)
        num_args = len(func_node.args.args)
        arg_index = func_node.args.args.index(arg)

        if arg_index >= num_args - num_defaults:
            default_index = arg_index - (num_args - num_defaults)
            default_node = func_node.args.defaults[default_index]
            # Try to extract literal default value
            try:
                default = ast.literal_eval(default_node)
            except (ValueError, TypeError):
                # If not a literal, store as string representation
                default = ast.unparse(default_node)

        params.append(ParamSpec(
            name=arg.arg,
            type_annotation=get_type_annotation_str(arg.annotation),
            default=default
        ))

    return params


def validate_external_function(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
    """
    Validate that external function meets requirements.

    Requirements:
    - Complete type annotations on all parameters
    - Return type annotation
    - Body is single Ellipsis statement

    Args:
        func_node: Function definition to validate

    Raises:
        CheckError: If validation fails
    """
    # Check return type
    if func_node.returns is None:
        raise CheckError(
            f"Function '{func_node.name}' missing return type annotation",
            lineno=func_node.lineno
        )

    # Check body is single Ellipsis
    if len(func_node.body) != 1:
        raise CheckError(
            f"External function '{func_node.name}' body must be single '...' (Ellipsis)",
            lineno=func_node.lineno
        )

    body_stmt = func_node.body[0]

    # Body should be Expr node containing Constant(value=Ellipsis)
    if not isinstance(body_stmt, ast.Expr):
        raise CheckError(
            f"External function '{func_node.name}' body must be '...' (Ellipsis)",
            lineno=func_node.lineno
        )

    if not isinstance(body_stmt.value, ast.Constant) or body_stmt.value.value != Ellipsis:
        raise CheckError(
            f"External function '{func_node.name}' body must be '...' (Ellipsis), not actual code",
            lineno=func_node.lineno
        )


def extract_externals(module: ast.Module) -> dict[str, ExternalSpec]:
    """
    Extract external function specifications from AST.

    Looks for functions decorated with @external.

    Args:
        module: Parsed AST module

    Returns:
        Dictionary mapping function names to ExternalSpec

    Raises:
        CheckError: If external declarations are malformed
    """
    externals = {}

    for node in ast.walk(module):
        # Check both regular and async function definitions
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Check if decorated with @external
        has_external = False
        for decorator in node.decorator_list:
            # Handle simple decorator: @external
            if isinstance(decorator, ast.Name) and decorator.id == 'external':
                has_external = True
                break
            # Handle attribute decorator: @grail.external (future-proofing)
            if isinstance(decorator, ast.Attribute) and decorator.attr == 'external':
                has_external = True
                break

        if not has_external:
            continue

        # Validate the external function
        validate_external_function(node)

        # Extract parameters
        params = extract_function_params(node)

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Create spec
        spec = ExternalSpec(
            name=node.name,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            parameters=params,
            return_type=get_type_annotation_str(node.returns),
            docstring=docstring,
            lineno=node.lineno,
            col_offset=node.col_offset
        )

        externals[node.name] = spec

    return externals


def extract_inputs(module: ast.Module) -> dict[str, InputSpec]:
    """
    Extract input specifications from AST.

    Looks for assignments like: x: int = Input("x")

    Args:
        module: Parsed AST module

    Returns:
        Dictionary mapping input names to InputSpec

    Raises:
        CheckError: If input declarations are malformed
    """
    inputs = {}

    for node in ast.walk(module):
        # Look for annotated assignments
        if not isinstance(node, ast.AnnAssign):
            continue

        # Check if RHS is a call to Input()
        if not isinstance(node.value, ast.Call):
            continue

        # Check if the function being called is 'Input'
        is_input_call = False
        if isinstance(node.value.func, ast.Name) and node.value.func.id == 'Input':
            is_input_call = True
        elif isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'Input':
            is_input_call = True

        if not is_input_call:
            continue

        # Validate annotation exists
        if node.annotation is None:
            raise CheckError(
                "Input() call must have type annotation",
                lineno=node.lineno
            )

        # Extract variable name
        if not isinstance(node.target, ast.Name):
            raise CheckError(
                "Input() must be assigned to a simple variable name",
                lineno=node.lineno
            )

        var_name = node.target.id

        # Extract Input() arguments
        # First positional arg should be the name (string)
        if len(node.value.args) == 0:
            raise CheckError(
                f"Input() call for '{var_name}' missing name argument",
                lineno=node.lineno
            )

        # Extract default value from 'default=' keyword argument
        default = None
        for keyword in node.value.keywords:
            if keyword.arg == 'default':
                try:
                    default = ast.literal_eval(keyword.value)
                except (ValueError, TypeError):
                    # If not a literal, store as string
                    default = ast.unparse(keyword.value)
                break

        # Create spec
        spec = InputSpec(
            name=var_name,
            type_annotation=get_type_annotation_str(node.annotation),
            default=default,
            required=(default is None),
            lineno=node.lineno,
            col_offset=node.col_offset
        )

        inputs[var_name] = spec

    return inputs


def parse_pym_file(path: Path) -> ParseResult:
    """
    Parse a .pym file and extract metadata.

    Args:
        path: Path to .pym file

    Returns:
        ParseResult with externals, inputs, AST, and source lines

    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If file has syntax errors
        CheckError: If declarations are malformed
    """
    if not path.exists():
        raise FileNotFoundError(f".pym file not found: {path}")

    # Read source
    source = path.read_text()
    source_lines = source.splitlines()

    # Parse AST
    try:
        module = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise ParseError(
            e.msg,
            lineno=e.lineno,
            col_offset=e.offset
        )

    # Extract externals and inputs
    externals = extract_externals(module)
    inputs = extract_inputs(module)

    return ParseResult(
        externals=externals,
        inputs=inputs,
        ast_module=module,
        source_lines=source_lines
    )


def parse_pym_content(content: str, filename: str = "<string>") -> ParseResult:
    """
    Parse .pym content from string (useful for testing).

    Args:
        content: .pym file content
        filename: Optional filename for error messages

    Returns:
        ParseResult

    Raises:
        ParseError: If content has syntax errors
        CheckError: If declarations are malformed
    """
    source_lines = content.splitlines()

    try:
        module = ast.parse(content, filename=filename)
    except SyntaxError as e:
        raise ParseError(
            e.msg,
            lineno=e.lineno,
            col_offset=e.offset
        )

    externals = extract_externals(module)
    inputs = extract_inputs(module)

    return ParseResult(
        externals=externals,
        inputs=inputs,
        ast_module=module,
        source_lines=source_lines
    )
```

### Testing/Validation

Create `tests/unit/test_parser.py`:

```python
"""Test .pym file parser."""
import pytest
from pathlib import Path

from grail.parser import parse_pym_file, parse_pym_content
from grail.errors import ParseError, CheckError

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_parse_simple_pym():
    """Parse simple.pym fixture."""
    result = parse_pym_file(FIXTURES_DIR / "simple.pym")

    # Should have 1 external: double
    assert "double" in result.externals
    ext = result.externals["double"]
    assert ext.is_async is True
    assert ext.return_type == "int"
    assert len(ext.parameters) == 1
    assert ext.parameters[0].name == "n"
    assert ext.parameters[0].type_annotation == "int"

    # Should have 1 input: x
    assert "x" in result.inputs
    inp = result.inputs["x"]
    assert inp.type_annotation == "int"
    assert inp.required is True


def test_parse_multiple_externals():
    """Parse fixture with multiple externals."""
    result = parse_pym_file(FIXTURES_DIR / "with_multiple_externals.pym")

    # Should have 2 externals
    assert "get_team" in result.externals
    assert "get_expenses" in result.externals

    # Should have 2 inputs
    assert "budget" in result.inputs
    assert "department" in result.inputs

    # Check input with default
    dept = result.inputs["department"]
    assert dept.required is False
    assert dept.default == "Engineering"


def test_missing_type_annotation_raises():
    """Missing type annotation should raise CheckError."""
    content = """
from grail import external

@external
def bad_func(x):
    ...
"""
    with pytest.raises(CheckError, match="missing type annotation"):
        parse_pym_content(content)


def test_missing_return_type_raises():
    """Missing return type should raise CheckError."""
    content = """
from grail import external

@external
def bad_func(x: int):
    ...
"""
    with pytest.raises(CheckError, match="missing return type annotation"):
        parse_pym_content(content)


def test_non_ellipsis_body_raises():
    """Non-ellipsis body should raise CheckError."""
    result = parse_pym_file(FIXTURES_DIR / "non_ellipsis_body.pym")
    # This should raise during parse

    # Actually, let's test directly
    content = """
from grail import external

@external
def bad_func(x: int) -> int:
    return x * 2
"""
    with pytest.raises(CheckError, match="body must be"):
        parse_pym_content(content)


def test_input_without_annotation_raises():
    """Input without type annotation should raise CheckError."""
    content = """
from grail import Input

x = Input("x")  # Missing annotation
"""
    with pytest.raises(CheckError, match="type annotation"):
        parse_pym_content(content)


def test_syntax_error_raises_parse_error():
    """Invalid Python syntax should raise ParseError."""
    content = "def bad syntax here"

    with pytest.raises(ParseError):
        parse_pym_content(content)


def test_extract_docstring():
    """Should extract function docstrings."""
    content = """
from grail import external

@external
async def fetch_data(url: str) -> dict:
    '''Fetch data from URL.'''
    ...
"""
    result = parse_pym_content(content)

    assert "fetch_data" in result.externals
    assert result.externals["fetch_data"].docstring == "Fetch data from URL."


def test_function_with_defaults():
    """Should handle function parameters with defaults."""
    content = """
from grail import external

@external
def process(x: int, y: int = 10) -> int:
    ...
"""
    result = parse_pym_content(content)

    func = result.externals["process"]
    assert len(func.parameters) == 2
    assert func.parameters[0].name == "x"
    assert func.parameters[0].default is None
    assert func.parameters[1].name == "y"
    assert func.parameters[1].default == 10
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_parser.py` passes
- [ ] Parser correctly extracts `@external` functions
- [ ] Parser correctly extracts `Input()` calls
- [ ] Validation errors are raised for malformed declarations
- [ ] Can parse all valid fixtures without errors
