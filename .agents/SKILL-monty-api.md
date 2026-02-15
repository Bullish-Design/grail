# SKILL-monty-api.md - Monty API Reference for Grail Developers

## Purpose

This skill document provides comprehensive guidance for AI agents writing code that interfaces directly with Monty (the secure Python interpreter written in Rust). Use this skill when working on modules that call `pydantic_monty`, such as `script.py`, `snapshot.py`, or integration tests.

## Context

Monty source code is available in `.context/monty-main/`. Key components:
- **pydantic-monty** — Python bindings for Monty Rust interpreter
- **Monty Core Classes** — `Monty`, `MontySnapshot`, `MontyFutureSnapshot`, `MontyComplete`
- **Error Classes** — `MontyError`, `MontySyntaxError`, `MontyRuntimeError`, `MontyTypingError`
- **Resource Limits** — `ResourceLimits` TypedDict
- **OS Access** — `OSAccess`, `MemoryFile`, `CallbackFile`, `AbstractOS`

## When to Use This Skill

**Use SKILL-monty-api when**:
- Creating `pydantic_monty.Monty` instances
- Calling `run()` or `start()` methods on Monty objects
- Handling `MontySnapshot`, `MontyComplete`, or `MontyFutureSnapshot`
- Translating Grail resource limits to Monty format
- Creating `OSAccess` with `MemoryFile` objects
- Passing external functions to Monty
- Handling Monty exceptions
- Using type checking with `type_check_stubs`
- Serializing/deserializing Monty instances and snapshots
- Writing integration tests with Monty

**Do NOT use when**:
- Working with AST parsing (use SKILL-ast-parsing.md instead)
- Generating stubs (use `stubs.py` patterns)
- CLI implementation (Monty is only called internally)

## Core Classes

### 1. Monty Class

**Purpose**: Create a Monty interpreter instance that can be run multiple times

**Location**: `pydantic_monty.Monty`

#### Constructor

```python
Monty(
    code: str,
    *,
    script_name: str = 'main.py',
    inputs: list[str] | None = None,
    external_functions: list[str] | None = None,
    type_check: bool = False,
    type_check_stubs: str | None = None,
    dataclass_registry: list[type] | None = None,
) -> Monty
```

**Parameters**:
- `code` (required): Python code to execute
- `script_name`: Name used in tracebacks and error messages (default: `'main.py'`)
- `inputs`: List of input variable names available in code (e.g., `['x', 'y']`)
- `external_functions`: List of external function names code can call (e.g., `['fetch', 'save']`)
- `type_check`: Whether to perform type checking (default: `False`)
- `type_check_stubs`: Optional code to prepend before type checking (e.g., input declarations, external function signatures)
- `dataclass_registry`: Optional list of dataclass types for `isinstance()` support on output

**Raises**:
- `MontySyntaxError`: If code cannot be parsed
- `MontyTypingError`: If `type_check=True` and type errors are found

**Example**:
```python
from pydantic_monty import Monty

code = """
result = await fetch_data(id)
result * 2
"""

# Without type checking
m = Monty(
    code,
    inputs=['id'],
    external_functions=['fetch_data'],
    script_name='process.py',
)

# With type checking and stubs
stubs = """
from typing import Any

async def fetch_data(id: int) -> dict[str, Any]:
    ...

id: int
"""

m = Monty(
    code,
    inputs=['id'],
    external_functions=['fetch_data'],
    type_check=True,
    type_check_stubs=stubs,
)
```

#### Methods

**`run()`** — Execute code synchronously
```python
m.run(
    *,
    inputs: dict[str, Any] | None = None,
    limits: ResourceLimits | None = None,
    external_functions: dict[str, Callable[..., Any]] | None = None,
    print_callback: Callable[[Literal['stdout'], str], None] | None = None,
    os: Callable[[OsFunction, tuple[Any, ...]], Any] | None = None,
) -> Any
```

**Returns**: The result of the last expression in code

**Example**:
```python
result = m.run(
    inputs={'id': 42},
    external_functions={'fetch_data': my_fetch_func},
)
```

**`start()`** — Start execution and pause on first external function call
```python
m.start(
    *,
    inputs: dict[str, Any] | None = None,
    limits: ResourceLimits | None = None,
    print_callback: Callable[[Literal['stdout'], str], None] | None = None,
) -> MontySnapshot | MontyFutureSnapshot | MontyComplete
```

**Returns**: 
- `MontySnapshot`: External function call pending
- `MontyFutureSnapshot`: Multiple futures pending
- `MontyComplete`: Execution finished without external calls

**Example**:
```python
progress = m.start(inputs={'id': 42})
if isinstance(progress, MontySnapshot):
    # Handle external function call
    func_name = progress.function_name
    args = progress.args
    result = await external_functions[func_name](*args)
    progress = progress.resume(return_value=result)
```

**`type_check()`** — Perform static type checking
```python
m.type_check(prefix_code: str | None = None) -> None
```

**Raises**: `MontyTypingError` if type errors found

**Example**:
```python
m = Monty('x + 1')
m.type_check()  # OK

m = Monty('"hello" + 1')
try:
    m.type_check()
except MontyTypingError as e:
    print(f"Type error: {e.display()}")
```

**`dump()`** — Serialize Monty instance to bytes
```python
m.dump() -> bytes
```

**Example**:
```python
# Serialize for caching
data = m.dump()

# Later, restore and run
m2 = Monty.load(data)
result = m2.run(inputs={'x': 41})
```

#### Static Methods

**`load()`** — Deserialize Monty instance from bytes
```python
@staticmethod
Monty.load(
    data: bytes,
    *,
    dataclass_registry: list[type] | None = None,
) -> Monty
```

### 2. MontySnapshot Class

**Purpose**: Represents paused execution waiting for an external function call

**Location**: `pydantic_monty.MontySnapshot`

#### Properties

```python
@property
def script_name(self) -> str: ...

@property
def is_os_function(self) -> bool: ...

@property
def function_name(self) -> str | OsFunction: ...

@property
def args(self) -> tuple[Any, ...]: ...

@property
def kwargs(self) -> dict[str, Any]: ...

@property
def call_id(self) -> int: ...
```

**Descriptions**:
- `script_name`: Name of script being executed
- `is_os_function`: `True` if this is an OS function call (e.g., `Path.stat`)
- `function_name`: Name of function being called (external or OS function)
- `args`: Positional arguments passed to function
- `kwargs`: Keyword arguments passed to function
- `call_id`: Unique identifier for this external function call

#### Methods

**`resume()`** — Resume execution with return value or exception
```python
@overload
def resume(self, *, return_value: Any) -> MontySnapshot | MontyFutureSnapshot | MontyComplete: ...

@overload
def resume(self, *, exception: BaseException) -> MontySnapshot | MontyFutureSnapshot | MontyComplete: ...

@overload
def resume(self, *, future: EllipsisType) -> MontySnapshot | MontyFutureSnapshot | MontyComplete: ...
```

**Parameters** (use one):
- `return_value`: Value to return from external function
- `exception`: Exception to raise in Monty interpreter
- `future`: Placeholder indicating a pending async operation

**Returns**: New progress object (snapshot, future snapshot, or complete)

**Example**:
```python
# Return value
snapshot = snapshot.resume(return_value=42)

# Raise exception
snapshot = snapshot.resume(exception=ValueError("error"))

# Mark as future
snapshot = snapshot.resume(future=...)
```

**`dump()`** — Serialize snapshot to bytes
```python
snapshot.dump() -> bytes
```

#### Static Methods

**`load()`** — Deserialize snapshot from bytes
```python
@staticmethod
def load(
    data: bytes,
    *,
    print_callback: Callable[[Literal['stdout'], str], None] | None = None,
    dataclass_registry: list[type] | None = None,
) -> MontySnapshot
```

### 3. MontyFutureSnapshot Class

**Purpose**: Represents paused execution waiting for multiple futures to resolve

**Location**: `pydantic_monty.MontyFutureSnapshot`

#### Properties

```python
@property
def script_name(self) -> str: ...

@property
def pending_call_ids(self) -> list[int]: ...
```

**Descriptions**:
- `script_name`: Name of script being executed
- `pending_call_ids`: List of call IDs for pending futures

#### Methods

**`resume()`** — Resume execution with results for futures
```python
def resume(
    self,
    results: dict[int, ExternalResult],
) -> MontySnapshot | MontyFutureSnapshot | MontyComplete
```

**Parameters**:
- `results`: Dict mapping call_id to result. Each result must have either `'return_value'` or `'exception'` key

**Returns**: New progress object

**Example**:
```python
results = {
    call_id_1: {'return_value': result1},
    call_id_2: {'exception': ValueError("error")},
}
snapshot = snapshot.resume(results)
```

**`dump()`** — Serialize future snapshot to bytes
```python
snapshot.dump() -> bytes
```

#### Static Methods

**`load()`** — Deserialize future snapshot from bytes
```python
@staticmethod
def load(
    data: bytes,
    *,
    print_callback: Callable[[Literal['stdout'], str], None] | None = None,
    dataclass_registry: list[type] | None = None,
) -> MontyFutureSnapshot
```

### 4. MontyComplete Class

**Purpose**: Represents completed execution with final result

**Location**: `pydantic_monty.MontyComplete`

#### Properties

```python
@property
def output(self) -> Any: ...
```

**Description**: Final output value from executed code

### 5. Error Classes

#### Hierarchy

```
MontyError (base)
├── MontySyntaxError
├── MontyTypingError
└── MontyRuntimeError
```

#### MontyError

**Purpose**: Base exception for all Monty errors

**Properties**:
```python
def exception(self) -> BaseException: ...

def __str__(self) -> str: ...
```

**Methods**:
```python
def exception(self) -> BaseException: 
    """Returns inner exception as a Python exception object."""
```

#### MontySyntaxError

**Purpose**: Raised when Python code has syntax errors or cannot be parsed

**Methods**:
```python
def display(self, format: Literal['type-msg', 'msg'] = 'msg') -> str:
    """Returns formatted exception string."""
```

#### MontyTypingError

**Purpose**: Raised when type checking finds errors in code

**Methods**:
```python
def display(
    self,
    format: Literal['full', 'concise', 'azure', 'json', 'jsonlines', 'rdjson', 'pylint', 'gitlab', 'github'] = 'full',
    color: bool = False,
) -> str:
    """Renders type error diagnostics with specified format and color."""
```

**Example**:
```python
try:
    m = Monty('"hello" + 1', type_check=True)
except MontyTypingError as e:
    print(e.display('full', color=False))
```

#### MontyRuntimeError

**Purpose**: Raised when Monty code fails during execution

**Properties**:
```python
def traceback(self) -> list[Frame]: ...
```

**Methods**:
```python
def traceback(self) -> list[Frame]:
    """Returns Monty traceback as a list of Frame objects."""

def display(self, format: Literal['traceback', 'type-msg', 'msg'] = 'traceback') -> str:
    """Returns formatted exception string."""
```

#### Frame Class

**Purpose**: Single frame in a Monty traceback

**Properties**:
```python
@property
def filename(self) -> str: ...

@property
def line(self) -> int: ...

@property
def column(self) -> int: ...

@property
def end_line(self) -> int: ...

@property
def end_column(self) -> int: ...

@property
def function_name(self) -> str | None: ...

@property
def source_line(self) -> str | None: ...
```

**Description**:
- `filename`: The filename where code is located
- `line`: Line number (1-based)
- `column`: Column number (1-based)
- `end_line`: End line number (1-based)
- `end_column`: End column number (1-based)
- `function_name`: Name of function, or `None` for module-level code
- `source_line`: The source code line for preview in traceback

## Resource Limits

### ResourceLimits TypedDict

**Location**: `pydantic_monty.ResourceLimits`

**Definition**:
```python
class ResourceLimits(TypedDict, total=False):
    max_allocations: int  # Maximum heap allocations
    max_duration_secs: float  # Maximum execution time in seconds
    max_memory: int  # Maximum heap memory in bytes
    gc_interval: int  # Run garbage collection every N allocations
    max_recursion_depth: int  # Maximum function call stack depth
```

**Grail Mapping**:
```python
# Grail limits
limits = {
    "max_memory": "16mb",      # String format
    "max_duration": "2s",      # String format
    "max_recursion": 200,         # Direct int
}

# Translate to Monty format
monty_limits = ResourceLimits(
    max_memory=parse_memory("16mb"),      # 16 * 1024 * 1024
    max_duration_secs=2.0,               # Parse "2s"
    max_recursion_depth=200,
)
```

**Parsing Functions** (implement in `limits.py`):
```python
def parse_memory(value: str | int) -> int:
    """Parse '16mb', '1gb', etc. to bytes."""
    if isinstance(value, int):
        return value
    # Parse string format...
    return bytes

def parse_duration(value: str | float) -> float:
    """Parse '500ms', '2s', etc. to seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    # Parse string format...
    return seconds
```

## OS Access and Filesystem

### OSAccess Class

**Purpose**: In-memory virtual filesystem for sandboxed Monty execution

**Location**: `pydantic_monty.OSAccess`

#### Constructor

```python
OSAccess(
    files: Sequence[AbstractFile] | None = None,
    environ: dict[str, str] | None = None,
    *,
    root_dir: str | PurePosixPath = '/',
)
```

**Parameters**:
- `files`: List of `AbstractFile` objects (typically `MemoryFile` instances)
- `environ`: Environment variables accessible via `os.getenv()`
- `root_dir`: Base directory for normalizing relative file paths (default: `'/'`)

**Example**:
```python
from pydantic_monty import OSAccess, MemoryFile

fs = OSAccess(
    files=[
        MemoryFile('/data/config.json', content='{"debug": true}'),
        MemoryFile('/data/data.bin', content=b'\\x00\\x01\\x02'),
    ],
    environ={'API_KEY': 'secret'},
)
```

### MemoryFile Class

**Purpose**: In-memory virtual file for use with OSAccess

**Location**: `pydantic_monty.MemoryFile`

#### Constructor

```python
MemoryFile(
    path: str | PurePosixPath,
    content: str | bytes,
    *,
    permissions: int = 0o644,
)
```

**Parameters**:
- `path`: Virtual path in OSAccess filesystem
- `content`: Initial file content (str for text, bytes for binary)
- `permissions`: Unix-style permission bits (default: `0o644`)

**Grail Mapping**:
```python
# Grail input
files = {
    "/data/config.json": '{"debug": true}',
    "/data/data.bin": b'\\x00\\x01\\x02',
}

# Convert to Monty format
fs = OSAccess([
    MemoryFile(path, content)
    for path, content in files.items()
])
```

### CallbackFile Class

**Purpose**: Virtual file backed by custom read/write callbacks

**Location**: `pydantic_monty.CallbackFile`

**Security Warning**: Callbacks run in host Python environment with FULL access to real filesystem. For sandboxed execution, use `MemoryFile` instead.

#### Constructor

```python
CallbackFile(
    path: str | PurePosixPath,
    read: Callable[[PurePosixPath], str | bytes],
    write: Callable[[PurePosixPath, str | bytes], None],
    *,
    permissions: int = 0o644,
)
```

## Convenience Function: run_monty_async

**Purpose**: Convenient way to run Monty code with async external functions and OS access

**Location**: `pydantic_monty.run_monty_async`

#### Signature

```python
async def run_monty_async(
    monty_runner: Monty,
    *,
    inputs: dict[str, Any] | None = None,
    external_functions: dict[str, Callable[..., Any]] | None = None,
    limits: ResourceLimits | None = None,
    print_callback: Callable[[Literal['stdout'], str], None] | None = None,
    os: AbstractOS | None = None,
) -> Any:
```

**Parameters**:
- `monty_runner`: The Monty runner to use
- `external_functions`: Dict of external functions (can be sync or async)
- `inputs`: Dict of input values
- `limits`: Resource limits configuration
- `print_callback`: Callback for print output
- `os`: Optional OS access handler for filesystem operations

**Returns**: The output of the Monty script

**Behavior**:
- Handles sync and async external functions automatically
- Manages `MontySnapshot`, `MontyFutureSnapshot`, `MontyComplete` state machine
- Calls OS functions via provided `os` handler
- Uses ThreadPoolExecutor to release GIL during Monty execution

**Example**:
```python
from pydantic_monty import Monty, OSAccess, MemoryFile, run_monty_async

m = Monty(
    'content = await read_file("/data/config.json"); content',
    external_functions=['read_file'],
)

fs = OSAccess([
    MemoryFile('/data/config.json', content='{"debug": true}'),
])

async def main():
    result = await run_monty_async(
        m,
        external_functions={
            'read_file': lambda path: fs.path_read_text(path),
        },
        os=fs,
    )
    print(result)
```

## Common Usage Patterns

### Pattern 1: Simple Execution

```python
from pydantic_monty import Monty

code = 'x + 1'
m = Monty(code, inputs=['x'])
result = m.run(inputs={'x': 41})  # result == 42
```

### Pattern 2: With External Functions

```python
from pydantic_monty import Monty

code = 'result = await fetch(url); result * 2'

def fetch(url):
    return f"data from {url}"

m = Monty(code, external_functions=['fetch'])
result = m.run(external_functions={'fetch': fetch})
```

### Pattern 3: Pause/Resume Execution

```python
from pydantic_monty import Monty

code = 'result = await fetch(1, 2); await save(result)'

m = Monty(code, external_functions=['fetch', 'save'])
progress = m.start()

# First call: fetch(1, 2)
assert isinstance(progress, MontySnapshot)
assert progress.function_name == 'fetch'
assert progress.args == (1, 2)
progress = progress.resume(return_value='data')

# Second call: save('data')
assert isinstance(progress, MontySnapshot)
assert progress.function_name == 'save'
assert progress.args == ('data',)
progress = progress.resume(return_value=None)

# Complete
assert isinstance(progress, MontyComplete)
assert progress.output is None
```

### Pattern 4: Type Checking

```python
from pydantic_monty import Monty, MontyTypingError

code = 'result = await fetch(url); result * 2'
stubs = """
from typing import Any

async def fetch(url: str) -> dict[str, Any]:
    ...
"""

m = Monty(code, external_functions=['fetch'], type_check=True, type_check_stubs=stubs)
# If code has type errors, MontyTypingError is raised here
result = m.run(external_functions={'fetch': fetch})
```

### Pattern 5: With Filesystem Access

```python
from pydantic_monty import Monty, OSAccess, MemoryFile

code = """
from pathlib import Path
content = Path('/data/config.json').read_text()
"""

fs = OSAccess([
    MemoryFile('/data/config.json', content='{"debug": true}'),
])

m = Monty(code)
result = m.run(os=fs)  # result == '{"debug": true}'
```

### Pattern 6: Serialization

```python
from pydantic_monty import Monty

# Serialize parsed code for caching
m = Monty('x + 1', inputs=['x'])
data = m.dump()

# Later, restore and run
m2 = Monty.load(data)
result = m2.run(inputs={'x': 41})  # result == 42
```

### Pattern 7: With Resource Limits

```python
from pydantic_monty import Monty, ResourceLimits

code = """
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
fib(10)
"""

m = Monty(code)
limits = ResourceLimits(
    max_recursion_depth=100,
    max_duration_secs=1.0,
)
result = m.run(limits=limits)
```

## Error Handling Patterns

### Pattern 1: Catch Specific Monty Errors

```python
from pydantic_monty import Monty, MontySyntaxError, MontyRuntimeError, MontyTypingError

try:
    m = Monty('x + 1', type_check=True)
except MontySyntaxError as e:
    print(f"Syntax error: {e.display('msg')}")
except MontyTypingError as e:
    print(f"Type error: {e.display('full')}")
except MontyRuntimeError as e:
    print(f"Runtime error: {e.display('traceback')}")
    print(f"Traceback frames:")
    for frame in e.traceback():
        print(f"  {frame.filename}:{frame.line} in {frame.function_name}")
```

### Pattern 2: Handle External Function Errors

```python
from pydantic_monty import Monty, MontyRuntimeError

code = 'result = await fetch(url)'

def fetch(url):
    raise ValueError("network error")

m = Monty(code, external_functions=['fetch'])
try:
    result = m.run(external_functions={'fetch': fetch})
except MontyRuntimeError as e:
    # Check if the error came from external function
    inner = e.exception()
    if isinstance(inner, ValueError):
        print(f"External function error: {inner}")
```

## Grail-Specific Integration Points

### 1. External Function Mapping

**Grail convention**: Use `externals` (singular), map to Monty's `external_functions` (plural)

```python
# In Grail's script.py
def run(self, inputs, externals):
    # Map Grail externals to Monty external_functions
    m = Monty(
        self.monty_code,
        external_functions=list(self.externals.keys()),
    )
    return m.run(
        inputs=inputs,
        external_functions=externals,  # Pass the implementations
    )
```

### 2. Input Variable Mapping

**Grail convention**: Declare inputs in Monty constructor, provide values in run()

```python
# In Grail's script.py
def __init__(self):
    # Extract input names from Input() declarations
    self.input_names = list(self.inputs.keys())

def load_monty(self):
    # Create Monty with input names
    self.monty = Monty(
        self.monty_code,
        inputs=self.input_names,
    )

def run(self, inputs, externals):
    # Provide input values at runtime
    return self.monty.run(
        inputs=inputs,  # Values for declared inputs
        external_functions=externals,
    )
```

### 3. Resource Limit Translation

**Grail convention**: Parse string formats, translate to bytes/seconds

```python
# In Grail's limits.py
def translate_limits(limits: dict) -> ResourceLimits:
    monty_limits = {}
    if 'max_memory' in limits:
        monty_limits['max_memory'] = parse_memory(limits['max_memory'])
    if 'max_duration' in limits:
        monty_limits['max_duration_secs'] = parse_duration(limits['max_duration'])
    if 'max_recursion' in limits:
        monty_limits['max_recursion_depth'] = limits['max_recursion']
    if 'max_allocations' in limits:
        monty_limits['max_allocations'] = limits['max_allocations']
    return ResourceLimits(**monty_limits)
```

### 4. Filesystem Translation

**Grail convention**: Convert dict to OSAccess with MemoryFile objects

```python
# In Grail's script.py
def translate_files(files: dict[str, str | bytes]) -> OSAccess:
    memory_files = []
    for path, content in files.items():
        if isinstance(content, str):
            memory_files.append(MemoryFile(path, content.encode()))
        else:
            memory_files.append(MemoryFile(path, content))
    return OSAccess(memory_files)
```

### 5. Type Stub Integration

**Grail convention**: Pass generated stubs to Monty for type checking

```python
# In Grail's script.py
def run_with_type_check(self, inputs, externals):
    # Generate stubs from @external and Input() declarations
    stubs = self._generate_stubs()
    
    # Create Monty with type checking enabled
    m = Monty(
        self.monty_code,
        inputs=list(self.inputs.keys()),
        external_functions=list(self.externals.keys()),
        type_check=True,
        type_check_stubs=stubs,
    )
    return m.run(inputs=inputs, external_functions=externals)
```

## Common Pitfalls

### 1. Confusing `inputs` Parameter Names

**Wrong**: Passing inputs as constructor argument
```python
# Don't do this
m = Monty(code, inputs={'x': 41})  # Wrong!
result = m.run()  # Error!
```

**Correct**: Pass input names as list, values in run()
```python
# Do this
m = Monty(code, inputs=['x'])
result = m.run(inputs={'x': 41})
```

### 2. Forgetting to Resume Snapshots

**Wrong**: Calling `start()` but not resuming
```python
progress = m.start()
# Execution never completes!
```

**Correct**: Resume in a loop until complete
```python
progress = m.start()
while not isinstance(progress, MontyComplete):
    if isinstance(progress, MontySnapshot):
        # Handle external function
        result = await external_functions[progress.function_name](*progress.args)
        progress = progress.resume(return_value=result)
```

### 3. Not Handling MontyFutureSnapshot

**Wrong**: Only handling `MontySnapshot`
```python
progress = m.start()
if isinstance(progress, MontySnapshot):
    # Handle single call
    progress = progress.resume(return_value=...)
# Misses MontyFutureSnapshot case!
```

**Correct**: Handle all progress types
```python
progress = m.start()
while True:
    if isinstance(progress, MontyComplete):
        break
    elif isinstance(progress, MontySnapshot):
        # Handle single external function
        progress = progress.resume(return_value=...)
    elif isinstance(progress, MontyFutureSnapshot):
        # Handle multiple futures
        results = {}
        for call_id in progress.pending_call_ids:
            results[call_id] = await external_functions[call_id]()
        progress = progress.resume(results)
```

### 4. Not Providing Required External Functions

**Wrong**: Declaring external functions but not providing implementations
```python
m = Monty('fetch()', external_functions=['fetch'])
result = m.run()  # Raises KeyError!
```

**Correct**: Provide implementations
```python
m = Monty('fetch()', external_functions=['fetch'])
result = m.run(external_functions={'fetch': my_fetch})
```

### 5. Mixing Sync/Async External Functions Incorrectly

**Wrong**: Assuming all external functions must be async
```python
# All externals must be awaitable, even sync ones?
async def my_sync_func():
    return "data"  # Not actually async

m.run(external_functions={'fetch': my_sync_func})  # Works but inefficient
```

**Correct**: Use sync functions for sync operations, async for async
```python
# Sync function
def my_sync_func():
    return "data"

# Async function
async def my_async_func():
    return await some_async_operation()

m.run(external_functions={
    'fetch': my_sync_func,    # Sync
    'fetch_async': my_async_func,  # Async
})
```

## Testing with Monty

### Pattern 1: Test Monty Accepts Generated Code

```python
def test_monty_accepts_generated_code():
    # Generate code as Grail would
    code = generate_monty_code_from_pym("example.pym")
    
    # Verify Monty can parse it
    from pydantic_monty import Monty
    m = Monty(code)
    assert m is not None
```

### Pattern 2: Test Type Checking Works

```python
def test_monty_type_checking():
    # Generate stubs as Grail would
    stubs = generate_stubs_from_declarations(...)
    code = generate_monty_code_from_pym("example.pym")
    
    # Verify type checking passes
    from pydantic_monty import Monty, MontyTypingError
    m = Monty(code, type_check=True, type_check_stubs=stubs)
    try:
        m.type_check()
    except MontyTypingError as e:
        pytest.fail(f"Type checking failed: {e.display()}")
```

### Pattern 3: Test External Functions Work

```python
def test_monty_external_functions():
    code = 'result = await fetch(42)'
    
    # Mock external function
    call_log = []
    def fetch(id):
        call_log.append(('fetch', id))
        return f"data-{id}"
    
    from pydantic_monty import Monty
    m = Monty(code, external_functions=['fetch'])
    result = m.run(external_functions={'fetch': fetch})
    
    assert result == "data-42"
    assert call_log == [('fetch', 42)]
```

### Pattern 4: Test Filesystem Access

```python
def test_monty_filesystem_access():
    code = """
    from pathlib import Path
    content = Path('/data/test.txt').read_text()
    content.upper()
    """
    
    from pydantic_monty import Monty, OSAccess, MemoryFile
    fs = OSAccess([
        MemoryFile('/data/test.txt', content='hello world'),
    ])
    
    m = Monty(code)
    result = m.run(os=fs)
    assert result == "HELLO WORLD"
```

### Pattern 5: Test Resource Limits

```python
def test_monty_resource_limits():
    code = """
    def recurse(n):
        return recurse(n - 1) if n > 0 else 0
    recurse(10)
    """
    
    from pydantic_monty import Monty, ResourceLimits, MontyRuntimeError
    m = Monty(code)
    
    # Should fail with low recursion limit
    limits = ResourceLimits(max_recursion_depth=5)
    with pytest.raises(MontyRuntimeError) as exc_info:
        m.run(limits=limits)
    
    # Check it's a RecursionError
    assert isinstance(exc_info.value.exception(), RecursionError)
```

## Performance Considerations

### 1. Reuse Monty Instances

**Good**: Create once, run multiple times
```python
m = Monty(code, inputs=['x'])
for value in range(1000):
    result = m.run(inputs={'x': value})
```

**Bad**: Recreate for each run
```python
for value in range(1000):
    m = Monty(code, inputs=['x'])  # Reparses each time!
    result = m.run(inputs={'x': value})
```

### 2. Use Serialization for Caching

**Good**: Serialize and reload parsed Monty
```python
# Parse and serialize once
m = Monty(code)
data = m.dump()

# Load serialized data (faster than reparsing)
for _ in range(1000):
    m = Monty.load(data)
    result = m.run(inputs={...})
```

### 3. Release GIL During Execution

**Good**: Monty releases GIL, allowing parallel execution
```python
# Monty execution doesn't block other threads
m = Monty(code)
result = m.run()  # GIL released during execution
```

### 4. Avoid Unnecessary Type Checking

**Good**: Type check once during development
```python
# Type check during testing
if testing:
    m = Monty(code, type_check=True, type_check_stubs=stubs)
    m.type_check()

# Skip type checking in production
m = Monty(code)  # No type_check=True
result = m.run()
```

## Monty Feature Support

### Supported Features

- Functions and closures
- Async/await
- Comprehensions (list, dict, set, generator expressions)
- Basic data structures (int, float, str, bool, list, dict, tuple, set, None)
- Control flow (if/elif/else, for, while, try/except/finally)
- F-strings
- Type annotations
- `dataclasses` (coming soon)
- `asyncio` module

### Unsupported Features

- Classes (coming soon)
- Generators and `yield`
- `with` statements
- `match` statements (coming soon)
- Lambda expressions
- Most of the standard library
- `eval()` and `exec()`
- `__import__()`

When generating code for Monty, ensure it only uses supported features.

## Debugging Monty Code

### 1. Inspect Generated Code

When debugging, check what code is sent to Monty:
```python
print("Code sent to Monty:")
print(monty_code)
print()
```

### 2. Use Type Checking

```python
# Check for type errors before running
try:
    m.type_check()
except MontyTypingError as e:
    print(f"Type errors found:\n{e.display('full')}")
```

### 3. Add Print Statements

```python
# Add prints to Monty code for debugging
code_with_debug = f"""
print(f"Starting execution with inputs: {{x}}")
result = x + 1
print(f"Result: {{result}}")
result
"""

m = Monty(code_with_debug, inputs=['x'])
result = m.run(inputs={'x': 41})
```

### 4. Use Traceback

```python
try:
    result = m.run()
except MontyRuntimeError as e:
    print("Full traceback:")
    print(e.display('traceback'))
    print()
    print("Frame details:")
    for frame in e.traceback():
        print(f"  {frame.filename}:{frame.line}")
        print(f"  Function: {frame.function_name}")
        print(f"  Source: {frame.source_line}")
```

## Summary Checklist

When writing code that interfaces with Monty, ensure you:

- [ ] Use correct parameter names (`inputs` as list in constructor, dict in run)
- [ ] Provide all declared external functions
- [ ] Handle `MontySnapshot`, `MontyFutureSnapshot`, and `MontyComplete`
- [ ] Resume snapshots until execution is complete
- [ ] Translate Grail limits to Monty format
- [ ] Convert dict files to `OSAccess` with `MemoryFile` objects
- [ ] Pass type stubs for type checking
- [ ] Handle Monty exceptions appropriately
- [ ] Test with both sync and async external functions
- [ ] Use serialization for performance when needed
- [ ] Verify generated code uses only supported Monty features

## References

- **Monty source code**: `.context/monty-main/`
- **Monty Python API**: `.context/monty-main/crates/monty-python/python/pydantic_monty/__init__.py`
- **Monty type stubs**: `.context/monty-main/crates/monty-python/python/pydantic_monty/_monty.pyi`
- **Monty examples**: `.context/monty-main/examples/`
- **Monty tests**: `.context/monty-main/crates/monty-python/tests/`
