## Step 11: Validate Generated Code in Codegen

**Priority:** Medium
**Files:** `src/grail/codegen.py`

### Background

The code review notes that `generate_monty_code()` does not validate that the generated Python code is syntactically valid. If a bug in the AST transformer produces invalid code, it would fail silently until Monty tries to run it.

### What to Do

1. Open `src/grail/codegen.py` and find `generate_monty_code()` (around line 87).

2. After calling `ast.unparse()` to produce the Monty code string, parse it back to verify it is valid Python:
   ```python
   monty_code = ast.unparse(transformed)

   # Validate generated code is syntactically valid
   try:
       ast.parse(monty_code)
   except SyntaxError as e:
       raise GrailError(
           f"Code generation produced invalid Python: {e}. "
           "This is a bug in grail — please report it."
       )
   ```

3. Import `GrailError` from `grail.errors` at the top of the file.

### Tests to Validate

```bash
pytest tests/unit/test_codegen.py -v
```

Add a new test:

```python
def test_generate_monty_code_produces_valid_python():
    """The output of generate_monty_code should always be valid Python."""
    from grail.parser import parse_pym_content
    from grail.codegen import generate_monty_code
    import ast

    content = '''\
from grail import external, Input

budget: float = Input("budget")

@external
async def fetch(url: str) -> str: ...

result = budget * 2
'''
    parsed = parse_pym_content(content)
    monty_code, _ = generate_monty_code(parsed)

    # Should not raise
    ast.parse(monty_code)
```

**Done when:** `generate_monty_code()` raises a clear error if it produces invalid Python, and the normal case is verified by a test.
