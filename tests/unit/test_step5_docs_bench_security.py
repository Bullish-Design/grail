from __future__ import annotations

import json
from pathlib import Path


def test_step5_docs_exist() -> None:
    for path in [
        Path("docs/getting-started.md"),
        Path("docs/concepts.md"),
        Path("docs/api-reference.md"),
        Path("docs/migration-guide.md"),
    ]:
        assert path.exists(), f"missing docs file: {path}"


def test_step5_security_policy_exists() -> None:
    assert Path("SECURITY.md").exists()
    assert Path("security/THREAT_MODEL.md").exists()


def test_step5_benchmark_outputs_json_schema() -> None:
    namespace: dict[str, object] = {}
    exec(Path("benchmarks/run_benchmarks.py").read_text(encoding="utf-8"), namespace)
    result = namespace["run"]()
    assert isinstance(result, dict)
    scenarios = result["scenarios"]
    for key in [
        "stub_generation_ms",
        "snapshot_roundtrip_ms",
        "startup_ms",
        "memory_overhead_bytes",
    ]:
        assert key in scenarios
        assert isinstance(scenarios[key], (int, float))


def test_step5_expected_benchmark_artifact_is_json_serializable() -> None:
    namespace: dict[str, object] = {}
    exec(Path("benchmarks/run_benchmarks.py").read_text(encoding="utf-8"), namespace)
    result = namespace["run"]()
    json.dumps(result)
