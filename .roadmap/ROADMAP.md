# Grail Development Roadmap

This roadmap outlines the development journey for Grail, a Pydantic-native wrapper around Monty that makes secure Python execution feel like a native part of the Pydantic ecosystem.

---

## Phase 0: Project Setup & Foundation

**Goal:** Establish a working development environment with minimal boilerplate for the first implementation.

### Deliverables

1. **Project Structure**
   - Create `src/grail/` directory with `__init__.py`
   - Set up `tests/` directory structure
   - Configure pytest for test discovery
   - Add basic logging configuration

2. **Dependency Management**
   - Verify `pydantic_monty` installation
   - Add development dependencies (pytest, pytest-asyncio, ty, ruff)
   - Configure `pyproject.toml` with project metadata and build system

3. **Development Tooling**
   - Configure ty for strict type checking
   - Set up ruff for linting and formatting
   - Add pre-commit hooks (optional but recommended)

4. **Basic Smoke Test**
   - Create `tests/test_smoke.py` that imports `pydantic_monty` and runs a trivial Monty execution
   - Validates that the development environment can execute Monty code

### Testing Requirements

- **Environment Verification:**
  - `pydantic_monty` imports successfully
  - Can instantiate `Monty` class
  - Can execute `Monty.run("1 + 1")` and get result `2`
  - All dev dependencies install cleanly

- **Tooling Validation:**
  - `pytest` discovers and runs smoke test
  - `ty` runs without errors on empty codebase
  - `ruff check` and `ruff format` execute successfully

**Success Criteria:** A contributor can clone the repo, run `pip install -e .`, and execute `pytest` to see passing smoke tests.

---

## Phase 1: Core Foundation - Minimal MontyContext

**Goal:** Implement a minimal, working `MontyContext` class that can execute simple code with validated inputs.

### Deliverables

1. **`MontyContext` Class (Basic)**
   - Generic over `InputT` only (no output validation yet)
   - Constructor accepts:
     - `input_model: type[BaseModel]`
     - Optional `limits: ResourceLimits`
   - Method: `execute(code: str, inputs: InputT) -> Any`
     - Validates inputs against `input_model`
     - Calls `pydantic_monty.run_monty_async()` with serialized inputs
     - Returns raw result (no output validation yet)

2. **Basic Input Serialization**
   - Convert Pydantic model instance to dictionary
   - Inject as `inputs` variable in Monty execution scope
   - Support primitive types (str, int, float, bool, list, dict)

3. **Resource Limits Integration**
   - Accept `ResourceLimits` TypedDict in constructor
   - Pass directly to Monty's `limits` parameter
   - Default to safe limits if not provided

4. **Error Handling (Basic)**
   - Catch and re-raise Monty exceptions with context
   - Preserve stack traces from Monty execution
   - Add helpful error messages for common failures

### Testing Requirements

- **Functional Tests:**
  - Execute simple arithmetic: `"inputs['a'] + inputs['b']"`
  - Access nested model fields: `"inputs['user'].name"`
  - Return complex types: `"{'result': inputs['value'] * 2}"`

- **Input Validation:**
  - Invalid input raises `ValidationError`
  - Extra fields are handled according to Pydantic config
  - Required fields must be present

- **Resource Limits:**
  - `max_duration_secs` terminates long-running code
  - `max_memory` prevents excessive allocation
  - `max_recursion_depth` catches infinite recursion

- **Error Propagation:**
  - Python exceptions in Monty code surface correctly
  - Stack traces point to the correct line in user code
  - Validation errors are distinguishable from execution errors

**Success Criteria:** Can execute `ctx.execute("inputs['name'].upper()", UserModel(name="alice"))` and get `"ALICE"`.

---

## Phase 2: MVP - Output Validation & External Functions

**Goal:** Complete the `MontyContext` API with output validation and external function support, creating a functional MVP.

### Deliverables

1. **Output Model Validation**
   - Add `output_model: type[OutputT]` to constructor
   - Update `execute()` return type to `OutputT`
   - Parse Monty result into `output_model` instance
   - Handle validation errors gracefully

2. **External Functions Support**
   - Add `tools: list[Callable]` parameter to constructor
   - Register tools as external functions with Monty
   - Support both sync and async tools
   - Handle tool execution errors and propagate to context

3. **Type Stub Generation (Minimal)**
   - Implement `StubGenerator` utility class
   - Generate type stubs from Pydantic model schemas
   - Generate stubs for registered tool signatures
   - Pass stubs to Monty's `type_check_stubs` parameter

4. **Async Support**
   - Ensure `execute()` is async-compatible
   - Support async external functions
   - Handle concurrent external function calls via `MontyFutureSnapshot`

### Testing Requirements

- **Output Validation:**
  - Valid output parses successfully: `return {"count": 5}` → `OutputModel(count=5)`
  - Invalid output raises `ValidationError` with field details
  - None/missing fields handled according to model config
  - Complex nested models parse correctly

- **External Functions:**
  - Can call registered sync function: `tools.add(1, 2)` → `3`
  - Can call registered async function: `await tools.fetch_data()`
  - Function exceptions propagate to caller correctly
  - Unregistered functions raise helpful error

- **Type Checking:**
  - Invalid type usage caught before execution
  - Type errors reference correct line numbers
  - Generated stubs match Pydantic field types
  - Tool signatures generate valid type stubs

- **Async Execution:**
  - Can await async external functions
  - Multiple concurrent external calls handled correctly
  - Event loop integration works properly

**Success Criteria:** Can execute code that calls external functions and validates output:

```python
ctx = MontyContext(
    input_model=InputModel,
    output_model=OutputModel,
    tools=[my_tool]
)
result = await ctx.execute(
    "output = my_tool(inputs['value']); {'result': output}",
    InputModel(value=42)
)
assert isinstance(result, OutputModel)
```

---

## Phase 3: Developer Experience - Decorator & Error Handling

**Goal:** Improve developer ergonomics with the `@secure` decorator and enhanced error reporting.

### Deliverables

1. **`@secure` Decorator**
   - Extract function source code using `inspect.getsource()`
   - Parse function signature to determine input/output types
   - Create `MontyContext` with inferred models
   - Return wrapper function that calls `ctx.execute()`
   - Support decorator parameters: `limits`, `tools`

2. **Enhanced Error Messages**
   - Pretty-print validation errors with field paths
   - Add context to Monty execution errors
   - Suggest fixes for common mistakes
   - Include relevant documentation links

3. **Debug Mode**
   - Add `debug: bool` parameter to `MontyContext`
   - Log execution steps, variable states, external calls
   - Capture stdout/stderr from Monty execution
   - Provide execution timeline for performance analysis

4. **Documentation Strings**
   - Comprehensive docstrings for all public APIs
   - Type hints on all functions and methods
   - Usage examples in docstrings

### Testing Requirements

- **Decorator Functionality:**
  - Source extraction works for simple functions
  - Type hints correctly infer input/output models
  - Decorated function behaves like original
  - Decorator parameters override defaults

- **Error Quality:**
  - Validation errors show field paths: `user.address.street`
  - Type errors reference original source line numbers
  - Stack traces exclude internal Grail frames
  - Error messages suggest actionable fixes

- **Debug Mode:**
  - Captures all stdout/stderr from execution
  - Logs external function call arguments and returns
  - Execution timeline shows bottlenecks
  - Debug output can be disabled in production

- **Documentation:**
  - All public APIs have docstrings
  - Examples in docstrings run without error
  - Type hints pass ty strict mode

**Success Criteria:** Can use decorator syntax for simple use case:

```python
@secure(limits=ResourceLimits(max_memory=1024))
def process_data(data: InputModel) -> OutputModel:
    result = data.value * 2
    return OutputModel(result=result)

output = process_data(InputModel(value=21))
assert output.result == 42
```

---

## Phase 4: Advanced Features - Serialization & Patterns

**Goal:** Implement advanced Monty features like snapshots, OSAccess, and complex execution patterns.

### Deliverables

1. **Snapshot Management**
   - Add `MontyContext.start()` method for iterative execution
   - Expose `snapshot.dump()` for serialization
   - Add `MontyContext.load_snapshot()` for resumption
   - Support cross-process snapshot restoration

2. **OSAccess Integration**
   - Add `filesystem: OSAccess` parameter to constructor
   - Support virtual filesystem operations
   - Provide helpers for creating `MemoryFile` instances
   - Enable callback-based file I/O

3. **Advanced Type Checking**
   - Support for complex generic types
   - Handle Union types and Optional fields
   - Generate stubs for dataclasses
   - Support type aliases and NewType

4. **Resource Guard**
   - Create `ResourceGuard` class for declarative limits
   - Pydantic model for resource configuration
   - Automatic conversion to Monty's `ResourceLimits`
   - Runtime resource usage reporting

5. **Execution Policies**
   - Reusable policy configurations
   - Pre-defined policies: "strict", "permissive", "ai_agent"
   - Policy inheritance and composition
   - Policy validation at construction time

### Testing Requirements

- **Snapshot Operations:**
  - Can pause execution at external function call
  - Snapshot serializes to bytes successfully
  - Can restore snapshot in new context
  - Cross-process restoration works correctly

- **OSAccess:**
  - Can read/write virtual files
  - File operations respect permissions
  - Callback files invoke handlers correctly
  - Filesystem isolation enforced

- **Advanced Type Checking:**
  - Generic types validated correctly: `List[User]`, `Dict[str, int]`
  - Union types handled: `Union[str, int]`, `Optional[str]`
  - Dataclass fields generate correct stubs
  - Complex nested types work

- **Resource Guard:**
  - Pydantic model validates limit ranges
  - Conversion to Monty limits is correct
  - Resource usage metrics returned after execution
  - Limit violations raise appropriate errors

- **Execution Policies:**
  - Named policies apply correct limits
  - Custom policies can be defined
  - Policy composition works as expected
  - Invalid policies rejected at construction

**Success Criteria:** Can execute multi-step agent loop with snapshots:

```python
ctx = MontyContext(input_model=InputModel, tools=[fetch_tool])
snapshot = await ctx.start(code, inputs)

while isinstance(snapshot, MontySnapshot):
    tool_name, args = snapshot.external_call
    result = await execute_tool(tool_name, args)
    snapshot = await snapshot.resume(return_value=result)

final_result = snapshot.value
```

---

## Phase 5: Production Ready - Examples, Docs & Polish

**Goal:** Prepare library for public release with comprehensive documentation, examples, and production features.

### Deliverables

1. **Comprehensive Examples**
   - Simple calculator with external functions
   - AI agent code execution loop
   - Data analysis with OSAccess filesystem
   - Multi-step workflow with snapshots
   - Type-safe API client code generation

2. **Full Documentation Site**
   - Getting started guide
   - API reference (auto-generated from docstrings)
   - Conceptual guides (architecture, security model)
   - Best practices and patterns
   - Migration guide from raw pydantic_monty

3. **Performance Optimization**
   - Benchmark suite for common operations
   - Optimize stub generation for large models
   - Cache parsed code when possible
   - Profile and optimize hot paths

4. **Security Hardening**
   - Security audit of external function handling
   - Review resource limit enforcement
   - Document threat model and mitigations
   - Add security policy and vulnerability reporting

5. **Production Features**
   - Structured logging with configurable verbosity
   - Metrics collection (execution count, duration, errors)
   - Graceful degradation on resource limit violations
   - Comprehensive error recovery patterns

### Testing Requirements

- **Examples Validation:**
  - All examples run successfully
  - Examples demonstrate best practices
  - Examples cover common use cases
  - Code snippets in docs are tested

- **Documentation Quality:**
  - All public APIs documented
  - No broken links in documentation
  - Code examples are syntax-highlighted and tested
  - Migration guide tested with real migration

- **Performance Benchmarks:**
  - Startup overhead < 5ms for typical use case
  - Stub generation < 100ms for large models (100+ fields)
  - Snapshot serialization < 50ms for typical state
  - Memory overhead < 10MB baseline

- **Security:**
  - No filesystem access without explicit OSAccess
  - No network access without external functions
  - Resource limits enforced correctly
  - No information leakage between executions

- **Production Features:**
  - Logs capture all important events
  - Metrics can be exported to monitoring systems
  - Error recovery patterns handle all error types
  - Graceful degradation doesn't crash application

**Success Criteria:**
- Complete documentation site deployed
- All examples run in CI
- Performance benchmarks meet targets
- Security audit findings addressed
- Library ready for 1.0 release

---

## Phase 6: Ecosystem Integration - Pydantic AI & Beyond

**Goal:** Integrate with broader Pydantic ecosystem and enable advanced use cases.

### Deliverables

1. **Pydantic AI Integration**
   - Support for Pydantic AI's code mode
   - Agent tool calling via Grail contexts
   - Persistent agent state via snapshots
   - Example: AI agent with Grail code execution

2. **FastAPI Integration**
   - Endpoint decorator: `@app.post(..., executor=grail_ctx)`
   - Request validation → Grail execution → response validation
   - Async streaming of execution results
   - Example: Serverless function executor API

3. **Distributed Execution**
   - Serialize execution context for remote execution
   - Support for snapshot distribution across workers
   - Message queue integration patterns
   - Example: Celery task executor with Grail

4. **Advanced Monitoring**
   - OpenTelemetry integration for tracing
   - Prometheus metrics exporter
   - Execution graph visualization
   - Cost tracking for resource usage

5. **JavaScript/TypeScript Support**
   - JS bindings for Grail (via Monty's JS API)
   - TypeScript type definitions
   - NPM package distribution
   - Example: Node.js server with Grail

6. **Plugin System**
   - Extension points for custom stub generators
   - Custom external function loaders
   - Execution middleware (logging, metrics, transforms)
   - Community plugin registry

### Testing Requirements

- **Pydantic AI:**
  - AI agent can execute code via Grail
  - Agent state persists across interactions
  - Tool calling integrates seamlessly
  - Example agent passes full conversation test

- **FastAPI:**
  - Endpoint receives request → executes code → returns response
  - Validation errors return proper HTTP status codes
  - Async execution doesn't block server
  - Example API passes load test (100 req/s)

- **Distributed Execution:**
  - Context serializes and deserializes correctly
  - Snapshots can be transferred between workers
  - Remote execution produces identical results
  - Example Celery task completes successfully

- **Monitoring:**
  - Traces appear in OpenTelemetry collector
  - Metrics exported to Prometheus
  - Visualization shows execution flow
  - Cost tracking is accurate

- **JavaScript Support:**
  - JS bindings install via npm
  - TypeScript types are accurate
  - Example Node.js app runs successfully
  - Cross-language execution is identical

- **Plugin System:**
  - Custom plugins can be registered
  - Plugins receive correct lifecycle events
  - Community plugins work out of the box
  - Plugin conflicts are detected and reported

**Success Criteria:**
- Pydantic AI documentation includes Grail code mode example
- FastAPI integration published as separate package
- Monitoring integration works with major observability platforms
- JavaScript bindings published to npm
- At least 3 community plugins in registry

---

## Maintenance & Long-term Vision

### Ongoing Activities

1. **Monty Alignment**
   - Track Monty releases and update compatibility
   - Test against Monty pre-releases
   - Contribute back to Monty when Grail uncovers issues
   - Maintain alignment check skill in `.agents/skills/`

2. **Community Support**
   - Respond to GitHub issues and discussions
   - Review and merge pull requests
   - Maintain example gallery
   - Host community calls or webinars

3. **Performance Monitoring**
   - Track benchmark trends over time
   - Identify and fix performance regressions
   - Optimize based on real-world usage patterns
   - Publish performance reports

4. **Security Updates**
   - Monitor security advisories for Monty and dependencies
   - Address vulnerabilities promptly
   - Conduct regular security audits
   - Maintain responsible disclosure process

### Long-term Research Areas

1. **Multi-language Support**
   - Investigate wrapping other Monty language bindings (Rust, JS)
   - Explore polyglot execution scenarios
   - Cross-language type checking

2. **Advanced Optimization**
   - JIT compilation of frequently-executed code
   - Predictive pre-parsing based on usage patterns
   - Intelligent snapshot caching

3. **Formal Verification**
   - Prove correctness of type stub generation
   - Verify resource limit enforcement
   - Security property verification

4. **AI-native Features**
   - Automatic code repair for validation errors
   - AI-assisted stub generation
   - Intelligent execution policy recommendation
   - Code quality scoring and feedback

---

## Summary Table: Roadmap Phases

| Phase | Primary Goal | Key Deliverables | Testing Focus | Success Metric |
|---|---|---|---|---|
| **Phase 0** | Project Setup | Dev environment, dependencies, smoke tests | Environment verification | Tests run on fresh clone |
| **Phase 1** | Core Foundation | Minimal `MontyContext`, input validation | Basic execution, limits | Simple code executes |
| **Phase 2** | MVP | Output validation, external functions, type checking | Function integration, async | Full MontyContext API works |
| **Phase 3** | Developer Experience | `@secure` decorator, error handling, docs | Decorator usability, error quality | Decorator syntax works |
| **Phase 4** | Advanced Features | Snapshots, OSAccess, execution policies | Serialization, complex patterns | Multi-step agent loop |
| **Phase 5** | Production Ready | Examples, docs site, performance, security | Performance benchmarks, security audit | Ready for 1.0 release |
| **Phase 6** | Ecosystem Integration | Pydantic AI, FastAPI, monitoring, plugins | Integration correctness, plugin API | Ecosystem adoption |

---

## Testing Philosophy

Throughout all phases, adhere to these testing principles:

1. **Test Pyramid:**
   - Many unit tests (fast, isolated)
   - Moderate integration tests (Grail ↔ Monty)
   - Few end-to-end tests (complete user workflows)

2. **Property-Based Testing:**
   - Use Hypothesis for input/output validation
   - Generate random Pydantic models and verify round-tripping
   - Test resource limit enforcement with random limits

3. **Regression Prevention:**
   - Add test for every bug fix
   - Maintain backward compatibility tests
   - Version-specific test suites for Monty compatibility

4. **Real-world Simulation:**
   - Test examples from documentation
   - Benchmark against actual AI agent workloads
   - Security testing with adversarial inputs

5. **Continuous Validation:**
   - Run tests on every commit (CI)
   - Nightly tests against Monty dev branch
   - Performance regression tests in CI
   - Security scans on dependencies

---

## Release Strategy

### Version Scheme (Semantic Versioning)

- **0.1.0:** MVP release (Phase 2 complete)
- **0.2.0:** Developer experience improvements (Phase 3 complete)
- **0.3.0:** Advanced features (Phase 4 complete)
- **1.0.0:** Production ready (Phase 5 complete)
- **1.x.0:** Ecosystem integrations (Phase 6 milestones)

### Pre-1.0 Expectations

- Breaking changes allowed between 0.x releases
- Deprecation warnings provided for 1 minor version
- Migration guides published for breaking changes
- Community feedback actively incorporated

### Post-1.0 Stability

- Backward compatibility guaranteed for 1.x series
- Deprecation cycle: warning → 2 minor versions → removal
- Security patches backported to previous minor version
- LTS releases for enterprise adoption

---

## Contributor Onboarding

Each phase should update `.agents/AGENTS.md` with:

1. **Current Phase Goals:** What we're working on now
2. **Open Tasks:** Specific implementation tasks available
3. **Testing Checklist:** How to verify your contribution
4. **Review Criteria:** What maintainers will check

This ensures both human and AI contributors can orient quickly and contribute effectively.

---

## Conclusion

This roadmap takes Grail from an empty repository to a production-ready, ecosystem-integrated library in 6 phases. Each phase builds on the previous, with clear testing requirements and success criteria.

The journey prioritizes:
- **Iterative delivery:** Each phase produces working, testable software
- **Developer ergonomics:** API design focuses on ease of use
- **Safety and security:** Monty's guarantees preserved and enhanced
- **Ecosystem alignment:** Deep integration with Pydantic and broader Python ecosystem

By following this roadmap, Grail will achieve its mission: making secure, isolated Python execution feel native to the Pydantic ecosystem, enabling the next generation of AI agent frameworks.
