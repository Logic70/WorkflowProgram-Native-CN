from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "resolve-task-model-policy.py"
DEVELOP_JS = ROOT / ".claude" / "workflows" / "workflowprogram-develop.js"
AUDIT_JS = ROOT / ".claude" / "workflows" / "workflowprogram-audit.js"
ITERATE_JS = ROOT / ".claude" / "workflows" / "workflowprogram-iterate.js"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"invalid JSON\nstdout={completed.stdout}\nstderr={completed.stderr}"
        ) from exc


def write_policy(path: Path, task_types: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schemaVersion": 1, "default": "inherit", "taskTypes": task_types}
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def read_resolution(run_root: Path) -> dict:
    resolution_path = run_root / "outputs" / "stages" / "task-model-resolution.json"
    return json.loads(resolution_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Resolver tests
# ---------------------------------------------------------------------------


def test_resolver_default_mapping_all_pass(tmp_path: Path) -> None:
    """Without a policy file, the resolver uses the built-in default mapping."""
    run_root = tmp_path / "run"
    completed = run_script("--run-root", str(run_root))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["policySource"] == "built-in-default"
    assert payload["taskModels"]["clarification"] == "deepseek-v4-flash[1M]"
    assert payload["taskModels"]["architecture"] == "deepseek-v4-pro[1M]"
    assert payload["taskModels"]["risk-review"] == "deepseek-v4-pro[1M]"
    assert payload["taskModels"]["publish-verification"] == "deepseek-v4-pro[1M]"
    assert payload["taskModels"]["repository-exploration"] == "deepseek-v4-flash[1M]"
    assert payload["taskModels"]["generation"] == "deepseek-v4-flash[1M]"
    assert payload["taskModels"]["static-review"] == "deepseek-v4-flash[1M]"
    assert payload["taskModels"]["complex-generation"] == "deepseek-v4-pro[1M]"
    assert len(payload["fallbacks"]) == 0

    # Verify the output file was written
    resolution = read_resolution(run_root)
    assert resolution["status"] == "PASS"


def test_resolver_writes_resolution_file(tmp_path: Path) -> None:
    """The resolver writes task-model-resolution.json to RUN_ROOT/outputs/stages/."""
    run_root = tmp_path / "run"
    run_script("--run-root", str(run_root))

    resolution = read_resolution(run_root)
    assert resolution["schemaVersion"] == 1
    assert resolution["status"] == "PASS"
    assert isinstance(resolution["taskModels"], dict)
    assert len(resolution["taskModels"]) == 8


def test_resolver_custom_policy_overrides_default(tmp_path: Path) -> None:
    """A policy file with explicit taskTypes overrides the built-in defaults."""
    run_root = tmp_path / "run"
    policy = tmp_path / "task-model-policy.json"
    write_policy(policy, {
        "clarification": "deepseek-v4-pro[1M]",
        "architecture": "deepseek-v4-flash[1M]",
    })

    completed = run_script("--run-root", str(run_root), "--policy", str(policy))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["policySource"] == str(policy)
    assert payload["taskModels"]["clarification"] == "deepseek-v4-pro[1M]"
    assert payload["taskModels"]["architecture"] == "deepseek-v4-flash[1M]"
    # Unspecified task types fall back to default
    assert payload["taskModels"]["risk-review"] == "deepseek-v4-pro[1M]"
    assert payload["taskModels"]["repository-exploration"] == "deepseek-v4-flash[1M]"


def test_resolver_unavailable_alias_falls_back_to_inherit(tmp_path: Path) -> None:
    """When AVAILABLE_MODELS excludes a required alias, it falls back to inherit."""
    run_root = tmp_path / "run"
    env = {"AVAILABLE_MODELS": "deepseek-v4-flash[1M]"}  # pro is unavailable

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--run-root", str(run_root), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**__import__("os").environ, **env},
    )

    # PASS_WITH_FALLBACKS is still a valid resolution (exit 0); fallbacks are warnings
    payload = load_json(completed)
    assert payload["status"] == "PASS_WITH_FALLBACKS"
    assert payload["taskModels"]["clarification"] == "deepseek-v4-flash[1M]"
    assert payload["taskModels"]["architecture"] == "inherit"  # pro unavailable
    assert payload["taskModels"]["risk-review"] == "inherit"
    assert payload["taskModels"]["publish-verification"] == "inherit"
    assert len(payload["fallbacks"]) >= 4

    # Each fallback has the expected shape
    for fb in payload["fallbacks"]:
        assert "taskType" in fb
        assert "requestedModel" in fb
        assert fb["effectiveModel"] == "inherit"
        assert fb["reason"] == "MODEL_ALIAS_UNAVAILABLE"


def test_resolver_unknown_alias_in_policy_accept_custom(tmp_path: Path) -> None:
    """A policy alias not in the default mapping is accepted when no availability list is provided."""
    run_root = tmp_path / "run"
    policy = tmp_path / "task-model-policy.json"
    write_policy(policy, {
        "architecture": "some-unknown-model-v99",
    })

    completed = run_script("--run-root", str(run_root), "--policy", str(policy))

    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["taskModels"]["architecture"] == "some-unknown-model-v99"
    assert len(payload["fallbacks"]) == 0


def test_resolver_missing_policy_file_uses_default(tmp_path: Path) -> None:
    """When --policy points to a non-existent file, the default mapping is used."""
    run_root = tmp_path / "run"
    nonexistent = tmp_path / "nonexistent.json"

    completed = run_script("--run-root", str(run_root), "--policy", str(nonexistent))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS_WITH_FALLBACKS"
    assert payload["policySource"] == "built-in-default"


def test_resolver_invalid_policy_json_uses_default(tmp_path: Path) -> None:
    """When the policy file is not valid JSON, the default mapping is used with fallback recorded."""
    run_root = tmp_path / "run"
    bad_policy = tmp_path / "bad-policy.json"
    bad_policy.write_text("not json", encoding="utf-8")

    completed = run_script("--run-root", str(run_root), "--policy", str(bad_policy))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS_WITH_FALLBACKS"
    assert payload["policySource"] == "built-in-default"


def test_resolver_inherit_alias_preserved(tmp_path: Path) -> None:
    """When a policy explicitly sets an alias to 'inherit', it is preserved as-is."""
    run_root = tmp_path / "run"
    policy = tmp_path / "task-model-policy.json"
    write_policy(policy, {
        "architecture": "inherit",
    })

    completed = run_script("--run-root", str(run_root), "--policy", str(policy))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["taskModels"]["architecture"] == "inherit"


# ---------------------------------------------------------------------------
# Native Workflow JS taskModel pass-through tests
# ---------------------------------------------------------------------------


_EXECUTE_JS_HARNESS = r"""
const fs = require('node:fs')
const payload = JSON.parse(fs.readFileSync(0, 'utf8'))
const source = fs.readFileSync(payload.script, 'utf8').replace('export const meta =', 'const meta =')
const phases = []
const labels = []
const models = []
const modelProperties = []
const queuedAgentResults = [...payload.agentResults]
const phase = title => phases.push(title)
const agent = async (_prompt, options) => {
  labels.push(options?.label || '')
  models.push(options?.model || null)
  modelProperties.push(Object.prototype.hasOwnProperty.call(options || {}, 'model'))
  if (queuedAgentResults.length === 0) {
    const err = new Error('Mock Agent result queue is empty')
    console.error(err.stack || String(err))
    process.exit(1)
  }
  return queuedAgentResults.shift()
}
const parallel = async thunks => Promise.all(thunks.map(thunk => thunk()))
const pipeline = async (items, ...stages) => {
  let current = items
  for (const stage of stages) {
    current = await Promise.all(current.map(stage))
  }
  return current
}
const workflow = async () => {
  throw new Error('Nested workflow is not expected in this test')
}
const run = new Function('args', 'phase', 'agent', 'parallel', 'pipeline', 'workflow', `return (async () => { ${source}\n })()`)
run(payload.args, phase, agent, parallel, pipeline, workflow)
  .then(result => console.log(JSON.stringify({ result, phases, labels, models, modelProperties })))
  .catch(error => {
    console.error(error.stack || String(error))
    process.exit(1)
  })
"""


def execute_workflow_js(script: Path, args: dict, *, agent_results: list[dict] | None = None) -> dict:
    """Execute a Native Workflow JS file in Node with a mock harness."""
    if agent_results is None:
        agent_results = []
    payload = {
        "script": str(script.resolve()),
        "args": args,
        "agentResults": agent_results,
    }
    completed = subprocess.run(
        ["node", "-e", _EXECUTE_JS_HARNESS],
        input=json.dumps(payload),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Node harness failed\nstdout={completed.stdout}\nstderr={completed.stderr}")
    try:
        return json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON from harness\nstdout={completed.stdout}\nstderr={completed.stderr}") from exc


DEVELOP_LENSES = {
    "purpose": "Create a code review workflow.",
    "objectModel": "Read a request and generate a Native Workflow JS candidate.",
    "processModel": "Clarify, design, review, generate, validate, smoke, and deliver.",
    "decisionModel": "Require confirmation, evidence, and explicit apply approval.",
    "evidenceModel": "Use design, validation, smoke, and apply evidence.",
    "acceptanceModel": "Cover positive, blocked, and candidate-only delivery scenarios.",
    "boundaryModel": "Do not write the target project without apply approval.",
}


def test_develop_task_models_passed_to_agents() -> None:
    """When taskModels are provided in args, the correct model aliases reach each agent."""
    base_args = {
        "request": "Create a code review workflow.",
        "targetRoot": "/tmp/target",
        "runRoot": "/tmp/run",
        "operation": "create",
        "runId": "test-run-1",
        "clarification": {
            "lenses": DEVELOP_LENSES,
            "confirmedByUser": True,
        },
        "taskModels": {
            "repository-exploration": "deepseek-v4-flash[1M]",
            "architecture": "deepseek-v4-pro[1M]",
            "risk-review": "deepseek-v4-pro[1M]",
        },
    }

    # Provide mock agent results for exploration (2), design (1), review (1)
    agent_results = [
        {"status": "PASS", "findings": ["f1"], "constraints": ["c1"], "blockingIssues": []},
        {"status": "PASS", "findings": ["f2"], "constraints": ["c2"], "blockingIssues": []},
        {"status": "PASS", "summary": "s", "highLevelDesign": "hld", "lowLevelDesign": "lld", "traceability": ["t"], "blockingIssues": []},
        {"status": "PASS", "blockingIssues": [], "requiredRevisions": [], "summary": "approved"},
    ]

    harness_result = execute_workflow_js(DEVELOP_JS, base_args, agent_results=agent_results)

    result = harness_result["result"]
    labels = harness_result.get("labels", [])
    models = harness_result.get("models", [])

    # Should reach PASS (no generation/validation/smoke/apply evidence, so stops at Deliver)
    assert result["status"] == "READY_FOR_GENERATION"

    assert len(labels) >= 4
    assert labels[0].startswith("workflowprogram-develop:explore:")
    assert labels[1].startswith("workflowprogram-develop:explore:")
    assert labels[2] == "workflowprogram-develop:design"
    assert labels[3] == "workflowprogram-develop:review"

    assert models[0] == "deepseek-v4-flash[1M]"  # exploration
    assert models[1] == "deepseek-v4-flash[1M]"  # exploration
    assert models[2] == "deepseek-v4-pro[1M]"    # design
    assert models[3] == "deepseek-v4-pro[1M]"    # review


def test_develop_default_model_when_task_models_absent() -> None:
    """When taskModels is not provided, agents receive undefined model (inherited)."""
    base_args = {
        "request": "Create a code review workflow.",
        "targetRoot": "/tmp/target",
        "runRoot": "/tmp/run",
        "operation": "create",
        "runId": "test-run-2",
        "clarification": {
            "lenses": DEVELOP_LENSES,
            "confirmedByUser": True,
        },
    }

    agent_results = [
        {"status": "PASS", "findings": ["f1"], "constraints": ["c1"], "blockingIssues": []},
        {"status": "PASS", "findings": ["f2"], "constraints": ["c2"], "blockingIssues": []},
        {"status": "PASS", "summary": "s", "highLevelDesign": "hld", "lowLevelDesign": "lld", "traceability": ["t"], "blockingIssues": []},
        {"status": "PASS", "blockingIssues": [], "requiredRevisions": [], "summary": "approved"},
    ]

    harness_result = execute_workflow_js(DEVELOP_JS, base_args, agent_results=agent_results)
    result = harness_result["result"]
    models = harness_result.get("models", [])

    assert result["status"] == "READY_FOR_GENERATION"
    # All models should be null/undefined when taskModels is absent
    assert all(m is None for m in models), f"Expected all null models, got: {models}"


def test_audit_task_models_passed_to_agents() -> None:
    """Audit JS passes taskModels to inspect and risk-review agents."""
    base_args = {
        "runId": "test-run-3",
        "targetRoot": "/tmp/target",
        "workflowScriptPath": "/tmp/target/.claude/workflows/test.js",
        "candidateHash": "sha256:abc123",
        "assetRefs": ["/tmp/target/.claude/workflows/test.js"],
        "discoveryEvidence": {
            "status": "PASS",
            "candidateHash": "sha256:abc123",
            "evidence": ["/tmp/evidence.json"],
        },
        "taskModels": {
            "repository-exploration": "deepseek-v4-flash[1M]",
            "risk-review": "deepseek-v4-pro[1M]",
        },
    }

    agent_results = [
        {"status": "PASS", "findings": ["f1"], "blockingIssues": []},
        {"status": "PASS", "issues": [], "blockingIssues": [], "summary": "clean"},
    ]

    harness_result = execute_workflow_js(AUDIT_JS, base_args, agent_results=agent_results)
    result = harness_result["result"]
    models = harness_result.get("models", [])

    # Stops at Verify (no verify evidence provided), but agents ran
    assert result["status"] in ("READY_FOR_AUDIT_VERIFICATION", "PASS")

    assert len(models) >= 2
    assert models[0] == "deepseek-v4-flash[1M]"  # inspect
    assert models[1] == "deepseek-v4-pro[1M]"    # risk-review


def test_iterate_task_models_passed_to_agents() -> None:
    """Iterate JS passes taskModels to all four agent calls."""
    base_args = {
        "runId": "test-run-4",
        "targetRoot": "/tmp/target",
        "runRoot": "/tmp/run",
        "stateHash": "sha256:state1",
        "readbackEvidence": {
            "status": "PASS",
            "stateHash": "sha256:state1",
            "evidence": ["/tmp/readback.json"],
            "blockingIssues": []
        },
        "taskModels": {
            "static-review": "deepseek-v4-flash[1M]",
            "generation": "deepseek-v4-flash[1M]",
            "architecture": "deepseek-v4-pro[1M]",
            "risk-review": "deepseek-v4-pro[1M]",
        },
    }

    agent_results = [
        {"status": "PASS", "stateHash": "sha256:state1", "findings": [], "blockingIssues": []},
        {"status": "PASS", "stateHash": "sha256:state1", "delta": [], "blockingIssues": []},
        {"status": "PASS", "stateHash": "sha256:state1", "constraintCandidates": [], "blockingIssues": []},
        {"status": "PASS", "stateHash": "sha256:state1", "approvedCandidates": [], "blockingIssues": []},
    ]

    harness_result = execute_workflow_js(ITERATE_JS, base_args, agent_results=agent_results)
    result = harness_result["result"]
    models = harness_result.get("models", [])

    # Empty findings → no-new-lessons path; only collect-findings agent runs
    assert result["status"] == "PASS"
    assert result.get("deliveryMode") == "no-new-lessons"

    assert len(models) >= 1
    assert models[0] == "deepseek-v4-flash[1M]"  # collect-findings


def test_task_models_partial_coverage_does_not_block() -> None:
    """When only some taskTypes are in taskModels, the rest get undefined (inherit)."""
    base_args = {
        "request": "Create a code review workflow.",
        "targetRoot": "/tmp/target",
        "runRoot": "/tmp/run",
        "operation": "create",
        "runId": "test-run-5",
        "clarification": {
            "lenses": DEVELOP_LENSES,
            "confirmedByUser": True,
        },
        "taskModels": {
            "architecture": "deepseek-v4-pro[1M]",
            # repository-exploration and risk-review are absent
        },
    }

    agent_results = [
        {"status": "PASS", "findings": ["f1"], "constraints": ["c1"], "blockingIssues": []},
        {"status": "PASS", "findings": ["f2"], "constraints": ["c2"], "blockingIssues": []},
        {"status": "PASS", "summary": "s", "highLevelDesign": "hld", "lowLevelDesign": "lld", "traceability": ["t"], "blockingIssues": []},
        {"status": "PASS", "blockingIssues": [], "requiredRevisions": [], "summary": "approved"},
    ]

    harness_result = execute_workflow_js(DEVELOP_JS, base_args, agent_results=agent_results)
    result = harness_result["result"]
    models = harness_result.get("models", [])

    assert result["status"] == "READY_FOR_GENERATION"
    assert models[0] is None  # exploration: no mapping
    assert models[1] is None  # exploration: no mapping
    assert models[2] == "deepseek-v4-pro[1M]"  # design: has mapping
    assert models[3] is None  # review: no mapping


def test_resolver_output_matches_js_expected_shape(tmp_path: Path) -> None:
    """The resolver output has the exact shape the JS taskModel helper expects."""
    run_root = tmp_path / "run"
    completed = run_script("--run-root", str(run_root))

    payload = load_json(completed)
    task_models = payload["taskModels"]

    # All 8 standard task types are present
    assert set(task_models.keys()) == {
        "clarification", "repository-exploration", "generation", "static-review",
        "architecture", "complex-generation", "risk-review", "publish-verification",
    }

    # All values are non-empty strings
    for k, v in task_models.items():
        assert isinstance(v, str)
        assert len(v) > 0


# ---------------------------------------------------------------------------
# M13 repair: new resolver feature tests
# ---------------------------------------------------------------------------


def test_resolver_task_type_filter_repeated(tmp_path: Path) -> None:
    """--task-type filters to only the requested types in first-seen CLI order."""
    run_root = tmp_path / "run"
    completed = run_script(
        "--run-root", str(run_root),
        "--task-type", "architecture",
        "--task-type", "generation",
    )

    assert completed.returncode == 0
    payload = load_json(completed)
    keys = list(payload["taskModels"].keys())
    assert keys == ["architecture", "generation"]
    assert payload["taskModels"]["architecture"] == "deepseek-v4-pro[1M]"
    assert payload["taskModels"]["generation"] == "deepseek-v4-flash[1M]"


def test_resolver_task_type_deduplicates_first_seen_order(tmp_path: Path) -> None:
    """Duplicate --task-type values are deduplicated, preserving first-seen order."""
    run_root = tmp_path / "run"
    completed = run_script(
        "--run-root", str(run_root),
        "--task-type", "risk-review",
        "--task-type", "risk-review",
        "--task-type", "architecture",
        "--task-type", "risk-review",
    )

    assert completed.returncode == 0
    payload = load_json(completed)
    keys = list(payload["taskModels"].keys())
    assert keys == ["risk-review", "architecture"]


def test_resolver_unknown_task_type_fallback(tmp_path: Path) -> None:
    """A requested task type not in DEFAULT_MAPPING resolves to inherit with TASK_TYPE_UNMAPPED."""
    run_root = tmp_path / "run"
    completed = run_script(
        "--run-root", str(run_root),
        "--task-type", "architecture",
        "--task-type", "imaginary-task-type-v99",
    )

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["taskModels"]["architecture"] == "deepseek-v4-pro[1M]"
    assert payload["taskModels"]["imaginary-task-type-v99"] == "inherit"
    assert len(payload["fallbacks"]) == 1
    assert payload["fallbacks"][0]["taskType"] == "imaginary-task-type-v99"
    assert payload["fallbacks"][0]["reason"] == "TASK_TYPE_UNMAPPED"


def test_resolver_available_model_repeated_overrides_env(tmp_path: Path) -> None:
    """--available-model CLI values take precedence over AVAILABLE_MODELS env var."""
    run_root = tmp_path / "run"
    env = {"AVAILABLE_MODELS": "deepseek-v4-flash[1M]"}
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--run-root", str(run_root), "--json",
         "--available-model", "deepseek-v4-pro[1M]"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**__import__("os").environ, **env},
    )

    payload = load_json(completed)
    # Only pro is available via CLI, so flash models should fall back
    assert payload["status"] == "PASS_WITH_FALLBACKS"
    assert payload["taskModels"]["architecture"] == "deepseek-v4-pro[1M]"  # available
    assert payload["taskModels"]["clarification"] == "inherit"  # flash unavailable
    assert len(payload["fallbacks"]) >= 4  # all flash task types fall back


def test_resolver_exact_out_path(tmp_path: Path) -> None:
    """--out writes the resolution to the exact specified path."""
    custom_out = tmp_path / "custom" / "resolution.json"
    run_root = tmp_path / "run"  # Also provided but output goes to --out
    completed = run_script("--run-root", str(run_root), "--out", str(custom_out))

    assert completed.returncode == 0
    assert custom_out.is_file()
    payload = json.loads(custom_out.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["schemaVersion"] == 1

    # The default run-root output should NOT be written
    default_path = run_root / "outputs" / "stages" / "task-model-resolution.json"
    assert not default_path.is_file()


def test_resolver_out_without_run_root(tmp_path: Path) -> None:
    """--out alone (without --run-root) still writes to the specified path."""
    custom_out = tmp_path / "only-out.json"
    completed = run_script("--out", str(custom_out))

    assert completed.returncode == 0
    assert custom_out.is_file()
    payload = json.loads(custom_out.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"


def test_resolver_requires_output_destination() -> None:
    """The resolver must not report success when it cannot persist evidence."""
    completed = run_script()

    assert completed.returncode == 2
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert payload["error_code"] == "OUTPUT_PATH_REQUIRED"


def test_resolver_custom_alias_accepted_without_availability(tmp_path: Path) -> None:
    """A custom policy alias not in DEFAULT_MAPPING values is accepted when no availability list exists."""
    run_root = tmp_path / "run"
    policy = tmp_path / "policy.json"
    write_policy(policy, {
        "clarification": "my-custom-model-v42",
    })

    completed = run_script("--run-root", str(run_root), "--policy", str(policy))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["taskModels"]["clarification"] == "my-custom-model-v42"


def test_resolver_custom_alias_rejected_with_explicit_availability(tmp_path: Path) -> None:
    """A custom policy alias is rejected when explicit --available-model list does not contain it."""
    run_root = tmp_path / "run"
    policy = tmp_path / "policy.json"
    write_policy(policy, {
        "clarification": "my-custom-model-v42",
    })

    completed = run_script(
        "--run-root", str(run_root),
        "--policy", str(policy),
        "--available-model", "deepseek-v4-flash[1M]",
    )

    payload = load_json(completed)
    assert payload["status"] == "PASS_WITH_FALLBACKS"
    assert payload["taskModels"]["clarification"] == "inherit"
    assert len(payload["fallbacks"]) >= 1
    clarification_fb = [fb for fb in payload["fallbacks"] if fb.get("taskType") == "clarification"]
    assert len(clarification_fb) == 1
    assert clarification_fb[0]["reason"] == "MODEL_ALIAS_UNAVAILABLE"
    assert clarification_fb[0]["requestedModel"] == "my-custom-model-v42"


def test_resolver_policy_file_unavailable(tmp_path: Path) -> None:
    """When an explicit --policy path does not exist, fall back with POLICY_FILE_UNAVAILABLE."""
    run_root = tmp_path / "run"
    nonexistent = tmp_path / "no-such-policy.json"

    completed = run_script("--run-root", str(run_root), "--policy", str(nonexistent))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS_WITH_FALLBACKS"
    assert payload["policySource"] == "built-in-default"
    # A fallback entry should record the unavailable policy
    assert len(payload["fallbacks"]) == 1
    assert payload["fallbacks"][0]["reason"] == "POLICY_FILE_UNAVAILABLE"


def test_resolver_policy_file_invalid_json(tmp_path: Path) -> None:
    """When the policy file is invalid JSON, fall back with POLICY_FILE_INVALID."""
    run_root = tmp_path / "run"
    bad_policy = tmp_path / "bad-policy.json"
    bad_policy.write_text("{invalid json content}", encoding="utf-8")

    completed = run_script("--run-root", str(run_root), "--policy", str(bad_policy))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS_WITH_FALLBACKS"
    assert payload["policySource"] == "built-in-default"
    assert len(payload["fallbacks"]) == 1
    assert payload["fallbacks"][0]["reason"] == "POLICY_FILE_INVALID"


def test_resolver_policy_file_invalid_not_dict(tmp_path: Path) -> None:
    """When the policy file is valid JSON but not a dict, fall back with POLICY_FILE_INVALID."""
    run_root = tmp_path / "run"
    bad_policy = tmp_path / "bad-policy.json"
    bad_policy.write_text('["not", "a", "dict"]', encoding="utf-8")

    completed = run_script("--run-root", str(run_root), "--policy", str(bad_policy))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS_WITH_FALLBACKS"
    assert payload["policySource"] == "built-in-default"
    assert len(payload["fallbacks"]) == 1
    assert payload["fallbacks"][0]["reason"] == "POLICY_FILE_INVALID"


def test_resolver_resolution_order_tracked(tmp_path: Path) -> None:
    """Resolution output contains resolutionOrder reflecting which paths were taken."""
    run_root = tmp_path / "run"
    completed = run_script("--run-root", str(run_root))

    payload = load_json(completed)
    assert "resolutionOrder" in payload
    assert "built-in-default" in payload["resolutionOrder"]


# ---------------------------------------------------------------------------
# M13 repair: JS withTaskModel helper tests
# ---------------------------------------------------------------------------


AUTHORING_JS = ROOT / ".claude" / "workflows" / "workflowprogram-native-authoring.js"


def test_develop_task_model_omit_when_inherit() -> None:
    """When taskModels maps a type to 'inherit', the model property is omitted (null)."""
    base_args = {
        "request": "Create a code review workflow.",
        "targetRoot": "/tmp/target",
        "runRoot": "/tmp/run",
        "operation": "create",
        "runId": "test-run-inherit",
        "clarification": {
            "lenses": DEVELOP_LENSES,
            "confirmedByUser": True,
        },
        "taskModels": {
            "repository-exploration": " inherit ",
            "architecture": " deepseek-v4-pro[1M] ",
            "risk-review": " ",
        },
    }

    agent_results = [
        {"status": "PASS", "findings": ["f1"], "constraints": ["c1"], "blockingIssues": []},
        {"status": "PASS", "findings": ["f2"], "constraints": ["c2"], "blockingIssues": []},
        {"status": "PASS", "summary": "s", "highLevelDesign": "hld", "lowLevelDesign": "lld", "traceability": ["t"], "blockingIssues": []},
        {"status": "PASS", "blockingIssues": [], "requiredRevisions": [], "summary": "approved"},
    ]

    harness_result = execute_workflow_js(DEVELOP_JS, base_args, agent_results=agent_results)
    models = harness_result.get("models", [])
    model_properties = harness_result.get("modelProperties", [])

    # exploration agents: inherit → model should be null
    assert models[0] is None
    assert models[1] is None
    # design: explicit model
    assert models[2] == "deepseek-v4-pro[1M]"
    # review: inherit → model should be null
    assert models[3] is None
    assert model_properties == [False, False, True, False]


def test_develop_task_model_omit_when_absent() -> None:
    """When a task type is absent from taskModels, the model property is omitted (null)."""
    base_args = {
        "request": "Create a code review workflow.",
        "targetRoot": "/tmp/target",
        "runRoot": "/tmp/run",
        "operation": "create",
        "runId": "test-run-absent",
        "clarification": {
            "lenses": DEVELOP_LENSES,
            "confirmedByUser": True,
        },
        "taskModels": {
            "architecture": "deepseek-v4-pro[1M]",
            # repository-exploration and risk-review are absent
        },
    }

    agent_results = [
        {"status": "PASS", "findings": ["f1"], "constraints": ["c1"], "blockingIssues": []},
        {"status": "PASS", "findings": ["f2"], "constraints": ["c2"], "blockingIssues": []},
        {"status": "PASS", "summary": "s", "highLevelDesign": "hld", "lowLevelDesign": "lld", "traceability": ["t"], "blockingIssues": []},
        {"status": "PASS", "blockingIssues": [], "requiredRevisions": [], "summary": "approved"},
    ]

    harness_result = execute_workflow_js(DEVELOP_JS, base_args, agent_results=agent_results)
    models = harness_result.get("models", [])
    model_properties = harness_result.get("modelProperties", [])

    assert models[0] is None  # exploration absent
    assert models[1] is None  # exploration absent
    assert models[2] == "deepseek-v4-pro[1M]"  # design present
    assert models[3] is None  # review absent
    assert model_properties == [False, False, True, False]


def test_iterate_full_path_task_types(tmp_path: Path) -> None:
    """Iterate passes taskModels to all four Agent paths when findings exist."""
    base_args = {
        "runId": "test-iterate-full",
        "targetRoot": "/tmp/target",
        "runRoot": "/tmp/run",
        "stateHash": "sha256:full-iterate",
        "readbackEvidence": {
            "status": "PASS",
            "stateHash": "sha256:full-iterate",
            "evidence": ["/tmp/readback.json"],
            "blockingIssues": [],
        },
        # Provide handoff evidence for intermediate deterministic phases so the
        # JS reaches the Propose Constraints and Review agent stages.
        "deltaValidationEvidence": {
            "status": "PASS",
            "stateHash": "sha256:full-iterate",
            "evidence": ["/tmp/delta-validation.json"],
            "deltaHash": "sha256:delta1",
            "blockingIssues": [],
        },
        "appendEvidence": {
            "status": "PASS",
            "stateHash": "sha256:post-append",
            "baselineHash": "sha256:full-iterate",
            "deltaHash": "sha256:delta1",
            "evidence": ["/tmp/append.json"],
            "blockingIssues": [],
        },
        "taskModels": {
            "static-review": "deepseek-v4-flash[1M]",
            "generation": "deepseek-v4-flash[1M]",
            "architecture": "deepseek-v4-pro[1M]",
            "risk-review": "deepseek-v4-pro[1M]",
        },
    }

    # Provide results for all 4 agents (findings with content to reach all stages)
    agent_results = [
        {"status": "PASS", "stateHash": "sha256:full-iterate",
         "findings": [{"id": "f1", "category": "pattern", "summary": "Missing validation gate"}],
         "blockingIssues": []},
        {"status": "PASS", "stateHash": "sha256:full-iterate",
         "delta": [{"type": "lesson", "summary": "Add validation", "body": "Validation gates prevent drift"}],
         "blockingIssues": []},
        {"status": "PASS", "stateHash": "sha256:full-iterate",
         "constraintCandidates": [{"rule": "Always validate", "reason": "Prevents drift"}],
         "blockingIssues": []},
        {"status": "PASS", "stateHash": "sha256:full-iterate",
         "approvedCandidates": [{"rule": "Always validate", "reason": "Prevents drift"}],
         "blockingIssues": []},
    ]

    harness_result = execute_workflow_js(ITERATE_JS, base_args, agent_results=agent_results)
    models = harness_result.get("models", [])

    # All 4 agents should have received their specific task models
    assert len(models) >= 4, f"Expected >=4 models, got {len(models)}: {models}"
    assert models[0] == "deepseek-v4-flash[1M]"  # collect-findings -> static-review
    assert models[1] == "deepseek-v4-flash[1M]"  # build-lessons-delta -> generation
    assert models[2] == "deepseek-v4-pro[1M]"    # propose-constraints -> architecture
    assert models[3] == "deepseek-v4-pro[1M]"    # review-constraints -> risk-review


def test_authoring_task_models_passed_to_agents() -> None:
    """Transitional authoring passes taskModels to explore, design, and review agents."""
    base_args = {
        "requirement": "Create a simple audit workflow.",
        "targetRoot": "/tmp/target",
        "readinessPacket": '{"confirmed_by_user": true}',
        "readinessStatus": "PASS",
        "taskModels": {
            "repository-exploration": "deepseek-v4-flash[1M]",
            "architecture": "deepseek-v4-pro[1M]",
            "risk-review": "deepseek-v4-pro[1M]",
        },
    }

    # Provide results for explore (1), design (2), review (1)
    agent_results = [
        {"status": "PASS", "findings": ["f1"], "constraints": ["c1"], "reusableAssets": ["a1"], "blockingIssues": []},
        {"status": "PASS", "strategy": "minimal", "workflowName": "test", "description": "test", "phases": ["p"], "schemas": ["s"], "gates": ["g"], "supportingAssets": [], "smokeScenarios": ["s"], "blockingIssues": []},
        {"status": "PASS", "strategy": "risk-first", "workflowName": "test", "description": "test", "phases": ["p"], "schemas": ["s"], "gates": ["g"], "supportingAssets": [], "smokeScenarios": ["s"], "blockingIssues": []},
        {"status": "PASS", "selectedStrategy": "minimal", "blockingIssues": [], "requiredRevisions": [], "handoffSummary": "ok"},
    ]

    harness_result = execute_workflow_js(AUTHORING_JS, base_args, agent_results=agent_results)
    result = harness_result["result"]
    models = harness_result.get("models", [])

    assert result["status"] == "PASS"
    assert len(models) >= 4
    assert models[0] == "deepseek-v4-flash[1M]"  # explore -> repository-exploration
    assert models[1] == "deepseek-v4-pro[1M]"    # design1 -> architecture
    assert models[2] == "deepseek-v4-pro[1M]"    # design2 -> architecture
    assert models[3] == "deepseek-v4-pro[1M]"    # review -> risk-review
