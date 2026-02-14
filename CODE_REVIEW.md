# Grail Library - Comprehensive Code Review

**Review Date**: 2026-02-14
**Library Version**: 0.1.0
**Reviewer**: Claude
**Lines of Code**: ~3,532 (source + tests)

---

## Executive Summary

Grail is a well-architected, security-focused Python library that provides a Pydantic-native wrapper around Monty (a secure Python interpreter written in Rust). The library enables safe execution of untrusted code, particularly AI-generated code, with strong type safety, resource controls, and filesystem isolation. The codebase demonstrates excellent software engineering practices, comprehensive documentation, and thoughtful API design.

**Overall Rating**: ⭐⭐⭐⭐⭐ (Excellent)

**Key Strengths**:
- Outstanding documentation and developer experience
- Robust security model with defense-in-depth approach
- Clean, well-structured codebase with strong type safety
- Comprehensive test coverage with contract-based testing
- Thoughtful API design with excellent ergonomics

**Areas for Improvement**:
- Minor edge cases in error handling
- Some opportunities for performance optimization
- A few minor code duplication issues

---

## 1. Architecture & Design

### 1.1 Overall Architecture ⭐⭐⭐⭐⭐

**Strengths**:
- **Excellent layering**: The library follows a clear layered architecture:
  - API Layer (`MontyContext`, `@secure` decorator)
  - Policy & Resource Management (`ResourceGuard`, `ResourcePolicy`)
  - Type System (`StubGenerator`)
  - Filesystem Abstraction (`GrailFilesystem`)
  - Observability (`MetricsCollector`, `StructuredLogger`)
  - Error Handling (`GrailExecutionError` hierarchy)

- **Separation of Concerns**: Each module has a well-defined responsibility:
  - `context.py`: Orchestration and lifecycle management
  - `stubs.py`: Type stub generation
  - `filesystem.py`: Filesystem security layer
  - `policies.py`: Resource policy composition
  - `tools.py`: Tool registry and invocation
  - `snapshots.py`: Resumable execution state

- **Clean Dependencies**: The dependency graph is acyclic and well-organized.

**Observations**:
- The use of Generic types (`MontyContext[InputT, OutputT]`) provides excellent type safety.
- The adapter pattern for `GrailFilesystem` wrapping `AbstractOS` is well-executed.
- The strategy pattern for resource policies is elegant and extensible.

### 1.2 Design Patterns ⭐⭐⭐⭐⭐

**Patterns Used**:
1. **Facade Pattern**: `MontyContext` provides a simplified interface to Monty
2. **Adapter Pattern**: `GrailFilesystem` adapts Monty's `AbstractOS`
3. **Builder Pattern**: Resource policy composition
4. **Strategy Pattern**: Pluggable policies, filesystem backends
5. **Decorator Pattern**: `@secure` decorator for function wrapping
6. **Registry Pattern**: `ToolRegistry` for tool management
7. **Template Method**: Error normalization in `_normalize_monty_exception`

**Example of Excellent Design** (from `context.py:68`):
```python
self.limits = resolve_effective_limits(limits=limits, guard=guard, policy=policy)
```
This single line elegantly handles complex precedence resolution using a composable approach.

### 1.3 API Design ⭐⭐⭐⭐⭐

**Strengths**:
- **Intuitive**: The API is self-documenting and follows Python conventions
- **Progressive Disclosure**: Simple cases are simple, complex cases are possible
- **Type-Safe**: Excellent use of generics and type hints
- **Consistent**: Naming conventions are consistent throughout

**Examples**:

Simple usage:
```python
ctx = MontyContext(InputModel, output_model=OutputModel)
result = ctx.execute(code, inputs)
```

Complex usage with all features:
```python
ctx = MontyContext(
    InputModel,
    output_model=OutputModel,
    tools=[tool1, tool2],
    filesystem=fs,
    policy="strict",
    debug=True,
    logger=logger,
    metrics=metrics
)
```

**Minor Observation**:
- The `execute()` vs `execute_async()` distinction is well-handled with a clear error message (context.py:255-258), though this could be confusing for beginners who don't understand asyncio.

---

## 2. Code Quality

### 2.1 Code Organization ⭐⭐⭐⭐⭐

**Strengths**:
- **Module Size**: All modules are reasonably sized (largest is `context.py` at 454 lines)
- **Clear Naming**: Function and variable names are descriptive and follow PEP 8
- **Import Organization**: Imports are well-organized with `from __future__ import annotations`
- **Type Hints**: Comprehensive type hints throughout (Python 3.13+ style)

**Example of Clean Code** (from `tools.py`):
```python
class ToolRegistry:
    """Maintain a deterministic mapping of callable names to tools."""

    def __init__(self, tools: list[Callable[..., Any]] | None = None) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        if tools:
            for tool in tools:
                self.register(tool)
```

Clean, simple, and self-documenting.

### 2.2 Type Safety ⭐⭐⭐⭐⭐

**Strengths**:
- Excellent use of `TypedDict` for structured dictionaries (`ResourceLimits`, `DebugPayload`)
- Generic types for `MontyContext[InputT, OutputT]`
- Proper use of `Union` types with the modern `|` syntax
- Type guards and runtime checks where needed

**Example** (from `context.py:50`):
```python
class MontyContext(Generic[InputT, OutputT]):
    def __init__(
        self,
        input_model: type[InputT],
        # ... parameters
    ) -> None:
```

This provides excellent IDE support and type checking.

### 2.3 Error Handling ⭐⭐⭐⭐

**Strengths**:
- **Clear Exception Hierarchy**: Well-designed exception types
  ```
  Exception
  ├── ValueError
  │   └── GrailValidationError
  │       └── GrailOutputValidationError
  └── RuntimeError
      └── GrailExecutionError
          └── GrailLimitError
  ```

- **Informative Error Messages**: Error formatting functions provide clear, actionable messages
- **Exception Normalization**: `_normalize_monty_exception` properly converts Monty errors to Grail errors

**Areas for Improvement**:

1. **Broad Exception Catching** (context.py:155, 217, 238):
   ```python
   except Exception as exc:  # noqa: BLE001
   ```
   While `# noqa: BLE001` indicates this is intentional, catching all exceptions should be carefully considered. The normalization function should handle specific exception types.

2. **OSError errno Check** (context.py:366):
   ```python
   if isinstance(exc, OSError) and getattr(exc, "errno", None) == 13:
   ```
   This magic number `13` should be a named constant (e.g., `errno.EACCES`).

**Recommendation**:
```python
import errno

if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.EACCES:
    return GrailExecutionError(f"Monty filesystem permission denied: {exc}")
```

### 2.4 Code Duplication ⭐⭐⭐⭐

**Minor Issues**:

1. **Similar filesystem factory functions** (filesystem.py:178-255): The three factory functions (`memory_filesystem`, `hooked_filesystem`, `callback_filesystem`) share similar patterns. Consider extracting common logic.

2. **Debug payload initialization** (context.py:76, 90, 165): The `_debug_payload` initialization is duplicated. Consider a helper method:
   ```python
   def _reset_debug_payload(self) -> None:
       self._debug_payload = {
           "events": [],
           "stdout": "",
           "stderr": "",
           "tool_calls": [],
           "resource_metrics": {},
       }
   ```

3. **Type stub generation setup** (context.py:101-105, 176-180): Similar code blocks could be extracted to a helper method.

---

## 3. Security Analysis

### 3.1 Security Model ⭐⭐⭐⭐⭐

**Strengths**:
- **Defense in Depth**: Multiple layers of security controls
- **Fail-Safe Defaults**: Filesystem access denied by default
- **Explicit Permissions**: All access must be explicitly granted
- **Path Traversal Prevention**: Robust normalization and validation
- **Resource Limits**: Comprehensive resource controls prevent DoS

**Security Layers**:
1. **Input Validation**: Pydantic models validate all inputs
2. **Filesystem Isolation**: `GrailFilesystem` with explicit permissions
3. **Resource Limits**: Configurable limits on memory, time, recursion
4. **Type Checking**: AOT type checking via stub generation
5. **Tool Whitelisting**: Only explicitly registered tools are available
6. **Output Validation**: Results validated against output models

### 3.2 Filesystem Security ⭐⭐⭐⭐⭐

**Excellent Implementation** (filesystem.py):

```python
def _normalize(self, path: PurePosixPath) -> PurePosixPath:
    normalized = PurePosixPath(self._os.path_absolute(path))
    if ".." in normalized.parts:
        raise PermissionError(f"Path escapes filesystem root: {normalized}")
    try:
        normalized.relative_to(self._root)
    except ValueError as exc:
        raise PermissionError(f"Path escapes filesystem root: {normalized}") from exc
    return normalized
```

**Security Strengths**:
1. **Path normalization**: All paths normalized before checking
2. **Traversal prevention**: Explicit `.." check
3. **Root confinement**: Validates paths are within root
4. **Permission hierarchy**: Permissions cascade from parent to child
5. **Hook system**: Safe interception of read/write operations

**Potential Edge Case**:
- **Symlink handling** (filesystem.py:101): The library exposes `path_is_symlink()` but doesn't explicitly prevent symlinks from escaping the root. Consider adding symlink resolution validation.

**Recommendation**:
```python
def _normalize(self, path: PurePosixPath) -> PurePosixPath:
    normalized = PurePosixPath(self._os.path_absolute(path))

    # Prevent ".." in paths
    if ".." in normalized.parts:
        raise PermissionError(f"Path escapes filesystem root: {normalized}")

    # Check symlink resolution
    if self._os.path_is_symlink(normalized):
        resolved = PurePosixPath(self._os.path_resolve(normalized))
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise PermissionError(f"Symlink escapes filesystem root: {normalized}") from exc

    # Ensure within root
    try:
        normalized.relative_to(self._root)
    except ValueError as exc:
        raise PermissionError(f"Path escapes filesystem root: {normalized}") from exc

    return normalized
```

### 3.3 Resource Limits ⭐⭐⭐⭐⭐

**Strengths**:
- **Comprehensive Coverage**: Memory, time, recursion depth, allocations, GC interval
- **Composable Policies**: Elegant policy system with inheritance
- **Strictest-Wins Semantics**: Safe default when combining policies
- **Validation**: Pydantic-based validation ensures limits are sensible

**Example** (resource_guard.py:17-21):
```python
max_allocations: int | None = Field(default=None, ge=1)
max_duration_secs: float | None = Field(default=None, gt=0)
max_memory: int | None = Field(default=None, ge=1024)
```

The validation ensures limits are positive and memory is at least 1KB.

### 3.4 Information Leakage ⭐⭐⭐⭐

**Good Practices**:
- Error messages are normalized and don't expose internal details
- Debug mode is explicit and opt-in
- Structured logging allows auditing

**Minor Concern**:
- **Error messages** (errors.py:35-43): Pydantic validation errors might expose schema details. Consider sanitizing these in production.

---

## 4. Testing

### 4.1 Test Coverage ⭐⭐⭐⭐⭐

**Strengths**:
- **Multiple Test Types**: Unit, integration, and contract tests
- **Comprehensive Coverage**: Tests cover happy paths, error cases, and edge cases
- **Fixture-Based Testing**: Contract tests use JSON fixtures for reproducibility
- **Clear Test Organization**: Tests organized by module and type

**Test Structure**:
```
tests/
├── unit/              # Fast unit tests
├── integration/       # Integration tests with pydantic_monty
├── contracts/         # Contract tests with fixtures
└── helpers/           # Test utilities
```

### 4.2 Test Quality ⭐⭐⭐⭐⭐

**Example of Good Test** (test_policies.py:17-42):
```python
@pytest.mark.unit
@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (ResourceGuard(max_duration_secs=1.0), ResourceGuard(max_duration_secs=0.5), 0.5),
        # ...
    ],
)
def test_compose_guards_strictest_wins(left, right, expected):
    composed = compose_guards([left, right])
    assert expected in composed.to_monty_limits().values()
```

**Strengths**:
- **Parameterized Tests**: Good use of `pytest.mark.parametrize`
- **Clear Assertions**: Tests verify specific behavior
- **Good Coverage**: Edge cases like policy cycles, unknown policies tested

### 4.3 Missing Tests

**Recommended Additional Tests**:

1. **Concurrent Execution**: Test thread safety of `MontyContext`
2. **Large Input/Output**: Test with large Pydantic models
3. **Nested Models**: Deep nesting in type stub generation
4. **Unicode/Special Characters**: Filesystem paths with special characters
5. **Resource Exhaustion**: Tests that actually hit resource limits
6. **Snapshot Persistence**: Round-trip serialization of large snapshots

---

## 5. Performance

### 5.1 Performance Characteristics ⭐⭐⭐⭐

**Strengths**:
- **Lazy Initialization**: Monty runner only created when needed
- **Metrics Collection**: Built-in performance tracking
- **Fast Startup**: Monty claims <1μs startup time

**Potential Optimizations**:

1. **Type Stub Caching** (stubs.py:26-67): Type stubs are regenerated for every execution. Consider caching based on model/tool signatures:
   ```python
   @functools.lru_cache(maxsize=128)
   def _generate_stub_key(
       input_model: type[BaseModel],
       output_model: type[BaseModel] | None,
       tool_names: tuple[str, ...]
   ) -> str:
       # Generate cache key
   ```

2. **Tool Mapping** (context.py:433-441): Debug tool wrapping creates new async functions every time. Consider lazy wrapping or caching.

3. **String Concatenation** (stubs.py:49, 67): Multiple string operations could use `io.StringIO` for better performance with large stubs.

**Benchmark Suggestion**:
The library includes a `benchmarks/` directory but I couldn't see the actual benchmark implementation. Consider adding:
- Execution time for various code complexity levels
- Memory overhead of Grail wrapper
- Type stub generation performance
- Filesystem operation overhead

### 5.2 Memory Management ⭐⭐⭐⭐

**Strengths**:
- Proper cleanup with context managers
- No obvious memory leaks
- Resource limits prevent memory exhaustion

**Observation**:
- **Debug Payload Accumulation** (context.py:159, 316): Debug payloads accumulate stdout/stderr. For long-running contexts with many executions, this could grow large. Consider adding a `clear_debug_payload()` method or automatic cleanup.

---

## 6. Documentation

### 6.1 Documentation Quality ⭐⭐⭐⭐⭐

**Outstanding Documentation**:
- **Comprehensive Guide**: 2,100+ line `GRAIL_GUIDE.md` is excellent
- **Multiple Levels**: CONCEPT.md, ARCHITECTURE.md, SPEC.md, detailed API reference
- **Examples**: Well-commented examples with explanations
- **Security Documentation**: Clear threat model and security policy

**Strengths**:
1. **Progressive Disclosure**: Starts simple, builds to complex
2. **Code Examples**: Extensive, realistic examples
3. **Use Cases**: Clear use cases for each feature
4. **Best Practices**: Dedicated section on best practices
5. **Migration Guide**: Helps users migrate from direct Monty usage

### 6.2 Code Documentation ⭐⭐⭐⭐

**Strengths**:
- **Docstrings**: Most public APIs have docstrings
- **Type Hints**: Comprehensive type hints serve as documentation
- **Comments**: Minimal but effective inline comments

**Areas for Improvement**:
1. **Missing Docstrings**: Some methods lack docstrings:
   - `context.py:_supported_kwargs` (line 389)
   - `context.py:_coerce_external_functions` (line 384)
   - `stubs.py:_reset` (line 69)

2. **Complex Logic Comments**: Some complex logic could benefit from explanatory comments:
   - Policy resolution logic in `policies.py:79-99`
   - Hook iteration in `filesystem.py:84-90`

**Recommendation**:
Add docstrings to all public and non-trivial private methods.

---

## 7. Maintainability

### 7.1 Code Maintainability ⭐⭐⭐⭐⭐

**Strengths**:
- **Clear Module Boundaries**: Easy to locate functionality
- **Minimal Coupling**: Modules are loosely coupled
- **Extensibility**: Easy to add new policies, filesystem backends, tools
- **Version Control**: Good use of semantic versioning (0.1.0)

### 7.2 Dependency Management ⭐⭐⭐⭐⭐

**Strengths** (pyproject.toml):
- **Minimal Dependencies**: Only `pydantic>=2.12.5` and `pydantic_monty`
- **Python 3.13+**: Uses modern Python features
- **Clear Dev Dependencies**: Separate dev dependencies for testing/linting
- **Build System**: Uses modern `hatchling` build backend

### 7.3 Configuration ⭐⭐⭐⭐⭐

**Excellent Configuration**:
- **Pytest Config**: Clear test markers and paths
- **Ruff Config**: Sensible linting rules (E, F, I)
- **Type Checker Config**: `ty` configuration for strict type checking

---

## 8. Specific Issues & Recommendations

### 8.1 Critical Issues

**None Found** ✅

### 8.2 High Priority Issues

1. **Symlink Security** (filesystem.py:56-64)
   - **Issue**: Symlinks could potentially escape root
   - **Impact**: Security vulnerability
   - **Recommendation**: Add symlink resolution validation (see Security section)

### 8.3 Medium Priority Issues

1. **Magic Numbers** (context.py:366)
   - **Issue**: Magic number `13` for errno
   - **Impact**: Code readability
   - **Recommendation**: Use `errno.EACCES` constant

2. **Type Stub Caching** (stubs.py)
   - **Issue**: Type stubs regenerated every execution
   - **Impact**: Performance
   - **Recommendation**: Implement caching strategy

3. **Debug Payload Cleanup** (context.py:76-82)
   - **Issue**: Debug payloads accumulate without cleanup
   - **Impact**: Memory usage over time
   - **Recommendation**: Add cleanup method or automatic rotation

### 8.4 Low Priority Issues

1. **Code Duplication** (filesystem.py:178-255)
   - **Issue**: Similar patterns in factory functions
   - **Impact**: Maintainability
   - **Recommendation**: Extract common logic

2. **Missing Docstrings** (various files)
   - **Issue**: Some methods lack documentation
   - **Impact**: Developer experience
   - **Recommendation**: Add comprehensive docstrings

3. **String Concatenation** (stubs.py)
   - **Issue**: Multiple string operations in loops
   - **Impact**: Performance with large stubs
   - **Recommendation**: Use `io.StringIO` for efficiency

### 8.5 Suggestions for Enhancement

1. **Async Context Manager Support**:
   ```python
   async with MontyContext(InputModel) as ctx:
       result = await ctx.execute_async(code, inputs)
   ```

2. **Decorator Configuration**:
   Allow `@secure` decorator to accept policies:
   ```python
   @secure(policy="strict")
   def my_function(x: int) -> int:
       return x * 2
   ```

3. **Streaming Output**:
   For long-running executions, support streaming stdout/stderr:
   ```python
   async for line in ctx.execute_streaming(code, inputs):
       print(line)
   ```

4. **Tool Middleware**:
   Allow middleware for tool calls (logging, rate limiting, etc.):
   ```python
   ctx = MontyContext(
       InputModel,
       tools=[my_tool],
       tool_middleware=[rate_limiter, logger]
   )
   ```

5. **Policy Validation CLI**:
   A CLI tool to validate and test policies:
   ```bash
   grail validate-policy --policy strict --test-code test.py
   ```

---

## 9. Comparison with Best Practices

### 9.1 Python Best Practices ⭐⭐⭐⭐⭐

- ✅ PEP 8 compliance
- ✅ Type hints throughout
- ✅ Modern Python features (3.13+)
- ✅ Proper use of `from __future__ import annotations`
- ✅ Context managers for resource management
- ✅ Proper exception handling
- ✅ Clear package structure

### 9.2 Security Best Practices ⭐⭐⭐⭐⭐

- ✅ Principle of least privilege
- ✅ Fail-safe defaults
- ✅ Defense in depth
- ✅ Input validation
- ✅ Output validation
- ✅ Resource limits
- ✅ Explicit permissions
- ✅ Security documentation

### 9.3 Testing Best Practices ⭐⭐⭐⭐⭐

- ✅ Multiple test types (unit, integration, contract)
- ✅ Parameterized tests
- ✅ Clear test organization
- ✅ Test markers for categorization
- ✅ Fixture-based testing
- ✅ Edge case coverage
- ✅ Error case testing

### 9.4 Documentation Best Practices ⭐⭐⭐⭐⭐

- ✅ Comprehensive user guide
- ✅ API reference
- ✅ Architecture documentation
- ✅ Examples
- ✅ Best practices guide
- ✅ Security documentation
- ✅ Migration guide
- ✅ Getting started guide

---

## 10. Strengths Summary

### Technical Strengths

1. **Excellent Architecture**: Clean layering, clear separation of concerns, well-designed abstractions
2. **Security First**: Multiple security layers, fail-safe defaults, comprehensive threat model
3. **Type Safety**: Extensive use of type hints, Pydantic validation, generic types
4. **Developer Experience**: Intuitive API, progressive disclosure, excellent documentation
5. **Testing**: Comprehensive test coverage, multiple test types, contract-based testing
6. **Error Handling**: Clear exception hierarchy, informative error messages, proper normalization
7. **Observability**: Built-in metrics, structured logging, debug mode
8. **Extensibility**: Easy to extend with new policies, tools, filesystem backends

### Process Strengths

1. **Documentation**: Outstanding documentation at all levels
2. **Code Quality**: Clean, readable, well-organized code
3. **Dependency Management**: Minimal dependencies, modern tooling
4. **Configuration**: Sensible defaults, flexible configuration
5. **Version Control**: Proper semantic versioning

---

## 11. Areas for Improvement Summary

### High Priority
1. ⚠️ Symlink security validation
2. 🔧 Replace magic numbers with constants

### Medium Priority
1. 🚀 Type stub caching for performance
2. 🧹 Debug payload cleanup mechanism
3. 📝 Complete missing docstrings

### Low Priority
1. 🔄 Reduce code duplication in filesystem factories
2. ⚡ String builder optimization in stub generation
3. 🧪 Additional test coverage for edge cases

### Nice to Have
1. 💡 Async context manager support
2. 🎨 Enhanced decorator configuration
3. 📊 Streaming output support
4. 🔌 Tool middleware system
5. 🛠️ Policy validation CLI tool

---

## 12. Conclusion

Grail is an **exceptionally well-designed and implemented library** that achieves its goal of providing a Pydantic-native wrapper around Monty for secure code execution. The codebase demonstrates:

- **Outstanding software engineering practices**
- **Security-first design with multiple defense layers**
- **Excellent developer experience through intuitive APIs and comprehensive documentation**
- **Production-ready quality with robust error handling and observability**

### Recommendations for Production Use

**Ready for Production** ✅ with the following recommendations:

1. **Security Hardening**: Address the symlink validation issue before deploying in high-security environments
2. **Performance Optimization**: Implement type stub caching for high-throughput scenarios
3. **Monitoring**: Utilize the built-in metrics and logging for production observability
4. **Testing**: Add your own integration tests specific to your use cases
5. **Documentation**: Review the excellent documentation and customize for your organization

### Final Rating

**Overall Quality**: ⭐⭐⭐⭐⭐ (9.5/10)

**Breakdown**:
- Architecture & Design: 10/10
- Code Quality: 9/10
- Security: 9.5/10
- Testing: 10/10
- Documentation: 10/10
- Performance: 8/10
- Maintainability: 10/10

### Recognition

This library represents a **model example** of how to build a secure, well-documented, and developer-friendly Python library. The attention to detail in API design, security controls, and documentation is exemplary. The authors should be commended for their excellent work.

---

## Appendix A: File-by-File Analysis

### `src/grail/__init__.py` ⭐⭐⭐⭐⭐
- **Lines**: 78
- **Purpose**: Package initialization and exports
- **Quality**: Excellent, clean exports with `__all__`
- **Issues**: None

### `src/grail/context.py` ⭐⭐⭐⭐
- **Lines**: 454
- **Purpose**: Core orchestration and lifecycle management
- **Quality**: Excellent architecture, minor issues with exception handling
- **Issues**:
  - Broad exception catching (lines 155, 217, 238)
  - Magic number for errno (line 366)
  - Code duplication in debug payload init

### `src/grail/resource_guard.py` ⭐⭐⭐⭐⭐
- **Lines**: 47
- **Purpose**: Resource limit validation
- **Quality**: Perfect, clean Pydantic models
- **Issues**: None

### `src/grail/filesystem.py` ⭐⭐⭐⭐
- **Lines**: 256
- **Purpose**: Filesystem security layer
- **Quality**: Excellent security implementation
- **Issues**:
  - Symlink security edge case (line 101)
  - Code duplication in factory functions

### `src/grail/errors.py` ⭐⭐⭐⭐⭐
- **Lines**: 74
- **Purpose**: Error types and formatting
- **Quality**: Excellent, clear hierarchy
- **Issues**: None

### `src/grail/decorators.py` ⭐⭐⭐⭐⭐
- **Lines**: 76
- **Purpose**: `@secure` decorator
- **Quality**: Excellent implementation
- **Issues**: None

### `src/grail/observability.py` ⭐⭐⭐⭐⭐
- **Lines**: 70
- **Purpose**: Metrics and logging
- **Quality**: Clean, simple, effective
- **Issues**: None

### `src/grail/stubs.py` ⭐⭐⭐⭐
- **Lines**: 327
- **Purpose**: Type stub generation
- **Quality**: Comprehensive type handling
- **Issues**:
  - No caching (performance)
  - String concatenation in loops
  - Missing docstrings

### `src/grail/types.py` ⭐⭐⭐⭐⭐
- **Lines**: 36
- **Purpose**: Core type definitions
- **Quality**: Clean, simple
- **Issues**: None

### `src/grail/policies.py` ⭐⭐⭐⭐⭐
- **Lines**: 185
- **Purpose**: Resource policy system
- **Quality**: Excellent design, elegant composition
- **Issues**: None

### `src/grail/tools.py` ⭐⭐⭐⭐⭐
- **Lines**: 40
- **Purpose**: Tool registry
- **Quality**: Simple, effective
- **Issues**: None

### `src/grail/snapshots.py` ⭐⭐⭐⭐⭐
- **Lines**: 101
- **Purpose**: Resumable execution state
- **Quality**: Clean wrapper with good serialization helpers
- **Issues**: None

---

## Appendix B: Security Checklist

- ✅ Input validation (Pydantic models)
- ✅ Output validation (Pydantic models)
- ✅ Filesystem isolation (GrailFilesystem)
- ✅ Path traversal prevention
- ⚠️ Symlink resolution validation (needs attention)
- ✅ Resource limits (memory, time, recursion)
- ✅ Tool whitelisting
- ✅ Type checking (AOT via stubs)
- ✅ Error sanitization
- ✅ Audit logging
- ✅ Fail-safe defaults
- ✅ Defense in depth
- ✅ Threat model documented
- ✅ Security policy documented

---

## Appendix C: Test Coverage Summary

**Test Files Reviewed**: 14+
**Test Types**: Unit, Integration, Contract
**Frameworks**: pytest, pytest-asyncio

**Coverage Areas**:
- ✅ Resource guards and limits
- ✅ Type stub generation
- ✅ Context execution (sync/async)
- ✅ Error handling
- ✅ Tool registry
- ✅ Policy composition
- ✅ Decorator functionality
- ✅ Filesystem operations
- ✅ Validation (input/output)
- ✅ Snapshots and resumption
- ✅ Contract tests with fixtures

**Recommended Additional Tests**:
- Concurrent execution
- Large models
- Deep nesting
- Resource exhaustion
- Unicode paths

---

**End of Code Review**
