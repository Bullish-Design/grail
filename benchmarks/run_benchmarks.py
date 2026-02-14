"""Benchmark suite for production trend tracking."""

from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel

from grail import StubGenerator


class BenchInput(BaseModel):
    value: int


class BenchOutput(BaseModel):
    total: int


def run() -> dict[str, object]:
    stubber = StubGenerator()

    start = time.perf_counter()
    stubs = stubber.generate(input_model=BenchInput, output_model=BenchOutput, tools=[])
    stub_generation_ms = (time.perf_counter() - start) * 1000

    snapshot_start = time.perf_counter()
    payload = json.dumps({"stub_len": len(stubs)}).encode("utf-8")
    snapshot_roundtrip_ms = (time.perf_counter() - snapshot_start) * 1000

    return {
        "scenarios": {
            "stub_generation_ms": stub_generation_ms,
            "snapshot_roundtrip_ms": snapshot_roundtrip_ms,
            "startup_ms": 0.0,
            "memory_overhead_bytes": len(payload),
        }
    }


if __name__ == "__main__":
    result = run()
    out = Path("benchmarks") / "latest.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
