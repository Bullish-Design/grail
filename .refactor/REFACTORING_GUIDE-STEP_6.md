## Step 6: Implement Proper Source Mapping

**Priority:** P0 — This is the highest-impact functional fix.
**Files:** `src/grail/codegen.py`, `src/grail/_types.py`

### Background

The current source map implementation in `codegen.py` (lines 50–84) is a **naive heuristic** — it matches lines by content between the original `.pym` source and the generated Monty code. This breaks when:

- Lines don't match exactly (e.g., removed decorators shift line numbers)
- Multiline statements are involved
- AST transformations change line structure

The fix is to track line numbers **during the AST transformation** itself.

### What to Do

1. **Understand the current flow:**
   - `GrailDeclarationStripper` (an `ast.NodeTransformer`) visits the AST and removes grail-specific nodes (`from grail import ...`, `@external` functions, `Input()` assignments).
   - After transformation, `ast.unparse()` produces the Monty code.
   - `build_source_map()` then tries to correlate the result with the original lines.

2. **Replace the heuristic with AST-based tracking:**

   In the `GrailDeclarationStripper`, every AST node already has a `lineno` attribute (its original line in the `.pym` file). The key insight is: after transformation, when you call `ast.unparse()`, the resulting code's line numbers correspond to the **remaining** AST nodes which still carry their original `.pym` line numbers.

   Modify the approach:
   - After stripping, call `ast.fix_missing_locations()` on the transformed module.
   - Walk the transformed AST and record the original `lineno` of each remaining node.
   - After `ast.unparse()`, parse the result back and build the mapping from the new code's line numbers to the original `.pym` line numbers.

   A practical implementation:

   ```python
   def build_source_map(original_ast: ast.Module, transformed_ast: ast.Module,
                         monty_code: str) -> SourceMap:
       source_map = SourceMap()

       # Re-parse the generated code to get new line numbers
       generated_ast = ast.parse(monty_code)

       # Walk both transformed and generated ASTs in parallel
       # Nodes in transformed_ast still have original .pym lineno
       # Nodes in generated_ast have the new Monty lineno
       for t_node, g_node in zip(ast.walk(transformed_ast), ast.walk(generated_ast)):
           if hasattr(t_node, 'lineno') and hasattr(g_node, 'lineno'):
               source_map.add_mapping(
                   monty_line=g_node.lineno,
                   pym_line=t_node.lineno,
               )

       return source_map
   ```

   > **Note:** This parallel-walk approach works because `ast.unparse()` preserves the structure of the AST — it just re-serializes it. The node order in `ast.walk()` will be the same for both trees.

3. **Update `generate_monty_code()`** to pass the transformed AST (before unparsing) to the new `build_source_map()`.

4. **Update the `SourceMap` class in `_types.py`** if needed — the `add_mapping()` method should handle duplicate keys gracefully (keep the first mapping for each Monty line).

### Tests to Validate

```bash
pytest tests/unit/test_codegen.py -v
```

Add new tests in `tests/unit/test_codegen.py`:

```python
def test_source_map_accounts_for_stripped_lines():
    """
    When @external functions are removed, the source map should still
    point Monty lines back to the correct .pym lines.
    """
    from grail.parser import parse_pym_content
    from grail.codegen import generate_monty_code

    content = '''\
from grail import external, Input

budget: float = Input("budget")

@external
async def fetch_data(key: str) -> dict: ...

result = budget * 2
'''
    parsed = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parsed)

    # "result = budget * 2" is line 8 in the .pym
    # In the Monty code it appears earlier since the import, Input, and @external are stripped
    # Find which Monty line contains "result = budget * 2"
    monty_lines = monty_code.strip().splitlines()
    result_monty_line = None
    for i, line in enumerate(monty_lines, 1):
        if "result = budget * 2" in line:
            result_monty_line = i
            break

    assert result_monty_line is not None, "Expected 'result = budget * 2' in Monty code"
    # The source map should point this Monty line back to line 8 of the .pym
    assert source_map.monty_to_pym.get(result_monty_line) == 8


def test_source_map_identity_for_unchanged_lines():
    """Lines that aren't affected by stripping should still map correctly."""
    from grail.parser import parse_pym_content
    from grail.codegen import generate_monty_code

    content = '''\
x = 1
y = 2
z = x + y
'''
    parsed = parse_pym_content(content)
    monty_code, source_map = generate_monty_code(parsed)

    # No stripping needed — all lines should map 1:1
    for monty_line, pym_line in source_map.monty_to_pym.items():
        assert monty_line == pym_line
```

**Done when:** Source maps correctly track line number offsets caused by stripping `@external` functions, `Input()` declarations, and `from grail import` statements.
