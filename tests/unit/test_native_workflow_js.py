from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / ".claude" / "scripts" / "validate-native-workflow-js.py"
GENERATOR = ROOT / ".claude" / "scripts" / "generate-native-workflow.py"
FIXTURES = ROOT / "tests" / "native-workflow-fixtures"
SAMPLE_MIGRATION = ROOT / "tests" / "manual-fixtures" / "native-workflow-sample-migration"
AUTHORING_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-native-authoring.js"
DEVELOP_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-develop.js"
PRODUCT_WORKFLOW_SKELETONS: dict[str, str] = {}
VALIDATE_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-validate.js"
ITERATE_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-iterate.js"
AUDIT_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-audit.js"
PUBLISH_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-publish.js"
DEVELOP_LENSES = {
    "purpose": "Create a workflow.",
    "objectModel": "Read a request and generate a Native Workflow JS candidate.",
    "processModel": "Clarify, design, review, generate, validate, smoke, and deliver.",
    "decisionModel": "Require confirmation, evidence, and explicit apply approval.",
    "evidenceModel": "Use design, validation, smoke, and apply evidence.",
    "acceptanceModel": "Cover positive, blocked, and candidate-only delivery scenarios.",
    "boundaryModel": "Do not write the target project without apply approval.",
}


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON\nstdout={completed.stdout}\nstderr={completed.stderr}") from exc


def execute_native_workflow(
    script: Path,
    args: dict,
    *,
    agent_results: list[dict] | None = None,
) -> dict:
    harness = r"""
const fs = require('node:fs')
const payload = JSON.parse(fs.readFileSync(0, 'utf8'))
const source = fs.readFileSync(payload.script, 'utf8').replace('export const meta =', 'const meta =')
const phases = []
const labels = []
const queuedAgentResults = [...payload.agentResults]
const phase = title => phases.push(title)
const agent = async (_prompt, options) => {
  labels.push(options?.label || '')
  if (queuedAgentResults.length === 0) {
    throw new Error('Mock Agent result queue is empty')
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
  .then(result => console.log(JSON.stringify({ result, phases, labels })))
  .catch(error => {
    console.error(error.stack || String(error))
    process.exit(1)
  })
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        input=json.dumps(
            {
                "script": str(script),
                "args": args,
                "agentResults": agent_results or [],
            }
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return load_json(completed)


def develop_args(**overrides: object) -> dict:
    payload = {
        "request": "Design a deterministic Native Workflow JS probe.",
        "targetRoot": "/tmp/native-target",
        "runRoot": "/tmp/native-run",
        "runId": "run-001",
        "operation": "create",
        "clarification": {
            "lenses": DEVELOP_LENSES,
            "openQuestions": [],
            "confirmedByUser": True,
        },
        "applyApproved": False,
    }
    payload.update(overrides)
    return payload


def pass_design_evidence() -> dict:
    return {
        "status": "PASS",
        "summary": "Design is complete.",
        "highLevelDesign": "Use one Native JS control plane.",
        "lowLevelDesign": "Return structured handoffs for external effects.",
        "traceability": ["REQ-001 -> Validate -> smoke evidence"],
        "blockingIssues": [],
    }


def pass_review_evidence() -> dict:
    return {
        "status": "PASS",
        "blockingIssues": [],
        "requiredRevisions": [],
        "summary": "Design review is closed.",
    }


def pass_generation_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:probe",
        "candidateRefs": ["/tmp/native-run/outputs/candidate/.claude/workflows/probe.js"],
        "evidence": ["/tmp/native-run/outputs/stages/native-workflow-generation.json"],
        "blockingIssues": [],
    }


def pass_validation_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:probe",
        "evidence": ["/tmp/native-run/outputs/stages/native-workflow-validation.json"],
        "blockingIssues": [],
    }


def pass_smoke_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:probe",
        "evidence": ["/tmp/native-run/outputs/stages/native-workflow-smoke.json"],
        "blockingIssues": [],
    }


def pass_apply_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:probe",
        "applyManifest": "/tmp/native-run/outputs/stages/native-workflow-apply-manifest.json",
        "evidence": ["/tmp/native-run/outputs/stages/native-workflow-apply.json"],
        "blockingIssues": [],
    }


def write_readiness_packet(path: Path, target_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "request": "Generate a deterministic read-only Native Workflow probe.",
                "target_root": str(target_root),
                "confirmed_by_user": True,
                "lenses": {
                    "purpose": "Verify Native authoring.",
                    "object_model": "Read a probe request and return a structured result.",
                    "process_model": "Run one Probe phase.",
                    "decision_model": "Return PASS when the probe completes.",
                    "evidence_model": "Use the structured workflow result.",
                    "acceptance_model": "The workflow returns PASS.",
                    "boundary_model": "Do not write files.",
                },
                "success_criteria": ["The workflow returns PASS without writing files."],
                "open_questions": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_generator(spec: Path, target_root: Path, run_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    readiness = run_root / "readiness.json"
    write_readiness_packet(readiness, target_root)
    return run_script(
        GENERATOR,
        "--spec",
        str(spec),
        "--readiness",
        str(readiness),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
        *args,
    )


def test_validator_accepts_valid_minimal_fixture() -> None:
    completed = run_script(VALIDATOR, "--script", str(FIXTURES / "valid-minimal.js"), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["meta"]["name"] == "valid-minimal"
    assert payload["phases"] == ["Probe"]


@pytest.mark.parametrize(
    ("fixture", "rule"),
    [
        ("invalid-meta-literal.js", "META_LITERAL_REQUIRED"),
        ("invalid-meta-expression.js", "META_LITERAL_INVALID"),
        ("invalid-phase-alignment.js", "PHASE_ALIGNMENT"),
        ("invalid-forbidden-api.js", "FORBIDDEN_API"),
        ("invalid-gate-without-schema.js", "SCHEMA_REQUIRED_FOR_GATE"),
        ("invalid-parallel-write.js", "PARALLEL_WRITE_HINT"),
        ("invalid-return-envelope.js", "RETURN_ENVELOPE_REQUIRED"),
    ],
)
def test_validator_rejects_invalid_fixture(fixture: str, rule: str) -> None:
    completed = run_script(VALIDATOR, "--script", str(FIXTURES / fixture), "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert rule in {item["rule"] for item in payload["errors"]}


def test_validator_allows_forbidden_api_words_inside_prompt_strings(tmp_path: Path) -> None:
    script = tmp_path / "prompt-word.js"
    script.write_text(
        """export const meta = {
  name: 'prompt-word',
  description: 'Prompt words are not executable APIs.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
await agent({ prompt: 'Review this process and require() documentation.' })
return { status: 'PASS' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def write_authoring_spec(
    path: Path,
    *,
    description: str = "Generate a minimal native workflow probe.",
    body: str = "phase('Probe')\n\nreturn { status: 'PASS' }\n",
    supporting_assets: list[dict[str, str]] | None = None,
    task_model_policy: dict | None = None,
) -> None:
    payload = {
        "name": "generated-probe",
        "description": description,
        "phases": [{"title": "Probe", "detail": "Return PASS."}],
        "body": body,
        "supporting_assets": supporting_assets or [],
    }
    if task_model_policy is not None:
        payload["task_model_policy"] = task_model_policy
    path.write_text(
        json.dumps(payload, indent=2)
        + "\n",
        encoding="utf-8",
    )


def test_generator_stages_only_native_workflow_by_default(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(spec)

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "generated-probe.js"
    assert candidate.exists()
    assert "workflowprogramAgent" not in candidate.read_text(encoding="utf-8")
    assert not (target / ".claude" / "workflows" / "generated-probe.js").exists()
    assert not (run_root / "outputs" / "candidate" / ".workflowprogram").exists()
    assert (run_root / "outputs" / "stages" / "native-workflow-validation.json").exists()


def execute_generated_workflow_with_models(script: Path, args: dict, agent_results: list[dict]) -> dict:
    harness = r"""
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
    throw new Error('Mock Agent result queue is empty')
  }
  return queuedAgentResults.shift()
}
const parallel = async thunks => Promise.all(thunks.map(thunk => thunk()))
const pipeline = async (items, ...stages) => {
  let current = items
  for (const stage of stages) current = await Promise.all(current.map(stage))
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
    completed = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        input=json.dumps({"script": str(script), "args": args, "agentResults": agent_results}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout)


def test_generator_injects_task_model_control_plane_for_target_workflow(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(
        spec,
        body=(
            "phase('Probe')\n"
            "const result = await agent('Return a PASS probe result.', {\n"
            "  label: 'generated-probe:probe',\n"
            "  schema: {\n"
            "    type: 'object',\n"
            "    properties: { status: { type: 'string', enum: ['PASS', 'BLOCKED'] } },\n"
            "    required: ['status'],\n"
            "    additionalProperties: false,\n"
            "  },\n"
            "})\n"
            "if (result.status !== 'PASS') return { status: 'BLOCKED' }\n"
            "return { status: 'PASS' }\n"
        ),
        task_model_policy={
            "agent_task_models": {
                "generated-probe:probe": "architecture",
            },
        },
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "generated-probe.js"
    source = candidate.read_text(encoding="utf-8")
    assert source.startswith("export const meta = {")
    assert "const taskModels = args?.taskModels || {}" in source
    assert "workflowprogramAgent(" in source
    assert "agentTaskTypes" in source

    execution = execute_generated_workflow_with_models(
        candidate,
        {"taskModels": {"architecture": "deepseek-v4-pro[1M]"}},
        [{"status": "PASS"}],
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["labels"] == ["generated-probe:probe"]
    assert execution["models"] == ["deepseek-v4-pro[1M]"]
    assert execution["modelProperties"] == [True]


def test_generated_target_workflow_omits_model_for_inherit_and_missing_mapping(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(
        spec,
        body=(
            "phase('Probe')\n"
            "const first = await agent('Return PASS.', { label: 'generated-probe:first', schema: { type: 'object', properties: { status: { type: 'string' } }, required: ['status'], additionalProperties: false } })\n"
            "const second = await agent('Return PASS.', { label: 'generated-probe:second', schema: { type: 'object', properties: { status: { type: 'string' } }, required: ['status'], additionalProperties: false } })\n"
            "return { status: first.status === 'PASS' && second.status === 'PASS' ? 'PASS' : 'BLOCKED' }\n"
        ),
        task_model_policy={
            "agent_task_models": {
                "generated-probe:first": "architecture",
            },
        },
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "generated-probe.js"

    execution = execute_generated_workflow_with_models(
        candidate,
        {"taskModels": {"architecture": " inherit "}},
        [{"status": "PASS"}, {"status": "PASS"}],
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["models"] == [None, None]
    assert execution["modelProperties"] == [False, False]


def test_generator_apply_creates_managed_native_workflow(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(spec)

    completed = run_generator(spec, target, run_root, "--apply", "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    target_script = target / ".claude" / "workflows" / "generated-probe.js"
    assert target_script.exists()
    manifest = json.loads((target / ".workflowprogram" / "managed-files.json").read_text(encoding="utf-8"))
    assert [item["relative_path"] for item in manifest["entries"]] == [".claude/workflows/generated-probe.js"]


def test_generator_apply_does_not_overwrite_unmanaged_native_workflow(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    existing = target / ".claude" / "workflows" / "generated-probe.js"
    existing.parent.mkdir(parents=True)
    existing.write_text("// user-owned\n", encoding="utf-8")
    write_authoring_spec(spec)

    completed = run_generator(spec, target, run_root, "--apply", "--json")
    assert completed.returncode == 2
    payload = load_json(completed)
    assert payload["status"] == "CONFLICT"
    assert existing.read_text(encoding="utf-8") == "// user-owned\n"
    conflict_copy = run_root / "outputs" / "conflicts" / ".claude" / "workflows" / "generated-probe.js"
    assert conflict_copy.exists()


def test_generator_apply_updates_managed_native_workflow(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    first_run = tmp_path / "first-run"
    second_run = tmp_path / "second-run"
    target.mkdir()
    write_authoring_spec(spec)

    first = run_generator(spec, target, first_run, "--apply", "--json")
    assert first.returncode == 0, first.stderr or first.stdout

    write_authoring_spec(spec, description="Updated managed native workflow probe.")
    second = run_generator(spec, target, second_run, "--apply", "--json")
    assert second.returncode == 0, second.stderr or second.stdout
    target_script = target / ".claude" / "workflows" / "generated-probe.js"
    assert "Updated managed native workflow probe." in target_script.read_text(encoding="utf-8")


def test_generator_does_not_apply_static_validation_failure(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(spec, body="phase('Wrong')\n\nreturn { status: 'PASS' }\n")

    completed = run_generator(spec, target, run_root, "--apply", "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "PHASE_ALIGNMENT" in {item["rule"] for item in payload["errors"]}
    assert not (target / ".claude" / "workflows" / "generated-probe.js").exists()


def test_generator_stages_explicit_optional_supporting_assets(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(
        spec,
        supporting_assets=[
            {
                "kind": "skill",
                "path": ".claude/skills/probe-review/SKILL.md",
                "content": "---\nname: probe-review\ndescription: Review probe output.\n---\n\nReview the probe output.",
                "reason": "Reused by multiple Native workflows.",
            },
            {
                "kind": "agent",
                "path": ".claude/agents/probe-reviewer.md",
                "content": "# Probe Reviewer\n\nReview probe output.",
                "reason": "Requires a reusable reviewer role.",
            },
            {
                "kind": "script",
                "path": ".claude/scripts/probe-check.py",
                "content": "print('PASS')",
                "reason": "Checks an external fact deterministically.",
            },
            {
                "kind": "workflow-spec-ir",
                "path": ".workflowprogram/design/workflow-spec.yaml",
                "content": "name: generated-probe",
                "reason": "Complex authoring requires a stable optional IR.",
            },
        ],
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    candidate_root = run_root / "outputs" / "candidate"
    assert (candidate_root / ".claude" / "skills" / "probe-review" / "SKILL.md").exists()
    assert (candidate_root / ".claude" / "agents" / "probe-reviewer.md").exists()
    assert (candidate_root / ".claude" / "scripts" / "probe-check.py").exists()
    assert (candidate_root / ".workflowprogram" / "design" / "workflow-spec.yaml").exists()
    assert {item["kind"] for item in payload["supporting_assets"]} == {
        "skill",
        "agent",
        "script",
        "workflow-spec-ir",
    }


@pytest.mark.parametrize(
    "supporting_assets",
    [
        [
            {
                "kind": "script",
                "path": "../outside.py",
                "content": "print('unsafe')",
                "reason": "Must be rejected.",
            }
        ],
        [
            {
                "kind": "skill",
                "path": ".claude/agents/not-a-skill.md",
                "content": "# Wrong prefix",
                "reason": "Must be rejected.",
            }
        ],
        [
            {
                "kind": "agent",
                "path": ".claude/agents/no-reason.md",
                "content": "# Missing reason",
                "reason": "",
            }
        ],
    ],
)
def test_generator_rejects_invalid_optional_supporting_assets(tmp_path: Path, supporting_assets: list[dict[str, str]]) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(spec, supporting_assets=supporting_assets)

    completed = run_generator(spec, target, run_root, "--apply", "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert not (target / ".claude").exists()


def run_generator_handoff(spec: Path, target_root: Path, run_root: Path, handoff: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_script(
        GENERATOR,
        "--spec",
        str(spec),
        "--generation-handoff",
        str(handoff),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
        *args,
    )


_UNSET = object()


def write_handoff_packet(
    path: Path,
    *,
    target_root: Path,
    run_root: Path,
    run_id: str = "run-001",
    status: str = "READY_FOR_GENERATION",
    workflow: str = "workflowprogram-develop",
    design_evidence: object = _UNSET,
    review_evidence: object = _UNSET,
    generation_request: object = _UNSET,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "status": status,
        "workflow": workflow,
        "launchMode": "plugin-script-path",
        "runId": run_id,
        "targetRoot": str(target_root),
        "runRoot": str(run_root),
        "requirementSummary": {
            "request": "Design a deterministic Native Workflow JS probe.",
            "targetRoot": str(target_root),
            "runRoot": str(run_root),
            "operation": "create",
            "lenses": DEVELOP_LENSES,
        },
    }
    if generation_request is not _UNSET:
        payload["generationRequest"] = generation_request
    else:
        payload["generationRequest"] = {
            "targetRoot": str(target_root),
            "runRoot": str(run_root),
            "operation": "create",
            "rule": "Write candidate assets under RUN_ROOT only.",
        }
    if design_evidence is not _UNSET:
        payload["designEvidence"] = design_evidence
    else:
        payload["designEvidence"] = {
            "status": "PASS",
            "summary": "Design is complete.",
            "highLevelDesign": "Use one Native JS control plane.",
            "lowLevelDesign": "Return structured handoffs for external effects.",
            "traceability": ["REQ-001 -> Validate -> smoke evidence"],
            "blockingIssues": [],
        }
    if review_evidence is not _UNSET:
        payload["reviewEvidence"] = review_evidence
    else:
        payload["reviewEvidence"] = {
            "status": "PASS",
            "blockingIssues": [],
            "requiredRevisions": [],
            "summary": "Design review is closed.",
        }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ── handoff gate tests ─────────────────────────────────────────────────

def test_generator_handoff_passes_with_valid_handoff(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    handoff_report = run_root / "outputs" / "stages" / "native-workflow-generation-handoff.json"
    assert payload["generation_handoff_report"] == str(handoff_report)
    assert handoff_report.exists()
    # Validate the handoff report schema
    report_data = json.loads(handoff_report.read_text(encoding="utf-8"))
    assert report_data["schema_name"] == "native-workflow-generation-handoff-validation"
    assert report_data["status"] == "PASS"
    assert report_data["errors"] == []
    assert report_data["packet"] == str(handoff.resolve())
    assert payload["readiness_report"] is None
    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "generated-probe.js"
    assert candidate.exists()


def test_generator_handoff_blocks_wrong_status(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, status="NEEDS_USER_INPUT")

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "READY_FOR_GENERATION" in str(payload["errors"])
    assert not target.exists()


def test_generator_handoff_blocks_target_root_mismatch(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    other_target = tmp_path / "other-target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    other_target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=other_target, run_root=run_root)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "targetRoot" in str(payload["errors"])


def test_generator_handoff_blocks_run_root_mismatch(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    other_run = tmp_path / "other-run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=other_run)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "runRoot" in str(payload["errors"])


def test_generator_handoff_blocks_missing_design_evidence(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, design_evidence=None)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "designEvidence" in str(payload["errors"])


def test_generator_handoff_blocks_failed_design_evidence(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        design_evidence={"status": "BLOCKED", "summary": "", "highLevelDesign": "", "lowLevelDesign": "", "traceability": [], "blockingIssues": ["incomplete"]},
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "designEvidence" in str(payload["errors"])


def test_generator_handoff_blocks_missing_review_evidence(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, review_evidence=None)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "reviewEvidence" in str(payload["errors"])


def test_generator_handoff_blocks_failed_review_evidence(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        review_evidence={"status": "BLOCKED", "blockingIssues": ["unresolved risk"], "requiredRevisions": ["fix boundary"], "summary": "Blocked."},
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "reviewEvidence" in str(payload["errors"])


def test_generator_handoff_blocks_missing_run_id(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, run_id="")

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "runId" in str(payload["errors"])


def test_generator_handoff_blocks_non_string_run_id(tmp_path: Path) -> None:
    """runId must remain a string identifier."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root)
    packet = json.loads(handoff.read_text(encoding="utf-8"))
    packet["runId"] = 123
    handoff.write_text(json.dumps(packet), encoding="utf-8")

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    assert "runId" in str(load_json(completed)["errors"])


def test_generator_handoff_blocks_wrong_workflow(tmp_path: Path) -> None:
    """Handoff with wrong workflow value must block."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, workflow="wrong-workflow")

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "workflowprogram-develop" in str(payload["errors"])


def test_generator_handoff_blocks_missing_generation_request(tmp_path: Path) -> None:
    """Handoff without generationRequest object must block."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, generation_request=None)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "generationRequest" in str(payload["errors"])


def test_generator_handoff_blocks_non_string_generation_rule(tmp_path: Path) -> None:
    """generationRequest.rule must remain a textual write boundary."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        generation_request={
            "targetRoot": str(target),
            "runRoot": str(run_root),
            "rule": 123,
        },
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    assert "generationRequest.rule" in str(load_json(completed)["errors"])


def test_generator_handoff_blocks_empty_design_traceability(tmp_path: Path) -> None:
    """Handoff with empty designEvidence.traceability must block."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        design_evidence={
            "status": "PASS",
            "summary": "Design summary.",
            "highLevelDesign": "HLD content.",
            "lowLevelDesign": "LLD content.",
            "traceability": [],
            "blockingIssues": [],
        },
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "traceability" in str(payload["errors"])


def test_generator_handoff_blocks_review_with_nonempty_blockers(tmp_path: Path) -> None:
    """Handoff with non-empty reviewEvidence.blockingIssues must block."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        review_evidence={
            "status": "PASS",
            "blockingIssues": ["unresolved risk"],
            "requiredRevisions": [],
            "summary": "Review summary.",
        },
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "blockingIssues" in str(payload["errors"])


def test_generator_handoff_report_path_on_fail(tmp_path: Path) -> None:
    """Even on FAIL, the handoff validation report must be persisted."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, status="NEEDS_USER_INPUT")

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    handoff_report = run_root / "outputs" / "stages" / "native-workflow-generation-handoff.json"
    assert payload["generation_handoff_report"] == str(handoff_report)
    assert handoff_report.exists()
    report_data = json.loads(handoff_report.read_text(encoding="utf-8"))
    assert report_data["schema_name"] == "native-workflow-generation-handoff-validation"
    assert report_data["status"] == "FAIL"
    assert len(report_data["errors"]) > 0
    # No candidate files must exist when handoff validation fails
    assert not (run_root / "outputs" / "candidate").exists()


def test_generator_handoff_handoff_report_schema(tmp_path: Path) -> None:
    """The handoff validation report must have the expected schema fields."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    handoff_report = run_root / "outputs" / "stages" / "native-workflow-generation-handoff.json"
    report_data = json.loads(handoff_report.read_text(encoding="utf-8"))
    assert "schema_version" in report_data
    assert "schema_name" in report_data
    assert "status" in report_data
    assert "packet" in report_data
    assert "target_root" in report_data
    assert "run_root" in report_data
    assert "run_id" in report_data
    assert "errors" in report_data


def test_generator_readiness_still_works(tmp_path: Path) -> None:
    """M7 compatibility: --readiness path must still generate successfully."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(spec)

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["readiness_report"] is not None
    assert payload["generation_handoff_report"] is None
    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "generated-probe.js"
    assert candidate.exists()


def test_generator_handoff_with_apply_creates_managed_workflow(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--apply", "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    target_script = target / ".claude" / "workflows" / "generated-probe.js"
    assert target_script.exists()


def test_generator_handoff_still_validates_js(tmp_path: Path) -> None:
    """Handoff path must still run static JS validation and reject invalid candidates."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec, body="phase('Wrong')\n\nreturn { status: 'PASS' }\n")
    write_handoff_packet(handoff, target_root=target, run_root=run_root)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "PHASE_ALIGNMENT" in {item["rule"] for item in payload["errors"]}


def test_generator_rejects_both_handoff_and_readiness_missing(tmp_path: Path) -> None:
    """When neither --generation-handoff nor --readiness is provided, argparse must fail."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(spec)

    completed = run_script(
        GENERATOR,
        "--spec", str(spec),
        "--target-root", str(target),
        "--run-root", str(run_root),
        "--json",
    )
    # Argparse exits 2 when a required mutually exclusive group is missing
    assert completed.returncode == 2
    assert "one of the arguments --generation-handoff --readiness is required" in completed.stderr


def test_generator_rejects_both_handoff_and_readiness_passed(tmp_path: Path) -> None:
    """Passing both --generation-handoff and --readiness must fail visibly."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    readiness = tmp_path / "readiness.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_readiness_packet(readiness, target)
    write_handoff_packet(handoff, target_root=target, run_root=run_root)

    completed = run_script(
        GENERATOR,
        "--spec", str(spec),
        "--generation-handoff", str(handoff),
        "--readiness", str(readiness),
        "--target-root", str(target),
        "--run-root", str(run_root),
        "--json",
    )
    # Argparse exits 2 when mutually exclusive args are both provided
    assert completed.returncode == 2
    assert "not allowed with argument" in completed.stderr


def test_sample_migration_fixture_is_static_valid() -> None:
    script = SAMPLE_MIGRATION / "target-root" / ".claude" / "workflows" / "workflowprogram-native-sample-migration.js"

    completed = run_script(VALIDATOR, "--script", str(script), "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_native_authoring_meta_workflow_is_static_valid() -> None:
    completed = run_script(VALIDATOR, "--script", str(AUTHORING_WORKFLOW), "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_develop_native_workflow_is_static_valid() -> None:
    completed = run_script(VALIDATOR, "--script", str(DEVELOP_WORKFLOW), "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_develop_native_workflow_blocks_missing_input() -> None:
    execution = execute_native_workflow(DEVELOP_WORKFLOW, {})

    assert execution["result"]["status"] == "BLOCKED_INPUT"


def test_develop_native_workflow_requests_missing_lenses() -> None:
    payload = develop_args(
        clarification={
            "lenses": {"purpose": "Create a workflow."},
            "openQuestions": [],
            "confirmedByUser": False,
        }
    )

    execution = execute_native_workflow(DEVELOP_WORKFLOW, payload)

    assert execution["result"]["status"] == "NEEDS_USER_INPUT"
    assert {item["id"] for item in execution["result"]["questions"]} == {
        "objectModel",
        "processModel",
        "decisionModel",
        "evidenceModel",
        "acceptanceModel",
        "boundaryModel",
    }


def test_develop_native_workflow_requests_confirmation() -> None:
    payload = develop_args(
        clarification={
            "lenses": DEVELOP_LENSES,
            "openQuestions": [],
            "confirmedByUser": False,
        }
    )

    execution = execute_native_workflow(DEVELOP_WORKFLOW, payload)

    assert execution["result"]["status"] == "READY_FOR_CONFIRMATION"
    assert execution["result"]["nextAction"] == "REINVOKE_WITH_CONFIRMATION"


def test_develop_native_workflow_requests_controlled_generation_after_design_review() -> None:
    exploration = {
        "status": "PASS",
        "findings": ["Use a single JS control plane."],
        "constraints": ["Do not write target files directly."],
        "blockingIssues": [],
    }
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(),
        agent_results=[exploration, exploration, pass_design_evidence(), pass_review_evidence()],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["nextAction"] == "RUN_CONTROLLED_GENERATION"
    assert execution["phases"] == ["Intake", "Clarify", "Confirm", "Design", "Review", "Generate"]


def test_develop_native_workflow_handoff_includes_target_and_run_root() -> None:
    """READY_FOR_GENERATION response must include top-level targetRoot and runRoot."""
    exploration = {
        "status": "PASS",
        "findings": ["Use a single JS control plane."],
        "constraints": ["Do not write target files directly."],
        "blockingIssues": [],
    }
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(),
        agent_results=[exploration, exploration, pass_design_evidence(), pass_review_evidence()],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["targetRoot"] == "/tmp/native-target"
    assert execution["result"]["runRoot"] == "/tmp/native-run"


@pytest.mark.parametrize(
    ("extra_args", "expected_status"),
    [
        ({"generationEvidence": {"status": "FAIL", "blockingIssues": ["generation failed"]}}, "BLOCKED_GENERATION"),
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": {"status": "FAIL", "blockingIssues": ["validation failed"]},
            },
            "BLOCKED_VALIDATION",
        ),
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": pass_validation_evidence(),
                "smokeEvidence": {"status": "FAIL", "blockingIssues": ["smoke failed"]},
            },
            "BLOCKED_SMOKE",
        ),
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": pass_validation_evidence(),
                "smokeEvidence": pass_smoke_evidence(),
                "applyApproved": True,
                "applyEvidence": {"status": "CONFLICT", "blockingIssues": ["target drift"]},
            },
            "BLOCKED_CONFLICT",
        ),
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": {
                    "status": "PASS",
                    "candidateHash": "sha256:stale",
                    "evidence": ["/tmp/native-run/outputs/stages/stale-validation.json"],
                    "blockingIssues": [],
                },
            },
            "BLOCKED_VALIDATION",
        ),
        (
            {
                "generationEvidence": {
                    **pass_generation_evidence(),
                    "candidateRefs": [""],
                },
            },
            "BLOCKED_GENERATION",
        ),
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": {
                    **pass_validation_evidence(),
                    "evidence": [""],
                },
            },
            "BLOCKED_VALIDATION",
        ),
    ],
)
def test_develop_native_workflow_blocks_failed_external_handoff(
    extra_args: dict,
    expected_status: str,
) -> None:
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            designEvidence=pass_design_evidence(),
            reviewEvidence=pass_review_evidence(),
            **extra_args,
        ),
    )

    assert execution["result"]["status"] == expected_status


@pytest.mark.parametrize(
    ("extra_args", "expected_status", "next_action"),
    [
        ({}, "READY_FOR_GENERATION", "RUN_CONTROLLED_GENERATION"),
        ({"generationEvidence": pass_generation_evidence()}, "READY_FOR_VALIDATION", "RUN_DETERMINISTIC_VALIDATION"),
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": pass_validation_evidence(),
            },
            "READY_FOR_SMOKE",
            "RUN_INTERACTIVE_SMOKE",
        ),
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": pass_validation_evidence(),
                "smokeEvidence": pass_smoke_evidence(),
                "applyApproved": True,
            },
            "READY_FOR_APPLY",
            "RUN_CONTROLLED_APPLY",
        ),
    ],
)
def test_develop_native_workflow_returns_external_handoff(
    extra_args: dict,
    expected_status: str,
    next_action: str,
) -> None:
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            designEvidence=pass_design_evidence(),
            reviewEvidence=pass_review_evidence(),
            **extra_args,
        ),
    )

    assert execution["result"]["status"] == expected_status
    assert execution["result"]["nextAction"] == next_action


def test_develop_native_workflow_delivers_candidate_without_apply() -> None:
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            designEvidence=pass_design_evidence(),
            reviewEvidence=pass_review_evidence(),
            generationEvidence=pass_generation_evidence(),
            validationEvidence=pass_validation_evidence(),
            smokeEvidence=pass_smoke_evidence(),
        ),
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "candidate-only"


def test_develop_native_workflow_delivers_managed_apply() -> None:
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            designEvidence=pass_design_evidence(),
            reviewEvidence=pass_review_evidence(),
            generationEvidence=pass_generation_evidence(),
            validationEvidence=pass_validation_evidence(),
            smokeEvidence=pass_smoke_evidence(),
            applyApproved=True,
            applyEvidence=pass_apply_evidence(),
        ),
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "managed-apply"


def validate_args(**overrides: object) -> dict:
    return {
        "runId": "run-001",
        "targetRoot": "/tmp/native-target",
        "workflowScriptPath": "/tmp/native-target/.claude/workflows/target.js",
        "candidateHash": "sha256:abc123",
        **overrides,
    }


def pass_static_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:abc123",
        "evidence": ["/tmp/evidence/static.json"],
        "blockingIssues": [],
    }


def pass_external_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:abc123",
        "evidence": ["/tmp/evidence/external.json"],
        "blockingIssues": [],
    }


def test_validate_native_workflow_is_static_valid() -> None:
    completed = run_script(VALIDATOR, "--script", str(VALIDATE_WORKFLOW), "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validate_blocks_missing_input() -> None:
    execution = execute_native_workflow(VALIDATE_WORKFLOW, {})

    assert execution["result"]["status"] == "BLOCKED_INPUT"


def test_validate_requests_static_validation() -> None:
    execution = execute_native_workflow(VALIDATE_WORKFLOW, validate_args())

    assert execution["result"]["status"] == "READY_FOR_VALIDATION"
    assert execution["result"]["nextAction"] == "RUN_DETERMINISTIC_VALIDATION"


def test_validate_blocks_failed_static_evidence() -> None:
    execution = execute_native_workflow(
        VALIDATE_WORKFLOW,
        validate_args(staticEvidence={"status": "FAIL", "candidateHash": "sha256:abc123", "evidence": ["/tmp/e.json"], "blockingIssues": ["fail"]}),
    )

    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


def test_validate_blocks_stale_static_hash() -> None:
    execution = execute_native_workflow(
        VALIDATE_WORKFLOW,
        validate_args(staticEvidence={"status": "PASS", "candidateHash": "sha256:stale", "evidence": ["/tmp/e.json"], "blockingIssues": []}),
    )

    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


def test_validate_blocks_empty_static_evidence_array() -> None:
    execution = execute_native_workflow(
        VALIDATE_WORKFLOW,
        validate_args(staticEvidence={"status": "PASS", "candidateHash": "sha256:abc123", "evidence": [], "blockingIssues": []}),
    )

    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


def test_validate_requests_external_verify() -> None:
    execution = execute_native_workflow(
        VALIDATE_WORKFLOW,
        validate_args(staticEvidence=pass_static_evidence()),
    )

    assert execution["result"]["status"] == "READY_FOR_EXTERNAL_VERIFY"
    assert execution["result"]["nextAction"] == "RUN_EXTERNAL_VERIFY"


def test_validate_blocks_failed_external_evidence() -> None:
    execution = execute_native_workflow(
        VALIDATE_WORKFLOW,
        validate_args(
            staticEvidence=pass_static_evidence(),
            externalEvidence={"status": "FAIL", "candidateHash": "sha256:abc123", "evidence": ["/tmp/e.json"], "blockingIssues": ["fail"]},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


def test_validate_blocks_stale_external_hash() -> None:
    execution = execute_native_workflow(
        VALIDATE_WORKFLOW,
        validate_args(
            staticEvidence=pass_static_evidence(),
            externalEvidence={"status": "PASS", "candidateHash": "sha256:stale", "evidence": ["/tmp/e.json"], "blockingIssues": []},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


def test_validate_passes() -> None:
    execution = execute_native_workflow(
        VALIDATE_WORKFLOW,
        validate_args(
            staticEvidence=pass_static_evidence(),
            externalEvidence=pass_external_evidence(),
        ),
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["workflow"] == "workflowprogram-validate"
    assert execution["result"]["launchMode"] == "plugin-script-path"
    assert execution["result"]["candidateHash"] == "sha256:abc123"
    assert len(execution["result"]["evidence"]) == 2
    assert execution["result"]["blockingIssues"] == []
    assert execution["result"]["nextAction"] == "DELIVER"


def audit_args(**overrides: object) -> dict:
    return {
        "runId": "run-001",
        "targetRoot": "/tmp/native-target",
        "workflowScriptPath": "/tmp/native-target/.claude/workflows/target.js",
        "candidateHash": "sha256:abc123",
        "assetRefs": [".claude/workflows/target.js"],
        **overrides,
    }


def pass_discovery_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:abc123",
        "evidence": ["/tmp/evidence/discovery.json"],
        "blockingIssues": [],
    }


def pass_inspect_evidence() -> dict:
    return {
        "status": "PASS",
        "findings": ["Clean structure."],
        "blockingIssues": [],
    }


def pass_audit_evidence() -> dict:
    return {
        "status": "PASS",
        "issues": [],
        "blockingIssues": [],
        "summary": "No risks.",
    }


def pass_verify_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:abc123",
        "evidence": ["/tmp/evidence/verify.json"],
        "blockingIssues": [],
    }


def test_audit_native_workflow_is_static_valid() -> None:
    completed = run_script(VALIDATOR, "--script", str(AUDIT_WORKFLOW), "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_audit_blocks_missing_input() -> None:
    execution = execute_native_workflow(AUDIT_WORKFLOW, {})

    assert execution["result"]["status"] == "BLOCKED_INPUT"


def test_audit_blocks_missing_asset_refs() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        {
            "runId": "run-001",
            "targetRoot": "/tmp/native-target",
            "workflowScriptPath": "/tmp/native-target/.claude/workflows/target.js",
            "candidateHash": "sha256:abc123",
            "assetRefs": [],
        },
    )

    assert execution["result"]["status"] == "BLOCKED_INPUT"


def test_audit_requests_discovery() -> None:
    execution = execute_native_workflow(AUDIT_WORKFLOW, audit_args())

    assert execution["result"]["status"] == "READY_FOR_AUDIT_DISCOVERY"
    assert execution["result"]["nextAction"] == "RUN_AUDIT_DISCOVERY"


def test_audit_blocks_failed_discovery() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(discoveryEvidence={"status": "FAIL", "candidateHash": "sha256:abc123", "evidence": ["/tmp/e.json"], "blockingIssues": ["fail"]}),
    )

    assert execution["result"]["status"] == "BLOCKED_AUDIT"


def test_audit_blocks_stale_discovery_hash() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(discoveryEvidence={"status": "PASS", "candidateHash": "sha256:stale", "evidence": ["/tmp/e.json"], "blockingIssues": []}),
    )

    assert execution["result"]["status"] == "BLOCKED_AUDIT"


def test_audit_runs_inspect_and_risk_review_agents() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(discoveryEvidence=pass_discovery_evidence()),
        agent_results=[pass_inspect_evidence(), pass_audit_evidence()],
    )

    assert "Inspect" in execution["phases"]
    assert "Audit" in execution["phases"]
    assert "workflowprogram-audit:inspect" in execution["labels"]
    assert "workflowprogram-audit:risk-review" in execution["labels"]


def test_audit_blocks_inspect_failure() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(
            discoveryEvidence=pass_discovery_evidence(),
            inspectEvidence={"status": "BLOCKED", "findings": ["Broken structure."], "blockingIssues": ["fatal"]},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_AUDIT"


def test_audit_blocks_risk_review_failure() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(
            discoveryEvidence=pass_discovery_evidence(),
            inspectEvidence=pass_inspect_evidence(),
            auditEvidence={"status": "BLOCKED", "issues": [{"id": "R1", "severity": "CRITICAL", "summary": "Critical risk."}], "blockingIssues": ["critical risk"], "summary": "Blocked."},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_AUDIT"


def test_audit_blocks_malformed_injected_inspect_evidence() -> None:
    """Injected inspectEvidence with PASS status but non-array findings is blocked."""
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(
            discoveryEvidence=pass_discovery_evidence(),
            inspectEvidence={"status": "PASS", "findings": "not-an-array", "blockingIssues": []},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_AUDIT"
    assert len(execution["result"]["blockingIssues"]) > 0


def test_audit_blocks_malformed_injected_audit_evidence() -> None:
    """Injected auditEvidence with PASS status but empty summary is blocked."""
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(
            discoveryEvidence=pass_discovery_evidence(),
            inspectEvidence=pass_inspect_evidence(),
            auditEvidence={"status": "PASS", "issues": [], "blockingIssues": [], "summary": ""},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_AUDIT"
    assert len(execution["result"]["blockingIssues"]) > 0


def test_audit_inspect_uses_fallback_blocker_when_blocking_issues_empty() -> None:
    """BLOCKED inspect with empty blockingIssues gets a fallback blocker."""
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(
            discoveryEvidence=pass_discovery_evidence(),
            inspectEvidence={"status": "BLOCKED", "findings": ["Broken structure."], "blockingIssues": []},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_AUDIT"
    assert len(execution["result"]["blockingIssues"]) >= 1


def test_audit_requests_verification() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(
            discoveryEvidence=pass_discovery_evidence(),
            inspectEvidence=pass_inspect_evidence(),
            auditEvidence=pass_audit_evidence(),
        ),
    )

    assert execution["result"]["status"] == "READY_FOR_AUDIT_VERIFICATION"
    assert execution["result"]["nextAction"] == "RUN_AUDIT_VERIFICATION"


def test_audit_blocks_failed_verification() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(
            discoveryEvidence=pass_discovery_evidence(),
            inspectEvidence=pass_inspect_evidence(),
            auditEvidence=pass_audit_evidence(),
            verifyEvidence={"status": "FAIL", "candidateHash": "sha256:abc123", "evidence": ["/tmp/e.json"], "blockingIssues": ["fail"]},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_AUDIT"


def test_audit_passes() -> None:
    execution = execute_native_workflow(
        AUDIT_WORKFLOW,
        audit_args(
            discoveryEvidence=pass_discovery_evidence(),
            inspectEvidence=pass_inspect_evidence(),
            auditEvidence=pass_audit_evidence(),
            verifyEvidence=pass_verify_evidence(),
        ),
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["workflow"] == "workflowprogram-audit"
    assert execution["result"]["launchMode"] == "plugin-script-path"
    assert execution["result"]["candidateHash"] == "sha256:abc123"
    assert len(execution["result"]["evidence"]) == 2
    assert execution["result"]["blockingIssues"] == []
    assert execution["result"]["nextAction"] == "DELIVER"


def iterate_args(**overrides: object) -> dict:
    return {
        "runId": "run-001",
        "targetRoot": "/tmp/native-target",
        "runRoot": "/tmp/native-run",
        **overrides,
    }


def pass_readback_evidence(state_hash: str = "sha256:abc123") -> dict:
    return {
        "status": "PASS",
        "stateHash": state_hash,
        "evidence": ["/tmp/native-target/lessons.md", "/tmp/native-target/.claude/rules/constraints.md"],
        "blockingIssues": [],
    }


def pass_findings_evidence(state_hash: str = "sha256:abc123") -> dict:
    return {
        "status": "PASS",
        "stateHash": state_hash,
        "findings": [
            {"id": "F1", "category": "process", "summary": "Missing validation step."},
        ],
        "blockingIssues": [],
    }


def pass_empty_findings_evidence(state_hash: str = "sha256:abc123") -> dict:
    return {
        "status": "PASS",
        "stateHash": state_hash,
        "findings": [],
        "blockingIssues": [],
    }


def pass_delta_evidence(state_hash: str = "sha256:abc123") -> dict:
    return {
        "status": "PASS",
        "stateHash": state_hash,
        "delta": [
            {"type": "lesson", "summary": "Lesson 1", "body": "Body of lesson 1."},
        ],
        "blockingIssues": [],
    }


def pass_delta_validation_evidence(state_hash: str = "sha256:abc123", delta_hash: str = "sha256:delta-789abc") -> dict:
    return {
        "status": "PASS",
        "stateHash": state_hash,
        "deltaHash": delta_hash,
        "evidence": ["/tmp/native-run/outputs/stages/delta-validation.json"],
        "blockingIssues": [],
    }


def pass_append_evidence(
    baseline_hash: str = "sha256:abc123",
    post_write_state_hash: str = "sha256:post-append-def456",
    delta_hash: str = "sha256:delta-789abc",
) -> dict:
    return {
        "status": "PASS",
        "baselineHash": baseline_hash,
        "stateHash": post_write_state_hash,
        "deltaHash": delta_hash,
        "evidence": ["/tmp/native-target/lessons.md"],
        "blockingIssues": [],
        "receipt": {"runId": "run-001", "idempotent": False},
    }


def pass_proposal_evidence(state_hash: str = "sha256:abc123", with_candidates: bool = True) -> dict:
    return {
        "status": "PASS",
        "stateHash": state_hash,
        "constraintCandidates": [
            {"rule": "ALWAYS validate before commit.", "reason": "Lesson F1."},
        ] if with_candidates else [],
        "blockingIssues": [],
    }


def pass_iterate_review_evidence(state_hash: str = "sha256:abc123") -> dict:
    return {
        "status": "PASS",
        "stateHash": state_hash,
        "approvedCandidates": [
            {"rule": "ALWAYS validate before commit.", "reason": "Lesson F1."},
        ],
        "blockingIssues": [],
    }


def pass_apply_constraints_evidence(
    baseline_hash: str = "sha256:post-append-def456",
    post_write_state_hash: str = "sha256:post-apply-fed",
    proposal_hash: str = "sha256:proposal-xyz",
) -> dict:
    return {
        "status": "PASS",
        "baselineHash": baseline_hash,
        "stateHash": post_write_state_hash,
        "proposalHash": proposal_hash,
        "evidence": ["/tmp/native-target/.claude/rules/constraints.md"],
        "blockingIssues": [],
        "receipt": {"runId": "run-001", "idempotent": False},
    }


def pass_empty_review_evidence(state_hash: str = "sha256:abc123") -> dict:
    return {
        "status": "PASS",
        "stateHash": state_hash,
        "approvedCandidates": [],
        "blockingIssues": [],
    }


# Static validity

def test_iterate_native_workflow_is_static_valid() -> None:
    completed = run_script(VALIDATOR, "--script", str(ITERATE_WORKFLOW), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


# Missing input

def test_iterate_blocks_missing_input() -> None:
    execution = execute_native_workflow(ITERATE_WORKFLOW, {})
    assert execution["result"]["status"] == "BLOCKED_INPUT"
    assert "runId" in execution["result"]["blockingIssues"][0]


# Readback handoff

def test_iterate_requests_readback() -> None:
    execution = execute_native_workflow(ITERATE_WORKFLOW, iterate_args())
    assert execution["result"]["status"] == "READY_FOR_ITERATION_READBACK"
    assert execution["result"]["nextAction"] == "RUN_ITERATION_READBACK"


def test_iterate_blocks_malformed_readback() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(readbackEvidence={"status": "FAIL", "stateHash": "", "evidence": [], "blockingIssues": ["fail"]}),
    )
    assert execution["result"]["status"] == "BLOCKED_ITERATION"


def test_iterate_blocks_stale_readback() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(readbackEvidence={"status": "PASS", "stateHash": "", "evidence": [], "blockingIssues": []}),
    )
    assert execution["result"]["status"] == "BLOCKED_ITERATION"


# No-new-lessons PASS

def test_iterate_empty_findings_is_no_new_lessons_pass() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_empty_findings_evidence(),
        ),
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "no-new-lessons"
    assert execution["result"]["nextAction"] == "DELIVER"


# Malformed injected evidence

def test_iterate_blocks_malformed_injected_findings() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence={"status": "PASS", "stateHash": "sha256:abc123", "findings": "not-an-array", "blockingIssues": []},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_ITERATION"


def test_iterate_blocks_malformed_injected_delta() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence={"status": "PASS", "stateHash": "sha256:abc123", "delta": "not-an-array", "blockingIssues": []},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_ITERATION"


def test_iterate_blocks_malformed_injected_proposal() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence={"status": "PASS", "stateHash": "sha256:abc123", "constraintCandidates": "not-an-array", "blockingIssues": []},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_ITERATION"


def test_iterate_blocks_malformed_injected_review() -> None:
    proposal = pass_proposal_evidence()
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=proposal,
            reviewEvidence={"status": "PASS", "stateHash": "sha256:abc123", "approvedCandidates": "not-an-array", "blockingIssues": []},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_ITERATION"


# Delta validation handoff

def test_iterate_requests_delta_validation() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_LESSONS_DELTA_VALIDATION"
    assert execution["result"]["nextAction"] == "RUN_LESSONS_DELTA_VALIDATION"


def test_iterate_blocks_invalid_delta_validation() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence={"status": "FAIL", "stateHash": "sha256:abc123", "evidence": [], "blockingIssues": ["Invalid delta format."]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


def test_iterate_blocks_stale_delta_validation() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence={"status": "PASS", "stateHash": "sha256:stale", "evidence": ["/tmp/e.json"], "blockingIssues": []},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


# Append handoff

def test_iterate_requests_lessons_append() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_LESSONS_APPEND"
    assert execution["result"]["nextAction"] == "RUN_CONTROLLED_LESSONS_APPEND"


def test_iterate_blocks_drifted_append() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence={"status": "FAIL", "stateHash": "sha256:abc123", "evidence": [], "blockingIssues": ["Baseline drift."]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"


# No constraints PASS

def test_iterate_no_constraint_candidates_is_append_only_pass() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(with_candidates=False),
        ),
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "append-only"


# Confirmation handoff

def test_iterate_requests_confirmation() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(),
            reviewEvidence=pass_iterate_review_evidence(),
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_CONFIRMATION"
    assert execution["result"]["nextAction"] == "REINVOKE_WITH_CONFIRMATION"
    assert "proposals" in execution["result"]


# Explicit rejection

def test_iterate_explicit_rejection_is_proposal_only_pass() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(),
            reviewEvidence=pass_iterate_review_evidence(),
            constraintsApproved=False,
        ),
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "proposal-only"


# Constraints apply handoff

def test_iterate_requests_constraints_apply() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(),
            reviewEvidence=pass_iterate_review_evidence(),
            constraintsApproved=True,
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_CONSTRAINTS_APPLY"
    assert execution["result"]["nextAction"] == "RUN_CONTROLLED_CONSTRAINTS_APPLY"


def test_iterate_blocks_drifted_apply() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(),
            reviewEvidence=pass_iterate_review_evidence(),
            constraintsApproved=True,
            applyConstraintsEvidence={"status": "FAIL", "stateHash": "sha256:abc123", "evidence": [], "blockingIssues": ["Drift."]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"


# Managed constraints apply PASS

def test_iterate_managed_constraints_apply_pass() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(),
            reviewEvidence=pass_iterate_review_evidence(),
            constraintsApproved=True,
            applyConstraintsEvidence=pass_apply_constraints_evidence(),
        ),
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "managed-constraints-apply"
    assert execution["result"]["nextAction"] == "DELIVER"
    assert execution["result"]["blockingIssues"] == []


# Stable envelope

def test_iterate_stable_envelope_includes_blocking_issues_and_launch_mode() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(),
            reviewEvidence=pass_iterate_review_evidence(),
            constraintsApproved=True,
            applyConstraintsEvidence=pass_apply_constraints_evidence(),
        ),
    )
    assert "blockingIssues" in execution["result"]
    assert execution["result"]["launchMode"] == "plugin-script-path"
    assert execution["result"]["workflow"] == "workflowprogram-iterate"


# Zero approvedCandidates early exit (no confirmation)

def test_iterate_zero_approved_candidates_is_append_only_pass() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(),
            reviewEvidence=pass_empty_review_evidence(),
        ),
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "append-only"
    assert execution["result"]["reason"] == "no-approved-constraints"
    assert execution["result"]["nextAction"] == "DELIVER"


# BlockingIssues validation

def test_iterate_blocks_findings_with_nonempty_blocking_issues() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence={
                "status": "PASS",
                "stateHash": "sha256:abc123",
                "findings": [{"id": "F1", "category": "process", "summary": "Test"}],
                "blockingIssues": ["unresolved block"],
            },
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_ITERATION"


def test_iterate_blocks_proposal_with_empty_rule_candidate() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence={
                "status": "PASS",
                "stateHash": "sha256:abc123",
                "constraintCandidates": [{"rule": "", "reason": "Some reason."}],
                "blockingIssues": [],
            },
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_ITERATION"


# Append evidence: baselineHash and deltaHash validation

def test_iterate_blocks_append_wrong_baseline_hash() -> None:
    """Append evidence with baselineHash != initial stateHash must be blocked."""
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(baseline_hash="sha256:wrong-baseline"),
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"


def test_iterate_blocks_append_wrong_delta_hash() -> None:
    """Append evidence with deltaHash != delta validation deltaHash must be blocked."""
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(delta_hash="sha256:wrong-delta"),
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"


# Apply evidence: baselineHash must match post-append stateHash

def test_iterate_blocks_apply_wrong_baseline_hash() -> None:
    """Apply evidence with baselineHash != post-append stateHash must be blocked."""
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence=pass_delta_validation_evidence(),
            appendEvidence=pass_append_evidence(),
            proposalEvidence=pass_proposal_evidence(),
            reviewEvidence=pass_iterate_review_evidence(),
            constraintsApproved=True,
            applyConstraintsEvidence=pass_apply_constraints_evidence(baseline_hash="sha256:wrong-baseline"),
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"


# Delta validation deltaHash required

def test_iterate_blocks_delta_validation_without_delta_hash() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence={
                "status": "PASS",
                "stateHash": "sha256:abc123",
                "deltaHash": "",
                "evidence": ["/tmp/e.json"],
                "blockingIssues": [],
            },
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


# BlockingIssues on delta validation

def test_iterate_blocks_delta_validation_with_nonempty_blocking_issues() -> None:
    execution = execute_native_workflow(
        ITERATE_WORKFLOW,
        iterate_args(
            readbackEvidence=pass_readback_evidence(),
            findingsEvidence=pass_findings_evidence(),
            lessonsDeltaEvidence=pass_delta_evidence(),
            deltaValidationEvidence={
                "status": "PASS",
                "stateHash": "sha256:abc123",
                "deltaHash": "sha256:some-delta",
                "evidence": ["/tmp/e.json"],
                "blockingIssues": ["Delta is invalid."],
            },
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_VALIDATION"


def test_product_workflow_skeleton_map_is_empty() -> None:
    """All product workflows are fully implemented; the skeleton map must be empty."""
    assert PRODUCT_WORKFLOW_SKELETONS == {}, (
        f"PRODUCT_WORKFLOW_SKELETONS expected empty, got {PRODUCT_WORKFLOW_SKELETONS}"
    )


# ── publish ──────────────────────────────────────────────────────

VALID_REPO_MODES = ["current_repo", "export_repo", "existing_marketplace"]
VALID_RUNTIME_MODES = ["workflowprogram_dependency", "vendored_runtime"]


def publish_args(**overrides: object) -> dict:
    return {
        "runId": "run-001",
        "targetRoot": "/tmp/native-target",
        "runRoot": "/tmp/native-run",
        "pluginId": "my-plugin",
        "repository": "https://github.com/example/repo",
        "version": "0.1.0",
        "repoMode": "export_repo",
        "runtimeMode": "workflowprogram_dependency",
        **overrides,
    }


def pass_qualification_evidence() -> dict:
    return {
        "status": "PASS",
        "targetHash": "sha256:target-abc123",
        "evidence": ["/tmp/evidence/qualification.json"],
        "blockingIssues": [],
    }


def pass_package_evidence(target_hash: str = "sha256:target-abc123", package_hash: str = "sha256:pkg-def456") -> dict:
    return {
        "status": "PASS",
        "targetHash": target_hash,
        "packageHash": package_hash,
        "evidence": ["/tmp/evidence/package.json"],
        "blockingIssues": [],
    }


def pass_verification_evidence(package_hash: str = "sha256:pkg-def456") -> dict:
    return {
        "status": "PASS",
        "packageHash": package_hash,
        "evidence": ["/tmp/evidence/verification.json"],
        "blockingIssues": [],
    }


def pass_marketplace_evidence(package_hash: str = "sha256:pkg-def456") -> dict:
    return {
        "status": "PASS",
        "packageHash": package_hash,
        "evidence": ["/tmp/evidence/marketplace.json"],
        "blockingIssues": [],
    }


def pass_local_delivery_evidence(package_hash: str = "sha256:pkg-def456") -> dict:
    return {
        "status": "PASS",
        "packageHash": package_hash,
        "evidence": ["/tmp/evidence/local-delivery.json"],
        "blockingIssues": [],
    }


def pass_external_apply_evidence(package_hash: str = "sha256:pkg-def456") -> dict:
    return {
        "status": "PASS",
        "packageHash": package_hash,
        "evidence": ["/tmp/evidence/external-apply.json"],
        "blockingIssues": [],
    }


# Static validity

def test_publish_native_workflow_is_static_valid() -> None:
    completed = run_script(VALIDATOR, "--script", str(PUBLISH_WORKFLOW), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


# Missing input

def test_publish_blocks_missing_input() -> None:
    execution = execute_native_workflow(PUBLISH_WORKFLOW, {})
    assert execution["result"]["status"] == "BLOCKED_INPUT"
    assert "runId" in execution["result"]["blockingIssues"][0]


def test_publish_blocks_invalid_repo_mode() -> None:
    execution = execute_native_workflow(PUBLISH_WORKFLOW, publish_args(repoMode="invalid"))
    assert execution["result"]["status"] == "BLOCKED_INPUT"


def test_publish_blocks_invalid_runtime_mode() -> None:
    execution = execute_native_workflow(PUBLISH_WORKFLOW, publish_args(runtimeMode="invalid"))
    assert execution["result"]["status"] == "BLOCKED_INPUT"


# Qualification handoff

def test_publish_requests_qualification() -> None:
    execution = execute_native_workflow(PUBLISH_WORKFLOW, publish_args())
    assert execution["result"]["status"] == "READY_FOR_PUBLISH_QUALIFICATION"
    assert execution["result"]["nextAction"] == "RUN_PUBLISH_QUALIFICATION"


def test_publish_blocks_failed_qualification() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(qualificationEvidence={"status": "FAIL", "targetHash": "", "evidence": ["/tmp/e.json"], "blockingIssues": ["fail"]}),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_publish_blocks_empty_target_hash() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(qualificationEvidence={"status": "PASS", "targetHash": "", "evidence": ["/tmp/e.json"], "blockingIssues": []}),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_publish_blocks_empty_qualification_evidence_array() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(qualificationEvidence={"status": "PASS", "targetHash": "sha256:abc", "evidence": [], "blockingIssues": []}),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


# Package handoff

def test_publish_requests_package() -> None:
    execution = execute_native_workflow(PUBLISH_WORKFLOW, publish_args(qualificationEvidence=pass_qualification_evidence()))
    assert execution["result"]["status"] == "READY_FOR_PUBLISH_PACKAGE"
    assert execution["result"]["nextAction"] == "RUN_PUBLISH_PACKAGE"


def test_publish_blocks_failed_package() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence={"status": "FAIL", "targetHash": "sha256:target-abc123", "packageHash": "sha256:pkg-def456", "evidence": ["/tmp/e.json"], "blockingIssues": ["fail"]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_publish_blocks_stale_package_target_hash() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(target_hash="sha256:stale"),
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_publish_blocks_empty_package_hash() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence={"status": "PASS", "targetHash": "sha256:target-abc123", "packageHash": "", "evidence": ["/tmp/e.json"], "blockingIssues": []},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


# Verification handoff

def test_publish_requests_verification() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_PUBLISH_VERIFICATION"
    assert execution["result"]["nextAction"] == "RUN_PUBLISH_VERIFICATION"


def test_publish_blocks_failed_verification() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence={"status": "FAIL", "packageHash": "sha256:pkg-def456", "evidence": ["/tmp/e.json"], "blockingIssues": ["fail"]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_publish_blocks_stale_verification_package_hash() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(package_hash="sha256:stale"),
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


# Marketplace merge (existing_marketplace)

def test_publish_requests_marketplace_merge_for_existing_marketplace() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            repoMode="existing_marketplace",
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_MARKETPLACE_MERGE"
    assert execution["result"]["nextAction"] == "RUN_MARKETPLACE_MERGE"


def test_publish_passes_marketplace_merge() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            repoMode="existing_marketplace",
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            marketplaceEvidence=pass_marketplace_evidence(),
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_LOCAL_DELIVERY"


def test_publish_blocks_failed_marketplace_merge() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            repoMode="existing_marketplace",
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            marketplaceEvidence={"status": "FAIL", "packageHash": "sha256:pkg-def456", "evidence": ["/tmp/e.json"], "blockingIssues": ["conflict"]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"


def test_publish_blocks_stale_marketplace_package_hash() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            repoMode="existing_marketplace",
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            marketplaceEvidence=pass_marketplace_evidence(package_hash="sha256:stale"),
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"


def test_publish_skips_marketplace_for_non_existing_repo_modes() -> None:
    for mode in ["current_repo", "export_repo"]:
        execution = execute_native_workflow(
            PUBLISH_WORKFLOW,
            publish_args(
                repoMode=mode,
                qualificationEvidence=pass_qualification_evidence(),
                packageEvidence=pass_package_evidence(),
                verificationEvidence=pass_verification_evidence(),
            ),
        )
        assert execution["result"]["status"] == "READY_FOR_LOCAL_DELIVERY"


# Local delivery handoff

def test_publish_requests_local_delivery() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_LOCAL_DELIVERY"
    assert execution["result"]["nextAction"] == "RUN_LOCAL_DELIVERY"


def test_publish_blocks_failed_local_delivery() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence={"status": "FAIL", "packageHash": "sha256:pkg-def456", "evidence": ["/tmp/e.json"], "blockingIssues": ["install failed"]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_publish_blocks_stale_local_delivery_package_hash() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(package_hash="sha256:stale"),
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


# Local-only PASS

def test_publish_passes_local_only_without_external_request() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(),
        ),
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "local-only"
    assert execution["result"]["nextAction"] == "DELIVER"
    assert execution["result"]["blockingIssues"] == []


def test_publish_passes_local_only_when_external_apply_false_explicit() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(),
            externalApplyApproved=False,
        ),
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "local-only"


# External apply handoff

def test_publish_requests_external_apply() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(),
            externalApplyApproved=True,
        ),
    )
    assert execution["result"]["status"] == "READY_FOR_EXTERNAL_APPLY"
    assert execution["result"]["nextAction"] == "RUN_EXTERNAL_PUBLISH_APPLY"


def test_publish_blocks_stale_external_apply_package_hash() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(),
            externalApplyApproved=True,
            externalApplyEvidence=pass_external_apply_evidence(package_hash="sha256:stale"),
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_publish_blocks_blocked_external_apply() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(),
            externalApplyApproved=True,
            externalApplyEvidence={"status": "BLOCKED", "packageHash": "sha256:pkg-def456", "evidence": ["/tmp/e.json"], "blockingIssues": ["auth missing"]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"
    assert "auth missing" in execution["result"]["blockingIssues"][0]


def test_publish_blocks_fail_external_apply() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(),
            externalApplyApproved=True,
            externalApplyEvidence={"status": "FAIL", "packageHash": "sha256:pkg-def456", "evidence": ["/tmp/e.json"], "blockingIssues": ["push rejected"]},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_CONFLICT"


# PASS external apply

def test_publish_passes_external_applied() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(),
            externalApplyApproved=True,
            externalApplyEvidence=pass_external_apply_evidence(),
        ),
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["deliveryMode"] == "external-applied"
    assert execution["result"]["nextAction"] == "DELIVER"
    assert len(execution["result"]["evidence"]) == 5


# Stable blockingIssues envelope

def test_publish_stable_envelope_includes_blocking_issues_and_launch_mode() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence=pass_package_evidence(),
            verificationEvidence=pass_verification_evidence(),
            localDeliveryEvidence=pass_local_delivery_evidence(),
        ),
    )
    assert "blockingIssues" in execution["result"]
    assert execution["result"]["launchMode"] == "plugin-script-path"
    assert execution["result"]["workflow"] == "workflowprogram-publish"


# Malformed injected evidence

def test_publish_blocks_malformed_qualification() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(qualificationEvidence={"status": "PASS", "targetHash": 123, "evidence": [], "blockingIssues": []}),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_publish_blocks_pass_evidence_with_nonempty_blocking_issues() -> None:
    """PASS status with non-empty blockingIssues is malformed and must block."""
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence={
                "status": "PASS",
                "targetHash": "sha256:target-abc123",
                "evidence": ["/tmp/evidence/qualification.json"],
                "blockingIssues": ["unresolved issue"],
            },
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"
    assert len(execution["result"]["blockingIssues"]) > 0


def test_publish_blocks_malformed_package_empty_evidence_refs() -> None:
    execution = execute_native_workflow(
        PUBLISH_WORKFLOW,
        publish_args(
            qualificationEvidence=pass_qualification_evidence(),
            packageEvidence={"status": "PASS", "targetHash": "sha256:target-abc123", "packageHash": "sha256:pkg-def456", "evidence": [""], "blockingIssues": []},
        ),
    )
    assert execution["result"]["status"] == "BLOCKED_PUBLISH"


def test_sample_migration_authoring_spec_generates_only_native_workflow(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()

    completed = run_generator(SAMPLE_MIGRATION / "authoring-spec.json", target, run_root, "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout
    candidate = run_root / "outputs" / "candidate"
    assert (candidate / ".claude" / "workflows" / "workflowprogram-native-sample-migration.js").exists()
    assert not (candidate / ".workflowprogram").exists()
