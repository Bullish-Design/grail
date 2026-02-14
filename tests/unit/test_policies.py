from __future__ import annotations

import pytest

from grail.policies import (
    PolicySpec,
    NAMED_POLICIES,
    PolicyValidationError,
    ResourcePolicy,
    compose_guards,
    resolve_effective_limits,
    resolve_policy,
)
from grail.resource_guard import ResourceGuard


@pytest.mark.unit
@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (
            ResourceGuard(max_duration_secs=1.0),
            ResourceGuard(max_duration_secs=0.5),
            0.5,
        ),
        (
            ResourceGuard(max_memory=10_000_000),
            ResourceGuard(max_memory=5_000_000),
            5_000_000,
        ),
        (
            ResourceGuard(max_recursion_depth=300),
            ResourceGuard(max_recursion_depth=120),
            120,
        ),
    ],
)
def test_compose_guards_strictest_wins(
    left: ResourceGuard, right: ResourceGuard, expected: float | int
) -> None:
    composed = compose_guards([left, right])
    assert expected in composed.to_monty_limits().values()


@pytest.mark.unit
def test_named_policy_resolution() -> None:
    resolved = resolve_policy("strict")
    assert resolved is not None
    assert resolved.max_duration_secs == NAMED_POLICIES["strict"].guard.max_duration_secs


@pytest.mark.unit
def test_policy_inheritance_applies_parent_then_child() -> None:
    child = ResourcePolicy(
        name="custom_child",
        inherits=("strict",),
        guard=ResourceGuard(max_duration_secs=0.2),
    )
    resolved = resolve_policy(child)
    assert resolved is not None
    assert resolved.max_duration_secs == 0.2
    assert resolved.max_memory == NAMED_POLICIES["strict"].guard.max_memory


@pytest.mark.unit
def test_effective_limit_precedence_limits_override_guard_and_policy() -> None:
    effective = resolve_effective_limits(
        limits={"max_duration_secs": 2.4},
        guard=ResourceGuard(max_duration_secs=1.1, max_memory=20_000_000),
        policy="strict",
    )
    assert effective["max_duration_secs"] == 2.4
    assert effective["max_memory"] == 20_000_000


@pytest.mark.unit
def test_unknown_policy_raises() -> None:
    with pytest.raises(PolicyValidationError, match="Unknown policy"):
        resolve_policy("does-not-exist")


@pytest.mark.unit
def test_policy_inheritance_cycle_raises() -> None:
    loop = ResourcePolicy(name="loop", guard=ResourceGuard(), inherits=("loop",))
    with pytest.raises(PolicyValidationError, match="cycle"):
        resolve_policy(loop, available_policies={**NAMED_POLICIES, "loop": loop})


@pytest.mark.unit
def test_policy_inherits_unknown_parent_raises() -> None:
    bad = ResourcePolicy(name="bad", guard=ResourceGuard(), inherits=("missing",))
    with pytest.raises(PolicyValidationError, match="unknown policy"):
        resolve_policy(bad)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("policy_specs", "expected"),
    [
        (["strict", "permissive"], {"max_duration_secs": 0.5, "max_memory": 8 * 1024 * 1024}),
        (["ai_agent", "permissive"], {"max_duration_secs": 0.5, "max_memory": 8 * 1024 * 1024}),
        (
            [
                ResourcePolicy(name="tight-recursion", guard=ResourceGuard(max_recursion_depth=80)),
                "strict",
            ],
            {"max_recursion_depth": 80, "max_memory": 8 * 1024 * 1024},
        ),
    ],
)
def test_policy_composition_matrix(policy_specs: list[PolicySpec], expected: dict[str, int | float]) -> None:
    resolved = resolve_policy(policy_specs)
    assert resolved is not None
    payload = resolved.to_monty_limits()
    for key, value in expected.items():
        assert payload[key] == value


@pytest.mark.unit
def test_inline_registered_policy_conflict_raises() -> None:
    with pytest.raises(PolicyValidationError, match="Conflicting"):
        resolve_policy(ResourcePolicy(name="strict", guard=ResourceGuard(max_duration_secs=9.0)))
