# Grail v2 Development Guide 

This guide provides detailed, step-by-step instructions for implementing Grail v2 from scratch. Each step includes concrete implementation details, algorithms, and comprehensive testing requirements.

---

## Development Principles

1. **Build incrementally** - Each step should be fully tested before moving to the next
2. **Test everything** - Unit tests before integration tests, validate before building
3. **Keep it simple** - No premature optimization, no unnecessary abstractions
4. **Make errors visible** - All errors map back to `.pym` file line numbers

---

## Step 8: Code Generator - Transform .pym to Monty Code

**Critical step**: This strips grail declarations and produces the actual code that runs in Monty.

### Work to be done

Create `src/grail/codegen.py`:

```python
"""Code generator - transforms .pym to Monty-compatible code."""
import ast
from grail._types import ParseResult, SourceMap


class GrailDeclarationStripper(ast.NodeTransformer):
    """
    AST transformer that removes grail-specific declarations.

    Removes:
    - from grail import ... statements
    - @external decorated function definitions
    - Input() assignment statements

    Preserves:
    - All executable code
    - from typing import ... statements
    """

    def __init__(self, externals: set[str], inputs: set[str]):
        self.externals = externals  # Set of external function names
        self.inputs = inputs  # Set of input variable names

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom | None:
        """Remove 'from grail import ...' statements."""
        if node.module == "grail":
            return None  # Remove this node
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef | None:
        """Remove @external function definitions."""
        if node.name in self.externals:
            return None  # Remove this node
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef | None:
        """Remove @external async function definitions."""
        if node.name in self.externals:
            return None
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AnnAssign | None:
        """Remove Input() assignment statements."""
        if isinstance(node.target, ast.Name) and node.target.id in self.inputs:
            return None
        return node


def build_source_map(original_lines: list[str], generated_code: str) -> SourceMap:
    """
    Build line number mapping between .pym and generated code.

    This is a simplified version - for more accurate mapping,
    we'd need to track transformations during AST processing.

    Args:
        original_lines: Source lines from .pym file
        generated_code: Generated Monty code

    Returns:
        SourceMap with line mappings
    """
    source_map = SourceMap()

    # Simple heuristic: map based on matching content
    # For now, just create identity mapping for matching lines
    generated_lines = generated_code.splitlines()

    pym_idx = 0
    monty_idx = 0

    while pym_idx < len(original_lines) and monty_idx < len(generated_lines):
        pym_line = original_lines[pym_idx].strip()
        monty_line = generated_lines[monty_idx].strip()

        if pym_line == monty_line and pym_line:
            # Lines match - create mapping
            source_map.add_mapping(pym_line=pym_idx + 1, monty_line=monty_idx + 1)

        pym_idx += 1
        monty_idx += 1

    return source_map


def generate_monty_code(parse_result: ParseResult) -> tuple[str, SourceMap]:
    """
    Generate Monty-compatible code from parsed .pym file.

    Args:
        parse_result: Result from parse_pym_file()

    Returns:
        Tuple of (monty_code, source_map)
    """
    # Get sets of names to remove
    external_names = set(parse_result.externals.keys())
    input_names = set(parse_result.inputs.keys())

    # Transform AST
    stripper = GrailDeclarationStripper(external_names, input_names)
    transformed = stripper.visit(parse_result.ast_module)

    # Fix missing locations after transformation
    ast.fix_missing_locations(transformed)

    # Generate code from transformed AST
    monty_code = ast.unparse(transformed)

    # Build source map
    source_map = build_source_map(parse_result.source_lines, monty_code)

    return monty_code, source_map
```

### Testing/Validation

Create `tests/unit/test_codegen.py`:

```python
"""Test code generation."""
from grail.parser import parse_pym_content
from grail.codegen import generate_monty_code


def test_strips_grail_imports():
    """Should remove 'from grail import ...' statements."""
    content = """
from grail import external, Input
from typing import Any

x: int = Input("x")

@external
async def double(n: int) -> int:
    ...

result = await double(x)
result
"""
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    assert "from grail" not in monty_code
    assert "from typing import Any" in monty_code  # typing imports preserved


def test_strips_external_functions():
    """Should remove @external function definitions."""
    content = """
from grail import external

@external
async def double(n: int) -> int:
    ...

result = await double(5)
"""
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    assert "async def double" not in monty_code
    assert "await double(5)" in monty_code  # Call preserved


def test_strips_input_declarations():
    """Should remove Input() assignment statements."""
    content = """
from grail import Input

x: int = Input("x")
y = x * 2
"""
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    assert "Input(" not in monty_code
    assert "y = x * 2" in monty_code  # Usage preserved


def test_preserves_executable_code():
    """Should preserve all executable code."""
    content = """
from grail import external, Input

x: int = Input("x")

@external
async def process(n: int) -> int:
    ...

result = await process(x)
final = result * 2

{
    "value": final,
    "doubled": final * 2
}
"""
    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    # Check executable code is preserved
    assert "result = await process(x)" in monty_code
    assert "final = result * 2" in monty_code
    assert '"value": final' in monty_code


def test_source_map_created():
    """Should create source map for line number mapping."""
    content = """x = 1
y = 2
z = x + y"""

    parse_result = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parse_result)

    # Source map should have mappings
    assert len(source_map.pym_to_monty) > 0
    assert len(source_map.monty_to_pym) > 0
```

**Validation checklist**:
- [ ] `pytest tests/unit/test_codegen.py` passes
- [ ] Grail imports are removed
- [ ] External functions are removed
- [ ] Input declarations are removed
- [ ] Executable code is preserved
- [ ] Source map is created
