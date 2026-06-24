from __future__ import annotations

import json
import html
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


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
DEVELOP_SKILL = ROOT / ".claude" / "skills" / "workflowprogram-develop" / "SKILL.md"
LOWLEVEL_EXAMPLES = ROOT / ".claude" / "skills" / "workflowprogram-lowlevel-design" / "references" / "examples"
NATIVE_WORKFLOW_LLD = ROOT / "docs" / "native-workflow-control-plane-lowlevel-design.md"
SETTINGS = ROOT / ".claude" / "settings.json"
PRODUCT_WORKFLOW_SKELETONS: dict[str, str] = {}
VALIDATE_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-validate.js"
ITERATE_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-iterate.js"
AUDIT_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-audit.js"
PUBLISH_WORKFLOW = ROOT / ".claude" / "workflows" / "workflowprogram-publish.js"
PRODUCT_WORKFLOWS = [
    DEVELOP_WORKFLOW,
    AUDIT_WORKFLOW,
    ITERATE_WORKFLOW,
    VALIDATE_WORKFLOW,
    PUBLISH_WORKFLOW,
]
DEVELOP_LENSES = {
    "purpose": "Create a workflow.",
    "objectModel": "Read a request and generate a Native Workflow JS candidate.",
    "processModel": "Clarify, design, review, generate, validate, smoke, and deliver.",
    "decisionModel": "Require confirmation, evidence, and explicit apply approval.",
    "evidenceModel": "Use design, validation, smoke, and apply evidence.",
    "acceptanceModel": "Cover positive, blocked, and candidate-only delivery scenarios.",
    "boundaryModel": "Do not write the target project without apply approval.",
}


def product_meta_name(source: str) -> str:
    marker = "name: '"
    start = source.index(marker) + len(marker)
    end = source.index("'", start)
    return source[start:end]


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


def test_product_workflow_meta_names_do_not_shadow_public_entry_skills() -> None:
    """Claude Code may expose plugin workflows as synthetic skills by meta name.

    Product JS names must stay internal so natural-language requests for
    workflowprogram-develop/audit/iterate/validate/publish load the foreground
    adapter skills instead of name-launching the product workflow with string
    args.
    """
    public_entry_names = {
        "workflowprogram-develop",
        "workflowprogram-audit",
        "workflowprogram-iterate",
        "workflowprogram-validate",
        "workflowprogram-publish",
    }

    for workflow in PRODUCT_WORKFLOWS:
        source = workflow.read_text(encoding="utf-8")
        name = product_meta_name(source)
        assert name.startswith("workflowprogram-product-")
        assert name not in public_entry_names


def test_workflow_meta_names_do_not_match_registered_skill_names() -> None:
    """Synthetic workflow exposure must not collide with registered skills."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    skill_names = set(settings["skills"])

    for workflow in sorted((ROOT / ".claude" / "workflows").glob("*.js")):
        source = workflow.read_text(encoding="utf-8")
        name = product_meta_name(source)
        assert name not in skill_names, f"{workflow.name} meta.name shadows registered skill {name}"


def execute_native_workflow(
    script: Path,
    args: dict | str,
    *,
    agent_results: list[dict] | None = None,
) -> dict:
    harness = r"""
const fs = require('node:fs')
const path = require('node:path')
const payload = JSON.parse(fs.readFileSync(0, 'utf8'))
const source = fs.readFileSync(payload.script, 'utf8').replace('export const meta =', 'const meta =')
const phases = []
const labels = []
const agentTypes = []
const prompts = []
const queuedAgentResults = [...payload.agentResults]
const handleArtifactWriterPrompt = prompt => {
  const legacy = prompt.match(/File path: ([^\n]+)\nContent begins after this line:\n---BEGIN_ARTIFACT_CONTENT---\n([\s\S]*?)---END_ARTIFACT_CONTENT---/)
  if (legacy) {
    const filePath = legacy[1].trim()
    const content = legacy[2]
    fs.mkdirSync(path.dirname(filePath), { recursive: true })
    fs.writeFileSync(filePath, content, 'utf8')
    return { status: 'PASS', files: [filePath], blockingIssues: [] }
  }
  const fileMeta = prompt.match(/Artifact operation: ([^\n]+)\nFile path: ([^\n]+)\nChunk count: ([^\n]+)/)
  const batchMeta = prompt.match(/Batch command count: ([^\n]+)/)
  const commands = [...prompt.matchAll(/---BEGIN_ARTIFACT_COMMAND (\d+)\/(\d+) (write|append)---\n([\s\S]*?)\n---END_ARTIFACT_COMMAND \1\/\2 \3---/g)]
  const payloads = new Map()
  for (const payloadMatch of prompt.matchAll(/---BEGIN_ARTIFACT_PAYLOAD ([^\n]+)---\n([\s\S]*?)\n---END_ARTIFACT_PAYLOAD \1---/g)) {
    payloads.set(payloadMatch[1], JSON.parse(payloadMatch[2]))
  }
  if (fileMeta && commands.length > 0) {
    const filePath = fileMeta[2].trim()
    const chunkCount = Number(fileMeta[3].trim())
    const expectedCommandCount = batchMeta ? Number(batchMeta[1].trim()) : chunkCount
    if (commands.length !== expectedCommandCount) {
      return { status: 'BLOCKED', files: [], blockingIssues: [`Expected ${expectedCommandCount} artifact commands, got ${commands.length}.`] }
    }
    fs.mkdirSync(path.dirname(filePath), { recursive: true })
    for (const match of commands.sort((a, b) => Number(a[1]) - Number(b[1]))) {
      const operation = match[3].trim()
      const helperPayload = match[4].match(/--payload-id '([^']+)'/)
      const helperFile = match[4].match(/--file-id '([^']+)'/)
      let payloadBytes
      if (helperFile) {
        const filePayloads = [...payloads.values()]
          .filter(payload => payload.file_id === helperFile[1])
          .sort((a, b) => Number(a.chunk_index) - Number(b.chunk_index))
        if (filePayloads.length !== chunkCount) {
          return { status: 'BLOCKED', files: [], blockingIssues: [`Expected ${chunkCount} payload markers for file ${helperFile[1]}, got ${filePayloads.length}.`] }
        }
        if (operation !== 'write') {
          return { status: 'BLOCKED', files: [], blockingIssues: [`File helper command must use write operation, got ${operation}.`] }
        }
        const buffers = []
        let expectedOffset = 0
        for (const payload of filePayloads) {
          if (payload.target_file !== filePath || Number(payload.byte_offset || 0) !== expectedOffset) {
            return { status: 'BLOCKED', files: [], blockingIssues: [`Payload metadata mismatch for file ${helperFile[1]}.`] }
          }
          const chunkBytes = Buffer.from(payload.base64, 'base64')
          const offset = Number(payload.byte_offset || 0)
          const maskKey = Number(payload.mask_key || 0)
          for (let index = 0; index < chunkBytes.length; index += 1) {
            chunkBytes[index] = chunkBytes[index] ^ ((maskKey + offset + index) & 255)
          }
          expectedOffset += chunkBytes.length
          buffers.push(chunkBytes)
        }
        payloadBytes = Buffer.concat(buffers)
      } else if (helperPayload) {
        const payload = payloads.get(helperPayload[1])
        if (!payload) {
          return { status: 'BLOCKED', files: [], blockingIssues: [`No payload marker for chunk ${match[1]}.`] }
        }
        if (payload.operation !== operation || payload.target_file !== filePath) {
          return { status: 'BLOCKED', files: [], blockingIssues: [`Payload metadata mismatch for chunk ${match[1]}.`] }
        }
        payloadBytes = Buffer.from(payload.base64, 'base64')
        const offset = Number(payload.byte_offset || 0)
        const maskKey = Number(payload.mask_key || 0)
        for (let index = 0; index < payloadBytes.length; index += 1) {
          payloadBytes[index] = payloadBytes[index] ^ ((maskKey + offset + index) & 255)
        }
      } else {
        const base64Payload = match[4].match(/base64\.b64decode\("([^"]*)"\)/)
        if (!base64Payload) {
          return { status: 'BLOCKED', files: [], blockingIssues: [`No payload for chunk ${match[1]}.`] }
        }
        const maskedOffset = match[4].match(/173\+(\d+)\+i/)
        payloadBytes = Buffer.from(base64Payload[1], 'base64')
        if (maskedOffset) {
          const offset = Number(maskedOffset[1])
          for (let index = 0; index < payloadBytes.length; index += 1) {
            payloadBytes[index] = payloadBytes[index] ^ ((173 + offset + index) & 255)
          }
        }
      }
      if (operation === 'write') {
        fs.writeFileSync(filePath, payloadBytes)
      } else if (operation === 'append') {
        fs.appendFileSync(filePath, payloadBytes)
      } else {
        return { status: 'BLOCKED', files: [], blockingIssues: [`Unknown artifact operation ${operation}.`] }
      }
    }
    return { status: 'PASS', files: [filePath], blockingIssues: [] }
  }
  const chunk = prompt.match(/Artifact operation: ([^\n]+)\nFile path: ([^\n]+)\nChunk index: ([^\n]+)\nChunk count: ([^\n]+)/)
  const command = prompt.match(/---BEGIN_ARTIFACT_COMMAND---\n([\s\S]*?)\n---END_ARTIFACT_COMMAND---/)
  const base64Payload = command?.[1]?.match(/base64\.b64decode\("([^"]*)"\)/)
  if (!chunk || !base64Payload) {
    return { status: 'BLOCKED', files: [], blockingIssues: ['No artifact command parsed.'] }
  }
  const operation = chunk[1].trim()
  const filePath = chunk[2].trim()
  const base64Content = base64Payload[1]
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  if (operation === 'write') {
    fs.writeFileSync(filePath, Buffer.from(base64Content, 'base64'))
  } else if (operation === 'append') {
    fs.appendFileSync(filePath, Buffer.from(base64Content, 'base64'))
  } else {
    return { status: 'BLOCKED', files: [], blockingIssues: [`Unknown artifact operation ${operation}.`] }
  }
  return { status: 'PASS', files: [filePath], blockingIssues: [] }
}
const phase = title => phases.push(title)
const agent = async (prompt, options) => {
  prompts.push(prompt)
  labels.push(options?.label || '')
  agentTypes.push(options?.agentType || null)
  if ((options?.label || '').startsWith('artifact-writer:')) {
    return handleArtifactWriterPrompt(prompt)
  }
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


def assert_chunked_artifact_labels(labels: list[str], group: str, filenames: list[str]) -> None:
    for filename in filenames:
        prefix = f"artifact-writer:{group}:{filename}:"
        assert f"{prefix}write" in labels


def artifact_commands_from_prompt(prompt: str) -> list[str]:
    pattern = re.compile(
        r"---BEGIN_ARTIFACT_COMMAND (?P<index>\d+)/(?P<count>\d+) (?P<operation>write|append)---\n"
        r"(?P<command>[\s\S]*?)\n"
        r"---END_ARTIFACT_COMMAND (?P=index)/(?P=count) (?P=operation)---"
    )
    return [match.group("command").strip() for match in pattern.finditer(prompt)]


def artifact_base64_payloads_from_commands(commands: list[str]) -> list[str]:
    payloads = []
    for command in commands:
        match = re.search(r'base64\.b64decode\("([^"]*)"\)', command)
        assert match, f"no base64 payload in command: {command}"
        payloads.append(match.group(1))
    return payloads


def artifact_base64_payloads_from_prompts(prompts: list[str]) -> list[str]:
    pattern = re.compile(
        r"---BEGIN_ARTIFACT_PAYLOAD (?P<payload_id>[^\n]+)---\n"
        r"(?P<payload>[\s\S]*?)\n"
        r"---END_ARTIFACT_PAYLOAD (?P=payload_id)---"
    )
    payloads: list[str] = []
    for prompt in prompts:
        for match in pattern.finditer(prompt):
            payload = json.loads(match.group("payload"))
            payloads.append(payload["base64"])
    return payloads


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
const path = require('node:path')
const payload = JSON.parse(fs.readFileSync(0, 'utf8'))
const source = fs.readFileSync(payload.script, 'utf8').replace('export const meta =', 'const meta =')
const phases = []
const labels = []
const models = []
const modelProperties = []
const queuedAgentResults = [...payload.agentResults]
const handleArtifactWriterPrompt = prompt => {
  const legacy = prompt.match(/File path: ([^\n]+)\nContent begins after this line:\n---BEGIN_ARTIFACT_CONTENT---\n([\s\S]*?)---END_ARTIFACT_CONTENT---/)
  if (legacy) {
    const filePath = legacy[1].trim()
    const content = legacy[2]
    fs.mkdirSync(path.dirname(filePath), { recursive: true })
    fs.writeFileSync(filePath, content, 'utf8')
    return { status: 'PASS', files: [filePath], blockingIssues: [] }
  }
  const fileMeta = prompt.match(/Artifact operation: ([^\n]+)\nFile path: ([^\n]+)\nChunk count: ([^\n]+)/)
  const batchMeta = prompt.match(/Batch command count: ([^\n]+)/)
  const commands = [...prompt.matchAll(/---BEGIN_ARTIFACT_COMMAND (\d+)\/(\d+) (write|append)---\n([\s\S]*?)\n---END_ARTIFACT_COMMAND \1\/\2 \3---/g)]
  const payloads = new Map()
  for (const payloadMatch of prompt.matchAll(/---BEGIN_ARTIFACT_PAYLOAD ([^\n]+)---\n([\s\S]*?)\n---END_ARTIFACT_PAYLOAD \1---/g)) {
    payloads.set(payloadMatch[1], JSON.parse(payloadMatch[2]))
  }
  if (fileMeta && commands.length > 0) {
    const filePath = fileMeta[2].trim()
    const chunkCount = Number(fileMeta[3].trim())
    const expectedCommandCount = batchMeta ? Number(batchMeta[1].trim()) : chunkCount
    if (commands.length !== expectedCommandCount) {
      return { status: 'BLOCKED', files: [], blockingIssues: [`Expected ${expectedCommandCount} artifact commands, got ${commands.length}.`] }
    }
    fs.mkdirSync(path.dirname(filePath), { recursive: true })
    for (const match of commands.sort((a, b) => Number(a[1]) - Number(b[1]))) {
      const operation = match[3].trim()
      const helperPayload = match[4].match(/--payload-id '([^']+)'/)
      const helperFile = match[4].match(/--file-id '([^']+)'/)
      let payloadBytes
      if (helperFile) {
        const filePayloads = [...payloads.values()]
          .filter(payload => payload.file_id === helperFile[1])
          .sort((a, b) => Number(a.chunk_index) - Number(b.chunk_index))
        if (filePayloads.length !== chunkCount) {
          return { status: 'BLOCKED', files: [], blockingIssues: [`Expected ${chunkCount} payload markers for file ${helperFile[1]}, got ${filePayloads.length}.`] }
        }
        if (operation !== 'write') {
          return { status: 'BLOCKED', files: [], blockingIssues: [`File helper command must use write operation, got ${operation}.`] }
        }
        const buffers = []
        let expectedOffset = 0
        for (const payload of filePayloads) {
          if (payload.target_file !== filePath || Number(payload.byte_offset || 0) !== expectedOffset) {
            return { status: 'BLOCKED', files: [], blockingIssues: [`Payload metadata mismatch for file ${helperFile[1]}.`] }
          }
          const chunkBytes = Buffer.from(payload.base64, 'base64')
          const offset = Number(payload.byte_offset || 0)
          const maskKey = Number(payload.mask_key || 0)
          for (let index = 0; index < chunkBytes.length; index += 1) {
            chunkBytes[index] = chunkBytes[index] ^ ((maskKey + offset + index) & 255)
          }
          expectedOffset += chunkBytes.length
          buffers.push(chunkBytes)
        }
        payloadBytes = Buffer.concat(buffers)
      } else if (helperPayload) {
        const payload = payloads.get(helperPayload[1])
        if (!payload) {
          return { status: 'BLOCKED', files: [], blockingIssues: [`No payload marker for chunk ${match[1]}.`] }
        }
        if (payload.operation !== operation || payload.target_file !== filePath) {
          return { status: 'BLOCKED', files: [], blockingIssues: [`Payload metadata mismatch for chunk ${match[1]}.`] }
        }
        payloadBytes = Buffer.from(payload.base64, 'base64')
        const offset = Number(payload.byte_offset || 0)
        const maskKey = Number(payload.mask_key || 0)
        for (let index = 0; index < payloadBytes.length; index += 1) {
          payloadBytes[index] = payloadBytes[index] ^ ((maskKey + offset + index) & 255)
        }
      } else {
        const base64Payload = match[4].match(/base64\.b64decode\("([^"]*)"\)/)
        if (!base64Payload) {
          return { status: 'BLOCKED', files: [], blockingIssues: [`No payload for chunk ${match[1]}.`] }
        }
        const maskedOffset = match[4].match(/173\+(\d+)\+i/)
        payloadBytes = Buffer.from(base64Payload[1], 'base64')
        if (maskedOffset) {
          const offset = Number(maskedOffset[1])
          for (let index = 0; index < payloadBytes.length; index += 1) {
            payloadBytes[index] = payloadBytes[index] ^ ((173 + offset + index) & 255)
          }
        }
      }
      if (operation === 'write') {
        fs.writeFileSync(filePath, payloadBytes)
      } else if (operation === 'append') {
        fs.appendFileSync(filePath, payloadBytes)
      } else {
        return { status: 'BLOCKED', files: [], blockingIssues: [`Unknown artifact operation ${operation}.`] }
      }
    }
    return { status: 'PASS', files: [filePath], blockingIssues: [] }
  }
  const chunk = prompt.match(/Artifact operation: ([^\n]+)\nFile path: ([^\n]+)\nChunk index: ([^\n]+)\nChunk count: ([^\n]+)/)
  const command = prompt.match(/---BEGIN_ARTIFACT_COMMAND---\n([\s\S]*?)\n---END_ARTIFACT_COMMAND---/)
  const base64Payload = command?.[1]?.match(/base64\.b64decode\("([^"]*)"\)/)
  if (!chunk || !base64Payload) {
    return { status: 'BLOCKED', files: [], blockingIssues: ['No artifact command parsed.'] }
  }
  const operation = chunk[1].trim()
  const filePath = chunk[2].trim()
  const base64Content = base64Payload[1]
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  if (operation === 'write') {
    fs.writeFileSync(filePath, Buffer.from(base64Content, 'base64'))
  } else if (operation === 'append') {
    fs.appendFileSync(filePath, Buffer.from(base64Content, 'base64'))
  } else {
    return { status: 'BLOCKED', files: [], blockingIssues: [`Unknown artifact operation ${operation}.`] }
  }
  return { status: 'PASS', files: [filePath], blockingIssues: [] }
}
const phase = title => phases.push(title)
const agent = async (_prompt, options) => {
  labels.push(options?.label || '')
  models.push(options?.model || null)
  modelProperties.push(Object.prototype.hasOwnProperty.call(options || {}, 'model'))
  if ((options?.label || '').startsWith('artifact-writer:')) {
    return handleArtifactWriterPrompt(_prompt)
  }
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
    supporting_assets = [
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
        {
            "kind": "settings",
            "path": ".claude/settings.json",
            "content": "{\"workflows\": {}}",
            "reason": "Registers the generated workflow.",
        },
        {
            "kind": "managed-files",
            "path": ".workflowprogram/managed-files.json",
            "content": "{\"files\": []}",
            "reason": "Tracks managed workflow assets.",
        },
    ]
    write_authoring_spec(
        spec,
        supporting_assets=supporting_assets,
        asset_disposition=[
            {
                "path": item["path"],
                "action": "generate",
                "reason": item["reason"],
                "supporting_asset_path": item["path"],
            }
            for item in supporting_assets
        ],
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    candidate_root = run_root / "outputs" / "candidate"
    assert (candidate_root / ".claude" / "skills" / "probe-review" / "SKILL.md").exists()
    assert (candidate_root / ".claude" / "agents" / "probe-reviewer.md").exists()
    assert (candidate_root / ".claude" / "scripts" / "probe-check.py").exists()
    assert (candidate_root / ".claude" / "settings.json").exists()
    assert (candidate_root / ".workflowprogram" / "design" / "workflow-spec.yaml").exists()
    assert not (candidate_root / ".workflowprogram" / "managed-files.json").exists()
    assert {item["kind"] for item in payload["supporting_assets"]} == {
        "skill",
        "agent",
        "script",
        "settings",
        "workflow-spec-ir",
        "managed-files",
    }
    managed_asset = next(item for item in payload["supporting_assets"] if item["kind"] == "managed-files")
    assert managed_asset["path"] == ".workflowprogram/managed-files.json"


def test_generator_rejects_supporting_asset_reason_drift(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    write_authoring_spec(
        spec,
        supporting_assets=[
            {
                "kind": "script",
                "path": ".claude/scripts/probe-check.py",
                "content": "print('PASS')",
                "reason": "Authoring drift reason.",
            }
        ],
        asset_disposition=[
            {
                "path": ".claude/scripts/probe-check.py",
                "action": "generate",
                "reason": "Canonical Design reason.",
                "supporting_asset_path": ".claude/scripts/probe-check.py",
            }
        ],
    )

    completed = run_generator(spec, target, run_root, "--json")

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any(error["rule"] == "CANONICAL_SUPPORTING_ASSET_REASON_MISMATCH" for error in payload["errors"])
    assert not (run_root / "outputs" / "candidate").exists()


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


def test_generator_handoff_normalizes_absolute_design_asset_paths(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    supporting_assets = [
        {
            "kind": "settings",
            "path": ".claude/settings.json",
            "content": "{\"permissions\":{\"allow\":[]}}\n",
            "reason": "Settings must be generated with the migrated workflow.",
        }
    ]
    disposition = [
        {
            "path": ".claude/settings.json",
            "action": "update",
            "reason": "Settings must be generated with the migrated workflow.",
            "supporting_asset_path": ".claude/settings.json",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": str(target / ".claude" / "settings.json"),
            "action": "update",
            "reason": "Settings must be generated with the migrated workflow.",
            "supportingAssetPath": str(target / ".claude" / "agents" / "stride-ui-verifier.md"),
        }
    ]
    write_authoring_spec(spec, supporting_assets=supporting_assets, asset_disposition=disposition)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        operation="update",
        design_evidence=design,
        authoring_spec=authoring_spec_payload(
            supporting_assets=supporting_assets,
            asset_disposition=disposition,
        ),
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_generator_handoff_clears_primary_workflow_supporting_asset_path(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "update",
            "reason": "Primary workflow content comes from body, not supporting_assets.",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": str(target / ".claude" / "workflows" / "generated-probe.js"),
            "action": "update",
            "reason": "Primary workflow content comes from body, not supporting_assets.",
            "supportingAssetPath": str(target / ".claude" / "workflows" / "generated-probe.js"),
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

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_generator_handoff_clears_non_content_supporting_asset_path(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    disposition = [
        {
            "path": ".agents",
            "action": "remove",
            "reason": "Legacy runtime directory is not part of the native workflow surface.",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": str(target / ".agents"),
            "action": "remove",
            "reason": "Legacy runtime directory is not part of the native workflow surface.",
            "supportingAssetPath": str(target / ".claude" / "workflows" / "generated-probe.js"),
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

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_generator_handoff_prunes_run_evidence_asset_disposition(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "update",
            "reason": "Primary workflow content comes from body, not supporting_assets.",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": str(target / ".claude" / "workflows" / "generated-probe.js"),
            "action": "update",
            "reason": "Primary workflow content comes from body, not supporting_assets.",
        },
        {
            "path": str(target / ".workflowprogram" / "runs" / "run-001"),
            "action": "generate",
            "reason": "Run evidence is produced by WPN and must not be a managed target asset.",
            "supportingAssetPath": str(target / ".claude" / "workflows" / "generated-probe.js"),
        },
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

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_generator_handoff_sorts_design_asset_disposition_before_compare(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    disposition = [
        {
            "path": ".claude/agents/probe.md",
            "action": "retain",
            "reason": "Existing probe agent is retained.",
        },
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "update",
            "reason": "Primary workflow content comes from body, not supporting_assets.",
        },
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": str(target / ".claude" / "workflows" / "generated-probe.js"),
            "action": "update",
            "reason": "Primary workflow content comes from body, not supporting_assets.",
        },
        {
            "path": str(target / ".claude" / "agents" / "probe.md"),
            "action": "retain",
            "reason": "Existing probe agent is retained.",
        },
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

    assert execution["result"]["status"] == "NEEDS_FOREGROUND_ARGS"
    assert execution["result"]["nextAction"] == "DERIVE_ARGS_AND_REINVOKE"
    assert execution["result"]["missingArgs"] == ["request", "targetRoot", "runRoot", "runId"]
    assert "Do not ask the user" in execution["result"]["userQuestionPolicy"]


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
    assert "## Step 1: Derive Invocation Inputs Without Side Effects" in text
    assert "Do not create `RUN_ROOT`, run `route-native-control-plane.py`" in text
    assert "BLOCKED_WORKFLOW_TOOL_UNAVAILABLE" in text
    assert "non-interactive `claude -p` / `--print` / `sdk-cli` sessions" in text
    assert "route/preflight" in text
    assert "`RUN_ROOT` creation" in text
    assert "### Canonical Invocation" in text
    assert 'scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-develop.js"' in text
    assert "migrationDecisions" in text
    assert 'args: "operation=migrate clarification.confirmedByUser=true decisions.flatOutputDir=outputs/stride-audit"' in text
    assert "dotted keys can" in text
    assert "READY_FOR_CONFIRMATION" in text
    assert "workflowprogram-develop-*.js" in text
    assert "--workflow-task-output <WORKFLOW_TASK_OUTPUT_FILE>" in text
    assert "Never recover from a missing" in text
    assert "foreground assistant must not create that file manually" in text
    assert "Do not convert a confirmed WPN continuation into Claude Code plan mode" in text
    assert "do not call `ExitPlanMode`" in text


def test_primary_develop_skill_derives_first_invocation_args() -> None:
    """The primary user-facing skill should not ask users for derivable product
    JS intake fields before first Workflow invocation."""
    text = DEVELOP_SKILL.read_text(encoding="utf-8")

    assert "### First Invocation Defaults" in text
    assert "The user should not need to provide these fields manually" in text
    assert "`request`: original user request text after removing the skill trigger" in text
    assert "`targetRoot`: current working directory absolute path unless the user explicitly names another target" in text
    assert "`runId`: create a stable new id such as `develop-YYYYMMDD-HHMMSS`" in text
    assert "`runRoot`: `<targetRoot>/.workflowprogram/runs/<runId>`" in text
    assert "`operation`: infer `migrate`" in text
    assert "Call the product JS on the first invocation with structured nested args" in text
    assert "Do not call Workflow with only `scriptPath`" in text
    assert "### Foreground Guard Protocol" in text
    assert "--workflow-task-output <WORKFLOW_TASK_OUTPUT_FILE>" in text
    assert "Do not create `RUN_ROOT`, do not use `Write`" in text
    assert "Only an explicit external user confirmation may set" in text
    assert "must not infer or" in text
    assert "Do not convert a confirmed WPN continuation into Claude Code plan mode" in text
    assert "do not call `ExitPlanMode`" in text
    assert "disable-model-invocation" not in text


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


def test_develop_design_prompt_enforces_first_attempt_output_budgets() -> None:
    """Large migration designs should be compact before the first
    StructuredOutput call instead of relying on schema rejection retries."""
    exploration = {
        "status": "PASS",
        "findings": ["The current command and registered assets define behavior."],
        "constraints": ["Do not write target files directly."],
        "migrationTasks": ["Generate the target Native Workflow JS control plane."],
        "trueBlockers": [],
        "userDecisions": [],
        "sourceOfTruth": [".claude/commands/stride-audit.md"],
        "assetDispositionHints": [
            {
                "path": ".claude/workflows/stride-audit.js",
                "action": "generate",
                "reason": "Target Native Workflow JS deliverable.",
            }
        ],
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[exploration, exploration, pass_design_evidence()],
    )

    design_prompt = execution["prompts"][execution["labels"].index("workflowprogram-develop:design")]
    assert "The first StructuredOutput call must satisfy the schema" in design_prompt
    assert "hard first-attempt budgets" in design_prompt
    assert "lowLevelDesign target <= 9000 chars" in design_prompt
    assert "traceability <= 35 items" in design_prompt
    assert "Before calling StructuredOutput, self-check field lengths and item counts" in design_prompt
    assert "It is not a full target implementation or copied design document" in design_prompt

    source = DEVELOP_WORKFLOW.read_text(encoding="utf-8")
    assert "Hard max 12000 chars; target <= 9000 chars" in source
    assert "Hard max 40 items; target <= 35 items" in source


def test_develop_reuses_supplied_explorations_on_review_fix_reinvoke() -> None:
    """Review-fix re-entry should not repeat expensive exploration when the
    prior exploration evidence is supplied.

    Phase 3: Primary workflow content comes from body, not supporting_assets.
    Primary workflow disposition must not carry supporting_asset_path.
    """
    exploration = {
        "status": "PASS",
        "findings": ["Existing command, agents, and skills define behavior."],
        "constraints": ["Only WPN controlled generation may write assets."],
        "migrationTasks": ["Regenerate design after review fixes."],
        "trueBlockers": [],
        "userDecisions": [],
        "sourceOfTruth": [".claude/commands/stride-audit.md"],
        "assetDispositionHints": [
            {
                "path": ".claude/workflows/stride-audit.js",
                "action": "generate",
                "reason": "Target Native Workflow JS deliverable.",
            }
        ],
        "blockingIssues": [],
    }
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            name="stride-audit",
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=[
                {
                    "path": ".claude/workflows/stride-audit.js",
                    "action": "generate",
                    "reason": "Target Native Workflow JS deliverable.",
                }
            ],
        ),
        "blockingIssues": [],
    }
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/stride-audit.js",
            "action": "generate",
            "reason": "Target Native Workflow JS deliverable.",
        }
    ]

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            operation="migrate",
            explorations=[exploration, exploration],
            designReviewRebuttal={"requiredRevisionsClosed": ["Fix phantom asset disposition entries."]},
        ),
        agent_results=[design, pass_review_evidence(), authoring],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert "workflowprogram-develop:explore:target-context" not in execution["labels"]
    assert "workflowprogram-develop:explore:runtime-boundaries" not in execution["labels"]
    assert execution["labels"][:3] == [
        "workflowprogram-develop:design",
        "workflowprogram-develop:review",
        "workflowprogram-develop:author",
    ]
    design_prompt = execution["prompts"][0]
    assert "Review correction input:" in design_prompt
    assert "design review" in design_prompt
    assert "requiredRevisionsClosed" in design_prompt
    assert "Do not treat these corrections as new userDecisions" in design_prompt


def test_develop_native_workflow_allows_pass_review_required_revisions_as_followups() -> None:
    review = {
        **pass_review_evidence(),
        "requiredRevisions": ["Update the retired command documentation during generation."],
    }
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            designEvidence=pass_design_evidence(),
            reviewEvidence=review,
        ),
        agent_results=[pass_authoring_evidence()],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["reviewEvidence"] == review
    assert execution["result"]["generationHandoff"]["reviewEvidence"] == review


def test_develop_native_workflow_blocks_non_pass_review_required_revisions() -> None:
    review = {
        **pass_review_evidence(),
        "status": "BLOCKED",
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
    assert execution["result"]["reinvokeArgsPolicy"]["supportedCorrectionField"] == "reviewFixes"
    assert "designReviewRebuttal" in execution["result"]["reinvokeArgsPolicy"]["acceptedAliases"]
    assert "reviewEvidence" in execution["result"]["reinvokeArgsPolicy"]["omitStaleFields"]


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
    """Phase 3: Primary workflow content comes from body, not supporting_assets."""
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
    asset_disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow is the migration deliverable.",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = asset_disposition
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
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
                "supportingAssetPath": ".workflowprogram/design/archive/stride-ui-verifier.md",
            },
        ],
        "blockingIssues": [],
    }
    supporting_assets = []
    asset_disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow is the migration deliverable.",
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
        },
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow is the migration deliverable.",
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
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
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
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
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


def test_develop_migrate_does_not_block_defaulted_existing_workflow_decisions() -> None:
    """Existing-workflow migration defaults should not become Design gates.

    The FreeSTRIDE migration hit this shape when Exploration described v0.5 vs
    v0.6, command/workflow registration, and AGENTS.md disposition as
    questions even though the request already says to migrate and preserve the
    existing workflow behavior.
    """
    pass_exploration = {
        "status": "PASS",
        "findings": ["Existing STRIDE workflow assets are readable."],
        "constraints": ["Preserve current behavior unless the migration plan says otherwise."],
        "migrationTasks": ["Migrate the existing workflow to Native Workflow JS."],
        "trueBlockers": [],
        "userDecisions": [
            "Whether to upgrade the pipeline from v0.5 (current JS) to v0.6 (described in AGENTS.md) -- the requirement says 'migrate existing workflow' which implies v0.5 preservation, but AGENTS.md represents the evolved design intent.",
            "Whether to keep .claude/commands/stride-audit.md as the primary entry point (updated to delegate to the JS) or let the workflow registration take over execution.",
            "Whether AGENTS.md should remain as the forward design reference or be updated to match the migrated JS output.",
            "No additional user decisions required -- all migration decisions are settled in the requirement.migrationDecisions and no topology-changing questions remain unresolved.",
        ],
        "sourceOfTruth": [".claude/workflows/stride-security-audit.js"],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Existing workflow migration candidate.",
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    review = pass_review_evidence()
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(
            operation="migrate",
            request="Migrate the existing STRIDE workflow while preserving current behavior and supporting targets/security_device_auth.",
        ),
        agent_results=[pass_exploration, pass_exploration, design, pass_review_evidence(), authoring],
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


# Phase 2: Design Gate Robustness

@pytest.mark.parametrize(
    "operation",
    ["create", "update", "migrate"],
)
def test_develop_malformed_exploration_null_blocks_with_structured_error(operation: str) -> None:
    """Null exploration items must still produce structured blockers when the
    internal retry also returns null."""
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation=operation),
        agent_results=[None, None, None, None],
    )
    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert len(execution["result"]["blockingIssues"]) == 2
    assert all("null/undefined" in issue for issue in execution["result"]["blockingIssues"])
    assert all(f"operation={operation}" in issue for issue in execution["result"]["blockingIssues"])


@pytest.mark.parametrize(
    "operation",
    ["create", "update", "migrate"],
)
def test_develop_malformed_exploration_string_blocks_with_structured_error(operation: str) -> None:
    """String exploration items must still produce structured blockers when the
    internal retry also returns strings."""
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation=operation),
        agent_results=["exploration complete", "all good", "still bad", "also bad"],
    )
    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert len(execution["result"]["blockingIssues"]) == 2
    assert all("is a string" in issue for issue in execution["result"]["blockingIssues"])
    assert all(f"operation={operation}" in issue for issue in execution["result"]["blockingIssues"])


@pytest.mark.parametrize(
    "operation",
    ["create", "update", "migrate"],
)
def test_develop_malformed_exploration_missing_status_blocks_with_structured_error(operation: str) -> None:
    """Exploration items with missing or invalid status enum must still produce
    structured blockers when the internal retry also returns invalid objects."""
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation=operation),
        agent_results=[
            {"findings": [], "constraints": []},
            {"status": "INVALID", "findings": [], "constraints": []},
            {"findings": [], "constraints": []},
            {"status": "INVALID", "findings": [], "constraints": []},
        ],
    )
    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert len(execution["result"]["blockingIssues"]) == 2
    assert all(f"operation={operation}" in issue for issue in execution["result"]["blockingIssues"])


def test_develop_malformed_exploration_non_object_json_blocks_with_structured_error() -> None:
    """A JSON non-object value (e.g. a number, array, or boolean) exploration
    item must produce structured blockers rather than silent PASS or crash."""
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="create"),
        agent_results=[42, True, 42, True],
    )
    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert len(execution["result"]["blockingIssues"]) == 2
    assert all("is a number" in issue or "is a boolean" in issue for issue in execution["result"]["blockingIssues"])


def test_develop_retries_transient_null_exploration_before_design_block() -> None:
    """A transient null from an internally generated exploration should be
    retried once before Design blocks the workflow."""
    asset_disposition = [
        {
            "path": ".claude/commands/probe.md",
            "action": "retain",
            "reason": "Existing command remains the user-facing entry point.",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = asset_disposition
    authoring = pass_authoring_evidence()
    authoring["authoringSpec"] = authoring_spec_payload(asset_disposition=asset_disposition)
    exploration = {
        "status": "PASS",
        "findings": ["Target context found."],
        "constraints": ["Use managed candidate generation."],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }
    review = pass_review_evidence()
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            exploration,
            None,
            {**exploration, "findings": ["Runtime boundaries found after retry."]},
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["labels"][:3] == [
        "workflowprogram-develop:explore:target-context",
        "workflowprogram-develop:explore:runtime-boundaries",
        "workflowprogram-develop:explore:runtime-boundaries",
    ]
    design_prompt = execution["prompts"][3]
    assert "Runtime boundaries found after retry." in design_prompt


def test_develop_valid_exploration_with_blocked_status_still_produces_blockers() -> None:
    """Valid exploration items with BLOCKED status and meaningful blockingIssues
    should still produce those issues, not the generic fallback."""
    exploration = {
        "status": "BLOCKED",
        "findings": [],
        "constraints": [],
        "blockingIssues": ["Target root is not readable."],
    }
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="create"),
        agent_results=[exploration, exploration],
    )
    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert execution["result"]["blockingIssues"] == ["Target root is not readable.", "Target root is not readable."]


@pytest.mark.parametrize("field", ["blockingIssues", "trueBlockers"])
def test_develop_pass_exploration_with_blockers_is_invalid(field: str) -> None:
    """PASS exploration evidence is internally inconsistent when it still
    carries blockers; WPN should block before Design consumes it."""
    exploration = {
        "status": "PASS",
        "findings": ["Target context found."],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }
    exploration[field] = ["placeholder blocker"]

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[exploration, {**exploration, field: []}],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert execution["result"]["blockingIssues"] == [
        "Exploration item 0 (target-context) is PASS but includes blockingIssues or trueBlockers; operation=migrate"
    ]


# Phase 2: No-op userDecision phrase family

@pytest.mark.parametrize(
    "no_op_phrase",
    [
        "Confirmed: all migration decisions have been reviewed.",
        "resolved migration decisions are exhaustive",
        "No unresolved topology-changing decisions remain",
        "No additional external user decisions required",
        "No external user decisions beyond the resolved migration decisions are needed at this stage.",
        "No true blockers identified",
        "All decisions resolved",
        "All 12+ decisions resolved during design review",
    ],
)
def test_develop_migrate_no_op_user_decisions_do_not_block(no_op_phrase: str) -> None:
    """Historical no-op user decision phrases must not block migrate design
    when they are the only user decisions."""
    pass_exploration = {
        "status": "PASS",
        "findings": ["All assets readable."],
        "constraints": [],
        "migrationTasks": ["Generate missing workflow."],
        "trueBlockers": [],
        "userDecisions": [no_op_phrase],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[pass_exploration, pass_exploration, design, pass_review_evidence(), authoring],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert "User decision required" not in json.dumps(execution["result"])


def test_develop_migrate_mixed_no_op_and_real_decisions_blocks_only_real() -> None:
    """When userDecisions mix no-op phrases with genuine unresolved decisions,
    only the genuine decisions should block."""
    pass_exploration = {
        "status": "PASS",
        "findings": ["All assets readable."],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [
            "Confirmed: all migration sources verified.",
            "No additional external user decisions required.",
            "Should managed apply target the current branch or a new release branch?",
        ],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[pass_exploration, pass_exploration],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    # Only the real decision should appear as a blocker
    matching = [issue for issue in execution["result"]["blockingIssues"] if "User decision required" in issue]
    assert len(matching) >= 1
    assert all("Should managed apply" in issue for issue in matching)


def test_develop_migrate_confirmed_prefix_real_approval_decision_still_blocks() -> None:
    """A Confirmed prefix is only a no-op for settled migration facts; it must
    not hide a real approval or write-boundary decision."""
    pass_exploration = {
        "status": "PASS",
        "findings": ["Target readable."],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [
            "Confirmed: Should managed apply require explicit user approval?"
        ],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[pass_exploration, pass_exploration],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert execution["result"]["blockingIssues"] == [
        "User decision required: Confirmed: Should managed apply require explicit user approval?",
        "User decision required: Confirmed: Should managed apply require explicit user approval?",
    ]


def test_develop_migrate_real_unresolved_decision_about_write_boundary_still_blocks() -> None:
    """True unresolved decisions about write boundaries must still block."""
    pass_exploration = {
        "status": "PASS",
        "findings": ["Target readable."],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [
            "What is the write boundary for generated candidate assets?"
        ],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[pass_exploration, pass_exploration],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert any("User decision required" in issue for issue in execution["result"]["blockingIssues"])


def test_develop_migrate_real_unresolved_decision_about_external_policy_still_blocks() -> None:
    """True unresolved decisions about external policy must still block."""
    pass_exploration = {
        "status": "PASS",
        "findings": ["Target readable."],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [
            "Which external policy governs the archived asset retention period?"
        ],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[pass_exploration, pass_exploration],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert any("User decision required" in issue for issue in execution["result"]["blockingIssues"])


def test_develop_migrate_real_unresolved_decision_about_approval_still_blocks() -> None:
    """True unresolved decisions about user approval must still block."""
    pass_exploration = {
        "status": "PASS",
        "findings": ["Target readable."],
        "constraints": [],
        "migrationTasks": [],
        "trueBlockers": [],
        "userDecisions": [
            "Does the user approve migrating the legacy agent registry to Native Workflow JS?"
        ],
        "sourceOfTruth": [],
        "assetDispositionHints": [],
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[pass_exploration, pass_exploration],
    )

    assert execution["result"]["status"] == "BLOCKED_DESIGN"
    assert any("User decision required" in issue for issue in execution["result"]["blockingIssues"])


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
                "authoringFixes": {"missingSupportingAssets": [".claude/settings.json"]},
            },
            "READY_FOR_VALIDATION",
            "RUN_DETERMINISTIC_VALIDATION",
        ),
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
    assert execution["result"]["designEvidence"]["status"] == "PASS"
    assert execution["result"]["reviewEvidence"]["status"] == "PASS"
    assert execution["result"]["authoringSpec"]["name"] == authoring_spec_payload()["name"]
    if expected_status in {"READY_FOR_VALIDATION", "READY_FOR_SMOKE", "READY_FOR_APPLY"}:
        assert execution["result"]["generationEvidence"]["candidateHash"] == pass_generation_evidence()["candidateHash"]
    if expected_status in {"READY_FOR_SMOKE", "READY_FOR_APPLY"}:
        assert execution["result"]["validationEvidence"]["candidateHash"] == pass_validation_evidence()["candidateHash"]
    if expected_status == "READY_FOR_APPLY":
        assert execution["result"]["smokeEvidence"]["candidateHash"] == pass_smoke_evidence()["candidateHash"]


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
    assert "const runtimeContext =" in content
    assert "Runtime invocation context (authoritative command args)" in content
    assert "structuredOutputContract" in content
    assert "schema: phaseSchema" in content
    assert 'agentType: "workflowprogram-native-cn:structured-phase-runner"' in content
    assert "phasePrompt" in content
    assert "status: 'PASS'" in content

    execution = execute_native_workflow(
        candidate,
        {
            "runId": "template-smoke-001",
            "target": "targets/security_device_auth",
            "targetRoot": str(target),
            "mode": "auto",
            "options": {"no_sast": True},
        },
        agent_results=[{"status": "PASS"}],
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["agentTypes"] == ["workflowprogram-native-cn:structured-phase-runner"]
    assert "Structured output contract" in execution["prompts"][0]
    assert "Return exactly one JSON object that satisfies this schema" in execution["prompts"][0]
    assert "Call StructuredOutput with a JSON object input, not a stringified JSON blob" in execution["prompts"][0]
    assert "write every named output file before calling StructuredOutput" in execution["prompts"][0]
    assert "If this phase does not explicitly name output files, do not write files" in execution["prompts"][0]
    assert "write a deterministic fallback artifact at that requested path" in execution["prompts"][0]
    assert "use Bash here-doc/redirection or read the existing file before using Write" in execution["prompts"][0]
    assert "After required files are written, do not call Bash, Read, Write, Edit, Glob, or Grep for verification" in execution["prompts"][0]
    assert "make exactly one StructuredOutput attempt next" in execution["prompts"][0]
    assert "keep StructuredOutput compact" in execution["prompts"][0]
    assert "return paths, counts, hashes, top-level keys, and short summaries" in execution["prompts"][0]
    assert "correct only the JSON object and retry StructuredOutput once" in execution["prompts"][0]
    assert "Once StructuredOutput returns success, the phase is done" in execution["prompts"][0]
    assert "any later tool call can mutate files or replace captured evidence" in execution["prompts"][0]
    assert "respond with exactly DONE and no other text" in execution["prompts"][0]
    assert '"status":' in execution["prompts"][0]
    assert "targets/security_device_auth" in execution["prompts"][0]
    assert '"no_sast": true' in execution["prompts"][0]

    execution_from_string_args = execute_native_workflow(
        candidate,
        json.dumps(
            {
                "runId": "template-smoke-002",
                "target": "targets/security_device_auth",
                "targetRoot": str(target),
                "mode": "auto",
                "options": {"no_sast": True},
            }
        ),
        agent_results=[{"status": "PASS"}],
    )
    assert execution_from_string_args["result"]["status"] == "PASS"
    assert "targets/security_device_auth" in execution_from_string_args["prompts"][0]
    assert '"no_sast": true' in execution_from_string_args["prompts"][0]


def test_template_stride_aggregate_schema_normalized(tmp_path: Path) -> None:
    """All-six STRIDE prompts must not render a single-dimension output schema."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Stride",
            "detail": "Analyze all STRIDE dimensions.",
            "label": "template-probe:stride",
            "prompt": (
                "You perform 6-dimensional STRIDE threat analysis. "
                "Return result as a single JSON containing all six dimensions. "
                "Run each dimension analysis independently, then combine results."
            ),
            "schema": {
                "type": "object",
                "required": ["stride_tag", "threats"],
                "properties": {
                    "stride_tag": {"type": "string"},
                    "threats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["threat_id", "stride_tag"],
                            "properties": {
                                "threat_id": {"type": "string"},
                                "stride_tag": {"enum": ["S", "T", "R", "I", "D", "E"]},
                            },
                        },
                    },
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="stride-template",
        phases=[{"title": "Stride", "detail": "Analyze all STRIDE dimensions."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "stride-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert '"required": ["stride_tag", "threats"]' not in content
    assert "Return result as a single JSON containing all six dimensions" not in content
    assert "phase('Stride')" in content
    assert "Deterministic STRIDE candidate generator" in content
    assert "writeDeterministicStrideResultFromPriorPhases" in content
    assert "deterministic_dfd_candidate_generation" in content
    assert "phase('Stride Artifacts')" in content
    assert "Mechanical STRIDE artifact writer" in content
    assert "writeStrideArtifactsFromPhaseResult" in content
    assert "threat_list.json" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "stride-aggregate-001", "target": "target", "targetRoot": str(target)},
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["Stride", "Stride Artifacts"]
    assert_chunked_artifact_labels(execution["labels"], "stride", ["threat_list.json"])
    assert "Run the single Bash command between the command markers exactly once" in execution["prompts"][0]
    assert "Do not call Read, Write, Edit, Glob, Grep" in execution["prompts"][0]
    assert "respond exactly DONE" in execution["prompts"][0]
    assert "Artifact payloads are embedded only in payload markers for the helper" in execution["prompts"][0]
    assert "Base64 payloads are byte-masked" in execution["prompts"][0]
    assert "---BEGIN_ARTIFACT_BASE64---" not in execution["prompts"][0]
    assert "---BEGIN_ARTIFACT_COMMAND " in execution["prompts"][0]
    assert "Artifact operation: write" in execution["prompts"][0]
    threat_list = json.loads((target / "outputs" / "stride-audit" / "threat_list.json").read_text(encoding="utf-8"))
    assert threat_list["source_phase_label"] == "template-probe:stride"
    threats = threat_list["threats"]
    assert len(threats) == 11
    assert {item["stride_tag"] for item in threats} == {"S", "T", "R", "I", "D", "E"}
    assert [item["threat_id"] for item in threats[:3]] == ["S-001", "S-002", "T-001"]
    assert all(item["affected_object"]["dfd_element_ref"] for item in threats)
    assert all(item["mapping_rationale"]["object_property_impact"] for item in threats)
    assert all(item["evidence_refs"] for item in threats)


def test_template_stride_adds_freestride_must_detect_entries_for_device_auth(tmp_path: Path) -> None:
    """FreeSTRIDE/device_auth runs must carry regression corpus must-detect findings."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "FreeSTRIDE"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Stride",
            "detail": "Analyze all STRIDE dimensions.",
            "label": "template-probe:stride",
            "prompt": "Perform 6-dimensional STRIDE threat analysis and return result as a single JSON with threats.",
            "schema": {
                "type": "object",
                "required": ["threats"],
                "properties": {
                    "threats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"threat_id": {"type": "string"}, "stride_tag": {"type": "string"}},
                        },
                    },
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="stride-freestride-template",
        phases=[{"title": "Stride", "detail": "Analyze all STRIDE dimensions."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "stride-freestride-template.js"
    execution = execute_native_workflow(
        candidate,
        {
            "runId": "freestride-stride-001",
            "target": "targets/security_device_auth",
            "targetRoot": str(target),
        },
    )

    assert execution["result"]["status"] == "PASS"
    threat_list = json.loads((target / "outputs" / "stride-audit" / "threat_list.json").read_text(encoding="utf-8"))
    threats = threat_list["threats"]
    must_by_id = {item["threat_id"]: item for item in threats if item["threat_id"].startswith("MUST-")}
    assert len(threats) == 18
    assert set(must_by_id) == {f"MUST-{index:03d}" for index in range(1, 8)}
    assert must_by_id["MUST-001"]["final_classification"] == "confirmed_code_defect"
    assert "g_count is int32_t" in must_by_id["MUST-001"]["description"]
    assert must_by_id["MUST-002"]["source_file"] == "identity_group.c"
    assert must_by_id["MUST-002"]["file"].startswith("identity_group.c:")
    assert "ClearFreeUint8Buff exists but is unused" in must_by_id["MUST-002"]["description"]
    assert must_by_id["MUST-003"]["function"] == "GaIsDeviceInGroup"
    assert "AUTH_FORM_ACROSS_ACCOUNT" in must_by_id["MUST-003"]["description"]
    assert must_by_id["MUST-004"]["sink_operation"] == "LockHcMutex_followed_by_external_callback"
    assert must_by_id["MUST-006"]["source_line_number"] == 86
    assert must_by_id["MUST-007"]["final_classification"] == "partial"
    assert must_by_id["MUST-007"]["violated_property"] == "integrity"
    valid_properties = {
        "authentication",
        "integrity",
        "non-repudiation",
        "confidentiality",
        "availability",
        "authorization",
    }
    assert {item["violated_property"] for item in must_by_id.values()} <= valid_properties


def test_template_stride_anchors_freestride_design_threats_to_dfd_aliases(tmp_path: Path) -> None:
    """FreeSTRIDE deterministic design threats should use concrete DFD ids when available."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "FreeSTRIDE"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "DFD",
            "detail": "Infer a data flow diagram.",
            "label": "template-probe:dfd",
            "prompt": "Return dfd_yaml and dfd_index.",
            "schema": {
                "type": "object",
                "required": ["dfd_yaml", "dfd_index"],
                "properties": {
                    "dfd_yaml": {"type": "object"},
                    "dfd_index": {"type": "object"},
                },
            },
        },
        {
            "phase": "Stride",
            "detail": "Analyze all STRIDE dimensions.",
            "label": "template-probe:stride",
            "prompt": "Perform 6-dimensional STRIDE threat analysis and return result as a single JSON with threats.",
            "schema": {
                "type": "object",
                "required": ["threats"],
                "properties": {
                    "threats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["threat_id", "stride_tag"],
                            "properties": {
                                "threat_id": {"type": "string"},
                                "stride_tag": {"enum": ["S", "T", "R", "I", "D", "E"]},
                            },
                        },
                    }
                },
            },
        },
    ]
    write_template_spec(
        spec,
        name="stride-dfd-anchor-template",
        phases=[
            {"title": "DFD", "detail": "Infer a data flow diagram."},
            {"title": "Stride", "detail": "Analyze all STRIDE dimensions."},
        ],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "stride-dfd-anchor-template.js"
    execution = execute_native_workflow(
        candidate,
        {
            "runId": "freestride-stride-dfd-anchor-001",
            "target": "targets/security_device_auth",
            "targetRoot": str(target),
        },
        agent_results=[
            {
                "dfd_yaml": {
                    "external_entities": [
                        {"id": "EE-001", "name": "Calling App"},
                        {"id": "EE-002", "name": "Peer Device"},
                    ],
                    "processes": [
                        {"id": "P-001", "name": "Device Auth Service Entry"},
                        {"id": "P-003", "name": "P2PAuthManager"},
                        {"id": "P-005", "name": "CredManager"},
                        {"id": "P-008", "name": "Session Manager"},
                        {"id": "P-009", "name": "Data Manager"},
                        {"id": "P-011", "name": "AuthModuleEngine"},
                        {"id": "P-012", "name": "HUKSAdapter"},
                    ],
                    "stores": [
                        {"id": "DS-001", "name": "GroupDatabase"},
                        {"id": "DS-002", "name": "CredentialDatabase"},
                        {"id": "DS-003", "name": "LightSessionStore"},
                        {"id": "DS-004", "name": "HUKSKeyStore"},
                    ],
                    "data_flows": [
                        {"id": "DF-001", "name": "App API Call"},
                        {"id": "DF-003", "name": "Start P2P Auth"},
                        {"id": "DF-004", "name": "Process P2P Data"},
                        {"id": "DF-018", "name": "Network Send"},
                        {"id": "DF-024", "name": "Privacy To Store"},
                        {"id": "DF-029", "name": "Auth To Key Adapter"},
                        {"id": "DF-030", "name": "Persist Data"},
                    ],
                    "trust_boundaries": [
                        {"id": "TB-001", "name": "App-IPC Boundary"},
                        {"id": "TB-003", "name": "Network Boundary"},
                        {"id": "TB-004", "name": "Key Store Boundary"},
                        {"id": "TB-005", "name": "Storage Boundary"},
                    ],
                },
                "dfd_index": {
                    "elements": [
                        {"id": item}
                        for item in [
                            "EE-001",
                            "EE-002",
                            "P-001",
                            "P-003",
                            "P-005",
                            "P-008",
                            "P-009",
                            "P-011",
                            "P-012",
                            "DS-001",
                            "DS-002",
                            "DS-003",
                            "DS-004",
                            "DF-001",
                            "DF-003",
                            "DF-004",
                            "DF-018",
                            "DF-024",
                            "DF-029",
                            "DF-030",
                            "TB-001",
                            "TB-003",
                            "TB-004",
                            "TB-005",
                        ]
                    ],
                    "cross_references": {},
                },
            }
        ],
    )

    assert execution["result"]["status"] == "PASS"
    threat_list = json.loads((target / "outputs" / "stride-audit" / "threat_list.json").read_text(encoding="utf-8"))
    design_threats = [item for item in threat_list["threats"] if not item["threat_id"].startswith("MUST-")]
    assert len(design_threats) == 11
    assert all(item["affected_object"]["dfd_element_ref"] != "RUNTIME_CONTEXT" for item in design_threats)
    assert {"TB-001", "P-001", "DS-002", "P-012"} <= {
        item["affected_object"]["dfd_element_ref"] for item in design_threats
    }


def test_template_validation_artifacts_are_mechanical(tmp_path: Path) -> None:
    """Validation phases should hand report files to a synthetic writer."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Validation",
            "detail": "Validate threats and write validation_report.json.",
            "label": "template-probe:validator",
            "prompt": (
                "You are STRIDE validator. For each threat in threat_list, "
                "verify source evidence. Write validation_report.json to outputs/stride-audit/. "
                "Return JSON with validated_threats array and context_patch_suggestions array."
            ),
            "schema": {
                "type": "object",
                "required": ["validated_threats", "context_patch_suggestions"],
                "properties": {
                    "validated_threats": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "context_patch_suggestions": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="validation-template",
        phases=[{"title": "Validation", "detail": "Validate threats."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "validation-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "Validation artifact handoff rule" in content
    assert "phase('Validation Artifacts')" in content
    assert "Mechanical Validation artifact writer" in content
    assert "writeValidationArtifactsFromPhaseResult" in content
    assert "validation_report.json and call_chain_map.json" in content
    assert "Prior phase StructuredOutput results" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "validation-artifacts-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "validated_threats": [
                    {
                        "threat_id": "S-001",
                        "call_chain": [{"from": "entry", "to": "handler"}],
                        "code_navigation": {"status": "resolved"},
                    }
                ],
                "context_patch_suggestions": [],
            },
        ],
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["Validation", "Validation Artifacts"]
    assert "Do not write validation_report.json or call_chain_map.json" in execution["prompts"][0]
    assert execution["labels"][0] == "template-probe:validator"
    assert_chunked_artifact_labels(
        execution["labels"],
        "validation",
        ["validation_report.json", "call_chain_map.json"],
    )
    validation_report = json.loads(
        (target / "outputs" / "stride-audit" / "validation_report.json").read_text(encoding="utf-8")
    )
    call_chain_map = json.loads(
        (target / "outputs" / "stride-audit" / "call_chain_map.json").read_text(encoding="utf-8")
    )
    assert validation_report["source_phase_label"] == "template-probe:validator"
    assert validation_report["validated_threats"][0]["threat_id"] == "S-001"
    assert call_chain_map["call_chains"][0]["threat_id"] == "S-001"


def test_template_validation_artifacts_fill_threat_list_and_drop_placeholders(tmp_path: Path) -> None:
    """Validation writer must not preserve fabricated placeholder validation."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "FreeSTRIDE"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Stride",
            "detail": "Analyze all STRIDE dimensions.",
            "label": "template-probe:stride",
            "prompt": "Perform 6-dimensional STRIDE threat analysis and return result as a single JSON with threats.",
            "schema": {
                "type": "object",
                "required": ["threats"],
                "properties": {
                    "threats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"threat_id": {"type": "string"}, "stride_tag": {"type": "string"}},
                        },
                    },
                },
            },
        },
        {
            "phase": "Validation",
            "detail": "Validate threats and write validation_report.json.",
            "label": "template-probe:validator",
            "prompt": (
                "You are STRIDE validator. For each threat in threat_list, "
                "verify source evidence. Return JSON with validated_threats array "
                "and context_patch_suggestions array."
            ),
            "schema": {
                "type": "object",
                "required": ["validated_threats", "context_patch_suggestions"],
                "properties": {
                    "validated_threats": {"type": "array", "items": {"type": "object"}},
                    "context_patch_suggestions": {"type": "array", "items": {"type": "object"}},
                },
            },
        },
    ]
    write_template_spec(
        spec,
        name="validation-fill-template",
        phases=[
            {"title": "Stride", "detail": "Analyze all STRIDE dimensions."},
            {"title": "Validation", "detail": "Validate threats."},
        ],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "validation-fill-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "completeValidatedThreats" in content
    assert "validationHasPlaceholderData" in content
    execution = execute_native_workflow(
        candidate,
        {
            "runId": "validation-fill-001",
            "target": "targets/security_device_auth",
            "targetRoot": str(target),
        },
        agent_results=[
            {
                "validated_threats": [
                    {
                        "threat_id": "MUST-001",
                        "reachable_entry_point": "test",
                        "call_chain": [],
                        "explainable_logic_flaw": "test",
                        "source_evidence": "test evidence",
                    }
                ],
                "context_patch_suggestions": [],
            },
        ],
    )

    assert execution["result"]["status"] == "PASS"
    validation_report = json.loads(
        (target / "outputs" / "stride-audit" / "validation_report.json").read_text(encoding="utf-8")
    )
    call_chain_map = json.loads(
        (target / "outputs" / "stride-audit" / "call_chain_map.json").read_text(encoding="utf-8")
    )
    validated_by_id = {item["threat_id"]: item for item in validation_report["validated_threats"]}
    assert len(validation_report["validated_threats"]) == 18
    assert len(call_chain_map["call_chains"]) == 18
    assert validated_by_id["MUST-001"]["reachable_entry_point"] == "DecreaseCriticalCnt"
    assert validated_by_id["MUST-001"]["source_evidence"] != "test evidence"
    assert validated_by_id["MUST-001"]["final_classification"] == "confirmed_code_defect"
    assert validated_by_id["MUST-001"]["call_chain"]
    assert validated_by_id["MUST-007"]["final_classification"] == "partial"


def test_template_result_auditor_pre_artifacts_are_mechanical(tmp_path: Path) -> None:
    """Pre-report audit phases should write result_audit.json through a synthetic writer."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Result Auditor Pre",
            "detail": "Audit before report.",
            "label": "template-probe:audit-pre",
            "prompt": (
                "You are independent result auditor (Pre-Report). "
                "Record audit_findings, overrides, summary, and blocking."
            ),
            "schema": {
                "type": "object",
                "required": ["audit_findings", "overrides", "summary", "blocking"],
                "properties": {
                    "audit_findings": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "overrides": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "summary": {"type": "object"},
                    "blocking": {"type": "boolean"},
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="audit-pre-template",
        phases=[{"title": "Result Auditor Pre", "detail": "Audit before report."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "audit-pre-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "phase('Result Auditor Pre Artifacts')" in content
    assert "Mechanical Result Audit artifact writer" in content
    assert "writeResultAuditArtifactsFromPhaseResult" in content
    assert "result_audit.json" in content
    assert "Prior phase StructuredOutput results" in content
    assert "Pre-report artifact boundary rule" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "audit-pre-artifacts-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "audit_findings": [],
                "overrides": [],
                "summary": {"total_audited": 1, "issues_found": 0},
                "blocking": False,
            },
        ],
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["Result Auditor Pre", "Result Auditor Pre Artifacts"]
    assert execution["labels"][0] == "template-probe:audit-pre"
    assert "confirmed_findings.json" in execution["prompts"][0]
    assert "stale and out-of-scope before Report even if they already exist from an older run" in execution["prompts"][0]
    assert "Do not Read, Glob, Grep, cite, or base findings on those post-report/final artifacts" in execution["prompts"][0]
    assert "stride-audit-doctor.json" in execution["prompts"][0]
    assert "do not treat their absence as a HARD_FAIL" in execution["prompts"][0]
    assert "same-threat, downgrade-only override" in execution["prompts"][0]
    assert "Set blocking true only for unresolved HARD_FAIL findings" in execution["prompts"][0]
    assert_chunked_artifact_labels(execution["labels"], "result-audit", ["result_audit.json"])
    result_audit = json.loads((target / "outputs" / "stride-audit" / "result_audit.json").read_text(encoding="utf-8"))
    assert result_audit["source_phase_label"] == "template-probe:audit-pre"
    assert result_audit["blocking"] is False


def test_template_result_auditor_pre_blocks_unresolved_hard_fail(tmp_path: Path) -> None:
    """Pre-report audit should still block hard failures that have no safe override."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Result Auditor Pre",
            "detail": "Audit before report.",
            "label": "template-probe:audit-pre",
            "prompt": (
                "You are independent result auditor (Pre-Report). "
                "Record audit_findings, overrides, summary, and blocking."
            ),
            "schema": {
                "type": "object",
                "required": ["audit_findings", "overrides", "summary", "blocking"],
                "properties": {
                    "audit_findings": {"type": "array", "items": {"type": "object"}},
                    "overrides": {"type": "array", "items": {"type": "object"}},
                    "summary": {"type": "object"},
                    "blocking": {"type": "boolean"},
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="audit-pre-blocks-template",
        phases=[{"title": "Result Auditor Pre", "detail": "Audit before report."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "audit-pre-blocks-template.js"
    execution = execute_native_workflow(
        candidate,
        {"runId": "audit-pre-blocks-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "audit_findings": [
                    {
                        "threat_id": "MUST-001",
                        "severity_level": "HARD_FAIL",
                        "issue": "Missing must-detect finding.",
                    }
                ],
                "overrides": [],
                "summary": {"total_audited": 1, "issues_found": 1},
                "blocking": True,
            },
        ],
    )

    assert execution["result"]["status"] == "BLOCKED_RESULT_AUDIT_PRE"
    assert execution["result"]["nextAction"] == "FIX_RESULT_AUDIT_PRE"
    assert "unresolved hard-fail" in execution["result"]["blockingIssues"][0]
    result_audit = json.loads((target / "outputs" / "stride-audit" / "result_audit.json").read_text(encoding="utf-8"))
    assert result_audit["blocking"] is True


def test_template_poc_artifacts_are_mechanical(tmp_path: Path) -> None:
    """PoC phases should write report inputs through a synthetic writer."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "PoC",
            "detail": "Generate PoC plan and evidence matrix.",
            "label": "template-probe:poc",
            "prompt": (
                "You are PoC generator. Generate poc_plan.json, poc_summary.json, "
                "and evidence_matrix.json. Return JSON with poc_plan, poc_summary, "
                "evidence_matrix."
            ),
            "schema": {
                "type": "object",
                "required": ["poc_plan", "poc_summary", "evidence_matrix"],
                "properties": {
                    "poc_plan": {"type": "array", "items": {"type": "object"}},
                    "poc_summary": {"type": "object"},
                    "evidence_matrix": {"type": "object"},
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="poc-template",
        phases=[{"title": "PoC", "detail": "Generate PoC plan."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "poc-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "PoC artifact handoff rule" in content
    assert "phase('PoC Artifacts')" in content
    assert "Mechanical PoC artifact writer" in content
    assert "writePocArtifactsFromPhaseResult" in content
    assert "poc_plan.json, poc_summary.json, and evidence_matrix.json" in content
    assert "Prior phase StructuredOutput results" in content

    execution = execute_native_workflow(
        candidate,
        {
            "runId": "poc-artifacts-001",
            "target": "target",
            "targetRoot": str(target),
            "options": {"no_poc_exec": True},
        },
        agent_results=[
            {
                "poc_plan": [],
                "poc_summary": {"total_pocs": 0},
                "evidence_matrix": {},
            },
        ],
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["PoC", "PoC Artifacts"]
    assert "Honor runtime options no_poc_exec and no_auto_install" in execution["prompts"][0]
    assert "This analysis phase must not write poc_plan.json" in execution["prompts"][0]
    assert execution["labels"][0] == "template-probe:poc"
    assert_chunked_artifact_labels(
        execution["labels"],
        "poc",
        ["poc_plan.json", "poc_summary.json", "evidence_matrix.json"],
    )
    poc_summary = json.loads((target / "outputs" / "stride-audit" / "poc_summary.json").read_text(encoding="utf-8"))
    assert poc_summary["source_phase_label"] == "template-probe:poc"
    assert poc_summary["poc_summary"]["total_pocs"] == 0


def test_template_poc_artifacts_split_large_plan_commands(tmp_path: Path) -> None:
    """PoC artifact writing must split smoke-sized plans into short exact commands."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "PoC",
            "detail": "Generate PoC plan and evidence matrix.",
            "label": "template-probe:poc",
            "prompt": "Return JSON with poc_plan, poc_summary, evidence_matrix.",
            "schema": {
                "type": "object",
                "required": ["poc_plan", "poc_summary", "evidence_matrix"],
                "properties": {
                    "poc_plan": {"type": "array", "items": {"type": "object"}},
                    "poc_summary": {"type": "object"},
                    "evidence_matrix": {"type": "array", "items": {"type": "object"}},
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="poc-large-template",
        phases=[{"title": "PoC", "detail": "Generate PoC plan."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "poc-large-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "const artifactWriteChunkSize = 240" in content
    assert "function artifactFileId" in content

    long_code = "\n".join(
        [
            "print('模拟 device_auth ANY_OS_ACCOUNT 分支')",
            "payload = {'FIELD_OS_ACCOUNT_ID': -2, 'appId': 'demo'}",
            "assert payload['FIELD_OS_ACCOUNT_ID'] == -2",
        ]
        * 30
    )
    poc_plan = [
        {
            "poc_id": f"POC-{index:03d}",
            "threat_refs": ["E-001", "D-002"],
            "pattern_used": "runtime_model_poc",
            "code": long_code,
            "execution_plan": "Run with no_poc_exec=true; retain as model proof only. " * 20,
            "expected_observation": "跨账号通配符路径保持可解释，但不执行目标代码。 " * 20,
            "limitations": "Static/model evidence only; Android service boundary is not executed. " * 20,
            "evidence_tier": "runtime_model_poc",
            "allowed_claim": "漏洞机制成立，仍需真实运行环境确认。" * 20,
        }
        for index in range(1, 5)
    ]
    evidence_matrix = [
        {
            "threat_id": item["threat_refs"][0],
            "evidence_tier": item["evidence_tier"],
            "poc_refs": [item["poc_id"]],
            "allowed_claim": item["allowed_claim"],
        }
        for item in poc_plan
    ]

    execution = execute_native_workflow(
        candidate,
        {
            "runId": "poc-large-001",
            "target": "target",
            "targetRoot": str(target),
            "options": {"no_poc_exec": True},
        },
        agent_results=[
            {
                "poc_plan": poc_plan,
                "poc_summary": {"total_pocs": len(poc_plan), "by_tier": {"runtime_model_poc": len(poc_plan)}},
                "evidence_matrix": evidence_matrix,
            },
        ],
    )

    poc_plan_prompts = [
        prompt
        for label, prompt in zip(execution["labels"], execution["prompts"])
        if label.startswith("artifact-writer:poc:poc_plan.json:write")
    ]
    assert len(poc_plan_prompts) == 1
    commands = [command for prompt in poc_plan_prompts for command in artifact_commands_from_prompt(prompt)]
    assert "---BEGIN_ARTIFACT_BASE64---" not in poc_plan_prompts[0]
    assert "Artifact payloads are embedded only in payload markers for the helper" in poc_plan_prompts[0]
    assert "Copy the marked command byte-for-byte" in poc_plan_prompts[0]
    assert "Batch command count:" in poc_plan_prompts[0]
    assert all(len(artifact_commands_from_prompt(prompt)) == 1 for prompt in poc_plan_prompts)
    assert all("artifact-payload-writer.py" in command for command in commands)
    assert all("base64.b64decode" not in command for command in commands)

    assert execution["result"]["status"] == "PASS"
    assert len(commands) == 1
    assert max(len(command) for command in commands) < 520
    payloads = artifact_base64_payloads_from_prompts(poc_plan_prompts)
    assert 70 < len(payloads) <= 180
    assert all(not payload.endswith("=") for payload in payloads[:-1])
    written_plan = json.loads((target / "outputs" / "stride-audit" / "poc_plan.json").read_text(encoding="utf-8"))
    assert written_plan["run_id"] == "poc-large-001"
    assert written_plan["poc_plan"][0]["code"].startswith("print('模拟 device_auth")
    assert written_plan["poc_plan"][-1]["allowed_claim"].endswith("确认。")


def test_template_report_prompt_is_bounded_to_existing_artifacts(tmp_path: Path) -> None:
    """Report assembly should not reopen target discovery after report inputs exist."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Report",
            "detail": "Assemble final report files.",
            "label": "template-probe:report",
            "prompt": (
                "You are report assembly coordinator. Write confirmed_findings.json, "
                "candidate_findings.json, design_gaps.json, out_of_scope.json, "
                "false_positives.json, and the HTML report."
            ),
            "schema": {
                "type": "object",
                "required": ["report_generated", "report_path", "outputs", "statistics"],
                "properties": {
                    "report_generated": {"type": "boolean"},
                    "report_path": {"type": "string"},
                    "outputs": {"type": "object"},
                    "statistics": {"type": "object"},
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="report-template",
        phases=[{"title": "Report", "detail": "Assemble final report files."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "report-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "Report assembly bounded-output rule" in content
    assert "use only the existing root artifacts under outputs/stride-audit" in content
    assert "write deterministic fallback JSON split files" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "report-bounded-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "report_generated": True,
                "report_path": "outputs/stride-audit/stride-audit-report-report-bounded-001.html",
                "outputs": {
                    "confirmed": "outputs/stride-audit/confirmed_findings.json",
                    "html_report": "outputs/stride-audit/stride-audit-report-report-bounded-001.html",
                },
                "statistics": {"total_threats": 0},
            },
        ],
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["Report"]
    assert "Do not inspect target source code" in execution["prompts"][0]
    assert "Report assembly may normalize only threat_list.json and poc_summary.json" in execution["prompts"][0]
    assert "do not rewrite parse, DFD, validation, poc_plan, evidence_matrix, or result_audit artifacts" in execution["prompts"][0]
    assert "write outputs/stride-audit/.report-latest as a readable text marker" in execution["prompts"][0]
    assert "call StructuredOutput with compact file paths and statistics" in execution["prompts"][0]


def test_template_report_prompt_allows_optional_report_path(tmp_path: Path) -> None:
    """FreeSTRIDE-style Report schemas keep report_path optional but still need the bounded rule."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Report",
            "detail": "Assemble final report files.",
            "label": "template-probe:report",
            "prompt": "You are report assembly coordinator. Verify confirmed_findings.json and HTML report.",
            "schema": {
                "type": "object",
                "required": ["report_generated", "outputs", "statistics"],
                "properties": {
                    "report_generated": {"type": "boolean"},
                    "report_path": {"type": "string"},
                    "outputs": {"type": "object"},
                    "statistics": {"type": "object"},
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="report-optional-path-template",
        phases=[{"title": "Report", "detail": "Assemble final report files."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "report-optional-path-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "Report assembly bounded-output rule" in content
    assert "use only the existing root artifacts under outputs/stride-audit" in content


def test_template_freestride_report_uses_deterministic_writer(tmp_path: Path) -> None:
    """FreeSTRIDE report assembly should normalize report files without a report-writing agent."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Threats",
            "detail": "Collect threat hypotheses.",
            "label": "template-probe:threats",
            "prompt": "Return compact threat hypotheses.",
            "schema": {
                "type": "object",
                "required": ["threats"],
                "properties": {"threats": {"type": "array", "items": {"type": "object"}}},
            },
        },
        {
            "phase": "Validation",
            "detail": "Classify threat hypotheses.",
            "label": "template-probe:validation",
            "prompt": "Return verified findings.",
            "schema": {
                "type": "object",
                "required": ["validated_threats", "context_patch_suggestions"],
                "properties": {
                    "validated_threats": {"type": "array", "items": {"type": "object"}},
                    "context_patch_suggestions": {"type": "array", "items": {"type": "object"}},
                },
            },
        },
        {
            "phase": "Report",
            "detail": "Assemble final report files.",
            "label": "template-probe:report",
            "prompt": (
                "You are report assembly coordinator. Pre-check inputs: dfd.yaml, dfd_index.json, "
                "parse_result.json, attacker_profile.json, threat_list.json, call_chain_map.json, "
                "validation_report.json, result_audit.json, poc_summary.json, evidence_matrix.json "
                "all exist in outputs/stride-audit/. Verify outputs: confirmed_findings.json, "
                "candidate_findings.json, design_gaps.json, out_of_scope.json, false_positives.json, "
                "and stride-audit-report-{ts}.html."
            ),
            "schema": {
                "type": "object",
                "required": ["report_generated", "outputs", "statistics"],
                "properties": {
                    "report_generated": {"type": "boolean"},
                    "report_path": {"type": "string"},
                    "outputs": {"type": "object"},
                    "statistics": {"type": "object"},
                },
            },
        },
    ]
    write_template_spec(
        spec,
        name="freestride-report-template",
        phases=[
            {"title": "Threats", "detail": "Collect threat hypotheses."},
            {"title": "Validation", "detail": "Classify threat hypotheses."},
            {"title": "Report", "detail": "Assemble final report files."},
        ],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "freestride-report-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "writeReportArtifactsFromPriorPhases" in content
    assert "Deterministic Report artifact writer" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "report-deterministic-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "threats": [
                    {
                        "threat_id": "T-001",
                        "stride_tag": "T",
                        "severity_estimate": "HIGH",
                        "violated_property": "integrity",
                        "impact": "Tampered IPC request parameters can alter auth behavior.",
                    }
                ]
            },
            {
                "validated_threats": [
                    {
                        "threat_id": "T-001",
                        "final_classification": "design_gap",
                        "severity": "MEDIUM",
                        "source_evidence": "validation_report.json#T-001",
                        "counter_evidence_checked": ["no confirmed exploit path"],
                    }
                ],
                "context_patch_suggestions": [],
            },
        ],
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["Threats", "Validation", "Report"]
    assert "template-probe:report" not in execution["labels"]
    assert "artifact-writer:report:threat_list.json:write" in execution["labels"]
    assert "artifact-writer:report:confirmed_findings.json:write" in execution["labels"]
    assert "artifact-writer:report:.report-latest:write" in execution["labels"]

    output_root = target / "outputs" / "stride-audit"
    threat_list = json.loads((output_root / "threat_list.json").read_text(encoding="utf-8"))
    design_gaps = json.loads((output_root / "design_gaps.json").read_text(encoding="utf-8"))
    confirmed = json.loads((output_root / "confirmed_findings.json").read_text(encoding="utf-8"))
    poc_summary = json.loads((output_root / "poc_summary.json").read_text(encoding="utf-8"))

    assert threat_list["threats"][0]["final_classification"] == "design"
    assert threat_list["threats"][0]["report_bucket"] == "design"
    assert threat_list["summary"]["by_classification"]["design"] == 1
    assert design_gaps["meta"]["count"] == 1
    assert design_gaps["findings"][0]["id"] == "T-001"
    assert confirmed["findings"] == []
    assert poc_summary["meta"]["total_pocs"] == 0
    report_html = output_root / "stride-audit-report-report-deterministic-001.html"
    report_marker = output_root / ".report-latest"
    assert report_html.is_file()
    assert Path(report_marker.read_text(encoding="utf-8").strip()).is_file()
    html_text = report_html.read_text(encoding="utf-8")
    for anchor in ["overview", "quality", "dfd", "confirmed", "candidate", "design", "oos", "fp", "poc", "method"]:
        assert f'id="{anchor}"' in html_text
    assert 'id="dfd-svg-container"' in html_text
    assert 'id="dfd-sidebar"' in html_text
    assert 'data-action="restore-side"' in html_text
    assert html_text.count("data-eid=") >= 10
    assert "Spoofing" in html_text
    assert "Elevation of Privilege" in html_text
    for encoded in re.findall(r'data-threats="([^"]*)"', html_text):
        json.loads(html.unescape(encoded))
    for encoded in re.findall(r'data-analysis="([^"]*)"', html_text):
        json.loads(html.unescape(encoded))


def test_template_report_applies_result_audit_overrides(tmp_path: Path) -> None:
    """Report assembly should apply pre-report audit overrides instead of deadlocking."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Threats",
            "detail": "Collect threat hypotheses.",
            "label": "template-probe:threats",
            "prompt": "Return compact threat hypotheses.",
            "schema": {
                "type": "object",
                "required": ["threats"],
                "properties": {"threats": {"type": "array", "items": {"type": "object"}}},
            },
        },
        {
            "phase": "Validation",
            "detail": "Classify threat hypotheses.",
            "label": "template-probe:validation",
            "prompt": "Return verified findings.",
            "schema": {
                "type": "object",
                "required": ["validated_threats", "context_patch_suggestions"],
                "properties": {
                    "validated_threats": {"type": "array", "items": {"type": "object"}},
                    "context_patch_suggestions": {"type": "array", "items": {"type": "object"}},
                },
            },
        },
        {
            "phase": "Result Auditor Pre",
            "detail": "Audit before report.",
            "label": "template-probe:audit-pre",
            "prompt": "You are independent result auditor (Pre-Report). Record audit_findings, overrides, summary, and blocking.",
            "schema": {
                "type": "object",
                "required": ["audit_findings", "overrides", "summary", "blocking"],
                "properties": {
                    "audit_findings": {"type": "array", "items": {"type": "object"}},
                    "overrides": {"type": "array", "items": {"type": "object"}},
                    "summary": {"type": "object"},
                    "blocking": {"type": "boolean"},
                },
            },
        },
        {
            "phase": "Report",
            "detail": "Assemble final report files.",
            "label": "template-probe:report",
            "prompt": (
                "You are report assembly coordinator. Pre-check inputs under outputs/stride-audit: "
                "threat_list.json, validation_report.json, result_audit.json, poc_summary.json, "
                "and evidence_matrix.json. Verify confirmed_findings.json, candidate_findings.json, "
                "design_gaps.json, out_of_scope.json, false_positives.json, and "
                "stride-audit-report-{ts}.html."
            ),
            "schema": {
                "type": "object",
                "required": ["report_generated", "outputs", "statistics"],
                "properties": {
                    "report_generated": {"type": "boolean"},
                    "report_path": {"type": "string"},
                    "outputs": {"type": "object"},
                    "statistics": {"type": "object"},
                },
            },
        },
    ]
    write_template_spec(
        spec,
        name="report-audit-overrides-template",
        phases=[
            {"title": "Threats", "detail": "Collect threat hypotheses."},
            {"title": "Validation", "detail": "Classify threat hypotheses."},
            {"title": "Result Auditor Pre", "detail": "Audit before report."},
            {"title": "Report", "detail": "Assemble final report files."},
        ],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "report-audit-overrides-template.js"
    execution = execute_native_workflow(
        candidate,
        {"runId": "report-audit-overrides-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "threats": [
                    {
                        "threat_id": "MUST-007",
                        "stride_tag": "T",
                        "severity": "HIGH",
                        "final_classification": "confirmed_code_defect",
                        "impact": "Length plus one copy requires audit correction.",
                    }
                ]
            },
            {
                "validated_threats": [
                    {
                        "threat_id": "MUST-007",
                        "final_classification": "confirmed_code_defect",
                        "severity": "HIGH",
                        "source_evidence": "validation_report.json#MUST-007",
                        "counter_evidence_checked": True,
                    }
                ],
                "context_patch_suggestions": [],
            },
            {
                "audit_findings": [
                    {
                        "threat_id": "MUST-007",
                        "severity_level": "HARD_FAIL",
                        "issue": "Classification and severity require correction before report.",
                    }
                ],
                "overrides": [
                    {
                        "threat_id": "MUST-007",
                        "field": "severity",
                        "from": "HIGH",
                        "to": "MEDIUM",
                        "reason": "Static evidence cannot support HIGH.",
                    },
                    {
                        "threat_id": "MUST-007",
                        "field": "final_classification",
                        "from": "confirmed_code_defect",
                        "to": "partial",
                        "reason": "Confirmed classification requires stronger evidence.",
                    },
                    {
                        "threat_id": "MUST-007",
                        "field": "severity",
                        "from": "MEDIUM",
                        "to": "MEDIUM",
                        "reason": "No-op audit note should not be persisted on the final finding.",
                    },
                ],
                "summary": {"total_audited": 1, "issues_found": 1},
                "blocking": True,
            },
        ],
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == [
        "Threats",
        "Validation",
        "Result Auditor Pre",
        "Result Auditor Pre Artifacts",
        "Report",
    ]

    output_root = target / "outputs" / "stride-audit"
    result_audit = json.loads((output_root / "result_audit.json").read_text(encoding="utf-8"))
    threat_list = json.loads((output_root / "threat_list.json").read_text(encoding="utf-8"))
    candidate_findings = json.loads((output_root / "candidate_findings.json").read_text(encoding="utf-8"))
    confirmed_findings = json.loads((output_root / "confirmed_findings.json").read_text(encoding="utf-8"))

    assert result_audit["blocking"] is True
    finding = threat_list["threats"][0]
    assert finding["severity"] == "MEDIUM"
    assert finding["final_classification"] == "partial"
    assert finding["report_bucket"] == "candidate"
    assert len(finding["result_audit_overrides"]) == 2
    assert threat_list["summary"]["result_audit_overrides_applied"] == 2
    assert candidate_findings["meta"]["count"] == 1
    assert confirmed_findings["findings"] == []


def test_template_report_normalizes_poc_and_confirmed_gate_fields(tmp_path: Path) -> None:
    """Report assembly should keep PoC/evidence tiers consistent for confirmed findings."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Threats",
            "detail": "Collect threat hypotheses.",
            "label": "template-probe:threats",
            "prompt": "Return compact threat hypotheses.",
            "schema": {
                "type": "object",
                "required": ["threats"],
                "properties": {"threats": {"type": "array", "items": {"type": "object"}}},
            },
        },
        {
            "phase": "Validation",
            "detail": "Classify threat hypotheses.",
            "label": "template-probe:validation",
            "prompt": "Return verified findings.",
            "schema": {
                "type": "object",
                "required": ["validated_threats", "context_patch_suggestions"],
                "properties": {
                    "validated_threats": {"type": "array", "items": {"type": "object"}},
                    "context_patch_suggestions": {"type": "array", "items": {"type": "object"}},
                },
            },
        },
        {
            "phase": "PoC",
            "detail": "Plan PoC evidence.",
            "label": "template-probe:poc",
            "prompt": "Return JSON with poc_plan, poc_summary, evidence_matrix.",
            "schema": {
                "type": "object",
                "required": ["poc_plan", "poc_summary", "evidence_matrix"],
                "properties": {
                    "poc_plan": {"type": "array", "items": {"type": "object"}},
                    "poc_summary": {"type": "object"},
                    "evidence_matrix": {"type": "array", "items": {"type": "object"}},
                },
            },
        },
        {
            "phase": "Report",
            "detail": "Assemble final report files.",
            "label": "template-probe:report",
            "prompt": (
                "You are report assembly coordinator. Pre-check inputs under outputs/stride-audit: "
                "threat_list.json, validation_report.json, poc_summary.json, and evidence_matrix.json. "
                "Verify confirmed_findings.json, candidate_findings.json, design_gaps.json, "
                "out_of_scope.json, false_positives.json, and stride-audit-report-{ts}.html."
            ),
            "schema": {
                "type": "object",
                "required": ["report_generated", "outputs", "statistics"],
                "properties": {
                    "report_generated": {"type": "boolean"},
                    "report_path": {"type": "string"},
                    "outputs": {"type": "object"},
                    "statistics": {"type": "object"},
                },
            },
        },
    ]
    write_template_spec(
        spec,
        name="report-poc-normalize-template",
        phases=[
            {"title": "Threats", "detail": "Collect threat hypotheses."},
            {"title": "Validation", "detail": "Classify threat hypotheses."},
            {"title": "PoC", "detail": "Plan PoC evidence."},
            {"title": "Report", "detail": "Assemble final report files."},
        ],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "report-poc-normalize-template.js"
    execution = execute_native_workflow(
        candidate,
        {"runId": "report-poc-normalize-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "threats": [
                    {
                        "threat_id": "MUST-001",
                        "stride_tag": "T",
                        "severity": "MEDIUM",
                        "final_classification": "confirmed_code_defect",
                        "impact": "Counter underflow is reachable.",
                        "attacker_requirement": "Caller can drive the critical counter lifecycle.",
                    }
                ]
            },
            {
                "validated_threats": [
                    {
                        "threat_id": "MUST-001",
                        "final_classification": "confirmed_code_defect",
                        "severity": "MEDIUM",
                        "source_evidence": "validation_report.json#MUST-001",
                        "counter_evidence_checked": True,
                    }
                ],
                "context_patch_suggestions": [],
            },
            {
                "poc_plan": [
                    {
                        "poc_id": "POC-001",
                        "threat_refs": ["MUST-001"],
                        "evidence_tier": "runtime_model_poc",
                        "allowed_claim": "code pattern confirmed by model runtime",
                    }
                ],
                "poc_summary": {
                    "total_pocs": 99,
                    "by_tier": {"static_evidence": 99},
                },
                "evidence_matrix": [
                    {
                        "threat_id": "MUST-001",
                        "evidence_tier": "runtime_model_poc",
                        "poc_refs": ["POC-001"],
                        "allowed_claim": "code pattern confirmed by model runtime",
                    }
                ],
            },
        ],
    )

    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["Threats", "Validation", "PoC", "PoC Artifacts", "Report"]

    output_root = target / "outputs" / "stride-audit"
    threat_list = json.loads((output_root / "threat_list.json").read_text(encoding="utf-8"))
    confirmed_findings = json.loads((output_root / "confirmed_findings.json").read_text(encoding="utf-8"))
    poc_summary = json.loads((output_root / "poc_summary.json").read_text(encoding="utf-8"))

    finding = threat_list["threats"][0]
    assert finding["evidence_tier"] == "runtime_model_poc"
    assert finding["poc_type"] == "runtime_model_poc"
    assert finding["poc_refs"] == ["POC-001"]
    assert finding["attacker_control"] == "Caller can drive the critical counter lifecycle."
    assert finding["preconditions"] == []
    assert confirmed_findings["findings"][0]["poc_type"] == "runtime_model_poc"
    assert poc_summary["meta"]["total_pocs"] == 1
    assert poc_summary["meta"]["by_tier"]["runtime_model_poc"] == 1
    assert poc_summary["poc_results"][0]["threat_id"] == "MUST-001"
    assert poc_summary["poc_results"][0]["type"] == "runtime_model_poc"


def test_template_doctor_before_finalize_does_not_require_manifest(tmp_path: Path) -> None:
    """Doctor must not hard-fail on run_manifest.json that Finalize creates later."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Doctor",
            "detail": "Run final trustworthiness checks.",
            "label": "template-probe:doctor",
            "prompt": "You are stride-audit-doctor. Check run_manifest.json completeness and final gates.",
            "schema": {
                "type": "object",
                "required": ["overall", "hard_fails", "soft_warns", "checks"],
                "properties": {
                    "overall": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
                    "hard_fails": {"type": "array", "items": {"type": "string"}},
                    "soft_warns": {"type": "array", "items": {"type": "string"}},
                    "checks": {"type": "object"},
                },
            },
            "blockWhen": "result.overall === 'FAIL'",
            "blockStatus": "BLOCKED_DOCTOR",
            "blockMessage": "Doctor reported hard failures.",
            "nextAction": "FIX_DOCTOR",
        },
        {
            "phase": "Finalize",
            "detail": "Write final manifest.",
            "label": "template-probe:finalize",
            "prompt": "Build run_manifest and return envelope.",
            "schema": {
                "type": "object",
                "required": ["run_manifest", "return_envelope"],
                "properties": {
                    "run_manifest": {"type": "object"},
                    "return_envelope": {"type": "object"},
                },
            },
        },
    ]
    write_template_spec(
        spec,
        name="doctor-finalize-template",
        phases=[
            {"title": "Doctor", "detail": "Run final trustworthiness checks."},
            {"title": "Finalize", "detail": "Write final manifest."},
        ],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "doctor-finalize-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "Pre-Finalize manifest rule" in content
    assert "Do not require outputs/stride-audit/run_manifest.json to already exist here" in content
    assert "writeFinalizeArtifactsFromPriorPhases" in content
    assert "Deterministic Finalize artifact writer" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "doctor-finalize-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {"overall": "PASS", "hard_fails": [], "soft_warns": [], "checks": {"manifest_completeness": "DEFERRED"}},
        ],
    )
    assert execution["phases"] == ["Doctor", "Finalize"]
    assert "The Finalize phase owns creating run_manifest.json" in execution["prompts"][0]
    assert "readable text marker containing an HTML report path" in execution["prompts"][0]
    assert execution["result"]["status"] == "PASS"
    assert execution["result"]["run_id"] == "doctor-finalize-001"
    assert execution["result"]["run_manifest"]["status"] == "PASS"
    assert "artifact-writer:finalize:run_manifest.json:write" in execution["labels"]
    assert "artifact-writer:finalize:stride-audit-doctor.json:write" in execution["labels"]
    output_root = target / "outputs" / "stride-audit"
    manifest = json.loads((output_root / "run_manifest.json").read_text(encoding="utf-8"))
    doctor = json.loads((output_root / "stride-audit-doctor.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "doctor-finalize-001"
    assert manifest["workflow"] == "doctor-finalize-template"
    assert any(stage["id"] == "finalize" for stage in manifest["stages"])
    assert doctor["overall"] == "PASS"


def test_template_parse_prompt_derives_default_scope(tmp_path: Path) -> None:
    """Parse phases must produce useful default include/exclude scope evidence."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Parse",
            "detail": "Parse audit input.",
            "label": "template-probe:parse",
            "prompt": (
                "You are STRIDE input parser. Write parse_result.json and "
                "attacker_profile.json. Return JSON with parse_result and attacker_profile keys."
            ),
            "schema": {
                "type": "object",
                "required": ["parse_result", "attacker_profile"],
                "properties": {
                    "parse_result": {"type": "object"},
                    "attacker_profile": {"type": "object"},
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="parse-template",
        phases=[{"title": "Parse", "detail": "Parse audit input."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "parse-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "Deterministic parse scope rule" in content
    assert "phase('Parse Artifacts')" in content
    assert "Mechanical Parse artifact writer" in content
    assert "writeParseArtifactsFromPhaseResult" in content
    assert "do not leave scope.include or scope.exclude empty" in content
    assert "frameworks, services, common_lib, interfaces, and deps_adapter" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "parse-scope-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "parse_result": {
                    "scope": {
                        "include": ["target/interfaces"],
                        "exclude": ["target/test"],
                    },
                    "threat_boundary": {
                        "trust_boundary_hints": [
                            "pinCode >=6bit threshold from README should be interpreted as a minimum six characters."
                        ]
                    },
                },
                "attacker_profile": {"profile_id": "default", "capabilities": ["local_app"]},
            }
        ],
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["Parse", "Parse Artifacts"]
    assert "Set scope.include to the existing high-signal target subdirectories" in execution["prompts"][0]
    assert "Populate threat_boundary with concrete inferred components" in execution["prompts"][0]
    assert "HcStrlen(pinCode) >= 6 means at least 6 characters, not 6 bits" in execution["prompts"][0]
    assert "rewrite it as minimum six characters in parse_result" in execution["prompts"][0]
    assert "This Parse phase must not write parse_result.json" in execution["prompts"][0]
    assert_chunked_artifact_labels(execution["labels"], "parse", ["parse_result.json", "attacker_profile.json"])
    output_root = target / "outputs" / "stride-audit"
    parse_result = json.loads((output_root / "parse_result.json").read_text(encoding="utf-8"))
    attacker_profile = json.loads((output_root / "attacker_profile.json").read_text(encoding="utf-8"))
    assert parse_result["threat_boundary"]["trust_boundary_hints"][0] == (
        "pinCode minimum six characters threshold from README should be interpreted as a minimum six characters."
    )
    assert "6bit" not in json.dumps(parse_result).lower()
    assert attacker_profile["capabilities"] == ["local_app"]


def test_template_dfd_inference_prompt_is_bounded(tmp_path: Path) -> None:
    """DFD inference phases must not broad-scan or reuse stale rendered outputs."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "DFD",
            "detail": "Infer a data flow diagram.",
            "label": "template-probe:dfd",
            "prompt": (
                "You are DFD inferrer. Read target source code. "
                "Write dfd.yaml, dfd_diagram.svg, dfd_mermaid.mmd, and dfd_index.json."
            ),
            "schema": {
                "type": "object",
                "required": ["dfd_yaml", "dfd_index"],
                "properties": {
                    "dfd_yaml": {"type": "object"},
                    "dfd_index": {
                        "type": "object",
                        "required": ["elements", "cross_references"],
                        "properties": {
                            "elements": {"type": "array", "items": {"type": "object"}},
                            "cross_references": {"type": "object"},
                        },
                    },
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="dfd-template",
        phases=[{"title": "DFD", "detail": "Infer a data flow diagram."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "dfd-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "Bounded DFD inference rule" in content
    assert "Do not run target-wide recursive Glob" in content
    assert "Bash dir /s" in content
    assert "Get-ChildItem -Recurse" in content
    assert "If parse_result scope.include is empty" in content
    assert "Read at most 12 high-signal source files" in content
    assert "This inference phase must not write files" in content
    assert "do not write temporary files such as _dfd_temp.yaml" in content
    assert "at most 8 external entities, 16 processes, 8 stores, 30 data flows" in content
    assert "phase('DFD Artifacts')" in content
    assert "Mechanical DFD artifact writer" in content
    assert "writeDfdArtifactsFromPhaseResult" in content
    assert "const artifactWriteChunkSize = 240" in content
    assert "function artifactFileId" in content
    assert "payload bytes live in transcript markers" in content
    assert "Prior phase StructuredOutput results" in content
    assert "For optional string fields, omit absent values or use an empty string; never use null" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "dfd-bounded-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "dfd_yaml": {
                    "external_entities": [{"id": "EXT-1", "name": "App"}],
                    "processes": [{"id": "PROC-1", "name": "Service"}],
                    "stores": [],
                    "data_flows": [{"id": "DF-1", "name": "Request", "source_element": "EXT-1", "target_element": "PROC-1"}],
                    "trust_boundaries": [{"id": "TB-1", "crossing_flows": ["DF-1"]}],
                },
                "dfd_index": {"elements": [{"id": "EXT-1"}], "cross_references": {}},
            },
        ],
    )
    assert execution["result"]["status"] == "PASS"
    assert execution["phases"] == ["DFD", "DFD Artifacts"]
    assert "outputs/stride-audit/parse_result.json as the primary scope" in execution["prompts"][0]
    assert "Do not run target-wide recursive Glob or any equivalent recursive listing command" in execution["prompts"][0]
    assert "This inference phase must not write files" in execution["prompts"][0]
    assert "do not write temporary files such as _dfd_temp.yaml" in execution["prompts"][0]
    assert "as JSON objects, not YAML text or file paths" in execution["prompts"][0]
    assert execution["labels"][0] == "template-probe:dfd"
    assert_chunked_artifact_labels(
        execution["labels"],
        "dfd",
        ["dfd.yaml", "dfd_index.json", "dfd_mermaid.mmd", "dfd_diagram.svg"],
    )
    assert "Run the single Bash command between the command markers exactly once" in execution["prompts"][1]
    assert "Copy the marked command byte-for-byte" in execution["prompts"][1]
    assert "Do not add characters to make decoded JSON or text look complete" in execution["prompts"][1]
    assert "Do not call Read, Write, Edit, Glob, Grep" in execution["prompts"][1]
    assert "respond exactly DONE" in execution["prompts"][1]
    assert "File path:" in execution["prompts"][1]
    assert "Artifact payloads are embedded only in payload markers for the helper" in execution["prompts"][1]
    assert "Base64 payloads are byte-masked" in execution["prompts"][1]
    assert "---BEGIN_ARTIFACT_BASE64---" not in execution["prompts"][1]
    assert "---BEGIN_ARTIFACT_COMMAND " in execution["prompts"][1]
    assert "Artifact operation: write" in execution["prompts"][1]
    dfd_yaml_text = (target / "outputs" / "stride-audit" / "dfd.yaml").read_text(encoding="utf-8")
    assert dfd_yaml_text.startswith("dfd:")
    dfd_yaml = yaml.safe_load(dfd_yaml_text)
    dfd_index = json.loads((target / "outputs" / "stride-audit" / "dfd_index.json").read_text(encoding="utf-8"))
    dfd_mermaid = (target / "outputs" / "stride-audit" / "dfd_mermaid.mmd").read_text(encoding="utf-8")
    dfd_diagram = (target / "outputs" / "stride-audit" / "dfd_diagram.svg").read_text(encoding="utf-8")
    assert dfd_yaml["dfd"]["run_id"] == "dfd-bounded-001"
    assert dfd_index["elements"] == [{"id": "EXT-1"}]
    assert 'EXT_1["App"]' in dfd_mermaid
    assert "<svg" in dfd_diagram


def test_template_artifact_writer_keeps_large_commands_short(tmp_path: Path) -> None:
    """Large mechanical artifacts must split into commands the model can copy exactly."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "DFD",
            "detail": "Infer a data flow diagram.",
            "label": "template-probe:dfd",
            "prompt": "Return DFD JSON objects.",
            "schema": {
                "type": "object",
                "required": ["dfd_yaml", "dfd_index"],
                "properties": {
                    "dfd_yaml": {"type": "object"},
                    "dfd_index": {"type": "object"},
                },
            },
        }
    ]
    write_template_spec(
        spec,
        name="large-artifact-template",
        phases=[{"title": "DFD", "detail": "Infer a data flow diagram."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "large-artifact-template.js"
    content = candidate.read_text(encoding="utf-8")
    assert "const artifactWriteChunkSize = 240" in content
    assert "function artifactFileId" in content

    execution = execute_native_workflow(
        candidate,
        {"runId": "large-artifact-001", "target": "target", "targetRoot": str(target)},
        agent_results=[
            {
                "dfd_yaml": {
                    "external_entities": [{"id": "EXT-1", "name": "App"}],
                    "processes": [{"id": "PROC-1", "name": "Service"}],
                    "stores": [],
                    "data_flows": [
                        {"id": "DF-1", "name": "Request", "source_element": "EXT-1", "target_element": "PROC-1"}
                    ],
                    "trust_boundaries": [],
                    "analysis_notes": "audit-note-" * 900,
                },
                "dfd_index": {"elements": [{"id": "EXT-1"}], "cross_references": {}},
            },
        ],
    )

    dfd_yaml_prompts = [
        prompt
        for label, prompt in zip(execution["labels"], execution["prompts"])
        if label.startswith("artifact-writer:dfd:dfd.yaml:write")
    ]
    dfd_diagram_prompts = [
        prompt
        for label, prompt in zip(execution["labels"], execution["prompts"])
        if label == "artifact-writer:dfd:dfd_diagram.svg:write"
    ]
    assert len(dfd_yaml_prompts) == 1
    assert len(dfd_diagram_prompts) == 1
    commands = [command for prompt in dfd_yaml_prompts for command in artifact_commands_from_prompt(prompt)]
    diagram_commands = artifact_commands_from_prompt(dfd_diagram_prompts[0])

    assert execution["result"]["status"] == "PASS"
    assert len(commands) == 1
    assert max(len(command) for command in commands) < 520
    assert all(len(artifact_commands_from_prompt(prompt)) == 1 for prompt in dfd_yaml_prompts)
    assert all("artifact-payload-writer.py" in command for command in commands)
    assert all("base64.b64decode" not in command for command in commands)
    payloads = artifact_base64_payloads_from_prompts(dfd_yaml_prompts)
    assert 20 < len(payloads) <= 70
    assert all(not payload.endswith("=") for payload in payloads[:-1])
    assert diagram_commands
    assert max(len(command) for command in diagram_commands) < 520


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


# ═══════════════════════════════════════════════════════════════════════
# Phase 4: Template Phase Metadata Single Source
# ═══════════════════════════════════════════════════════════════════════


def test_phase4_template_spec_without_phases_passes_generator(tmp_path: Path) -> None:
    """Template spec without phases must pass generator (phases derived from contracts)."""
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


def test_phase4_template_spec_without_phases_renders_meta_correctly(tmp_path: Path) -> None:
    """Generated meta must use derived phases from phase_contracts."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Analyze",
            "detail": "Analyze the request.",
            "label": "target:analyze",
            "prompt": "Analyze.",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        },
        {
            "phase": "Finalize",
            "detail": "Finalize the result.",
            "label": "target:finalize",
            "prompt": "Finalize.",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        },
    ]
    write_template_spec(
        spec,
        name="meta-test",
        phases=[],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "meta-test.js"
    content = candidate.read_text(encoding="utf-8")
    # Verify meta.phases contains derived phase titles
    assert '"phases": [' in content
    assert '"title": "Analyze"' in content
    assert '"title": "Finalize"' in content


def test_phase4_template_spec_with_matching_phases_still_passes(tmp_path: Path) -> None:
    """Template spec with matching explicit phases must still pass (no regression)."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Probe",
            "detail": "Return PASS.",
            "label": "template-probe:probe",
            "prompt": "Probe the request and return PASS.",
            "schema": {"type": "object", "properties": {"status": {"type": "string", "enum": ["PASS"]}}, "required": ["status"]},
        }
    ]
    write_template_spec(
        spec,
        phases=[{"title": "Probe", "detail": "Return PASS."}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "template-probe.js"
    content = candidate.read_text(encoding="utf-8")
    assert "phase('Probe')" in content


def test_phase4_template_spec_with_mismatched_phases_fails(tmp_path: Path) -> None:
    """Template spec with explicit phases that don't match phase_contracts must fail."""
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
        },
        {
            "phase": "Deliver",
            "detail": "Return final result.",
            "label": "target:deliver",
            "prompt": "Build the delivery report.",
            "schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
        },
    ]
    # Explicit phases with WRONG titles
    write_template_spec(
        spec,
        phases=[{"title": "WrongPhase"}, {"title": "AnotherWrong"}],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1, f"expected failure, got pass\nstdout: {completed.stdout}"
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    # Error should mention phase mismatch
    error_messages = " ".join(
        str(e.get("message", "")) if isinstance(e, dict) else str(e)
        for e in payload.get("errors", [])
    )
    assert "phases" in error_messages.lower() or "match" in error_messages.lower() or "contract" in error_messages.lower(), \
        f"Expected phase mismatch error, got: {error_messages}"


def test_phase4_body_spec_without_phases_still_fails(tmp_path: Path) -> None:
    """Body-mode spec without phases must still be rejected."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    # Write a body spec without phases
    payload = {
        "name": "body-no-phases",
        "description": "Body spec missing phases.",
        "body": "phase('Probe')\n\nreturn { status: 'PASS' }\n",
        "supporting_assets": [],
        "asset_disposition": [],
    }
    spec.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 1, f"expected failure for body spec without phases\nstdout: {completed.stdout}"
    payload_result = load_json(completed)
    assert payload_result["status"] == "FAIL"


def test_phase4_template_handoff_without_phases_passes(tmp_path: Path) -> None:
    """Template handoff without phases must pass validate_handoff (derived from contracts)."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    contracts = TEMPLATE_AUTHORING_BASE["phase_contracts"]
    spec_without_phases = {
        "name": "template-probe",
        "description": "Template-based minimal workflow probe.",
        "phases": [],
        "template": "sequential-agent-workflow-v1",
        "phase_contracts": contracts,
        "supporting_assets": [],
        "asset_disposition": [],
    }
    write_template_spec(spec, phases=[], phase_contracts=contracts)
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        authoring_spec=spec_without_phases,
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    # Handoff validation must pass
    handoff_report = run_root / "outputs" / "stages" / "native-workflow-generation-handoff.json"
    assert handoff_report.exists()
    report_data = json.loads(handoff_report.read_text(encoding="utf-8"))
    assert report_data["status"] == "PASS"
    assert report_data["errors"] == []

    # Candidate must exist with derived phases
    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "template-probe.js"
    assert candidate.exists()
    content = candidate.read_text(encoding="utf-8")
    assert "phase('Probe')" in content


def test_phase4_template_handoff_with_matching_phases_still_passes(tmp_path: Path) -> None:
    """Template handoff with matching explicit phases must still pass (no regression)."""
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
        authoring_spec={**TEMPLATE_AUTHORING_BASE},
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    handoff_report = run_root / "outputs" / "stages" / "native-workflow-generation-handoff.json"
    assert handoff_report.exists()
    report_data = json.loads(handoff_report.read_text(encoding="utf-8"))
    assert report_data["status"] == "PASS"


def test_phase4_template_handoff_with_mismatched_phases_fails(tmp_path: Path) -> None:
    """Template handoff with mismatched explicit phases must fail validate_handoff."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    contracts = [
        {
            "phase": "Intake",
            "label": "target:intake",
            "prompt": "Validate the request.",
            "schema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
        },
    ]
    mismatched_authoring = {
        "name": "template-probe",
        "description": "Template-based workflow.",
        "phases": [{"title": "WrongName"}],
        "template": "sequential-agent-workflow-v1",
        "phase_contracts": contracts,
        "supporting_assets": [],
        "asset_disposition": [],
    }
    write_template_spec(
        spec,
        phases=[{"title": "WrongName"}],
        phase_contracts=contracts,
    )
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        authoring_spec=mismatched_authoring,
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    assert completed.returncode == 1, f"expected failure for mismatched phases\nstdout: {completed.stdout}"
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_phase4_body_handoff_without_phases_fails(tmp_path: Path) -> None:
    """Body-mode handoff without phases must still fail validate_handoff."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    handoff = tmp_path / "handoff.json"
    target.mkdir()
    body_spec = {
        "name": "body-no-phases",
        "description": "Body spec missing phases.",
        "phases": [],
        "body": "phase('Probe')\n\nreturn { status: 'PASS' }\n",
        "supporting_assets": [],
        "asset_disposition": [],
    }
    spec.write_text(json.dumps(body_spec, indent=2) + "\n", encoding="utf-8")
    write_handoff_packet(
        handoff,
        target_root=target,
        run_root=run_root,
        authoring_spec=body_spec,
    )

    completed = run_generator_handoff(spec, target, run_root, handoff, "--json")
    # Body mode without phases should still fail
    payload = load_json(completed)
    assert payload["status"] == "FAIL" or completed.returncode != 0, \
        f"Expected failure for body handoff without phases, got: {payload}"


def test_phase4_develop_template_without_phases_reaches_ready_for_generation() -> None:
    """Template authoringSpec without phases must pass hasAuthoringSpec and reach READY_FOR_GENERATION."""
    template_authoring = {
        "status": "PASS",
        "authoringSpec": {
            "name": "template-probe",
            "description": "Template-based workflow.",
            # No phases key – must be derived from phase_contracts
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
    # Phases must be derived and appear in the output
    phases = execution["result"]["authoringSpec"].get("phases", [])
    assert len(phases) > 0, "phases should be derived from phase_contracts"
    assert phases[0]["title"] == "Probe"


def test_phase4_develop_template_with_explicit_phases_matching_contracts_passes() -> None:
    """Template authoringSpec with matching explicit phases must pass (regression)."""
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
    assert execution["result"]["authoringSpec"]["phases"] == [{"title": "Probe"}]
    assert execution["result"]["generationHandoff"]["authoringSpec"]["phases"] == [{"title": "Probe"}]


def test_phase4_develop_template_with_mismatched_phases_blocked() -> None:
    """Template authoringSpec with mismatched explicit phases must return BLOCKED_GENERATION."""
    template_authoring = {
        "status": "PASS",
        "authoringSpec": {
            "name": "template-probe",
            "description": "Template-based workflow.",
            "phases": [{"title": "WrongPhase"}],
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

    assert execution["result"]["status"] == "BLOCKED_GENERATION"
    blocking = " ".join(str(b) for b in execution["result"].get("blockingIssues", []))
    assert "match" in blocking.lower() or "phase" in blocking.lower(), \
        f"Expected phase mismatch error, got: {blocking}"


def test_phase4_develop_body_without_phases_still_blocked() -> None:
    """Body authoringSpec without phases must still be BLOCKED_GENERATION."""
    body_authoring = {
        "status": "PASS",
        "authoringSpec": {
            "name": "body-no-phases",
            "description": "Body spec without phases.",
            # No phases at all
            "body": "phase('Probe')\n\nreturn { status: 'PASS' }\n",
            "supporting_assets": [],
            "asset_disposition": [],
        },
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

    assert execution["result"]["status"] == "BLOCKED_GENERATION"


def test_phase4_develop_body_with_phases_still_passes() -> None:
    """Body authoringSpec with explicit phases must still pass (regression)."""
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
    assert execution["result"]["authoringSpec"]["body"] == "phase('Probe')\n\nreturn { status: 'PASS' }\n"


def test_phase4_template_empty_phases_array_derives_from_contracts(tmp_path: Path) -> None:
    """Template spec with empty phases array [] must derive from contracts and pass."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "Review",
            "detail": "Review the output.",
            "label": "target:review",
            "prompt": "Review.",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        }
    ]
    write_template_spec(spec, phases=[], phase_contracts=contracts)

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "template-probe.js"
    content = candidate.read_text(encoding="utf-8")
    assert "phase('Review')" in content
    assert '"title": "Review"' in content


def test_phase4_template_phases_derived_preserves_order(tmp_path: Path) -> None:
    """Derived phases must preserve the order from phase_contracts."""
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    contracts = [
        {
            "phase": "First",
            "label": "target:first",
            "prompt": "First phase.",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        },
        {
            "phase": "Second",
            "label": "target:second",
            "prompt": "Second phase.",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        },
        {
            "phase": "Third",
            "label": "target:third",
            "prompt": "Third phase.",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        },
    ]
    write_template_spec(
        spec,
        name="ordered-test",
        phases=[],
        phase_contracts=contracts,
    )

    completed = run_generator(spec, target, run_root, "--json")
    assert completed.returncode == 0, f"stderr: {completed.stderr}\nstdout: {completed.stdout}"

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "ordered-test.js"
    content = candidate.read_text(encoding="utf-8")
    # Check order in meta
    first_pos = content.index('"First"')
    second_pos = content.index('"Second"')
    third_pos = content.index('"Third"')
    assert first_pos < second_pos < third_pos, "Phases must appear in contract order"


def test_phase4_develop_template_derived_phases_in_generation_handoff() -> None:
    """Derived phases must appear in both authoringSpec and generationHandoff."""
    template_authoring = {
        "status": "PASS",
        "authoringSpec": {
            "name": "template-probe",
            "description": "Template-based workflow.",
            # No phases – will be derived
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

    # Top-level authoringSpec must have derived phases
    top_phases = execution["result"]["authoringSpec"].get("phases", [])
    assert len(top_phases) > 0
    assert top_phases[0]["title"] == "Probe"

    # generationHandoff.authoringSpec must also have derived phases
    handoff = execution["result"].get("generationHandoff", {})
    handoff_phases = handoff.get("authoringSpec", {}).get("phases", [])
    assert len(handoff_phases) > 0
    assert handoff_phases[0]["title"] == "Probe"


# ═══════════════════════════════════════════════════════════════════════
# Phase 3: Canonical Asset And Supporting Asset Boundary
# ═══════════════════════════════════════════════════════════════════════


def test_phase3_primary_workflow_without_supporting_asset_passes() -> None:
    """Primary workflow generate/update without supporting asset passes when
    body exists (content comes from body/template, not supporting_assets)."""
    asset_disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow is the migration deliverable.",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = asset_disposition
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=asset_disposition,
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    # Verify canonical projection keeps primary workflow without supporting_asset_path
    canonical_spec = execution["result"]["authoringSpec"]
    primary_disp = [d for d in canonical_spec["asset_disposition"] if d["path"] == ".claude/workflows/generated-probe.js"]
    assert len(primary_disp) == 1
    assert primary_disp[0].get("supporting_asset_path", "") == ""


def test_phase3_primary_workflow_with_supporting_asset_path_is_cleared() -> None:
    """Primary workflow disposition supportingAssetPath is ignored in the
    develop canonical projection because body/template is the only workflow
    content source."""
    asset_disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
            "supportingAssetPath": ".claude/workflows/generated-probe.js",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = asset_disposition
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=asset_disposition,
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    assert canonical_spec["asset_disposition"] == [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
            "supporting_asset_path": "",
        }
    ]


def test_phase3_supporting_asset_path_equals_primary_workflow_rejected() -> None:
    """supporting_assets[].path equal to the primary workflow path is rejected."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "script",
                    "path": ".claude/workflows/generated-probe.js",
                    "content": "// primary workflow as supporting asset",
                    "reason": "This should be rejected.",
                }
            ],
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "BLOCKED_GENERATION"
    assert any(
        "primary workflow" in issue.lower() or "not appear in supporting_assets" in issue.lower()
        for issue in execution["result"]["blockingIssues"]
    )


def test_phase3_non_content_action_supporting_asset_path_is_cleared() -> None:
    """Non-content action supportingAssetPath is model drift and should be
    cleared during develop canonical projection."""
    asset_disposition = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": ".claude/commands/old-cmd.md",
            "action": "retain",
            "reason": "Keep for compatibility.",
            "supportingAssetPath": ".claude/commands/old-cmd.md",
        },
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = asset_disposition
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=asset_disposition,
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    retained = [
        item for item in canonical_spec["asset_disposition"]
        if item["path"] == ".claude/commands/old-cmd.md"
    ]
    assert retained == [
        {
            "path": ".claude/commands/old-cmd.md",
            "action": "retain",
            "reason": "Keep for compatibility.",
            "supporting_asset_path": "",
        }
    ]


def test_phase3_auxiliary_generate_missing_supporting_asset_blocked() -> None:
    """Auxiliary generate action missing required supporting asset is blocked."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": ".claude/commands/probe.md",
            "action": "generate",
            "reason": "New compatibility command.",
            "supportingAssetPath": ".claude/commands/probe.md",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=[
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Missing target workflow.",
                },
                {
                    "path": ".claude/commands/probe.md",
                    "action": "generate",
                    "reason": "New compatibility command.",
                    "supporting_asset_path": ".claude/commands/probe.md",
                },
            ],
            # No supporting asset for .claude/commands/probe.md
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "BLOCKED_GENERATION"
    assert any(
        "missing supporting" in issue.lower() or "supporting asset" in issue.lower()
        for issue in execution["result"]["blockingIssues"]
    )


def test_phase3_unreferenced_supporting_asset_is_pruned() -> None:
    """Authoring overproduction is pruned when Design does not reference it."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "compatibility-command",
                    "path": ".claude/commands/orphan.md",
                    "content": "# Orphan command\n",
                    "reason": "This asset is not referenced by any disposition.",
                }
            ],
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["authoringSpec"]["supporting_assets"] == []


def test_phase3_auxiliary_supporting_asset_with_canonical_design_path_accepted() -> None:
    """Auxiliary supporting asset backed by canonical Design supporting path is accepted."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": ".claude/commands/probe.md",
            "action": "generate",
            "reason": "New compatibility command for probe workflow.",
            "supportingAssetPath": ".claude/commands/probe.md",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "compatibility-command",
                    "path": ".claude/commands/probe.md",
                    "content": "# Probe Command\n\nRun probe workflow.",
                    "reason": "New compatibility command for probe workflow.",
                }
            ],
            asset_disposition=[
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Missing target workflow.",
                },
                {
                    "path": ".claude/commands/probe.md",
                    "action": "generate",
                    "reason": "New compatibility command for probe workflow.",
                    "supporting_asset_path": ".claude/commands/probe.md",
                },
            ],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    # Verify canonical projection preserved auxiliary asset
    canonical_spec = execution["result"]["authoringSpec"]
    assert len(canonical_spec["supporting_assets"]) == 1
    assert canonical_spec["supporting_assets"][0]["path"] == ".claude/commands/probe.md"
    # Verify kind was derived from path (not authoring's original kind)
    assert canonical_spec["supporting_assets"][0]["kind"] == "compatibility-command"


def test_phase3_target_root_absolute_paths_project_to_relative_canonical_paths() -> None:
    """Target-root absolute Design and Authoring paths are canonicalized to target-relative paths."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": "/tmp/native-target/.claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": "/tmp/native-target/.claude/commands/probe.md",
            "action": "generate",
            "reason": "New compatibility command for probe workflow.",
            "supportingAssetPath": "/tmp/native-target/.claude/commands/probe.md",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "compatibility-command",
                    "path": "/tmp/native-target/.claude/commands/probe.md",
                    "content": "# Probe Command\n\nRun probe workflow.",
                    "reason": "New compatibility command for probe workflow.",
                }
            ],
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    assert [item["path"] for item in canonical_spec["asset_disposition"]] == [
        ".claude/commands/probe.md",
        ".claude/workflows/generated-probe.js",
    ]
    assert canonical_spec["asset_disposition"][0]["supporting_asset_path"] == ".claude/commands/probe.md"
    assert canonical_spec["supporting_assets"][0]["path"] == ".claude/commands/probe.md"


def test_phase3_run_evidence_paths_are_pruned_from_canonical_disposition() -> None:
    """Run-root evidence files are not managed target workflow assets."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": "/tmp/native-target/.workflowprogram/runs/run-001/generation-output.json",
            "action": "generate",
            "reason": "Run evidence, not a managed target asset.",
            "supportingAssetPath": "/tmp/native-target/.claude/workflows/generated-probe.js",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    review = pass_review_evidence()
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            review,
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    assert [item["path"] for item in canonical_spec["asset_disposition"]] == [
        ".claude/workflows/generated-probe.js",
    ]


def test_phase3_run_evidence_support_path_repairs_to_authoring_same_path_content() -> None:
    """Run evidence support paths are cleared before same-path content repair."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": "/tmp/native-target/.claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Primary workflow.",
        },
        {
            "path": "/tmp/native-target/.workflowprogram/managed-files.json",
            "action": "update",
            "reason": "Update managed files manifest.",
            "supportingAssetPath": "/tmp/native-target/.workflowprogram/runs/run-001/outputs/candidate/.claude/workflows/generated-probe.js",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "json",
                    "path": ".workflowprogram/managed-files.json",
                    "content": "{\"files\": []}",
                    "reason": "Authoring drift reason.",
                }
            ],
            asset_disposition=[
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Primary workflow.",
                },
                {
                    "path": ".workflowprogram/managed-files.json",
                    "action": "update",
                    "reason": "Update managed files manifest.",
                    "supporting_asset_path": ".workflowprogram/managed-files.json",
                },
            ],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    managed = [
        item for item in canonical_spec["asset_disposition"]
        if item["path"] == ".workflowprogram/managed-files.json"
    ]
    assert managed == [
        {
            "path": ".workflowprogram/managed-files.json",
            "action": "update",
            "reason": "Update managed files manifest.",
            "supporting_asset_path": ".workflowprogram/managed-files.json",
        }
    ]
    supporting = [
        item for item in canonical_spec["supporting_assets"]
        if item["path"] == ".workflowprogram/managed-files.json"
    ]
    assert supporting[0]["kind"] == "managed-files"
    assert supporting[0]["reason"] == "Update managed files manifest."


def test_phase3_invalid_design_supporting_path_uses_authoring_same_path_content() -> None:
    """The content asset path is derived from Authoring when Design's link points at evidence or the primary workflow."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": ".claude/commands/probe.md",
            "action": "update",
            "reason": "Command needs a Native workflow reference.",
            "supportingAssetPath": ".claude/workflows/generated-probe.js",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "compatibility-command",
                    "path": ".claude/commands/probe.md",
                    "content": "# Probe Command\n\nRun the Native workflow.",
                    "reason": "Command needs a Native workflow reference.",
                }
            ],
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    command = [item for item in canonical_spec["asset_disposition"] if item["path"] == ".claude/commands/probe.md"][0]
    assert command["supporting_asset_path"] == ".claude/commands/probe.md"


def test_phase3_missing_same_batch_supporting_assets_are_authoring_fixable() -> None:
    """Same-batch content assets must request Authoring content, not Design changes."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/stride-audit.js",
            "action": "generate",
            "reason": "Primary workflow.",
            "supportingAssetPath": ".claude/commands/stride-audit.md",
        },
        {
            "path": ".claude/settings.json",
            "action": "update",
            "reason": "Register workflow.",
            "supportingAssetPath": ".claude/workflows/stride-audit.js",
        },
        {
            "path": ".workflowprogram/managed-files.json",
            "action": "update",
            "reason": "Update managed files.",
            "supportingAssetPath": ".workflowprogram/design/workflow-spec.yaml",
        },
        {
            "path": ".workflowprogram/design/workflow-spec.yaml",
            "action": "update",
            "reason": "Update workflow spec.",
            "supportingAssetPath": ".claude/workflows/stride-audit.js",
        },
        {
            "path": ".claude/commands/stride-audit.md",
            "action": "update",
            "reason": "Update command.",
            "supportingAssetPath": ".claude/workflows/stride-audit.js",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            name="stride-audit",
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[],
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    review = pass_review_evidence()
    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            review,
            authoring,
        ],
    )

    result = execution["result"]
    assert result["status"] == "BLOCKED_GENERATION"
    assert result["nextAction"] == "FIX_AUTHORING_AND_REINVOKE"
    assert result["designEvidence"] == design
    assert result["reviewEvidence"] == review
    assert {
        item["path"] for item in result["authoringRepair"]["missingSupportingAssets"]
    } == {
        ".claude/settings.json",
        ".workflowprogram/managed-files.json",
        ".workflowprogram/design/workflow-spec.yaml",
        ".claude/commands/stride-audit.md",
    }
    assert all("Missing authoring supporting asset content" in issue for issue in result["blockingIssues"])


def test_phase3_mismatched_supporting_asset_kind_repairs_to_disposition_path() -> None:
    """A content asset cannot use an unrelated asset kind as its supporting
    content path; WPN should ask Authoring for the updated asset itself."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/settings.json",
            "action": "update",
            "reason": "Register stride-ui-verifier.",
            "supportingAssetPath": ".claude/agents/stride-ui-verifier.md",
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            supporting_assets=[],
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    result = execution["result"]
    assert result["status"] == "BLOCKED_GENERATION"
    assert result["nextAction"] == "FIX_AUTHORING_AND_REINVOKE"
    assert result["authoringRepair"]["missingSupportingAssets"] == [
        {
            "path": ".claude/settings.json",
            "dispositionPath": ".claude/settings.json",
            "action": "update",
        }
    ]
    assert "expected supporting_assets.path .claude/settings.json" in result["blockingIssues"][0]


def test_phase3_migrate_legacy_runtime_content_action_is_archived() -> None:
    """Native migration treats legacy WPN runtime assets as archive, not generated content."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/stride-audit.js",
            "action": "generate",
            "reason": "Primary workflow.",
        },
        {
            "path": ".workflowprogram/runtime/runtime-manifest.json",
            "action": "update",
            "reason": "Legacy runtime manifest is retired by Native Workflow JS.",
            "supportingAssetPath": ".claude/workflows/stride-audit.js",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            name="stride-audit",
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "authoring-metadata",
                    "path": ".workflowprogram/runtime/runtime-manifest.json",
                    "content": "{}",
                    "reason": "Should be pruned.",
                }
            ],
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    runtime = [
        item for item in canonical_spec["asset_disposition"]
        if item["path"] == ".workflowprogram/runtime/runtime-manifest.json"
    ][0]
    assert runtime["action"] == "archive"
    assert runtime["supporting_asset_path"] == ""
    assert canonical_spec["supporting_assets"] == []


def test_phase3_kind_derived_from_path_overwrites_authoring_kind() -> None:
    """Authoring-supplied kind is overwritten with path-derived kind in canonical projection."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": ".claude/commands/probe.md",
            "action": "generate",
            "reason": "Compatibility command.",
            "supportingAssetPath": ".claude/commands/probe.md",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "skill",  # Wrong kind deliberately - path implies compatibility-command
                    "path": ".claude/commands/probe.md",
                    "content": "# Probe Command\n",
                    "reason": "Compatibility command.",
                }
            ],
            asset_disposition=[
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Missing target workflow.",
                },
                {
                    "path": ".claude/commands/probe.md",
                    "action": "generate",
                    "reason": "Compatibility command.",
                    "supporting_asset_path": ".claude/commands/probe.md",
                },
            ],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    # Kind should be derived from path, not authoring's "skill"
    canonical_spec = execution["result"]["authoringSpec"]
    assert canonical_spec["supporting_assets"][0]["kind"] == "compatibility-command"


def test_phase3_reason_derived_from_design_disposition() -> None:
    """Supporting asset reason is derived from canonical Design disposition reason."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": ".claude/scripts/probe-helper.py",
            "action": "generate",
            "reason": "Design-specified helper script for probe workflow.",
            "supportingAssetPath": ".claude/scripts/probe-helper.py",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "script",
                    "path": ".claude/scripts/probe-helper.py",
                    "content": "print('PASS')",
                    "reason": "Authoring reason - should be overwritten.",
                }
            ],
            asset_disposition=[
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Missing target workflow.",
                },
                {
                    "path": ".claude/scripts/probe-helper.py",
                    "action": "generate",
                    "reason": "Design-specified helper script for probe workflow.",
                    "supporting_asset_path": ".claude/scripts/probe-helper.py",
                },
            ],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    # Reason should come from design, not authoring
    canonical_spec = execution["result"]["authoringSpec"]
    assert canonical_spec["supporting_assets"][0]["reason"] == "Design-specified helper script for probe workflow."


def test_phase3_duplicate_supporting_asset_path_rejected() -> None:
    """Duplicate supporting asset path is rejected."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        },
        {
            "path": ".claude/commands/probe.md",
            "action": "generate",
            "reason": "Compatibility command.",
            "supportingAssetPath": ".claude/commands/probe.md",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "compatibility-command",
                    "path": ".claude/commands/probe.md",
                    "content": "# First\n",
                    "reason": "First.",
                },
                {
                    "kind": "compatibility-command",
                    "path": ".claude/commands/probe.md",
                    "content": "# Second\n",
                    "reason": "Second.",
                },
            ],
            asset_disposition=[
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Missing target workflow.",
                },
                {
                    "path": ".claude/commands/probe.md",
                    "action": "generate",
                    "reason": "Compatibility command.",
                    "supporting_asset_path": ".claude/commands/probe.md",
                },
            ],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "BLOCKED_GENERATION"
    assert any(
        "duplicate" in issue.lower()
        for issue in execution["result"]["blockingIssues"]
    )


def test_phase3_template_primary_workflow_without_supporting_asset_passes() -> None:
    """Template primary workflow generate without supporting asset passes when
    template+phase_contracts exists."""
    asset_disposition = [
        {
            "path": ".claude/workflows/template-probe.js",
            "action": "generate",
            "reason": "Template-based target workflow.",
        }
    ]
    design = pass_design_evidence()
    design["assetDisposition"] = asset_disposition
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
            "asset_disposition": asset_disposition,
        },
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            template_authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"


def test_phase3_design_disposition_is_canonical_source() -> None:
    """The canonical asset_disposition is projected from designEvidence.assetDisposition,
    not from authoringSpec.asset_disposition, when they differ."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Design-specified reason for primary workflow.",
        },
        {
            "path": ".claude/scripts/helper.py",
            "action": "generate",
            "reason": "Design-specified helper script.",
            "supportingAssetPath": ".claude/scripts/helper.py",
        },
    ]
    # Authoring has different reason (drift that should be overwritten)
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "script",
                    "path": ".claude/scripts/helper.py",
                    "content": "print('PASS')",
                    "reason": "Authoring reason - should be overwritten by design.",
                }
            ],
            asset_disposition=[
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Authoring reason - should be overwritten.",
                },
                {
                    "path": ".claude/scripts/helper.py",
                    "action": "generate",
                    "reason": "Authoring helper reason - should be overwritten.",
                    "supporting_asset_path": ".claude/scripts/helper.py",
                },
            ],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    # Primary workflow reason from design
    primary = [d for d in canonical_spec["asset_disposition"] if d["path"] == ".claude/workflows/generated-probe.js"][0]
    assert primary["reason"] == "Design-specified reason for primary workflow."
    # Auxiliary reason from design
    auxiliary = [d for d in canonical_spec["asset_disposition"] if d["path"] == ".claude/scripts/helper.py"][0]
    assert auxiliary["reason"] == "Design-specified helper script."
    # Supporting asset reason from design
    assert canonical_spec["supporting_assets"][0]["reason"] == "Design-specified helper script."


def test_phase3_create_with_auxiliary_supporting_asset_passes() -> None:
    """Create operation with auxiliary supporting asset backed by canonical
    Design supporting path is accepted."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Target workflow.",
        },
        {
            "path": ".claude/commands/probe.md",
            "action": "generate",
            "reason": "Compatibility command.",
            "supportingAssetPath": ".claude/commands/probe.md",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "compatibility-command",
                    "path": ".claude/commands/probe.md",
                    "content": "# Probe Command\n",
                    "reason": "Compatibility command.",
                }
            ],
            asset_disposition=[
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Target workflow.",
                },
                {
                    "path": ".claude/commands/probe.md",
                    "action": "generate",
                    "reason": "Compatibility command.",
                    "supporting_asset_path": ".claude/commands/probe.md",
                },
            ],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="create"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Empty target."],
                "constraints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Empty target."],
                "constraints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"


def test_phase3_create_with_unchecked_auxiliary_supporting_asset_pruned() -> None:
    """Create cannot introduce auxiliary supporting assets unless Design owns
    the canonical supporting path; unchecked Authoring content is pruned."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Target workflow.",
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "compatibility-command",
                    "path": ".claude/commands/probe.md",
                    "content": "# Probe Command\n",
                    "reason": "Unchecked command.",
                }
            ],
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="create"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Empty target."],
                "constraints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Empty target."],
                "constraints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    assert execution["result"]["authoringSpec"]["supporting_assets"] == []


def test_phase3_deterministic_order_preserved() -> None:
    """Canonical projection preserves deterministic order (sorted by path)."""
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/commands/zebra.md",
            "action": "generate",
            "reason": "Z command.",
            "supportingAssetPath": ".claude/commands/zebra.md",
        },
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Workflow.",
        },
        {
            "path": ".claude/agents/alpha.md",
            "action": "generate",
            "reason": "A agent.",
            "supportingAssetPath": ".claude/agents/alpha.md",
        },
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            supporting_assets=[
                {
                    "kind": "compatibility-command",
                    "path": ".claude/commands/zebra.md",
                    "content": "# Z\n",
                    "reason": "Z.",
                },
                {
                    "kind": "agent",
                    "path": ".claude/agents/alpha.md",
                    "content": "# A\n",
                    "reason": "A.",
                },
            ],
            asset_disposition=[
                {
                    "path": ".claude/commands/zebra.md",
                    "action": "generate",
                    "reason": "Z command.",
                    "supporting_asset_path": ".claude/commands/zebra.md",
                },
                {
                    "path": ".claude/workflows/generated-probe.js",
                    "action": "generate",
                    "reason": "Workflow.",
                },
                {
                    "path": ".claude/agents/alpha.md",
                    "action": "generate",
                    "reason": "A agent.",
                    "supporting_asset_path": ".claude/agents/alpha.md",
                },
            ],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            {
                "status": "PASS",
                "findings": ["Readable."],
                "constraints": [],
                "migrationTasks": [],
                "trueBlockers": [],
                "userDecisions": [],
                "sourceOfTruth": [],
                "assetDispositionHints": [],
                "blockingIssues": [],
            },
            design,
            pass_review_evidence(),
            authoring,
        ],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
    canonical_spec = execution["result"]["authoringSpec"]
    # Should be sorted by path
    paths = [d["path"] for d in canonical_spec["asset_disposition"]]
    assert paths == sorted(paths)
    sup_paths = [a["path"] for a in canonical_spec["supporting_assets"]]
    assert sup_paths == sorted(sup_paths)


def test_phase3_empty_user_decisions_resolved_asset_disposition_still_passes() -> None:
    """When userDecisions are empty and migrationDecisions resolve asset disposition,
    the canonical projection still passes."""
    exploration = {
        "status": "PASS",
        "findings": ["All assets readable."],
        "constraints": [],
        "migrationTasks": ["Generate missing workflow."],
        "trueBlockers": [],
        "userDecisions": [],
        "sourceOfTruth": [],
        "assetDispositionHints": [
            {
                "path": ".claude/workflows/generated-probe.js",
                "action": "generate",
                "reason": "Missing target workflow.",
            }
        ],
        "blockingIssues": [],
    }
    design = pass_design_evidence()
    design["assetDisposition"] = [
        {
            "path": ".claude/workflows/generated-probe.js",
            "action": "generate",
            "reason": "Missing target workflow.",
        }
    ]
    authoring = {
        "status": "PASS",
        "authoringSpec": authoring_spec_payload(
            body="phase('Probe')\nreturn { status: 'PASS' }\n",
            asset_disposition=design["assetDisposition"],
        ),
        "blockingIssues": [],
    }

    execution = execute_native_workflow(
        DEVELOP_WORKFLOW,
        develop_args(operation="migrate"),
        agent_results=[exploration, exploration, design, pass_review_evidence(), authoring],
    )

    assert execution["result"]["status"] == "READY_FOR_GENERATION"
