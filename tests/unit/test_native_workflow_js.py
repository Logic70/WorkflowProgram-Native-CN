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
LOWLEVEL_SKILL = ROOT / ".claude" / "skills" / "workflowprogram-lowlevel-design" / "SKILL.md"
NATIVE_WORKFLOW_REFERENCE = (
    ROOT / ".claude" / "skills" / "workflowprogram-lowlevel-design" / "references" / "native-workflow-js.md"
)
NATIVE_DEVELOP_SKILL = ROOT / ".claude" / "skills" / "workflowprogram-native-develop" / "SKILL.md"
LOWLEVEL_EXAMPLES = ROOT / ".claude" / "skills" / "workflowprogram-lowlevel-design" / "references" / "examples"
NATIVE_WORKFLOW_LLD = ROOT / "docs" / "native-workflow-control-plane-lowlevel-design.md"
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
const agentTypes = []
const prompts = []
const queuedAgentResults = [...payload.agentResults]
const phase = title => phases.push(title)
const agent = async (prompt, options) => {
  prompts.push(prompt)
  labels.push(options?.label || '')
  agentTypes.push(options?.agentType || null)
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
  .then(result => console.log(JSON.stringify({ result, phases, labels, agentTypes, prompts })))
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
        encoding="utf-8",
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
        "assetDisposition": [],
        "blockingIssues": [],
    }


def pass_review_evidence() -> dict:
    return {
        "status": "PASS",
        "blockingIssues": [],
        "requiredRevisions": [],
        "summary": "Design review is closed.",
        "assetDispositionReviewed": True,
    }


def pass_authoring_evidence() -> dict:
    return {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(),
        "blockingIssues": [],
    }


def pass_generation_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:probe",
        "candidateRefs": ["/tmp/native-run/outputs/candidate/.claude/workflows/probe.js"],
        "workflowScriptPath": "/tmp/native-run/outputs/candidate/.claude/workflows/probe.js",
        "evidence": ["/tmp/native-run/outputs/stages/native-workflow-generation.json"],
        "blockingIssues": [],
    }


def pass_validation_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:probe",
        "workflowScriptPath": "/tmp/native-run/outputs/candidate/.claude/workflows/probe.js",
        "evidence": ["/tmp/native-run/outputs/stages/native-workflow-validation.json"],
        "blockingIssues": [],
    }


def pass_smoke_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:probe",
        "evidence": ["/tmp/native-run/outputs/stages/native-workflow-smoke.json"],
        "smokeReports": [
            {
                "reportPath": "/tmp/native-run/outputs/stages/native-workflow-smoke.json",
                "reportHash": "sha256:smoke",
                "workflow": "probe",
                "scriptPath": "/tmp/native-run/outputs/candidate/.claude/workflows/probe.js",
                "scriptHash": "sha256:script",
                "candidateHash": "sha256:probe",
                "scenarioId": "pass-smoke-001",
                "expectedStatus": "PASS",
                "evidenceProfile": "full",
                "runIds": ["wf_probe"],
                "evidence": {
                    "workflow_invoked": True,
                    "async_launched": True,
                    "agent_started": True,
                    "schema_result": True,
                    "completed_pass": True,
                },
            }
        ],
        "blockingIssues": [],
    }


def pass_apply_evidence() -> dict:
    return {
        "status": "PASS",
        "candidateHash": "sha256:probe",
        "targetRoot": "/tmp/native-target",
        "applyManifest": {
            "manifestPath": "/tmp/native-target/.workflowprogram/managed-files.json",
            "reportPath": "/tmp/native-run/outputs/managed-change-result.json",
            "entries": [
                {
                    "path": ".claude/workflows/probe.js",
                    "action": "create",
                    "sha256": "sha256:abc123",
                }
            ],
        },
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
        ("invalid-undeclared-api.js", "UNDECLARED_NATIVE_API"),
        ("invalid-undeclared-identifier.js", "UNDECLARED_IDENTIFIER"),
        ("invalid-agent-skills-option.js", "UNSUPPORTED_AGENT_OPTION"),
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
return { status: 'PASS', runId: args?.runId || '' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_allows_forbidden_api_words_inside_template_prompt(tmp_path: Path) -> None:
    script = tmp_path / "template-prompt-word.js"
    script.write_text(
        """export const meta = {
  name: 'template-prompt-word',
  description: 'Template prompt words are not executable APIs.',
  phases: [{ title: 'Probe' }],
}

const context = 'docs'
phase('Probe')
await agent(`Review this ${context} and mention require() only as text.`)
return { status: 'PASS', runId: args?.runId || '' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_rejects_forbidden_api_inside_template_expression(tmp_path: Path) -> None:
    script = tmp_path / "template-expression-api.js"
    script.write_text(
        """export const meta = {
  name: 'template-expression-api',
  description: 'Template expressions execute and must be checked.',
  phases: [{ title: 'Probe' }],
}

const unsafe = `${require('fs')}`
phase('Probe')
return { status: unsafe ? 'PASS' : 'BLOCKED', runId: args?.runId || '' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert "FORBIDDEN_API" in {item["rule"] for item in payload["errors"]}


def test_validator_rejects_duplicate_meta_export(tmp_path: Path) -> None:
    script = tmp_path / "duplicate-meta.js"
    script.write_text(
        """export const meta = {
  name: 'duplicate-meta',
  description: 'Duplicate meta must fail.',
  phases: [{ title: 'Probe' }],
}

export const meta = {
  name: 'second-meta',
  description: 'This must not be accepted.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
return { status: 'PASS', runId: args?.runId || '' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert "DUPLICATE_META_EXPORT" in {item["rule"] for item in payload["errors"]}
    assert "MODULE_PARSE_FAILED" in {item["rule"] for item in payload["errors"]}


def test_validator_rejects_non_async_await_inside_nested_function(tmp_path: Path) -> None:
    script = tmp_path / "non-async-await.js"
    script.write_text(
        """export const meta = {
  name: 'non-async-await',
  description: 'Nested non-async await must fail module parse.',
  phases: [{ title: 'Probe' }],
}

function probe() {
  await agent('This await is not inside an async function.')
}

phase('Probe')
return { status: 'PASS', runId: args?.runId || '' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert "MODULE_PARSE_FAILED" in {item["rule"] for item in payload["errors"]}


def test_validator_rejects_pipeline_without_items_argument(tmp_path: Path) -> None:
    script = tmp_path / "pipeline-no-items.js"
    script.write_text(
        """export const meta = {
  name: 'pipeline-no-items',
  description: 'Pipeline must start with items.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
await pipeline(async item => item)
return { status: 'PASS', runId: args?.runId || '' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert "PIPELINE_SHAPE_INVALID" in {item["rule"] for item in payload["errors"]}


def test_validator_allows_declared_run_id(tmp_path: Path) -> None:
    """A visibly declared runId may be used in a return envelope."""
    script = tmp_path / "declared-runid.js"
    script.write_text(
        """export const meta = {
  name: 'declared-runid',
  description: 'runId is declared from args before use.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const runId = args?.runId || 'run-001'
return { status: 'PASS', runId }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_allows_schema_property_named_skills(tmp_path: Path) -> None:
    script = tmp_path / "schema-skills.js"
    script.write_text(
        """export const meta = {
  name: 'schema-skills',
  description: 'Schema fields named skills are not Agent options.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const probe = await agent('Return a skills field.', {
  label: 'probe',
  schema: {
    type: 'object',
    properties: {
      skills: { type: 'array', items: { type: 'string' } },
      status: { type: 'string' },
    },
    required: ['skills', 'status'],
  },
})
return { status: probe.status }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_allows_agent_isolation_option(tmp_path: Path) -> None:
    script = tmp_path / "agent-isolation.js"
    script.write_text(
        """export const meta = {
  name: 'agent-isolation',
  description: 'Agent isolation is a supported Native Workflow JS option.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const probe = await agent('Return PASS.', {
  label: 'probe',
  isolation: 'worktree',
  schema: {
    type: 'object',
    properties: {
      status: { type: 'string' },
    },
    required: ['status'],
  },
})
return { status: probe.status }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_allows_run_id_property_key_without_local_declaration(tmp_path: Path) -> None:
    """Object keys and args member access are not bare identifier references."""
    script = tmp_path / "runid-property.js"
    script.write_text(
        """export const meta = {
  name: 'runid-property',
  description: 'runId is only an object key and args member.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
return { status: 'PASS', runId: args?.runId || '' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_allows_undeclared_api_in_comment(tmp_path: Path) -> None:
    """Undeclared tool names appearing only in comments must not be flagged."""
    script = tmp_path / "comment-mention.js"
    script.write_text(
        """export const meta = {
  name: 'comment-mention',
  description: 'Undeclared tool names in comments are safe.',
  phases: [{ title: 'Probe' }],
}

// TODO: consider using Bash or Read in agent prompts, not directly
phase('Probe')
return { status: 'PASS', runId: args?.runId || '' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_allows_undeclared_api_as_property_access(tmp_path: Path) -> None:
    """obj.Bash property access (not a call) must not trigger UNDECLARED_NATIVE_API."""
    script = tmp_path / "prop-access.js"
    script.write_text(
        """export const meta = {
  name: 'prop-access',
  description: 'Property access to tool names is not a direct call.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const toolNames = { Bash: true, Read: false }
const hasBash = toolNames.Bash
return { status: hasBash ? 'PASS' : 'BLOCKED' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_allows_undeclared_api_call_after_object_access(tmp_path: Path) -> None:
    """A locally declared object method is not a direct host tool call."""
    script = tmp_path / "obj-call.js"
    script.write_text(
        """export const meta = {
  name: 'obj-call',
  description: 'obj.Bash() is still a Bash() call pattern.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const obj = { Bash: () => 'PASS' }
const result = obj.Bash()
return { status: result }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_allows_locally_declared_bash_function(tmp_path: Path) -> None:
    """A local declaration named Bash must not be mistaken for a host tool."""
    script = tmp_path / "local-bash.js"
    script.write_text(
        """export const meta = {
  name: 'local-bash',
  description: 'Bash is a local helper in this contrived fixture.',
  phases: [{ title: 'Probe' }],
}

const Bash = value => value
phase('Probe')
return { status: Bash('PASS') }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.parametrize(
    "tool_name",
    [
        "EnterWorktree",
        "ExitWorktree",
        "TaskCreate",
        "TaskGet",
        "TaskList",
        "TaskOutput",
        "TaskStop",
        "TaskUpdate",
    ],
)
def test_validator_rejects_additional_host_tool_calls(tmp_path: Path, tool_name: str) -> None:
    """All known Claude Code host tools must fail when called as JS globals."""

    script = tmp_path / f"{tool_name}.js"
    script.write_text(
        f"""export const meta = {{
  name: 'invalid-{tool_name.lower()}',
  description: 'Host tools are not Native Workflow JS globals.',
  phases: [{{ title: 'Probe' }}],
}}

phase('Probe')
{tool_name}({{}})
return {{ status: 'PASS' }}
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")

    assert completed.returncode == 1
    payload = load_json(completed)
    assert "UNDECLARED_NATIVE_API" in {item["rule"] for item in payload["errors"]}


def test_validator_rejects_bare_host_tool_reference(tmp_path: Path) -> None:
    """A bare host tool identifier is also an undeclared runtime reference."""

    script = tmp_path / "bare-host-tool.js"
    script.write_text(
        """export const meta = {
  name: 'bare-host-tool',
  description: 'Bare host tool references are invalid.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const tool = Bash
return { status: tool ? 'PASS' : 'BLOCKED' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")

    assert completed.returncode == 1
    payload = load_json(completed)
    assert "UNDECLARED_NATIVE_API" in {item["rule"] for item in payload["errors"]}


@pytest.mark.parametrize(
    "expression",
    [
        "eval('Bash(\"pwd\")')",
        "new Function('Bash(\"pwd\")')()",
        "const indirectEval = eval\nindirectEval('Bash(\"pwd\")')",
        "const DynamicFunction = Function\nDynamicFunction('Bash(\"pwd\")')()",
    ],
)
def test_validator_rejects_dynamic_code_execution(tmp_path: Path, expression: str) -> None:
    """Dynamic code execution can hide unsupported runtime APIs."""

    script = tmp_path / "dynamic-code.js"
    script.write_text(
        f"""export const meta = {{
  name: 'invalid-eval',
  description: 'Dynamic evaluation is not allowed.',
  phases: [{{ title: 'Probe' }}],
}}

phase('Probe')
{expression}
return {{ status: 'PASS' }}
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")

    assert completed.returncode == 1
    payload = load_json(completed)
    assert "FORBIDDEN_API" in {item["rule"] for item in payload["errors"]}


def test_validator_allows_forbidden_api_names_in_comments(tmp_path: Path) -> None:
    """Documentation comments must not be treated as executable dynamic code."""

    script = tmp_path / "commented-dynamic-code.js"
    script.write_text(
        """export const meta = {
  name: 'commented-dynamic-code',
  description: 'Comments may explain rejected APIs.',
  phases: [{ title: 'Probe' }],
}

// Do not use eval() or Function() in Native Workflow JS.
phase('Probe')
return { status: 'PASS' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")

    assert completed.returncode == 0


def test_validator_ignores_phase_calls_in_comments(tmp_path: Path) -> None:
    """Phase alignment must ignore commented phase-call examples in body text."""

    script = tmp_path / "phase-comments.js"
    script.write_text(
        """export const meta = {
  name: 'phase-comments',
  description: 'Comments may include example phase names.',
  phases: [{ title: 'Probe' }],
}

// phase('BodyComment')
phase('Probe')
return { status: 'PASS' }
""",
        encoding="utf-8",
    )

    completed = run_script(VALIDATOR, "--script", str(script), "--json")

    assert completed.returncode == 0


def authoring_spec_payload(
    *,
    name: str = "generated-probe",
    description: str = "Generate a minimal native workflow probe.",
    body: str = "phase('Probe')\n\nreturn { status: 'PASS' }\n",
    supporting_assets: list[dict[str, str]] | None = None,
    asset_disposition: list[dict[str, str]] | None = None,
    task_model_policy: dict | None = None,
) -> dict:
    payload = {
        "name": name,
        "description": description,
        "phases": [{"title": "Probe", "detail": "Return PASS."}],
        "body": body,
        "supporting_assets": supporting_assets or [],
        "asset_disposition": asset_disposition or [],
    }
    if task_model_policy is not None:
        payload["task_model_policy"] = task_model_policy
    return payload


def write_authoring_spec(
    path: Path,
    *,
    name: str = "generated-probe",
    description: str = "Generate a minimal native workflow probe.",
    body: str = "phase('Probe')\n\nreturn { status: 'PASS' }\n",
    supporting_assets: list[dict[str, str]] | None = None,
    asset_disposition: list[dict[str, str]] | None = None,
    task_model_policy: dict | None = None,
) -> None:
    payload = authoring_spec_payload(
        name=name,
        description=description,
        body=body,
        supporting_assets=supporting_assets,
        asset_disposition=asset_disposition,
        task_model_policy=task_model_policy,
    )
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
            "if (result.status !== 'PASS') return { status: 'BLOCKED', runId: args?.runId || '' }\n"
            "return { status: 'PASS', runId: args?.runId || '' }\n"
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
            "return { status: first.status === 'PASS' && second.status === 'PASS' ? 'PASS' : 'BLOCKED', runId: args?.runId || '' }\n"
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
    write_authoring_spec(spec, body="phase('Wrong')\n\nreturn { status: 'PASS', runId: args?.runId || '' }\n")

    completed = run_generator(spec, target, run_root, "--apply", "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "PHASE_ALIGNMENT" in {item["rule"] for item in payload["errors"]}
    assert not (target / ".claude" / "workflows" / "generated-probe.js").exists()


def test_generator_rejects_full_js_body_with_meta_header(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(
        spec,
        body=(
            "export const meta = {\n"
            "  name: 'generated-probe',\n"
            "  description: 'A full JS body must be rejected.',\n"
            "  phases: [{ title: 'Probe' }],\n"
            "}\n\n"
            "phase('Probe')\n"
            "return { status: 'PASS', runId: args?.runId || '' }\n"
        ),
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert payload["errors"][0]["rule"] == "SPEC_INVALID"
    assert "AUTHORING_BODY_CONTAINS_META" in payload["errors"][0]["message"]
    assert not (run_root / "outputs" / "candidate").exists()


def test_generator_rejects_require_inside_template_expression_body(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(
        spec,
        body=(
            "phase('Probe')\n"
            "const unsafe = `${require('fs')}`\n"
            "return { status: unsafe ? 'PASS' : 'BLOCKED', runId: args?.runId || '' }\n"
        ),
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert payload["errors"][0]["rule"] == "SPEC_INVALID"
    assert "AUTHORING_BODY_CONTAINS_REQUIRE" in payload["errors"][0]["message"]
    assert not (run_root / "outputs" / "candidate").exists()


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


def test_generator_rejects_invalid_asset_disposition(tmp_path: Path) -> None:
    """asset_disposition with an unknown action must be rejected."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(
        spec,
        asset_disposition=[
            {
                "path": ".claude/scripts/probe.py",
                "reason": "Must be rejected for bad action.",
                "action": "delete-all",
            },
        ],
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "disposition" in str(payload["errors"]).lower()


def test_generator_rejects_task_model_policy_without_agent_task_models(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(spec, task_model_policy={"description": "This is not a supported mapping."})

    completed = run_generator(spec, target, run_root, "--json")

    assert completed.returncode == 1
    assert "agent_task_models" in str(load_json(completed)["errors"])


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
    operation: str = "create",
    design_evidence: object = _UNSET,
    review_evidence: object = _UNSET,
    authoring_spec: object = _UNSET,
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
            "operation": operation,
            "lenses": DEVELOP_LENSES,
        },
    }
    if generation_request is not _UNSET:
        payload["generationRequest"] = generation_request
    else:
        payload["generationRequest"] = {
            "targetRoot": str(target_root),
            "runRoot": str(run_root),
            "operation": operation,
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
            "assetDisposition": [],
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
            "assetDispositionReviewed": True,
        }
    if authoring_spec is not _UNSET:
        payload["authoringSpec"] = authoring_spec
    else:
        payload["authoringSpec"] = authoring_spec_payload()
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


def test_generator_handoff_update_requires_asset_disposition(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, operation="update")

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")

    assert completed.returncode == 1
    assert "asset_disposition" in str(load_json(completed)["errors"])


def test_generator_handoff_update_allows_retain_without_supporting_assets(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    disposition = [
        {
            "path": ".claude/commands/existing.md",
            "action": "retain",
            "reason": "The existing compatibility entry remains valid.",
        }
    ]
    design_disposition = [
        {
            "path": ".claude/commands/existing.md",
            "action": "retain",
            "reason": "The existing compatibility entry remains valid.",
        }
    ]
    write_authoring_spec(spec, asset_disposition=disposition)
    design = pass_design_evidence()
    design["assetDisposition"] = design_disposition
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        operation="update",
        design_evidence=design,
        authoring_spec=authoring_spec_payload(asset_disposition=disposition),
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_generator_handoff_update_requires_declared_generated_supporting_asset(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    disposition = [
        {
            "path": ".claude/commands/stride-audit.md",
            "action": "update",
            "reason": "The command must route to the Native Workflow.",
            "supporting_asset_path": ".claude/commands/stride-audit.md",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/commands/stride-audit.md",
            "action": "update",
            "reason": "The command must route to the Native Workflow.",
            "supportingAssetPath": ".claude/commands/stride-audit.md",
        }
    ]
    write_authoring_spec(spec, asset_disposition=disposition)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        operation="update",
        design_evidence=design,
        authoring_spec=authoring_spec_payload(asset_disposition=disposition),
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")

    assert completed.returncode == 1
    assert "supporting_asset_path" in str(load_json(completed)["errors"])


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


def test_generator_handoff_blocks_missing_authoring_spec(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, authoring_spec=None)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "HANDOFF_AUTHORING_SPEC_MISSING" in {item["rule"] for item in payload["errors"]}
    assert not (run_root / "outputs" / "candidate").exists()


def test_generator_handoff_blocks_authoring_spec_mismatch_before_candidate(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_authoring_spec(spec)
    mismatched = authoring_spec_payload(body="phase('Probe')\n\nreturn { status: 'PASS', drift: true, runId: args?.runId || '' }\n")
    write_handoff_packet(handoff, target_root=target, run_root=run_root, authoring_spec=mismatched)

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "HANDOFF_AUTHORING_SPEC_MISMATCH" in {item["rule"] for item in payload["errors"]}
    assert not (run_root / "outputs" / "candidate").exists()


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
    bad_body = "phase('Wrong')\n\nreturn { status: 'PASS', runId: args?.runId || '' }\n"
    bad_authoring_spec = authoring_spec_payload(body=bad_body)
    write_authoring_spec(spec, body=bad_body)
    write_handoff_packet(handoff, target_root=target, run_root=run_root, authoring_spec=bad_authoring_spec)

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


def test_phase_boundary_contract_is_documented_and_prompted() -> None:
    decision_sentence = (
        "If completing this process changes whether the workflow continues, blocks, re-enters, "
        "asks the user, or performs side effects, it is a Phase candidate."
    )
    develop_source = DEVELOP_WORKFLOW.read_text(encoding="utf-8")
    reference = NATIVE_WORKFLOW_REFERENCE.read_text(encoding="utf-8")
    lld = NATIVE_WORKFLOW_LLD.read_text(encoding="utf-8")
    skill = LOWLEVEL_SKILL.read_text(encoding="utf-8")

    assert "const phaseBoundaryGuidance" in develop_source
    assert decision_sentence in develop_source
    assert decision_sentence in reference
    assert decision_sentence in lld
    assert "Phase boundary criteria" in skill
    assert "single prompt paragraph" in develop_source
    assert "same-gate parallel exploration" in develop_source
    assert "phase candidates only when purpose, handoff, gate, evidence, recovery" in develop_source


def test_existing_workflow_migration_examples_are_implementation_level() -> None:
    example_index = (LOWLEVEL_EXAMPLES / "README.md").read_text(encoding="utf-8")
    positive = (LOWLEVEL_EXAMPLES / "migrate-existing-workflow-positive.md").read_text(encoding="utf-8")
    negative = (LOWLEVEL_EXAMPLES / "migrate-existing-workflow-negative.md").read_text(encoding="utf-8")
    phase_positive = (LOWLEVEL_EXAMPLES / "phase-boundary-positive.md").read_text(encoding="utf-8")
    phase_negative = (LOWLEVEL_EXAMPLES / "phase-boundary-negative.md").read_text(encoding="utf-8")

    assert "implementation-level references" in example_index
    assert '"operation": "migrate"' in positive
    assert '"migrationTasks"' in positive
    assert '"trueBlockers": []' in positive
    assert ".claude/workflows/audit.js does not exist" in negative
    assert "incorrect result creates an exploration loop" in negative
    assert "READY_FOR_GENERATION" in phase_positive
    assert "Read Prompt" in phase_negative


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
    questions = [
        {
            "id": lens,
            "lens": lens,
            "question": f"What design fact is required for {lens}?",
            "reason": f"{lens} changes the workflow design.",
        }
        for lens in [
            "objectModel",
            "processModel",
            "decisionModel",
            "evidenceModel",
            "acceptanceModel",
            "boundaryModel",
        ]
    ]

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        payload,
        agent_results=[
            {
                "status": "NEEDS_USER_INPUT",
                "questions": questions,
                "lensCoverage": {
                    "purpose": {"status": "complete", "summary": "Goal exists."},
                    "objectModel": {"status": "missing", "summary": ""},
                },
                "openQuestions": [],
                "blockingIssues": [],
            }
        ],
    )

    assert execution["result"]["status"] == "NEEDS_USER_INPUT"
    assert execution["labels"] == ["workflowprogram-develop:clarify"]
    assert execution["agentTypes"] == ["workflowprogram-native-cn:requirement-clarification-lead"]
    assert execution["result"]["missingLenses"] == [
        "objectModel",
        "processModel",
        "decisionModel",
        "evidenceModel",
        "acceptanceModel",
        "boundaryModel",
    ]
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


def test_develop_native_workflow_ignores_resolved_open_question_objects() -> None:
    payload = develop_args(
        clarification={
            "lenses": DEVELOP_LENSES,
            "openQuestions": [
                {
                    "id": "agent-migration-policy",
                    "lens": "decisionModel",
                    "question": "Inline prompts or separate Agent files?",
                    "answer": "Workflow-local prompts are inline by default.",
                }
            ],
            "confirmedByUser": False,
        }
    )

    execution = execute_native_workflow(DEVELOP_WORKFLOW, payload)

    assert execution["result"]["status"] == "READY_FOR_CONFIRMATION"
    assert execution["labels"] == []


def test_develop_native_workflow_does_not_stringify_open_question_object() -> None:
    payload = develop_args(
        clarification={
            "lenses": DEVELOP_LENSES,
            "openQuestions": [
                {
                    "id": "missing-question-text",
                    "lens": "purpose",
                }
            ],
            "confirmedByUser": False,
        }
    )

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        payload,
        agent_results=[
            {
                "status": "NEEDS_USER_INPUT",
                "questions": [],
                "lensCoverage": {},
                "openQuestions": [],
                "blockingIssues": [],
            }
        ],
    )

    assert execution["result"]["status"] == "NEEDS_USER_INPUT"
    assert execution["result"]["questions"][0]["question"] == "Clarify unresolved open question missing-question-text."
    assert "[object Object]" not in json.dumps(execution["result"], ensure_ascii=False)


def test_develop_migrate_with_empty_clarification_proceeds_to_confirmation() -> None:
    """migrate with empty lenses and no open questions seeds migration defaults
    and proceeds to READY_FOR_CONFIRMATION without calling the clarification agent."""
    payload = develop_args(
        operation="migrate",
        clarification={
            "lenses": {},
            "openQuestions": [],
            "confirmedByUser": False,
        },
    )

    execution = execute_native_workflow(DEVELOP_WORKFLOW, payload)

    assert execution["result"]["status"] == "READY_FOR_CONFIRMATION"
    assert execution["result"]["nextAction"] == "REINVOKE_WITH_CONFIRMATION"
    # No clarification agent was invoked — the migration defaults filled all lenses
    assert execution["labels"] == []
    assert execution["agentTypes"] == []


def test_develop_migrate_with_partial_lenses_and_no_agent_call() -> None:
    """migrate with some lenses filled and some missing seeds only the missing ones,
    then proceeds to confirmation without calling the agent."""
    payload = develop_args(
        operation="migrate",
        clarification={
            "lenses": {
                "purpose": "Custom purpose for migration.",
            },
            "openQuestions": [],
            "confirmedByUser": False,
        },
    )

    execution = execute_native_workflow(DEVELOP_WORKFLOW, payload)

    assert execution["result"]["status"] == "READY_FOR_CONFIRMATION"
    assert execution["labels"] == []
    assert execution["agentTypes"] == []


def test_develop_migrate_with_open_questions_still_calls_clarification_agent() -> None:
    """migrate seeds missing lenses with defaults, but unresolved open questions
    still trigger the clarification agent."""
    payload = develop_args(
        operation="migrate",
        clarification={
            "lenses": {},
            "openQuestions": [
                {
                    "id": "migrate-source",
                    "lens": "objectModel",
                    "question": "Which existing workflow should be migrated?",
                }
            ],
            "confirmedByUser": False,
        },
    )

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        payload,
        agent_results=[
            {
                "status": "NEEDS_USER_INPUT",
                "questions": [
                    {
                        "id": "migrate-source",
                        "lens": "objectModel",
                        "question": "Which existing workflow should be migrated?",
                        "reason": "The migration source determines asset discovery scope.",
                    }
                ],
                "lensCoverage": {},
                "openQuestions": [],
                "blockingIssues": [],
            }
        ],
    )

    assert execution["result"]["status"] == "NEEDS_USER_INPUT"
    assert execution["labels"] == ["workflowprogram-develop:clarify"]
    assert execution["agentTypes"] == ["workflowprogram-native-cn:requirement-clarification-lead"]
    # Only the open question is asked - no missing lens questions
    assert len(execution["result"]["questions"]) == 1
    assert execution["result"]["questions"][0]["id"] == "migrate-source"


def test_develop_create_still_asks_for_missing_lenses() -> None:
    """create with empty lenses still triggers the clarification agent
    (regression guard - migration defaults must not leak into create)."""
    payload = develop_args(
        operation="create",
        clarification={
            "lenses": {},
            "openQuestions": [],
            "confirmedByUser": False,
        },
    )

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        payload,
        agent_results=[
            {
                "status": "NEEDS_USER_INPUT",
                "questions": [
                    {
                        "id": lens_id,
                        "lens": lens_id,
                        "question": f"What design fact is required for {lens_id}?",
                        "reason": f"{lens_id} changes the workflow design.",
                    }
                    for lens_id in [
                        "purpose",
                        "objectModel",
                        "processModel",
                        "decisionModel",
                        "evidenceModel",
                        "acceptanceModel",
                        "boundaryModel",
                    ]
                ],
                "lensCoverage": {},
                "openQuestions": [],
                "blockingIssues": [],
            }
        ],
    )

    assert execution["result"]["status"] == "NEEDS_USER_INPUT"
    assert execution["labels"] == ["workflowprogram-develop:clarify"]
    assert execution["agentTypes"] == ["workflowprogram-native-cn:requirement-clarification-lead"]
    # All 7 lenses are missing - the agent should ask about them
    assert len(execution["result"]["questions"]) == 7


def test_native_develop_skill_documents_canonical_structured_invocation() -> None:
    """The leaf skill should steer the foreground model toward structured args,
    not string args or dotted-key examples."""
    text = NATIVE_DEVELOP_SKILL.read_text(encoding="utf-8")

    assert "## Step 2: Launch Or Reinvoke Product JS" in text
    assert "### Canonical Invocation" in text
    assert 'scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-develop.js"' in text
    assert "migrationDecisions" in text
    assert 'args: "operation=migrate clarification.confirmedByUser=true decisions.flatOutputDir=outputs/stride-audit"' in text
    assert "dotted keys can" in text
    assert "READY_FOR_CONFIRMATION" in text
    assert "workflowprogram-develop-*.js" in text


def test_develop_migrate_exploration_prompt_treats_migration_decisions_as_settled() -> None:
    """Migration prompts should teach exploration agents by example that resolved
    decisions are not blockers and no-op blocker text belongs in an empty array."""
    exploration = {
        "status": "BLOCKED",
        "findings": [],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": ["No usable behavioral source of truth exists."],
        "userDecisions": [],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            operation="migrate",
            migrationDecisions={
                "keepVerifyValidationPocSeparate": True,
                "flatOutputDir": "outputs/stride-audit",
            },
        ),
        agent_results=[exploration, exploration],
    )

    prompt = execution["prompts"][0]
    assert "Resolved migration decisions:" in prompt
    assert '"flatOutputDir":"outputs/stride-audit"' in prompt
    assert "Do not return them again in userDecisions" in prompt
    assert "Do not repeat them in userDecisions" in prompt
    assert "userDecisions is only for external user decisions" in prompt
    assert "Do not put Design work items in userDecisions" in prompt
    assert "removeDotAgentsDir means only target-root .agents/ and .agentos/" in prompt
    assert "return trueBlockers as an empty array" in prompt
    assert "No true blockers identified" in prompt


def test_develop_native_workflow_blocks_review_required_revisions() -> None:
    review = {
        **pass_review_evidence(),
        "requiredRevisions": ["Close the asset disposition decision before generation."],
    }
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            designEvidence=pass_design_evidence(),
            reviewEvidence=review,
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN_REVIEW"
    assert execution["result"]["blockingIssues"] == [
        "Required revision not closed: Close the asset disposition decision before generation."
    ]


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
        agent_results=[exploration, exploration, pass_design_evidence(), pass_review_evidence(), pass_authoring_evidence()],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["nextAction"] == "RUN_CONTROLLED_GENERATION"
    assert execution["result"]["authoringSpec"] == authoring_spec_payload()
    assert execution["result"]["generationHandoff"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["generationHandoff"]["workflow"] == "workflowprogram-develop"
    assert execution["result"]["generationHandoff"]["authoringSpec"] == authoring_spec_payload()
    assert execution["result"]["continuation"]["script"] == "workflowprogram-continue.py"
    assert execution["result"]["continuation"]["nextAction"] == "RUN_CONTROLLED_GENERATION"
    assert execution["labels"][-1] == "workflowprogram-develop:author"
    assert execution["phases"] == ["Intake", "Clarify", "Confirm", "Design", "Review", "Author", "Generate"]


def test_develop_migrate_continues_when_exploration_reports_only_migration_tasks() -> None:
    exploration = {
        "status": "BLOCKED",
        "findings": ["The command file is the current source of truth."],
        "constraints": ["Do not write target files directly."],
        "migrationTasks": [
            "Generate the missing .claude/workflows/generated-probe.js target workflow.",
            "Archive retired .workflowprogram/runtime assets.",
            "Update managed-files.json through controlled apply.",
        ],
        "trueBlockers": [],
        "userDecisions": [],
        "sourceOfTruth": [".claude/commands/generated-probe.md"],
        "assetDispositionHints": [
            {
                "path": ".claude/workflows/generated-probe.js",
                "action": "generate",
                "reason": "Missing target workflow is the migration deliverable.",
            }
        ],
        "blockingIssues": [
            ".claude/workflows/generated-probe.js does not exist.",
            "No existing Native Workflow JS reference exists.",
        ],
    }
    supporting_assets = [
        {
            "kind": "workflow",
            "path": ".claude/workflows/generated-probe.js",
            "content": "phase('Probe')\nreturn { status: 'PASS' }\n",
            "reason": "Generated Native Workflow JS target.",
        }
    ]
    asset_disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow is the migration deliverable.",
            "supportingAssetPath": ".claude/workflows/generated-probe.js",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = asset_disposition
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            supporting_assets=supporting_assets,
            asset_disposition=asset_disposition,
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[exploration, exploration, design, pass_review_evidence(), authoring],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert "workflowprogram-develop:design" in execution["labels"]
    assert execution["labels"][-1] == "workflowprogram-develop:author"


def test_develop_migrate_does_not_block_resolved_asset_disposition_questions() -> None:
    """Exploration may echo asset-disposition confirmations, but migrate design
    should continue when migrationDecisions or assetDispositionHints already
    settle them."""
    exploration = {
        "status": "PASS",
        "findings": ["Existing FreeSTRIDE assets are readable."],
        "constraints": ["Do not write target files directly."],
        "migrationTasks": [
            "Remove legacy .agents/ after controlled apply.",
            "Merge stride-ui-verifier behavior into the report phase.",
        ],
        "trueBlockers": [],
        "userDecisions": [
            "How should orphan .agents/skills/stride-input-parser/SKILL.md be handled?",
            "How should .claude/agents/stride-ui-verifier.md be handled if uiVerifierMergedIntoReport=true?",
        ],
        "sourceOfTruth": [".claude/commands/stride-audit.md"],
        "assetDispositionHints": [
            {
                "path": ".agents/",
                "action": "remove",
                "reason": "removeDotAgentsDir=true settles the legacy duplicate directory.",
            },
            {
                "path": ".claude/agents/stride-ui-verifier.md",
                "action": "archive",
                "reason": "uiVerifierMergedIntoReport=true merges behavior into report.",
                "supportingAssetPath": ".workflowprogram/archive/stride-ui-verifier.md",
            },
        ],
        "blockingIssues": [],
    }
    supporting_assets = [
        {
            "kind": "workflow",
            "path": ".claude/workflows/generated-probe.js",
            "content": "phase('Probe')\nreturn { status: 'PASS' }\n",
            "reason": "Generated Native Workflow JS target.",
        },
        {
            "kind": "archive",
            "path": ".workflowprogram/archive/stride-ui-verifier.md",
            "content": "# Archived stride-ui-verifier\n",
            "reason": "Archive merged agent behavior.",
        },
    ]
    asset_disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow is the migration deliverable.",
            "supportingAssetPath": ".claude/workflows/generated-probe.js",
        },
        {
            "path": ".agents/",
            "action": "remove",
            "reason": "removeDotAgentsDir=true settles the legacy duplicate directory.",
        },
        {
            "path": ".claude/agents/stride-ui-verifier.md",
            "action": "archive",
            "reason": "uiVerifierMergedIntoReport=true merges behavior into report.",
            "supportingAssetPath": ".workflowprogram/archive/stride-ui-verifier.md",
        },
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = asset_disposition
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            supporting_assets=supporting_assets,
            asset_disposition=asset_disposition,
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            operation="migrate",
            migrationDecisions={
                "removeDotAgentsDir": True,
                "uiVerifierMergedIntoReport": True,
            },
        ),
        agent_results=[exploration, exploration, design, pass_review_evidence(), authoring],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert "User decision required" not in json.dumps(execution["result"])
    assert execution["labels"][-1] == "workflowprogram-develop:author"


def test_develop_migrate_still_blocks_uncovered_user_decisions() -> None:
    exploration = {
        "status": "PASS",
        "findings": ["The target project is readable."],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [
            "Should managed apply be automatic or require a manual approval branch?"
        ],
        "sourceOfTruth": [".claude/commands/generated-probe.md"],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[exploration, exploration],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert execution["result"]["blockingIssues"] == [
        "User decision required: Should managed apply be automatic or require a manual approval branch?",
        "User decision required: Should managed apply be automatic or require a manual approval branch?",
    ]
    assert execution["labels"] == [
        "workflowprogram-develop:explore:target-context",
        "workflowprogram-develop:explore:runtime-boundaries",
    ]


def test_develop_migrate_does_not_block_internal_design_work_items() -> None:
    exploration = {
        "status": "PASS",
        "findings": ["The target has enough source-of-truth assets for migration."],
        "constraints": ["Use existing command, agent, skill, and config behavior."],
        "migrationTasks": ["Design the v0.6 phase contracts before authoring."],
        "trueBlockers": [],
        "userDecisions": [
            "The exact 12-phase topology needs to be designed during Design.",
            "The 12-stage gate-to-phase mapping must be determined during Design.",
            "The phase output intermediate schema set must be determined during Design.",
            "The Python script call strategy via Bash tool needs to be defined during Design.",
        ],
        "sourceOfTruth": [".claude/commands/stride-audit.md"],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }

    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow is the migration deliverable.",
            "supportingAssetPath": ".claude/workflows/generated-probe.js",
        }
    ]
    supporting_assets = [
        {
            "kind": "workflow",
            "path": ".claude/workflows/generated-probe.js",
            "content": "phase('Probe')\nreturn { status: 'PASS' }\n",
            "reason": "Generated Native Workflow JS target.",
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            supporting_assets=supporting_assets,
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            operation="migrate",
            migrationDecisions={
                "phaseCount": 12,
                "pythonScriptsViaBashTool": True,
                "stageGatesViaJSFlowControl": True,
            },
        ),
        agent_results=[exploration, exploration, design, pass_review_evidence(), authoring],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert "User decision required" not in json.dumps(execution["result"])
    assert execution["labels"][-1] == "workflowprogram-develop:author"


def test_develop_migrate_blocks_whole_claude_registry_removal() -> None:
    exploration = {
        "status": "PASS",
        "findings": ["The target has a registered .claude agent registry."],
        "constraints": ["Remove only duplicate root .agents/ assets."],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [],
        "sourceOfTruth": [".claude/settings.json"],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/agents/",
            "action": "remove",
            "reason": "Incorrectly interpreted removeDotAgentsDir.",
        }
    ]

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate", migrationDecisions={"removeDotAgentsDir": True}),
        agent_results=[exploration, exploration, design],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert execution["result"]["blockingIssues"] == [
        "Invalid assetDisposition: .claude/agents/ cannot be removed by removeDotAgentsDir; retain/reuse .claude registry assets or disposition individual files unless removeClaudeAgentsDir=true."
    ]
    assert execution["labels"] == [
        "workflowprogram-develop:explore:target-context",
        "workflowprogram-develop:explore:runtime-boundaries",
        "workflowprogram-develop:design",
    ]


def test_develop_migrate_blocks_true_exploration_blockers() -> None:
    exploration = {
        "status": "BLOCKED",
        "findings": [],
        "constraints": [],
        "migrationTasks": ["Generate .claude/workflows/generated-probe.js."],
        "trueBlockers": ["No usable behavioral source of truth exists."],
        "userDecisions": [],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [".claude/workflows/generated-probe.js does not exist."],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[exploration, exploration],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert execution["result"]["blockingIssues"] == [
        "No usable behavioral source of truth exists.",
        "No usable behavioral source of truth exists.",
    ]
    assert execution["labels"] == [
        "workflowprogram-develop:explore:target-context",
        "workflowprogram-develop:explore:runtime-boundaries",
    ]


def test_develop_create_still_blocks_failed_exploration_status() -> None:
    exploration = {
        "status": "BLOCKED",
        "findings": [],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": ["Target cannot be read."],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="create"),
        agent_results=[exploration, exploration],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert execution["result"]["blockingIssues"] == ["Target cannot be read.", "Target cannot be read."]


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
        agent_results=[exploration, exploration, pass_design_evidence(), pass_review_evidence(), pass_authoring_evidence()],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["targetRoot"] == "/tmp/native-target"
    assert execution["result"]["runRoot"] == "/tmp/native-run"
    assert execution["result"]["authoringSpec"] == authoring_spec_payload()
    assert execution["result"]["generationHandoff"]["targetRoot"] == "/tmp/native-target"
    assert execution["result"]["generationHandoff"]["runRoot"] == "/tmp/native-run"
    assert execution["result"]["generationHandoff"]["generationRequest"]["targetRoot"] == "/tmp/native-target"
    assert execution["result"]["generationHandoff"]["generationRequest"]["runRoot"] == "/tmp/native-run"


def test_develop_native_workflow_blocks_failed_authoring_evidence() -> None:
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            designEvidence=pass_design_evidence(),
            reviewEvidence=pass_review_evidence(),
            authoringEvidence={"status": "BLOCKED", "blockingIssues": ["invalid JS body"]},
        ),
    )

    assert execution["result"]["status"] == "BLOCKED_GENERATION"
    assert execution["result"]["blockingIssues"] == ["invalid JS body"]


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
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": {
                    **pass_validation_evidence(),
                    "workflowScriptPath": "/tmp/native-run/outputs/candidate/.claude/workflows/other.js",
                },
            },
            "BLOCKED_VALIDATION",
        ),
        (
            {
                "generationEvidence": {
                    **pass_generation_evidence(),
                    "evidence": ["x"],
                },
            },
            "BLOCKED_GENERATION",
        ),
        # Smoke evidence must come from evaluator PASS output
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": pass_validation_evidence(),
                "smokeEvidence": {
                    "status": "PASS",
                    "candidateHash": "sha256:probe",
                    "evidence": ["/tmp/raw-transcript.jsonl"],
                    "blockingIssues": [],
                },
            },
            "BLOCKED_SMOKE",
        ),
        # A smoke report cannot prove both PASS and BLOCKED completion
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": pass_validation_evidence(),
                "smokeEvidence": {
                    **pass_smoke_evidence(),
                    "smokeReports": [
                        {
                            **pass_smoke_evidence()["smokeReports"][0],
                            "evidence": {
                                **pass_smoke_evidence()["smokeReports"][0]["evidence"],
                                "completed_blocked": True,
                            },
                        }
                    ],
                },
            },
            "BLOCKED_SMOKE",
        ),
        # Apply evidence must have a structured manifest, not a path string
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": pass_validation_evidence(),
                "smokeEvidence": pass_smoke_evidence(),
                "applyApproved": True,
                "applyEvidence": {
                    "status": "PASS",
                    "candidateHash": "sha256:probe",
                    "applyManifest": "/tmp/native-run/outputs/stages/native-workflow-apply-manifest.json",
                    "evidence": ["/tmp/apply.json"],
                    "blockingIssues": [],
                },
            },
            "BLOCKED_CONFLICT",
        ),
        # Apply evidence must be bound to the current target root
        (
            {
                "generationEvidence": pass_generation_evidence(),
                "validationEvidence": pass_validation_evidence(),
                "smokeEvidence": pass_smoke_evidence(),
                "applyApproved": True,
                "applyEvidence": {
                    **pass_apply_evidence(),
                    "targetRoot": "/tmp/other-target",
                },
            },
            "BLOCKED_CONFLICT",
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
            authoringSpec=authoring_spec_payload(),
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
            authoringSpec=authoring_spec_payload(),
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
            authoringSpec=authoring_spec_payload(),
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
            authoringSpec=authoring_spec_payload(),
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


# ── Template / phase_contracts authoring tests ────────────────────────

TEMPLATE_AUTHORING_BASE: dict = {
    "name": "template-probe",
    "description": "Template-based minimal workflow probe.",
    "phases": [{"title": "Probe", "detail": "Return PASS."}],
    "template": "sequential-agent-workflow-v1",
    "phase_contracts": [
        {
            "phase": "Probe",
            "detail": "Return PASS.",
            "label": "template-probe:probe",
            "prompt": "Probe the request and return PASS.",
            "schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["PASS"]},
                },
                "required": ["status"],
            },
        }
    ],
    "supporting_assets": [],
    "asset_disposition": [],
}


def write_template_spec(
    path: Path,
    *,
    name: str = "template-probe",
    description: str = "Template-based minimal workflow probe.",
    phases: list[dict[str, str]] | None = None,
    template: str | None = "sequential-agent-workflow-v1",
    phase_contracts: list[dict[str, object]] | None = _UNSET,
    body: str | None = None,
    supporting_assets: list[dict[str, str]] | None = None,
    asset_disposition: list[dict[str, str]] | None = None,
    task_model_policy: dict | None = None,
) -> None:
    # When template is provided and phase_contracts is not explicitly set,
    # default to the TEMPLATE_AUTHORING_BASE contracts.
    resolved_contracts = phase_contracts
    if resolved_contracts is _UNSET:
        resolved_contracts = TEMPLATE_AUTHORING_BASE["phase_contracts"] if template else None
    payload: dict[str, object] = {
        "name": name,
        "description": description,
        "phases": phases if phases is not None else [{"title": "Probe", "detail": "Return PASS."}],
    }
    if template is not None:
        payload["template"] = template
    if resolved_contracts is not None:
        payload["phase_contracts"] = resolved_contracts
    if body is not None:
        payload["body"] = body
    if supporting_assets is not None:
        payload["supporting_assets"] = supporting_assets
    else:
        payload["supporting_assets"] = []
    if asset_disposition is not None:
        payload["asset_disposition"] = asset_disposition
    else:
        payload["asset_disposition"] = []
    if task_model_policy is not None:
        payload["task_model_policy"] = task_model_policy
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_template_authoring_spec_generates_valid_workflow(tmp_path: Path) -> None:
    """Template + phase_contracts should generate a valid Native Workflow JS."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_template_spec(spec)

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "template-probe.js"
    assert candidate.exists()
    content = candidate.read_text(encoding="utf-8")
    assert "export const meta" in content
    assert "phase('Probe')" in content
    assert "await agent(" in content
    assert "status: 'PASS'" in content


def test_template_authoring_spec_escapes_js_string_literals(tmp_path: Path) -> None:
    """Template rendering must escape single-quoted JS literals."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Owner's Review",
            "label": "template-probe:owner-review",
            "prompt": "Review the owner boundary.",
            "schema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
            "blockWhen": "result.status !== 'PASS'",
            "blockStatus": "BLOCKED_OWNER'S_REVIEW",
            "blockMessage": "Owner review blocked.",
            "nextAction": "FIX_OWNER'S_REVIEW",
        }
    ]
    write_template_spec(
        spec,
        phases=[{"title": "Owner's Review"}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "template-probe.js"
    content = candidate.read_text(encoding="utf-8")
    assert "phase('Owner\\'s Review')" in content
    assert "status: 'BLOCKED_OWNER\\'S_REVIEW'" in content
    assert "nextAction: 'FIX_OWNER\\'S_REVIEW'" in content


def test_template_authoring_spec_old_body_still_works(tmp_path: Path) -> None:
    """Old body-based authoring spec must still generate successfully (backward compat)."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(spec, body="phase('Probe')\n\nreturn { status: 'PASS' }\n")

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "generated-probe.js"
    assert candidate.exists()
    content = candidate.read_text(encoding="utf-8")
    assert "phase('Probe')" in content
    assert "return { status: 'PASS' }" in content


def test_template_authoring_spec_missing_body_and_template_fails(tmp_path: Path) -> None:
    """Spec with neither body nor template+phase_contracts must be rejected."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_template_spec(
        spec,
        template=None,
        phase_contracts=None,
        body=None,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "body" in str(payload["errors"]).lower() or "template" in str(payload["errors"]).lower()


def test_template_authoring_spec_body_and_template_both_provided_fails(tmp_path: Path) -> None:
    """Spec with both body and template+phase_contracts must be rejected."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    payload = {
        **TEMPLATE_AUTHORING_BASE,
        "body": "phase('Probe')\n\nreturn { status: 'PASS' }\n",
    }
    spec.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_template_unknown_template_name_fails(tmp_path: Path) -> None:
    """Unknown template name must be rejected."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_template_spec(spec, template="nonexistent-template-v99")

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_template_phase_contracts_empty_array_fails(tmp_path: Path) -> None:
    """Empty phase_contracts must be rejected."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_template_spec(spec, phase_contracts=[])

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1


def test_template_phase_contracts_missing_required_field_fails(tmp_path: Path) -> None:
    """Each phase_contract must have phase, label, prompt, and schema."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    bad_contracts = [
        {
            "phase": "Probe",
            "label": "probe:probe",
            # missing prompt and schema
        }
    ]
    write_template_spec(spec, phase_contracts=bad_contracts)

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1


def test_template_phase_contracts_duplicate_phase_fails(tmp_path: Path) -> None:
    """Duplicate phase titles in phase_contracts must be rejected."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    dup_contracts = [
        {
            "phase": "Probe",
            "label": "probe:probe-a",
            "prompt": "First probe.",
            "schema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
        },
        {
            "phase": "Probe",
            "label": "probe:probe-b",
            "prompt": "Second probe.",
            "schema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
        },
    ]
    write_template_spec(spec, phase_contracts=dup_contracts)

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1


def test_template_phase_contracts_derives_phases_from_contracts(tmp_path: Path) -> None:
    """When phases is not explicitly provided, it is derived from phase_contracts."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Intake",
            "detail": "Validate inputs.",
            "label": "target:intake",
            "prompt": "Validate the request.",
            "schema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
            "blockWhen": "result.status !== 'PASS'",
            "blockStatus": "BLOCKED_INPUT",
            "blockMessage": "Intake failed.",
            "nextAction": "REINVOKE_WITH_ANSWERS",
        },
        {
            "phase": "Deliver",
            "detail": "Return final result.",
            "label": "target:deliver",
            "prompt": "Build the delivery report.",
            "schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
        },
    ]
    write_template_spec(spec, phases=[], phase_contracts=contracts)

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "template-probe.js"
    content = candidate.read_text(encoding="utf-8")
    # Verify phases were derived from contracts
    assert '"title": "Intake"' in content
    assert '"title": "Deliver"' in content
    assert "phase('Intake')" in content
    assert "phase('Deliver')" in content
    # Verify gate block was rendered
    assert "BLOCKED_INPUT" in content
    assert "REINVOKE_WITH_ANSWERS" in content
    # Verify non-blocking phase has no gate
    assert "phase('Deliver')" in content
    assert "status: 'PASS'" in content


def test_template_freestride_level_multi_phase_contracts(tmp_path: Path) -> None:
    """12-phase contracts (FreeSTRIDE scale) must generate without requiring body.

    This proves that a large workflow avoids the token overflow caused by
    the Author agent having to emit a full JS body inside StructuredOutput.
    """
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()

    freestride_phases = [
        ("Intake", "Validate the request and inputs."),
        ("Analyze", "Analyze the codebase structure."),
        ("Design", "Design the implementation plan."),
        ("ReviewDesign", "Review the design for correctness."),
        ("Author", "Author the implementation."),
        ("CodeReview", "Review the authored code."),
        ("TestGen", "Generate test scenarios."),
        ("SecurityReview", "Review for security issues."),
        ("PerformanceReview", "Review for performance issues."),
        ("StyleReview", "Review for style and maintainability."),
        ("Validate", "Validate generated assets."),
        ("Deliver", "Return final verified result."),
    ]

    contracts: list[dict[str, object]] = []
    derived_phases: list[dict[str, str]] = []
    for idx, (phase_name, detail) in enumerate(freestride_phases):
        is_blocking = idx < len(freestride_phases) - 1
        contract: dict[str, object] = {
            "phase": phase_name,
            "detail": detail,
            "label": f"freestride:{phase_name.lower()}",
            "prompt": f"Execute the {phase_name} phase for FreeSTRIDE workflow. {detail}",
            "schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["PASS", "BLOCKED"]},
                    "blockingIssues": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["status", "blockingIssues"],
            },
        }
        if is_blocking:
            contract["blockWhen"] = "result.status !== 'PASS'"
            contract["blockStatus"] = f"BLOCKED_{phase_name.upper()}"
            contract["blockMessage"] = f"{phase_name} gate blocked."
            contract["nextAction"] = "FIX_AND_REINVOKE"
        contracts.append(contract)
        derived_phases.append({"title": phase_name, "detail": detail})

    write_template_spec(
        spec,
        name="freestride-native",
        description="FreeSTRIDE-scale 12-phase Native Workflow JS probe.",
        phases=derived_phases,
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "freestride-native.js"
    assert candidate.exists()
    content = candidate.read_text(encoding="utf-8")

    # All 12 phases must be present
    for phase_name, _detail in freestride_phases:
        assert f"phase('{phase_name}')" in content, f"Missing phase: {phase_name}"
        assert f'label: "freestride:{phase_name.lower()}"' in content

    # Verify gate blocks were rendered for non-terminal phases
    assert "BLOCKED_INTAKE" in content
    assert "BLOCKED_ANALYZE" in content

    # Terminal phase has no gate, returns PASS
    assert "status: 'PASS'" in content.split("phase('Deliver')")[1]

    # Verify the spec has no body field (compact mode)
    raw_spec = json.loads(spec.read_text(encoding="utf-8"))
    assert raw_spec.get("template") == "sequential-agent-workflow-v1"
    assert len(raw_spec["phase_contracts"]) == 12
    assert "body" not in raw_spec or raw_spec.get("body") in (None, "")

    # Verify there are 12 phases in the generated meta
    assert content.count("phase('") == 12


def test_template_handoff_integration_passes(tmp_path: Path) -> None:
    """Template authoring spec must work through the full handoff gate pipeline."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_template_spec(spec)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        authoring_spec={
            **TEMPLATE_AUTHORING_BASE,
        },
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "template-probe.js"
    assert candidate.exists()

    # Handoff report must pass
    handoff_report = run_root / "outputs" / "stages" / "native-workflow-generation-handoff.json"
    assert handoff_report.exists()
    report_data = json.loads(handoff_report.read_text(encoding="utf-8"))
    assert report_data["status"] == "PASS"
    assert report_data["errors"] == []


def test_template_handoff_blocks_body_and_template_both_provided(tmp_path: Path) -> None:
    """Handoff must block when authoringSpec has both body and template."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_template_spec(spec)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        authoring_spec={
            **TEMPLATE_AUTHORING_BASE,
            "body": "phase('Probe')\n\nreturn { status: 'PASS' }\n",
        },
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "BOTH_BODY_AND_TEMPLATE" in str(payload["errors"])


def test_template_handoff_blocks_missing_body_and_template(tmp_path: Path) -> None:
    """Handoff must block when authoringSpec has neither body nor template."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    write_template_spec(spec)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        authoring_spec={
            "name": "no-body-no-template",
            "description": "Should fail.",
            "phases": [{"title": "Probe"}],
            "supporting_assets": [],
            "asset_disposition": [],
        },
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "HANDOFF_AUTHORING_SPEC_BODY" in str(payload["errors"])


def test_template_authoring_spec_with_agent_type_and_model(tmp_path: Path) -> None:
    """Phase contracts with agentType should render correctly."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Review",
            "detail": "Review with a specialized agent.",
            "label": "target:review",
            "prompt": "Review the content for correctness.",
            "agentType": "workflowprogram-native-cn:logic-reviewer",
            "schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["PASS", "BLOCKED"]},
                    "findings": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["status", "findings"],
            },
        }
    ]
    write_template_spec(
        spec,
        name="agent-type-probe",
        phase_contracts=contracts,
        phases=[{"title": "Review", "detail": "Review with a specialized agent."}],
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "agent-type-probe.js"
    content = candidate.read_text(encoding="utf-8")
    assert 'agentType: "workflowprogram-native-cn:logic-reviewer"' in content


def test_template_authoring_spec_task_model_policy_injected(tmp_path: Path) -> None:
    """Template-generated workflow with task_model_policy must inject workflowprogramAgent."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Probe",
            "label": "template-probe:probe",
            "prompt": "Probe the request.",
            "schema": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
            },
        }
    ]
    write_template_spec(
        spec,
        phase_contracts=contracts,
        task_model_policy={"agent_task_models": {"template-probe:probe": "architecture"}},
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "template-probe.js"
    content = candidate.read_text(encoding="utf-8")
    assert "workflowprogramAgent" in content
    assert "agentTaskTypes" in content
    assert "withTaskModel" in content


def test_develop_authoring_spec_with_template_passes_has_authoring_spec() -> None:
    """The JS hasAuthoringSpec gate must accept a template-based authoringSpec."""
    template_authoring = {
        "status": "PASS",
        "authoringSpec": {
            "name": "template-probe",
            "description": "Template-based workflow.",
            "phases": [{"title": "Probe", "detail": "Return PASS."}],
            "template": "sequential-agent-workflow-v1",
            "phase_contracts": [
                {
                    "phase": "Probe",
                    "label": "template-probe:probe",
                    "prompt": "Probe.",
                    "schema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
                }
            ],
            "supporting_assets": [],
            "asset_disposition": [],
        },
        "blockingIssues": [],
    }
    exploration = {
        "status": "PASS",
        "findings": ["Template workflow."],
        "constraints": [],
        "blockingIssues": [],
    }
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(),
        agent_results=[exploration, exploration, pass_design_evidence(), pass_review_evidence(), template_authoring],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["nextAction"] == "RUN_CONTROLLED_GENERATION"
    assert execution["result"]["authoringSpec"]["template"] == "sequential-agent-workflow-v1"
    assert len(execution["result"]["authoringSpec"]["phase_contracts"]) == 1


def test_develop_authoring_spec_body_still_accepted() -> None:
    """The JS hasAuthoringSpec gate must continue to accept body-based authoringSpec."""
    body_authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(),
        "blockingIssues": [],
    }
    exploration = {
        "status": "PASS",
        "findings": ["Body workflow."],
        "constraints": [],
        "blockingIssues": [],
    }
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(),
        agent_results=[exploration, exploration, pass_design_evidence(), pass_review_evidence(), body_authoring],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["nextAction"] == "RUN_CONTROLLED_GENERATION"
    assert execution["result"]["authoringSpec"]["body"] == "phase('Probe')\n\nreturn { status: 'PASS' }\n"


def test_develop_authoring_spec_missing_body_and_template_blocks() -> None:
    """The JS hasAuthoringSpec gate must reject spec with neither body nor template."""
    bad_authoring = {
        "status": "PASS",
        "authoringSpec": {
            "name": "bad-spec",
            "description": "No body or template.",
            "phases": [{"title": "Probe"}],
            # no body, no template, no phase_contracts
            "supporting_assets": [],
            "asset_disposition": [],
        },
        "blockingIssues": [],
    }
    exploration = {
        "status": "PASS",
        "findings": ["Bad spec."],
        "constraints": [],
        "blockingIssues": [],
    }
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(),
        agent_results=[exploration, exploration, pass_design_evidence(), pass_review_evidence(), bad_authoring],
    )

    assert execution["result"]["status"] == "BLOCKED_GENERATION"
