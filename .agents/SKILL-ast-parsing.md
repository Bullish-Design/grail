# SKILL-ast-parsing.md - Python AST Patterns for Grail Developers

## Purpose

This skill document provides guidance for AI agents working with Python's `ast` module to parse and transform `.pym` files in the Grail library. Use this skill when working on `parser.py` or `codegen.py` modules.

## When to Use This Skill

**Use SKILL-ast-parsing when**:
- Parsing `.pym` files to extract declarations
- Walking AST to find decorated functions
- Extracting type annotations from function signatures
- Finding `Input()` calls in code
- Removing specific AST nodes (e.g., grail imports)
- Transforming AST to generate Monty code
- Preserving line numbers for source mapping
- Analyzing code structure (functions, classes, imports)

**Do NOT use when**:
- Working with Monty API (use SKILL-monty-api.md instead)
- Generating type stubs (use `stubs.py` patterns)
- Running code (use `script.py` or Monty directly)

## AST Fundamentals

### Importing AST

```python
import ast
```

### Parsing Code

```python
code = """
from grail import external

@external
async def fetch(url: str) -> dict[str, Any]:
    ...

result = await fetch("https://api.example.com")
"""

tree = ast.parse(code)
# tree is an ast.Module node
```

### Parsing with Filename

```python
# For better error messages with line numbers
tree = ast.parse(code, filename="example.pym")
```

### Handling Syntax Errors

```python
try:
    tree = ast.parse(code)
except SyntaxError as e:
    raise grail.ParseError(
        f"Syntax error at line {e.lineno}, column {e.offset}: {e.msg}"
    )
```

## AST Node Types

### Module Node

The root node of any parsed code.

```python
ast.Module(
    body=[...],  # List of statements
    type_ignores=[],
)
```

### FunctionDef Node

Represents a function definition.

```python
ast.FunctionDef(
    name='fetch',  # Function name
    args=arguments(...),  # Function arguments
    body=[...],  # Function body (list of statements)
    decorator_list=[...],  # Decorators (e.g., @external)
    returns=ast.Name(...),  # Return type annotation
    lineno=1,  # Line number (1-based)
    col_offset=0,  # Column offset (0-based)
)
```

### AsyncFunctionDef Node

Like `FunctionDef` but for `async def`.

```python
ast.AsyncFunctionDef(
    name='fetch',
    args=arguments(...),
    body=[...],
    decorator_list=[...],
    returns=ast.Name(...),
    lineno=1,
    col_offset=0,
)
```

### Import and ImportFrom Nodes

```python
# import x
ast.Import(names=[alias(name='x')])

# from grail import external
ast.ImportFrom(
    module='grail',
    names=[alias(name='external')],
    level=0,
)
```

### Assign Node

Represents variable assignment.

```python
# x = 1
ast.Assign(
    targets=[ast.Name(id='x', ctx=Store())],
    value=ast.Constant(value=1),
)

# budget: float = Input("budget")
ast.Assign(
    targets=[ast.AnnAssign(
        target=ast.Name(id='budget', ctx=Store()),
        annotation=ast.Name(id='float', ctx=Load()),
    )],
    value=ast.Call(
        func=ast.Name(id='Input', ctx=Load()),
        args=[ast.Constant(value='budget')],
    ),
)
```

### Call Node

Represents a function call.

```python
# fetch("https://api.example.com")
ast.Call(
    func=ast.Name(id='fetch', ctx=Load()),
    args=[ast.Constant(value='https://api.example.com')],
    keywords=[],
)

# Input("budget", default="Engineering")
ast.Call(
    func=ast.Name(id='Input', ctx=Load()),
    args=[ast.Constant(value='budget')],
    keywords=[keyword(arg='default', value=ast.Constant(value='Engineering'))],
)
```

### Annotation Node

Type annotation (used in `AnnAssign`).

```python
# budget: float
ast.Name(id='float', ctx=Load())
```

## Walking the AST

### Using ast.walk()

Simple iteration over all nodes.

```python
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        print(f"Found function: {node.name}")
    elif isinstance(node, ast.ImportFrom):
        print(f"Found import: {node.module}")
```

### Using NodeVisitor

Pattern for selective visiting.

```python
class ExternalFunctionVisitor(ast.NodeVisitor):
    def __init__(self):
        self.externals = []
    
    def visit_FunctionDef(self, node):
        if has_external_decorator(node):
            self.externals.append(node)
        self.generic_visit(node)

visitor = ExternalFunctionVisitor()
visitor.visit(tree)
print(visitor.externals)
```

### Using NodeTransformer

Pattern for modifying AST.

```python
class ImportRemover(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        # Remove all from grail import ... statements
        if node.module == 'grail':
            return None  # Remove this node
        return node

    def visit_Import(self, node):
        # Remove all import grail statements
        for alias in node.names:
            if alias.name == 'grail':
                return None  # Remove this node
        return node

transformer = ImportRemover()
clean_tree = transformer.visit(tree)
```

## Common Patterns

### Pattern 1: Find All Functions

```python
def find_all_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node)
    return functions
```

### Pattern 2: Check for Specific Decorator

```python
def has_external_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if function has @external decorator."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == 'external':
            return True
    return False
```

### Pattern 3: Extract Function Signature

```python
@dataclass
class FunctionSignature:
    name: str
    is_async: bool
    parameters: list[ParameterSpec]
    return_type: str
    docstring: str | None
    lineno: int
    col_offset: int

def extract_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionSignature:
    is_async = isinstance(node, ast.AsyncFunctionDef)
    parameters = extract_parameters(node.args)
    return_type = extract_return_type(node.returns)
    docstring = ast.get_docstring(node)
    
    return FunctionSignature(
        name=node.name,
        is_async=is_async,
        parameters=parameters,
        return_type=return_type,
        docstring=docstring,
        lineno=node.lineno,
        col_offset=node.col_offset,
    )
```

### Pattern 4: Extract Parameters

```python
@dataclass
class ParameterSpec:
    name: str
    type_annotation: str | None
    default: ast.expr | None

def extract_parameters(args: ast.arguments) -> list[ParameterSpec]:
    parameters = []
    
    # Extract positional args without defaults
    pos_only = args.posonlyargs if hasattr(args, 'posonlyargs') else []
    for arg in pos_only + args.args:
        param = ParameterSpec(
            name=arg.arg,
            type_annotation=extract_type_annotation(arg.annotation),
            default=None,
        )
        parameters.append(param)
    
    # Extract args with defaults
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args[defaults_offset:]):
        default = args.defaults[i - defaults_offset]
        param = ParameterSpec(
            name=arg.arg,
            type_annotation=extract_type_annotation(arg.annotation),
            default=default,
        )
        parameters.append(param)
    
    # Extract keyword-only args
    kw_only = args.kwonlyargs if hasattr(args, 'kwonlyargs') else []
    for arg in kw_only:
        param = ParameterSpec(
            name=arg.arg,
            type_annotation=extract_type_annotation(arg.annotation),
            default=None,  # Would need to check args.kw_defaults
        )
        parameters.append(param)
    
    return parameters
```

### Pattern 5: Extract Type Annotation

```python
def extract_type_annotation(node: ast.expr | None) -> str | None:
    """Extract type annotation as string."""
    if node is None:
        return None
    return ast.unparse(node)
```

### Pattern 6: Extract Return Type

```python
def extract_return_type(node: ast.expr | None) -> str:
    """Extract return type annotation as string."""
    if node is None:
        return 'None'  # Default return type
    return ast.unparse(node)
```

### Pattern 7: Find Input() Calls

```python
@dataclass
class InputCall:
    name: str
    type_annotation: str
    default: ast.expr | None
    lineno: int
    col_offset: int

def find_input_calls(tree: ast.Module) -> list[InputCall]:
    """Find all Input() function calls with type annotations."""
    input_calls = []
    
    for node in ast.walk(tree):
        # Look for: variable: type = Input(...)
        if isinstance(node, ast.AnnAssign):
            # Check if value is a Call to Input
            if isinstance(node.value, ast.Call):
                if is_input_call(node.value):
                    name = node.target.id
                    type_annotation = ast.unparse(node.annotation)
                    default = extract_default_from_call(node.value)
                    input_calls.append(InputCall(
                        name=name,
                        type_annotation=type_annotation,
                        default=default,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                    ))
    
    return input_calls

def is_input_call(node: ast.Call) -> bool:
    """Check if this is a call to Input()."""
    if isinstance(node.func, ast.Name):
        return node.func.id == 'Input'
    return False

def extract_default_from_call(node: ast.Call) -> ast.expr | None:
    """Extract default value from Input("name", default=...)."""
    for kw in node.keywords:
        if kw.arg == 'default':
            return kw.value
    return None
```

### Pattern 8: Extract Imports

```python
@dataclass
class ImportInfo:
    module: str
    names: list[str]
    lineno: int

def find_imports(tree: ast.Module) -> list[ImportInfo]:
    """Find all import statements."""
    imports = []
    
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            imports.append(ImportInfo(
                module='__import__',
                names=names,
                lineno=node.lineno,
            ))
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
            imports.append(ImportInfo(
                module=node.module,
                names=names,
                lineno=node.lineno,
            ))
    
    return imports
```

### Pattern 9: Check for Forbidden Features

```python
def check_forbidden_features(tree: ast.Module) -> list[str]:
    """Check for Python features not supported by Monty."""
    errors = []
    
    for node in ast.walk(tree):
        # Check for classes
        if isinstance(node, ast.ClassDef):
            errors.append(f"Class definition at line {node.lineno}: classes are not supported")
        
        # Check for generators/yield
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            errors.append(f"Yield expression at line {node.lineno}: generators are not supported")
        
        # Check for with statements
        if isinstance(node, ast.With):
            errors.append(f"With statement at line {node.lineno}: with is not supported")
        
        # Check for match statements
        if isinstance(node, ast.Match):
            errors.append(f"Match statement at line {node.lineno}: match is not supported")
        
        # Check for lambda
        if isinstance(node, ast.Lambda):
            errors.append(f"Lambda expression at line {node.lineno}: lambdas are not supported")
    
    return errors
```

### Pattern 10: Strip Grail Imports

```python
class GrailImportRemover(ast.NodeTransformer):
    """Remove all grail import statements."""
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST | None:
        if node.module == 'grail':
            return None  # Remove this node
        return node
    
    def visit_Import(self, node: ast.Import) -> ast.AST | None:
        for alias in node.names:
            if alias.name == 'grail':
                return None  # Remove this node
        return node

def strip_grail_imports(tree: ast.Module) -> ast.Module:
    """Remove all from grail import ... and import grail statements."""
    remover = GrailImportRemover()
    return remover.visit(tree)
```

### Pattern 11: Strip External Function Definitions

```python
class ExternalFunctionRemover(ast.NodeTransformer):
    """Remove @external decorated function definitions."""
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST | None:
        if has_external_decorator(node):
            return None  # Remove this node
        return node
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST | None:
        if has_external_decorator(node):
            return None  # Remove this node
        return node

def strip_external_functions(tree: ast.Module) -> ast.Module:
    """Remove all @external decorated function definitions."""
    remover = ExternalFunctionRemover()
    return remover.visit(tree)
```

### Pattern 12: Remove Input() Calls

```python
class InputCallRemover(ast.NodeTransformer):
    """Remove Input() calls and replace with just the variable name."""
    
    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST | None:
        # Check if: variable: type = Input(...)
        if isinstance(node.value, ast.Call) and is_input_call(node.value):
            # Replace with simple assignment: variable: type
            # This will be bound at runtime by Monty
            return ast.AnnAssign(
                target=node.target,
                annotation=node.annotation,
                value=ast.Name(id=node.target.id, ctx=Load()),
            )
        return node

def strip_input_calls(tree: ast.Module) -> ast.Module:
    """Remove Input() calls, keeping just the variable declarations."""
    remover = InputCallRemover()
    return remover.visit(tree)
```

## Source Mapping

### Pattern 13: Track Line Numbers During Transformation

```python
@dataclass
class SourceMap:
    """Maps line numbers between .pym and monty_code.py"""
    pym_to_monty: dict[int, int] = field(default_factory=dict)
    monty_to_pym: dict[int, int] = field(default_factory=dict)

class LineNumberTracker(ast.NodeTransformer):
    """Track line numbers during AST transformation."""
    
    def __init__(self, source_map: SourceMap):
        super().__init__()
        self.source_map = source_map
        self.monty_line = 0
    
    def generic_visit(self, node: ast.AST) -> ast.AST:
        # Track original line number
        pym_line = getattr(node, 'lineno', None)
        
        # Visit children
        node = self.generic_visit(node)
        
        # If node still exists (not removed), track its new line
        if hasattr(node, 'lineno'):
            self.monty_line += 1
            if pym_line is not None:
                self.source_map.pym_to_monty[pym_line] = self.monty_line
                self.source_map.monty_to_pym[self.monty_line] = pym_line
        
        return node

def transform_with_source_map(tree: ast.Module) -> tuple[ast.Module, SourceMap]:
    """Transform AST and track line number mapping."""
    source_map = SourceMap()
    tracker = LineNumberTracker(source_map)
    transformed_tree = tracker.visit(tree)
    
    # Fix line numbers on transformed tree
    ast.fix_missing_locations(transformed_tree)
    
    return transformed_tree, source_map
```

### Pattern 14: Regenerate Code from AST

```python
def generate_code(tree: ast.Module) -> str:
    """Generate Python code from AST."""
    return ast.unparse(tree)
```

## Grail-Specific Patterns

### Pattern 15: Extract External Functions from .pym

```python
@dataclass
class ExternalSpec:
    name: str
    is_async: bool
    parameters: list[ParameterSpec]
    return_type: str
    docstring: str | None
    lineno: int
    col_offset: int

def extract_externals_from_pym(tree: ast.Module) -> dict[str, ExternalSpec]:
    """Extract all @external decorated functions."""
    externals = {}
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if has_external_decorator(node):
                spec = ExternalSpec(
                    name=node.name,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    parameters=extract_parameters(node.args),
                    return_type=extract_return_type(node.returns),
                    docstring=ast.get_docstring(node),
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                )
                externals[node.name] = spec
    
    return externals
```

### Pattern 16: Extract Input Declarations from .pym

```python
@dataclass
class InputSpec:
    name: str
    type_annotation: str
    default: ast.expr | None
    required: bool
    lineno: int
    col_offset: int

def extract_inputs_from_pym(tree: ast.Module) -> dict[str, InputSpec]:
    """Extract all Input() declarations with type annotations."""
    inputs = {}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.value, ast.Call) and is_input_call(node.value):
                name = node.target.id
                type_annotation = ast.unparse(node.annotation)
                default = extract_default_from_call(node.value)
                
                spec = InputSpec(
                    name=name,
                    type_annotation=type_annotation,
                    default=default,
                    required=default is None,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                )
                inputs[name] = spec
    
    return inputs
```

### Pattern 17: Transform .pym to Monty Code

```python
def transform_pym_to_monty(tree: ast.Module) -> tuple[str, SourceMap]:
    """Transform .pym AST to Monty-compatible code."""
    # Step 1: Remove grail imports
    tree = strip_grail_imports(tree)
    
    # Step 2: Remove @external function definitions
    tree = strip_external_functions(tree)
    
    # Step 3: Remove Input() calls, keep declarations
    tree = strip_input_calls(tree)
    
    # Step 4: Track line numbers during transformation
    tree, source_map = transform_with_source_map(tree)
    
    # Step 5: Generate Python code
    code = ast.unparse(tree)
    
    return code, source_map
```

## Validation Patterns

### Pattern 18: Validate External Function Bodies

```python
def validate_external_function_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check that @external function body is just '...' (Ellipsis)."""
    if len(node.body) != 1:
        return False
    
    stmt = node.body[0]
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis
```

### Pattern 19: Validate Imports

```python
def validate_imports(tree: ast.Module) -> list[str]:
    """Check that only grail and typing imports are allowed."""
    errors = []
    
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ('typing',):
                    errors.append(f"Import at line {node.lineno}: {alias.name} is not allowed")
        
        elif isinstance(node, ast.ImportFrom):
            if node.module not in ('grail', 'typing'):
                errors.append(f"Import at line {node.lineno}: from {node.module} import ... is not allowed")
    
    return errors
```

### Pattern 19: Validate Type Annotations on External Functions

```python
def validate_external_function_annotations(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Check that @external function has complete type annotations."""
    errors = []
    
    # Check return type
    if node.returns is None:
        errors.append(f"Function {node.name} at line {node.lineno}: missing return type annotation")
    
    # Check parameter types
    for arg in node.args.args:
        if arg.annotation is None:
            errors.append(f"Function {node.name} parameter {arg.arg} at line {node.lineno}: missing type annotation")
    
    return errors
```

## Common Pitfalls

### Pitfall 1: Not Handling Async vs Regular Functions

**Wrong**: Only checking `ast.FunctionDef`
```python
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        # Misses async functions!
        pass
```

**Correct**: Check both types
```python
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        pass
```

### Pitfall 2: Not Preserving Line Numbers

**Wrong**: Modifying AST without tracking lines
```python
tree.body = [node for node in tree.body if condition(node)]
# Line numbers are now wrong!
```

**Correct**: Track line numbers during transformation
```python
class Transformer(ast.NodeTransformer):
    def __init__(self):
        self.line_map = {}
        self.new_line = 0
    
    def generic_visit(self, node):
        old_line = node.lineno
        node = super().generic_visit(node)
        if old_line:
            self.new_line += 1
            self.line_map[old_line] = self.new_line
        return node
```

### Pitfall 3: Forgetting to Fix Missing Locations

**Wrong**: Not calling `ast.fix_missing_locations`
```python
tree = transformer.visit(tree)
code = ast.unparse(tree)
# May fail if locations are missing
```

**Correct**: Fix missing locations before unparsing
```python
tree = transformer.visit(tree)
ast.fix_missing_locations(tree)
code = ast.unparse(tree)
```

### Pitfall 4: Confusing `args` Structure

**Wrong**: Assuming simple list
```python
# args is complex!
parameters = args.args  # Missing defaults, keyword-only, etc.
```

**Correct**: Handle all parts of `arguments`
```python
pos_only = args.posonlyargs  # Python 3.8+
args = args.args
defaults = args.defaults
kw_only = args.kwonlyargs  # Python 3.8+
kw_defaults = args.kw_defaults  # Python 3.8+
```

### Pitfall 5: Not Checking Decorator List

**Wrong**: Checking just first decorator
```python
if node.decorator_list[0].id == 'external':
    # Fails if decorator_list is empty!
    pass
```

**Correct**: Check all decorators
```python
for decorator in node.decorator_list:
    if isinstance(decorator, ast.Name) and decorator.id == 'external':
        pass
```

## Testing AST Patterns

### Pattern 20: Test AST Extraction

```python
def test_extract_external_functions():
    code = """
    @external
    async def fetch(url: str) -> dict[str, Any]:
        ...
    """
    tree = ast.parse(code)
    externals = extract_externals_from_pym(tree)
    
    assert 'fetch' in externals
    assert externals['fetch'].is_async
    assert externals['fetch'].name == 'fetch'
    assert externals['fetch'].lineno == 2
```

### Pattern 21: Test AST Transformation

```python
def test_strip_imports():
    code = """
    from grail import external, Input
    x = 1
    """
    tree = ast.parse(code)
    cleaned = strip_grail_imports(tree)
    
    generated = ast.unparse(cleaned)
    assert 'from grail import' not in generated
    assert 'x = 1' in generated
```

### Pattern 22: Test Source Mapping

```python
def test_source_mapping():
    code = """
    x = 1
    y = 2
    """
    tree = ast.parse(code)
    transformed, source_map = transform_with_source_map(tree)
    
    # Verify mapping
    assert 2 in source_map.pym_to_monty
    assert 1 in source_map.pym_to_monty
```

## Performance Considerations

### 1. Use NodeVisitor Instead of walk() When Possible

**Good**: NodeVisitor is more efficient
```python
class MyVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        # Process function
        pass

visitor = MyVisitor()
visitor.visit(tree)
```

**Acceptable**: ast.walk() is simpler
```python
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        # Process function
        pass
```

### 2. Cache AST Walks When Needed Multiple Times

**Good**: Cache if you need multiple passes
```python
# First pass: find all nodes
all_nodes = list(ast.walk(tree))

# Use cached list for multiple passes
functions = [n for n in all_nodes if isinstance(n, ast.FunctionDef)]
imports = [n for n in all_nodes if isinstance(n, isinstance(n, (ast.Import, ast.ImportFrom))]
```

### 3. Avoid Deep Copies of AST

**Good**: Modify in place when safe
```python
# Modify tree in place
tree.body = [node for node in tree.body if condition(node)]
```

**Acceptable**: Copy when needed
```python
# Create copy to preserve original
import copy
new_tree = copy.deepcopy(tree)
```

## Summary Checklist

When working with AST in Grail, ensure you:

- [ ] Handle both `ast.FunctionDef` and `ast.AsyncFunctionDef`
- [ ] Check all decorators in `decorator_list`, not just first
- [ ] Extract type annotations using `ast.unparse()`
- [ ] Handle complex `arguments` structure (posonly, args, defaults, kwonly)
- [ ] Track line numbers during transformations
- [ ] Call `ast.fix_missing_locations()` after transformations
- [ ] Use `ast.get_docstring()` for docstrings
- [ ] Handle `Ellipsis` as body for `@external` functions
- [ ] Validate imports (only `grail` and `typing` allowed)
- [ ] Check for forbidden Monty features (classes, generators, with, match)
- [ ] Preserve source mapping between `.pym` and `monty_code.py`
- [ ] Test AST transformations thoroughly

## References

- **Python AST documentation**: https://docs.python.org/3/library/ast.html
- **AST Explorer**: https://astexplorer.net/
- **Grail ARCHITECTURE.md**: Module responsibilities
- **Grail SPEC.md**: `.pym` file format specification
