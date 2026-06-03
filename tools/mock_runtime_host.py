#!/usr/bin/env python3
"""WorkflowProgram smoke 测试用的参考 runtime host 适配器。

这个 mock host 为 runtime_smoke 提供一条确定性的非 Claude 执行路径，
这样无需 Claude 登录也能验证 provider 抽象和 S5 judge。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / ".claude" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from lib.io_utils import iso_now, write_json
from lib.reporting import with_report_fields
from lib.target_design_refs import (
    PERSISTENT_DEFAULTS,
    iter_existing_node_design_refs,
    resolve_existing_run_refs,
    resolve_target_design_refs,
)


def write_text(path: Path, content: str) -> None:
    """创建父目录后写入 UTF-8 文本。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def managed_runtime_command_text() -> str:
    """Return the wrapper-only command body required by target managed runtime."""

    return "\n".join(
        [
            "## Usage",
            "",
            "```text",
            "/example <request>",
            "```",
            "",
            "This command is a thin wrapper for the generated WorkflowProgram target runtime.",
            "",
            "Run:",
            "",
            "```bash",
            "python3 .workflowprogram/runtime/workflow-entry.py run --request \"$ARGUMENTS\"",
            "```",
            "",
        ]
    )


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    """向 JSONL 流追加一条 JSON 记录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def manifest_path_for(target_root: Path) -> Path:
    """Return the managed manifest path used by real managed apply."""
    return target_root / ".workflowprogram" / "managed-files.json"


def write_design_source_artifacts(run_root: Path, request: str) -> None:
    """写出最小但可追踪的设计源证据，供 S5 lineage 检查消费。"""

    request_text = request.strip() or "mock request"
    stages_root = run_root / "outputs" / "stages"
    write_text(
        stages_root / "s1-requirements.yaml",
        yaml.safe_dump(
            {
                "requirements": [
                    {
                        "id": "REQ-001",
                        "source_ref": "USER-REQUEST-001",
                        "priority": "must",
                        "statement": f"Create a managed workflow for: {request_text}",
                        "acceptance_hint": "Generated assets, runtime evidence, and validation summary exist.",
                        "boundaries": [
                            "Do not overwrite unmanaged target assets silently.",
                            "Do not skip S5 validation.",
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    write_json(
        stages_root / "question-backlog.json",
        {
            "schema_version": 1,
            "complexity": "M",
            "lead_role": "requirement-clarification-lead",
            "questions": [
                {
                    "id": "Q-001",
                    "lens": "evidence_model",
                    "question": "哪些目标输出必须进入 registry 或 test_contract 以便 S5 验证？",
                    "why_it_matters": "Different answers can alter workflow nodes, decisions, evidence, acceptance tests, or boundaries.",
                    "blocking": False,
                    "expected_answer_shape": "Concrete output-to-evidence mapping.",
                    "linked_requirement_ids": ["REQ-001"],
                    "design_consequence": True,
                    "status": "resolved",
                }
            ],
            "selected_next_question_id": None,
            "blocking_count": 0,
            "design_consequential_count": 1,
        },
    )
    write_json(
        stages_root / "requirement-logic-map.json",
        {
            "schema_version": 1,
            "complexity": "M",
            "status": "READY",
            "lenses": {
                "purpose": {"status": "complete", "required": True, "items": ["Generate a verifiable workflow asset set."]},
                "object_model": {"status": "complete", "required": True, "items": ["User request, target assets, managed plan, runtime evidence."]},
                "process_model": {"status": "complete", "required": True, "items": ["clarify -> context -> design -> generate -> validate"]},
                "decision_model": {"status": "complete", "required": True, "items": ["Stop on conflict, approval gap, environment gap, or validation failure."]},
                "evidence_model": {"status": "complete", "required": True, "items": ["state.json, events.jsonl, managed result, S5 summary."]},
                "acceptance_model": {"status": "complete", "required": True, "items": ["Workflow assets exist and S5 PASS/WARN is justified."]},
                "boundary_model": {"status": "complete", "required": True, "items": ["Do not overwrite unmanaged assets or skip validation."]},
            },
            "elements": {
                "process": [{"id": "PROC-001", "summary": "clarify -> context -> design -> generate -> validate"}],
                "decisions": [{"id": "DEC-001", "summary": "Stop on conflict or validation failure."}],
                "evidence": [{"id": "EVD-001", "summary": "state.json, events.jsonl, managed result, S5 summary."}],
                "acceptance": [{"id": "ACC-001", "summary": "Workflow assets exist and S5 PASS/WARN is justified."}],
                "boundaries": [{"id": "BND-001", "summary": "Do not overwrite unmanaged assets or skip validation."}],
            },
            "workflow_node_candidates": ["entry", "generate-assets", "validate-assets"],
            "negative_or_stop_scenarios": ["Conflict, missing approval, or validation failure stops clean PASS."],
            "requirement_links": [
                {
                    "requirement_id": "REQ-001",
                    "priority": "must",
                    "process_refs": ["PROC-001"],
                    "decision_refs": ["DEC-001"],
                    "evidence_refs": ["EVD-001"],
                    "acceptance_refs": ["ACC-001"],
                    "boundary_refs": ["BND-001"],
                }
            ],
            "open_logic_gaps": [],
            "coverage": {
                "all_required_lenses_present": True,
                "has_process_refs": True,
                "has_evidence_refs": True,
                "has_acceptance_refs": True,
                "has_design_consequential_questions": True,
            },
        },
    )
    write_text(
        stages_root / "s2-context-findings.yaml",
        yaml.safe_dump(
            {
                "findings": [
                    {
                        "id": "CTX-001",
                        "requirement_refs": ["REQ-001"],
                        "kind": "workflow_asset_context",
                        "summary": "Target workflow assets and WorkflowProgram constraints are available to S3.",
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    write_text(
        stages_root / "s3-design-highlevel.md",
        "# S3 High-Level Design\n\n"
        "- Requirement refs: `REQ-001`\n"
        "- Target workflow purpose: generate managed Claude Code workflow assets with runtime evidence.\n"
        "- Target graph: `intake -> implement -> done`.\n",
    )
    write_text(
        stages_root / "s3-design-lowlevel.md",
        "# S3 Low-Level Design\n\n"
        "- Requirement refs: `REQ-001`\n"
        "- `intake` captures request context and produces an intake summary.\n"
        "- `implement` generates `.claude` and `.workflowprogram` assets.\n"
        "- S5 validates managed apply, state evidence, and design lineage.\n",
    )
    write_text(
        stages_root / "s3-implementation-plan.md",
        "# S3 Implementation Plan\n\n"
        "1. Generate candidate workflow assets from the accepted design.\n"
        "2. Apply managed assets through the managed-asset boundary.\n"
        "3. Run S5 validation and persist runtime evidence.\n",
    )
    write_text(
        stages_root / "acceptance-tests.yaml",
        yaml.safe_dump(
            {
                "acceptance_tests": [
                    {
                        "id": "AT-001",
                        "covers": ["REQ-001"],
                        "verifier": "S5",
                        "expected_evidence": [
                            "state.json",
                            "events.jsonl",
                            "outputs/stages/s5-validation-summary.json",
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    write_json(
        stages_root / "traceability-matrix.json",
        {
            "schema_version": 1,
            "links": [
                {
                    "requirement_id": "REQ-001",
                    "design_nodes": ["intake", "implement"],
                    "assets": [
                        ".workflowprogram/design/workflow-spec.yaml",
                        ".workflowprogram/runtime/workflow-entry.py",
                    ],
                    "acceptance_tests": ["AT-001"],
                    "evidence": [
                        "state.json",
                        "events.jsonl",
                        "outputs/stages/s5-validation-summary.json",
                    ],
                }
            ],
        },
    )
    canonical_pairs = {
        "s1-requirements.yaml": "target-requirements.yaml",
        "question-backlog.json": "target-question-backlog.json",
        "requirement-logic-map.json": "target-requirement-logic-map.json",
        "s2-context-findings.yaml": "target-context-findings.yaml",
        "s3-design-highlevel.md": "target-design-overview.md",
        "s3-design-lowlevel.md": "target-design-detail.md",
        "s3-implementation-plan.md": "target-implementation-plan.md",
        "acceptance-tests.yaml": "target-acceptance-tests.yaml",
        "traceability-matrix.json": "target-traceability-matrix.json",
    }
    for legacy_name, canonical_name in canonical_pairs.items():
        source = stages_root / legacy_name
        if source.exists():
            shutil.copy2(source, stages_root / canonical_name)


def render_target_node_design(node: Dict[str, Any]) -> str:
    """Return a minimal valid target node design for deterministic smoke fixtures."""

    node_id = str(node.get("id", "implement")).strip() or "implement"
    owner = str(node.get("owner", "example-skill")).strip() or "example-skill"
    template = str(node.get("template", "flexible-target-graph")).strip() or "flexible-target-graph"
    gate = str(node.get("gate", "none")).strip() or "none"
    complexity = str(node.get("complexity", "moderate")).strip() or "moderate"
    design_intensity = str(node.get("design_intensity", "standard")).strip() or "standard"
    inputs = node.get("input_refs", [])
    outputs = node.get("output_refs", [])
    input_refs = [str(item).strip() for item in inputs if str(item).strip()] if isinstance(inputs, list) else []
    output_refs = [str(item).strip() for item in outputs if str(item).strip()] if isinstance(outputs, list) else []
    loop_policy = node.get("loop_policy", {})
    loop_enabled = isinstance(loop_policy, dict) and loop_policy.get("enabled") is True
    input_rows = "\n".join(
        f"| `{ref}` | yes | previous node | Ref must exist before `{node_id}` starts. |" for ref in (input_refs or ["$ARGUMENTS"])
    )
    output_rows = "\n".join(
        f"| `{ref}` | yes | downstream node or S5 | Ref must be present and traceable. |" for ref in (output_refs or ["outputs/target-workflow/result.md"])
    )
    return f"""# Target Node Design: {node_id}

## 1. Node Metadata / 节点元信息

- Node ID: `{node_id}`
- Workflow spec path: `workflow_graph.nodes[id={node_id}]`
- Owner: `{owner}`
- Template: `{template}`
- Gate: `{gate}`
- Complexity: `{complexity}`
- Design intensity: `{design_intensity}`

## 2. Purpose And Boundary / 设计目的与职责边界

- Purpose: Execute `{node_id}` for the generated target workflow.
- In scope: Consume declared inputs and produce declared outputs.
- Out of scope: Modify undeclared target assets or bypass S5 validation.
- Upstream assumptions: WorkflowProgram has produced accepted target design source.

## 3. Input Contract / 输入契约

| Input ref | Required | Producer | Validation rule |
| --- | --- | --- | --- |
{input_rows}

## 4. Output Contract And Consumers / 输出契约与消费者

| Output ref | Required | Consumer | Pass criteria |
| --- | --- | --- | --- |
{output_rows}

## 5. Context Read/Write Rules / 上下文读写规则

- Reads: declared input refs and `workflow-spec.yaml`.
- Writes: declared output refs and runtime evidence.
- Must not mutate: unmanaged target files.
- Persistence rule: outputs are persisted under managed target paths or RUN_ROOT evidence paths.

## 6. Internal Execution Plan / 内部执行编排

1. Validate input refs.
2. Generate node outputs.
3. Record evidence for S5.
4. Stop only after verifier evidence is present.

Loop policy:

- Loop allowed: {str(loop_enabled).lower()}
- loop_policy evidence: `outputs/stages/loops/{node_id}/loop-plan.json`, `iteration-summary.jsonl`, and `final-verdict.json` when enabled.

## 7. Agent / Skill / Script / Tool Calls / 调用关系

| Capability | Name | Purpose | Input | Output |
| --- | --- | --- | --- | --- |
| skill | `{owner}` | Execute node work | declared inputs | declared outputs |
| script | `workflow-runner.py` | Record state transition | stage context | `state.json` |

## 8. Data Field Contract / 数据字段契约

| Field | Type | Required | Source | Meaning |
| --- | --- | --- | --- | --- |
| `node_id` | string | yes | workflow_graph | Node identity for evidence joins. |
| `result` | string | yes | verifier | PASS, WARN, FAIL, or ENVIRONMENT-SKIP. |

## 9. Exit Gate / 准出目标

- Gate decision: `{gate}`.
- Required evidence: declared outputs, `state.json`, and `events.jsonl`.
- Human approval rule: required only when gate is not `none`.
- Auto-approval rule: allowed only when the spec declares it.

## 10. Failure, Retry, And Degrade Strategy / 失败、重试与降级策略

- `FAIL` when required output refs are missing.
- `WARN` when optional evidence is incomplete but safe to inspect.
- `ENVIRONMENT-SKIP` when a required host capability is unavailable.
- Retry limit: follow workflow stage retry limits.
- Degrade strategy: degrade only to WARN with explicit evidence.

## 11. Verification And Tests / 验证与测试要求

- Unit or fixture test: deterministic smoke fixture covers this node.
- Runtime verifier: S5 checks state, events, outputs, and traceability.
- Acceptance test refs: `AT-001`.
- Evidence paths: `state.json`, `events.jsonl`, and `outputs/stages/s5-validation-summary.json`.

## 12. Observability And Debug Artifacts / 观测与调试产物

- Logs: `events.jsonl`.
- Reports: `outputs/stages/s5-validation-summary.json`.
- State artifacts: `state.json`.
- Debug reproduction: rerun the same fixture and inspect RUN_ROOT.

## 13. Safety And Execution Constraints / 安全与执行约束

- Path boundary: write only declared managed outputs.
- Approval boundary: do not bypass declared gates.
- Host capability boundary: missing required capability remains environment failure.
- Secret handling: never persist secrets in node outputs.
- Destructive action policy: destructive commands are not allowed in this fixture node.

## 14. Open Tasks And Extension Points / 遗留任务与扩展点

- Open tasks: none
- Extension points: add domain-specific verifier details in real workflows.
- Deferred decisions: none
"""


def copy_runtime_spec(
    repo_root: Path,
    run_root: Path,
    spec_name: str,
    *,
    entry_skill: str,
    deliverables: List[str] | None = None,
    target_root_allow: List[str] | None = None,
    host_capabilities: List[Dict[str, Any]] | None = None,
    agent_team_contract: Dict[str, Any] | None = None,
    capability_discovery: Dict[str, Any] | None = None,
    node_loop_policy: Dict[str, Any] | None = None,
    runtime_capabilities: List[str] | None = None,
) -> None:
    """把 fixture workflow spec 复制到 RUN_ROOT，并按需打补丁。

    mock host 直接复用真实 spec fixture，这样下游 validator 和 judge
    走的仍然是和真实运行一致的解析路径。
    """
    spec_path = repo_root / "tests" / "spec-fixtures" / spec_name
    run_root.mkdir(parents=True, exist_ok=True)
    write_design_source_artifacts(run_root, "mock request")
    target_path = run_root / "workflow-spec.yaml"
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    test_contract = payload.get("test_contract", {})
    if isinstance(test_contract, dict):
        artifacts = test_contract.get("artifacts", {})
        if deliverables is not None and isinstance(artifacts, dict):
            artifacts["deliverables"] = deliverables
    runtime_contract = payload.get("runtime_contract", {})
    if target_root_allow is not None and isinstance(runtime_contract, dict):
        write_boundaries = runtime_contract.get("write_boundaries", {})
        if isinstance(write_boundaries, dict):
            current = write_boundaries.get("target_root_allow", [])
            merged: List[str] = []
            for item in current if isinstance(current, list) else []:
                text = str(item).strip()
                if text and text not in merged:
                    merged.append(text)
            for item in target_root_allow:
                text = str(item).strip()
                if text and text not in merged:
                    merged.append(text)
            write_boundaries["target_root_allow"] = merged
    generated_runtime_contract = payload.get("generated_runtime_contract", {})
    if runtime_capabilities is not None and isinstance(generated_runtime_contract, dict):
        generated_runtime_contract["runtime_capabilities"] = runtime_capabilities
    target_runtime_policy = payload.get("target_runtime_policy", {})
    if (
        isinstance(target_runtime_policy, dict)
        and str(target_runtime_policy.get("mode", "")).strip() == "managed_runtime"
        and isinstance(generated_runtime_contract, dict)
    ):
        caps = generated_runtime_contract.get("runtime_capabilities", [])
        if isinstance(caps, list) and "target_managed_runtime" not in caps:
            caps.append("target_managed_runtime")
            generated_runtime_contract["runtime_capabilities"] = caps
    target_publish_policy = payload.get("target_publish_policy", {})
    if (
        isinstance(target_publish_policy, dict)
        and target_publish_policy.get("enabled") is True
        and isinstance(generated_runtime_contract, dict)
    ):
        caps = generated_runtime_contract.get("runtime_capabilities", [])
        if isinstance(caps, list) and "target_atomic_publish" not in caps:
            caps.append("target_atomic_publish")
            generated_runtime_contract["runtime_capabilities"] = caps
    if host_capabilities is not None:
        payload["host_capabilities"] = host_capabilities
        if isinstance(generated_runtime_contract, dict):
            caps = generated_runtime_contract.get("runtime_capabilities", [])
            if isinstance(caps, list) and "host_capability_probe" not in caps:
                caps.append("host_capability_probe")
                generated_runtime_contract["runtime_capabilities"] = caps
    if agent_team_contract is not None:
        payload["agent_team_contract"] = agent_team_contract
        if isinstance(generated_runtime_contract, dict):
            caps = generated_runtime_contract.get("runtime_capabilities", [])
            if isinstance(caps, list) and "team_orchestration" not in caps:
                caps.append("team_orchestration")
                generated_runtime_contract["runtime_capabilities"] = caps
    if capability_discovery is not None:
        payload["capability_discovery"] = capability_discovery
        if isinstance(generated_runtime_contract, dict):
            caps = generated_runtime_contract.get("runtime_capabilities", [])
            if isinstance(caps, list) and "capability_discovery" not in caps:
                caps.append("capability_discovery")
                generated_runtime_contract["runtime_capabilities"] = caps
    if node_loop_policy is not None:
        graph = payload.get("workflow_graph", {})
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        if isinstance(nodes, list) and nodes:
            nodes[-1]["loop_policy"] = node_loop_policy
            node_id = str(nodes[-1].get("id", "implement")).strip() or "implement"
            design_refs = payload.setdefault("design_refs", {})
            if isinstance(design_refs, dict):
                node_designs = design_refs.setdefault("node_designs", {})
                if isinstance(node_designs, dict):
                    node_designs[node_id] = f"outputs/stages/target-node-designs/{node_id}.md"
                persistent_refs = design_refs.setdefault("persistent", {})
                if isinstance(persistent_refs, dict):
                    persistent_node_designs = persistent_refs.setdefault("node_designs", {})
                    if isinstance(persistent_node_designs, dict):
                        persistent_node_designs[node_id] = f".workflowprogram/design/source/target-node-designs/{node_id}.md"
            write_text(
                run_root / "outputs" / "stages" / "target-node-designs" / f"{node_id}.md",
                render_target_node_design(nodes[-1]),
            )
        if isinstance(generated_runtime_contract, dict):
            caps = generated_runtime_contract.get("runtime_capabilities", [])
            if isinstance(caps, list) and "node_loop_execution" not in caps:
                caps.append("node_loop_execution")
                generated_runtime_contract["runtime_capabilities"] = caps
    target_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    write_design_review_evidence(repo_root, run_root, request="mock request", mode="closed")


def host_capability_missing_contract() -> List[Dict[str, Any]]:
    return [
        {
            "id": "missing_binary",
            "kind": "external_binary",
            "name": "Missing Binary",
            "required": True,
            "probe": {
                "binary": "workflowprogram_missing_binary_xyz",
                "args": ["--version"],
            },
            "bootstrap": {
                "scope": "host_global",
                "summary": "Install the missing binary globally",
                "project_local_outputs": [],
            },
            "approval_required": True,
        }
    ]


def host_capability_project_local_contract() -> List[Dict[str, Any]]:
    return [
        {
            "id": "project_local_marker",
            "kind": "external_binary",
            "name": "Project Local Marker",
            "required": True,
            "probe": {
                "binary": "workflowprogram_missing_binary_xyz",
                "args": ["--version"],
            },
            "bootstrap": {
                "scope": "project_local",
                "summary": "Create reusable project-local bootstrap assets",
                "assets": [
                    {
                        "path": ".workflowprogram/bootstrap/project-local-marker.json",
                        "format": "json",
                        "content": {
                            "kind": "project_local_marker",
                            "status": "ready",
                        },
                    },
                    {
                        "path": ".workflowprogram/bootstrap/config/tool-config.json",
                        "format": "json",
                        "content": {
                            "binary": "workflowprogram_missing_binary_xyz",
                            "mode": "project_local",
                            "managed_by": "WorkflowProgram",
                        },
                    },
                    {
                        "path": ".workflowprogram/bootstrap/bin/project-local-wrapper.sh",
                        "format": "shell",
                        "executable": True,
                        "content": "#!/usr/bin/env bash\nprintf 'project-local bootstrap ready\\n'\n",
                    },
                ],
            },
            "approval_required": False,
        }
    ]


def host_capability_host_global_contract(target_root: Path) -> List[Dict[str, Any]]:
    shim_dir = (target_root.parent / "host-global" / "bin").resolve()
    shim_name = "workflowprogram_python3_host_global"
    shim_path = (shim_dir / shim_name).resolve()
    return [
        {
            "id": "host_global_python3_shim",
            "kind": "external_binary",
            "name": "Host Global Python 3 Shim",
            "required": True,
            "probe": {
                "binary": shim_name,
                "args": ["--version"],
                "search_paths": [str(shim_dir)],
            },
            "bootstrap": {
                "scope": "host_global",
                "summary": "Create an approval-gated host-global shim for python3",
                "project_local_outputs": [],
                "adapter": {
                    "type": "symlink_binary",
                    "source_binary": "python3",
                    "target_path": str(shim_path),
                },
            },
            "approval_required": True,
        }
    ]


def agent_team_contract_fixture(*, max_fan_out: int = 2) -> Dict[str, Any]:
    return {
        "enabled": True,
        "max_fan_out": max_fan_out,
        "join_policy": "all_must_pass",
        "roles": [
            {
                "id": "reviewer",
                "responsibility": "Review generated assets",
                "ownership_stage_slots": ["S5"],
                "output_patterns": ["outputs/stages/team/S5/reviewer/review-report.md"],
                "required": True,
            },
            {
                "id": "security_reviewer",
                "responsibility": "Review security-sensitive outputs",
                "ownership_stage_slots": ["S5"],
                "output_patterns": ["outputs/stages/team/S5/security_reviewer/review-report.md"],
                "required": True,
            },
            {
                "id": "lead_reviewer",
                "responsibility": "Join team review results",
                "ownership_stage_slots": ["S5"],
                "output_patterns": ["outputs/stages/team/S5/lead_reviewer/join-summary.md"],
                "required": True,
            },
        ],
        "execution": [
            {
                "stage_slot": "S5",
                "role_ids": ["reviewer", "security_reviewer"],
                "join_role": "lead_reviewer",
            }
        ],
    }


def node_loop_policy_fixture(*, max_iterations: int = 3) -> Dict[str, Any]:
    return {
        "enabled": True,
        "mode": "ralph",
        "goal_source": "model_subgoal",
        "parent_goal_ref": "user_goal.workflow_quality",
        "max_iterations": max_iterations,
        "fresh_context_each_iteration": True,
        "prompt_package": ".workflowprogram/loops/implement/prompt-package.md",
        "tdd_policy": {
            "enabled": True,
            "test_first_required": True,
            "red_green_refactor": True,
        },
        "feedback_commands": [
            {
                "id": "validate_generated_workflow",
                "kind": "test",
                "argv": ["python3", ".workflowprogram/runtime/validate-run-state.py", "--json"],
                "timeout_seconds": 120,
                "failure_effect": "feedback",
            }
        ],
        "stop_conditions": {
            "success": ["verifier_passed"],
            "max_iterations": "fail",
            "no_progress_iterations": 2,
            "hard_fail_on": ["unsafe_write"],
        },
        "evidence_outputs": [
            "outputs/stages/loops/implement/loop-plan.json",
            "outputs/stages/loops/implement/iteration-summary.jsonl",
            "outputs/stages/loops/implement/final-verdict.json",
        ],
    }


def capability_discovery_reverse_engineering() -> Dict[str, Any]:
    return {
        "enabled": True,
        "domains": ["reverse_engineering"],
        "include_local_installed": True,
        "include_curated_profiles": True,
        "infer_from_request": True,
    }


def run_json_script(repo_root: Path, script_name: str, *args: str) -> Dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(repo_root / ".claude" / "scripts" / script_name), *args, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"{script_name} failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{script_name} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{script_name} must return a JSON object")
    return payload


def run_json_script_allow(repo_root: Path, script_name: str, allowed: set[int], *args: str) -> Dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(repo_root / ".claude" / "scripts" / script_name), *args, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in allowed:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"{script_name} failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{script_name} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{script_name} must return a JSON object")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_design_review_evidence(
    repo_root: Path,
    run_root: Path,
    *,
    request: str,
    mode: str = "closed",
) -> Dict[str, Any]:
    """Write deterministic S3 design-review evidence for smoke fixtures."""

    review_root = run_root / "outputs" / "stages" / "design-review"
    if mode == "missing":
        if review_root.exists():
            shutil.rmtree(review_root)
        return {"status": "MISSING"}

    packet = run_json_script_allow(
        repo_root,
        "generate-design-review-packet.py",
        {0, 2},
        "--run-root",
        str(run_root),
        "--request",
        request,
    )
    packet_path = review_root / "design-review-packet.json"
    packet_sha = sha256_file(packet_path)
    artifact_fingerprints = packet.get("artifact_fingerprints", {}) if isinstance(packet.get("artifact_fingerprints"), dict) else {}

    if mode == "blocker":
        issues = [
            {
                "id": "DRV-001",
                "round_found": 1,
                "status": "open",
                "severity": "blocker",
                "blocking": True,
                "lens": "spec_projection",
                "affected_requirements": ["REQ-001"],
                "affected_artifacts": ["outputs/stages/s3-design-highlevel.md", "workflow-spec.yaml"],
                "problem": "The high-level design changed executable flow but workflow-spec.yaml was not updated.",
                "why_it_matters": "S4 would generate assets from a stale control-plane projection.",
                "required_fix": "Update workflow-spec.yaml and traceability before implementation.",
                "resolved_by": "",
                "resolution_evidence": [],
                "residual_risk": "",
            }
        ]
        closure_status = "FAIL"
    elif mode == "accepted_risk":
        issues = [
            {
                "id": "DRV-001",
                "round_found": 1,
                "status": "accepted_risk",
                "severity": "minor",
                "blocking": False,
                "lens": "complexity_control",
                "affected_requirements": ["REQ-001"],
                "affected_artifacts": ["outputs/stages/s3-design-lowlevel.md"],
                "problem": "The generated lowlevel guide is slightly more verbose than necessary for the fixture.",
                "why_it_matters": "It may add reading overhead but does not change runtime behavior.",
                "required_fix": "Trim wording in a later docs pass if needed.",
                "resolved_by": "",
                "resolution_evidence": [],
                "residual_risk": "Accepted for deterministic smoke coverage; no runtime semantics are affected.",
            }
        ]
        closure_status = "PASS"
    else:
        issues = []
        closure_status = "PASS"

    write_json(
        review_root / "round-1.json",
        {
            "schema_version": 1,
            "round": 1,
            "status": "PASS" if closure_status == "PASS" else "FAIL",
            "summary": "Deterministic design-review fixture.",
            "issues": issues,
        },
    )
    write_json(
        review_root / "issues.json",
        {
            "schema_version": 1,
            "generated_at": iso_now(),
            "issues": issues,
        },
    )
    write_text(
        review_root / "report.md",
        "# Design Review Report\n\n"
        f"- mode: `{mode}`\n"
        f"- status: `{closure_status}`\n"
        f"- issues: `{len(issues)}`\n",
    )
    open_blocking = [item for item in issues if item.get("blocking") and item.get("status") == "open"]
    write_json(
        review_root / "closure.json",
        {
            "schema_version": 1,
            "schema_name": "design-review-closure",
            "generated_at": iso_now(),
            "status": closure_status,
            "packet_path": "outputs/stages/design-review/design-review-packet.json",
            "packet_sha256": packet_sha,
            "artifact_fingerprints": artifact_fingerprints,
            "issue_count": len(issues),
            "open_blocking_count": len(open_blocking),
            "accepted_risk_count": len([item for item in issues if item.get("status") == "accepted_risk"]),
        },
    )
    return run_json_script_allow(
        repo_root,
        "validate-design-review-gate.py",
        {0, 2},
        "--run-root",
        str(run_root),
    )


def write_existing_managed_seed(target_root: Path) -> None:
    """Create enough target-side evidence for resolve-change-context to see a managed workflow."""

    write_text(target_root / ".workflowprogram" / "design" / "workflow-spec.yaml", "name: existing-managed\n")
    write_text(target_root / ".workflowprogram" / "design" / "workflow-maintenance.md", "# Existing Maintenance Guide\n")
    write_json(
        manifest_path_for(target_root),
        {
            "schema_version": 1,
            "updated_at": iso_now(),
            "entries": [
                {
                    "relative_path": ".claude/settings.json",
                    "producer_version": "mock",
                    "last_applied_hash": "",
                    "ownership": "managed",
                    "last_applied_at": iso_now(),
                    "last_run_id": "seed",
                }
            ],
        },
    )


def write_change_policy_inputs(
    repo_root: Path,
    run_root: Path,
    target_root: Path,
    request: str,
    *,
    mode: str = "incremental",
    allowed_extra: List[str] | None = None,
    include_policy: bool = True,
    stale: bool = False,
) -> Dict[str, Any]:
    stages = run_root / "outputs" / "stages"
    route = run_json_script(
        repo_root,
        "route-intent.py",
        "--request",
        request,
        "--target-root",
        str(target_root),
        "--out",
        str(stages / "route-intent.json"),
    )
    context = run_json_script(
        repo_root,
        "resolve-change-context.py",
        "--request",
        request,
        "--target-root",
        str(target_root),
        "--route",
        str(stages / "route-intent.json"),
        "--out",
        str(stages / "change-context.json"),
    )
    write_json(
        stages / "existing-workflow-readback.json",
        {
            "generated_at": iso_now(),
            "sources": [
                {
                    "path": ".workflowprogram/design/workflow-spec.yaml",
                    "sha256": context.get("fingerprints", {}).get("design_spec_sha256"),
                    "summary": "Existing managed workflow spec was read before change.",
                }
            ],
            "managed_manifest_status": "present",
        },
    )
    if not include_policy:
        write_json(
            stages / "entry-orchestration-summary.json",
            {
                "generated_at": iso_now(),
                "status": "BLOCKED",
                "failure_kind": "design",
                "block_reason": "change_policy_required",
                "change_context": context,
            },
        )
        return {"route": route, "context": context}

    affected = [
        ".workflowprogram/design/workflow-spec.yaml",
        ".claude/settings.json",
        ".claude/rules/constraints.md",
        ".claude/commands/example.md",
        *(allowed_extra or []),
    ]
    write_json(
        stages / "change-policy.json",
        {
            "schema_version": 1,
            "mode": mode,
            "scope": "node" if mode == "incremental" else "graph",
            "target_state": context.get("target_state"),
            "affected_nodes": ["example"],
            "affected_artifacts": affected,
            "allowed_derived_artifacts": [
                ".workflowprogram/design/workflow-view.md",
                ".workflowprogram/design/workflow-maintenance.md",
                ".workflowprogram/design/source/**",
                ".workflowprogram/runtime/**",
            ],
            "preserve_user_edits": True,
            "requires_approval": True,
            "approval_reason": "Existing managed workflow assets are being modified.",
            "escalate_to_redesign": mode == "redesign_from_existing",
            "reason": "Mock change-policy fixture.",
        },
    )
    write_json(
        stages / "impact-analysis.json",
        {
            "old_design_sources_read": [".workflowprogram/design/workflow-spec.yaml"],
            "readback_evidence_path": "outputs/stages/existing-workflow-readback.json",
            "existing_managed_manifest_status": "present",
            "changed_requirement_ids": ["REQ-001"],
            "affected_spec_sections": ["workflow_graph.nodes.example"],
            "spec_change_required": True,
            "affected_design_source_sections": ["example node"],
            "test_contract_change_required": False,
            "test_contract_change_reason": "Mock fixture keeps test contract categories stable.",
            "affected_test_contract_categories": ["flow", "artifacts"],
            "affected_target_assets": affected,
            "approval_requirement": "required",
            "risks": ["managed scope drift"],
            "verification_plan": ["validate-change-policy", "S5 judge"],
        },
    )
    current_context_path = stages / "change-context-current.json"
    current_context = dict(context)
    if stale:
        current_context["fingerprints"] = dict(current_context.get("fingerprints", {}))
        current_context["fingerprints"]["design_spec_sha256"] = "stale"
    write_json(current_context_path, current_context)
    validation = run_json_script_allow(
        repo_root,
        "validate-change-policy.py",
        {0, 2},
        "--policy",
        str(stages / "change-policy.json"),
        "--impact",
        str(stages / "impact-analysis.json"),
        "--change-context",
        str(stages / "change-context.json"),
        "--current-context",
        str(current_context_path),
        "--readback",
        str(stages / "existing-workflow-readback.json"),
        "--run-root",
        str(run_root),
        "--approval-status",
        "approved",
    )
    if validation.get("status") != "PASS":
        write_json(
            stages / "entry-orchestration-summary.json",
            {
                "generated_at": iso_now(),
                "status": "BLOCKED",
                "failure_kind": "design",
                "block_reason": validation.get("block_reason") or "change_policy_invalid",
                "change_policy_validation": validation,
                "change_context": context,
            },
        )
    return {"route": route, "context": context, "validation": validation}


def write_host_capability_outputs(
    repo_root: Path,
    run_root: Path,
    target_root: Path,
    *,
    apply_project_local: bool,
) -> Dict[str, Any]:
    probe_payload = run_json_script(
        repo_root,
        "probe-host-capabilities.py",
        "--spec",
        str(run_root / "workflow-spec.yaml"),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
    )
    bootstrap_payload: Dict[str, Any] | None = None
    if apply_project_local:
        bootstrap_args = [
            "--spec",
            str(run_root / "workflow-spec.yaml"),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
        ]
        bootstrap_payload = run_json_script(
            repo_root,
            "apply-host-bootstrap.py",
            *bootstrap_args,
        )
        probe_payload = run_json_script(
            repo_root,
            "probe-host-capabilities.py",
            "--spec",
            str(run_root / "workflow-spec.yaml"),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
        )
    return {
        "report": probe_payload.get("report", {}),
        "bootstrap": bootstrap_payload,
    }


def seed_prior_host_capability_failure(target_root: Path, report: Dict[str, Any]) -> None:
    """为 remediation loop 构造一条历史环境失败运行。"""

    prior_run_root = target_root / ".workflowprogram" / "runs" / "prior-host-capability-failure"
    prior_report = dict(report) if isinstance(report, dict) else {}
    prior_report["run_root"] = str(prior_run_root)
    prior_report["target_root"] = str(target_root)
    write_json(prior_run_root / "state.json", {
        "values": {
            "request_id": "prior-host-capability-failure",
            "failure_kind": "environment",
        }
    })
    write_json(prior_run_root / "outputs" / "stages" / "host-capability-report.json", prior_report)


def write_capability_discovery_outputs(repo_root: Path, run_root: Path, target_root: Path, request: str) -> Dict[str, Any]:
    payload = run_json_script(
        repo_root,
        "discover-host-capabilities.py",
        "--spec",
        str(run_root / "workflow-spec.yaml"),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
        "--request",
        request,
    )
    return {
        "report": payload.get("report", {}),
        "report_path": payload.get("report_path"),
        "instructions_path": payload.get("instructions_path"),
    }


def write_team_evidence(
    run_root: Path,
    contract: Dict[str, Any],
    *,
    overflow: bool = False,
    join_satisfied: bool = True,
) -> None:
    roles = contract.get("roles", []) if isinstance(contract.get("roles"), list) else []
    execution = contract.get("execution", []) if isinstance(contract.get("execution"), list) else []
    fanout_roles = ["reviewer", "security_reviewer"]
    if overflow:
        fanout_roles.append("lead_reviewer")
    plan = {
        "generated_at": iso_now(),
        "execution": execution,
        "fan_out_count": len(fanout_roles),
        "roles": fanout_roles,
        "max_fan_out": contract.get("max_fan_out"),
    }
    results = {
        "generated_at": iso_now(),
        "roles": [
            {"id": role_id, "status": "PASS", "output": f"outputs/stages/team/S5/{role_id}/review-report.md"}
            for role_id in fanout_roles
        ],
    }
    join_summary = {
        "generated_at": iso_now(),
        "join_policy": contract.get("join_policy"),
        "join_role": execution[0].get("join_role") if execution else "",
        "satisfied": join_satisfied,
        "fan_out_count": len(fanout_roles),
    }
    write_json(run_root / "outputs" / "stages" / "team-plan.json", plan)
    write_json(run_root / "outputs" / "stages" / "team-results.json", results)
    write_json(run_root / "outputs" / "stages" / "team-join-summary.json", join_summary)
    for role_id in fanout_roles:
        output_path = run_root / "outputs" / "stages" / "team" / "S5" / role_id / "review-report.md"
        write_text(output_path, f"# Team Output\n\n- role: `{role_id}`\n- status: `PASS`\n")
    append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "TeamFanOutStart", "stage": "S5", "source": "mock-runtime-host", "status": "ok", "message": "Started team fan-out", "role_ids": fanout_roles})
    for role_id in fanout_roles:
        append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "TeamRoleStarted", "stage": "S5", "source": "mock-runtime-host", "status": "running", "message": f"Started role {role_id}", "role_id": role_id})
        append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "TeamRoleCompleted", "stage": "S5", "source": "mock-runtime-host", "status": "ok", "message": f"Completed role {role_id}", "role_id": role_id})
    append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "TeamJoinCompleted", "stage": "S5", "source": "mock-runtime-host", "status": "ok" if join_satisfied else "error", "message": "Team join completed", "join_policy": contract.get("join_policy"), "satisfied": join_satisfied})


def write_loop_evidence(
    run_root: Path,
    *,
    node_id: str = "implement",
    iterations: int = 2,
    final_status: str = "PASS",
    verifier_passed: bool = True,
    stop_reason: str = "verifier_passed",
) -> None:
    loop_root = run_root / "outputs" / "stages" / "loops" / node_id
    plan = {
        "generated_at": iso_now(),
        "node_id": node_id,
        "mode": "ralph",
        "goal_source": "model_subgoal",
        "parent_goal_ref": "user_goal.workflow_quality",
        "max_iterations": 3,
        "fresh_context_each_iteration": True,
        "test_first_observed": True,
        "prompt_package": f".workflowprogram/loops/{node_id}/prompt-package.md",
    }
    write_json(loop_root / "loop-plan.json", plan)
    iteration_path = loop_root / "iteration-summary.jsonl"
    for index in range(1, iterations + 1):
        status = "PASS" if index == iterations and final_status == "PASS" else "FAIL"
        entry = {
            "iteration": index,
            "status": status,
            "feedback_command_id": "validate_generated_workflow",
            "agent_result": "updated target workflow outputs" if status == "FAIL" else "no changes needed",
            "verifier_passed": status == "PASS",
        }
        append_jsonl(iteration_path, entry)
        iteration_dir = loop_root / "iterations" / str(index)
        write_json(iteration_dir / "feedback-commands.json", {"iteration": index, "commands": [{"id": "validate_generated_workflow", "status": status}]})
        write_json(iteration_dir / "agent-result.json", {"iteration": index, "status": status})
        write_json(iteration_dir / "verifier-result.json", {"iteration": index, "status": status, "passed": status == "PASS"})
    write_json(
        loop_root / "final-verdict.json",
        {
            "generated_at": iso_now(),
            "node_id": node_id,
            "status": final_status,
            "stop_reason": stop_reason,
            "iterations": iterations,
            "verifier_passed": verifier_passed,
        },
    )
    append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "LoopStart", "stage": "S4", "source": "mock-runtime-host", "status": "ok", "node_id": node_id})
    for index in range(1, iterations + 1):
        append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "LoopIterationStart", "stage": "S4", "source": "mock-runtime-host", "status": "running", "node_id": node_id, "iteration": index})
        append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "LoopFeedbackCommandCompleted", "stage": "S4", "source": "mock-runtime-host", "status": "ok", "node_id": node_id, "iteration": index})
        append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "LoopAgentCompleted", "stage": "S4", "source": "mock-runtime-host", "status": "ok", "node_id": node_id, "iteration": index})
        append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "LoopVerifierCompleted", "stage": "S4", "source": "mock-runtime-host", "status": "ok", "node_id": node_id, "iteration": index, "passed": index == iterations and verifier_passed})
    append_jsonl(run_root / "events.jsonl", {"ts": iso_now(), "type": "LoopStop", "stage": "S4", "source": "mock-runtime-host", "status": final_status.lower(), "node_id": node_id, "stop_reason": stop_reason})


def infer_intent(entry_skill: str) -> str:
    """根据入口技能名推断 workflow intent。"""
    if entry_skill.endswith("-audit"):
        return "audit"
    if entry_skill.endswith("-validate"):
        return "validate"
    if entry_skill.endswith("-iterate"):
        return "iterate"
    if entry_skill.endswith("-orchestrate"):
        return "orchestrate"
    return "develop"


def stage_history_for_intent(intent: str) -> List[str]:
    """返回给定 intent 对应的模拟 stage history。"""
    if intent == "audit":
        return ["validate", "lessons"]
    if intent == "validate":
        return ["validate"]
    if intent == "iterate":
        return ["lessons"]
    return ["requirement", "context", "design", "generate", "validate", "lessons"]


def derive_failure_kind(category: str) -> str:
    """把 smoke 层失败码映射为 runtime failure_kind。"""
    if category in {"", "none"}:
        return "none"
    if category in {"CONFLICT", "CONFLICT_FAILURE"}:
        return "conflict"
    if category in {"STRUCTURE_FAILURE", "MISSING_ARGUMENT", "INPUT_FAILURE"}:
        return "design"
    if category in {"RUNTIME_HOST_MISSING", "TARGET_NOT_WRITABLE", "RUNTIME_HOST_NOT_READY"}:
        return "environment"
    return "implementation"


def write_workflow_spec_draft(run_root: Path, entry_skill: str, request: str) -> None:
    """为 develop 类流程生成确定性的 S1 草案产物。"""
    draft = "\n".join(
        [
            "# Workflow Specification",
            "",
            "## Workflow Identity",
            "",
            "- 工作流名称：Mock Generated Workflow",
            f"- 触发命令：/{entry_skill}",
            "- 简要描述：由 mock_runtime_host 生成的确定性工作流草案。",
            "",
            "## User Intent",
            "",
            f"- 用户诉求：围绕 `{request.strip() or 'default request'}` 建立清晰的 workflow 方案。",
            "- 最终目的：把用户要解决的问题转成可交付、可验证、可迭代的目标工作流。",
            "- 成功标准：需求、目的、成功标准与质量门禁都已确认，可进入设计阶段。",
            "",
            "## Clarification Summary",
            "",
            "- 澄清轮次：2",
            "- 已确认事项：触发方式；核心输入输出；质量门禁；目标交付物；非目标边界。",
            "- 已消解歧义：用户诉求；最终目的；成功标准；默认交付范围已经明确。",
            "",
            "## Requirement Logic Interview",
            "",
            "- 复杂度：M",
            "- Purpose Lens：目标是为用户请求生成可持续运行、可验证、可审计的目标 workflow。",
            "- Object Lens：输入对象为用户请求和目标项目资产；中间对象为需求索引、设计源和 managed plan；输出对象为 `.claude/` 与 `.workflowprogram/` workflow 资产。",
            "- Process Lens：clarify requirement -> collect context -> design workflow graph -> generate managed assets -> validate runtime evidence。",
            "- Decision Lens：当存在资产冲突、审批未决、环境能力缺失或验证失败时，workflow 必须停止或回到对应阶段。",
            "- Evidence Lens：必须保留 clarification package、logic map、managed result、state.json、events.jsonl 和 S5 summary。",
            "- Acceptance Lens：给定明确用户请求时应生成目标 workflow 资产并通过 S5；给定冲突或验证失败时应留下失败证据。",
            "- Boundary Lens：不得静默覆盖非托管资产；不得跳过审批和 S5；不得自动修改应用代码。",
            "- 关键追问：哪些目标输出必须进入 registry 或 test_contract 以便 S5 验证；哪些失败证据足以阻止 clean PASS。",
            "- 候选节点：entry；generate-assets；validate-assets。",
            "- 负向/停止场景：审批未完成时停止；目标资产冲突时停止；必需环境能力缺失时失败并给出 remediation。",
            "",
            "## Open Questions",
            "",
            "- 阻塞未决问题：无",
            "- 可延后问题：可在 S3 继续细化的命名与文档措辞",
            "- 问题处理策略：阻塞问题必须在 S1 清零；可延后问题进入假设日志并在设计阶段追踪。",
            "",
            "## Assumptions and Boundaries",
            "",
            "- 当前假设：目标项目路径可访问；用户接受托管 workflow 资产；已有约束文件可读取。",
            "- 外部依赖：当前仓库中的 workflow 设计文档；constraints；目标项目现有 `.claude` 资产（如存在）。",
            "- 关键边界场景：审批未完成时不得进入 S4；目标资产冲突时不得静默覆盖；环境依赖缺失时必须显式失败或给出 remediation。",
            "- 明确不做：不直接修改应用代码；不跳过 S5 验证；不绕过 managed apply 边界。",
            "",
            "## Target Workflow Graph Readback",
            "",
            "- WorkflowProgram 自身是否仍按 `S0..S6` 开发主链执行：是，WorkflowProgram 自身仍按 S1-S6 控制面执行。",
            "- 目标工作流是否需要非 `S1..S6` 的业务节点：需要，目标工作流使用业务化节点而不是照搬 S1-S6。",
            "- 目标 workflow_graph 节点：entry -> generate-assets -> validate-assets",
            "- 目标 workflow_graph 入口与转移：entry 从注册命令进入；entry -> generate-assets；generate-assets -> validate-assets。",
            "- 每个 graph 节点的输入、输出、gate、owner：entry 输入用户请求并输出 intake summary；generate-assets 输出候选资产；validate-assets 输出验证报告。",
            "- 每个 graph 节点的执行模型（skill / agent / script / team / loop）：entry 使用 skill；generate-assets 使用 script；validate-assets 使用 script 与 judge。",
            "- 哪些 node 需要独立 agent，原因是什么：无，mock provider 使用确定性 provider 生成证据。",
            "- 哪些 node 不需要独立 agent，原因是什么：entry、generate-assets、validate-assets 均可由确定性 provider 模拟。",
            "- 复杂 node-design 输出路径：无。",
            "- 需要 `loop_policy` 的 graph 节点：无。",
            "- 每个 loop 节点的 `max_iterations`、反馈命令、停止条件、证据输出：无。",
            "- 目标输出是否已映射到 `registry` 或 `test_contract.artifacts`：是，`.claude/` 与 `.workflowprogram/` 交付物均由 registry 或 deliverables 声明。",
            "",
            "## File Plan",
            "",
            "- 需要创建的文件：`.claude/settings.json`；`.claude/commands/example.md`；`.workflowprogram/design/workflow-spec.yaml`；`.workflowprogram/runtime/workflow-entry.py`。",
            "- 需要修改的文件：`.claude/rules/constraints.md`。",
            "",
            "## Readback Confirmation",
            "",
            "- 回读摘要：本工作流将围绕请求形成可验证的 Claude Code workflow 资产，明确交付物、质量门禁和非目标边界。",
            "- 用户确认状态：confirmed",
            "- 最近修正：无",
            "",
            "## Trigger Model",
            "",
            "- 调用方式：手动命令",
            f"- 触发细节：使用 `/{entry_skill}` 处理请求 `{request.strip() or 'default request'}`。",
            "",
            "## Inputs",
            "",
            "- 必需输入：用户请求文本",
            "- 可选输入：目标项目上下文",
            "- 所需外部上下文：当前仓库中的 workflow 设计与约束文件",
            "",
            "## Outputs",
            "",
            "- 主交付物：WorkflowProgram 管理的 `.claude/` 资产",
            "- 次级产物：运行时验证报告与 lessons 增量",
            "- 输出格式：Markdown、YAML、JSON",
            "",
            "## Quality Gates",
            "",
            "- 阻塞条件：审批未完成或运行边界违规",
            "- 必需验证：spec schema、managed apply、S5 runtime judge",
            "- 完成定义：工作流资产生成完成且验证结论为 PASS/WARN",
            "",
        ]
    )
    write_text(run_root / "workflow-spec.md", draft + "\n")


def write_lessons_delta(
    run_root: Path,
    intent: str,
    failure_kind: str,
    request: str,
    *,
    extra_candidates: List[str] | None = None,
) -> None:
    """生成确定性的 S6 lessons delta 产物。"""
    run_id = run_root.name
    body = "\n".join(
        [
            "# S6 Lessons Delta",
            "",
            f"- run_id: `{run_id}`",
            f"- failure_kind: `{failure_kind}`",
            f"- intent: `{intent}`",
            "",
            "## Observations",
            "",
            f"- 本轮请求：`{request.strip() or 'default request'}`",
            "- 控制面证据和阶段流已被写入 RUN_ROOT。",
            "",
            "## Constraint Candidates",
            "",
            "- 继续将运行时证据限制在 RUN_ROOT，并只将托管产物写入 TARGET_ROOT/.claude。",
            *[f"- {item}" for item in (extra_candidates or [])],
            "",
        ]
    )
    write_text(run_root / "outputs" / "stages" / "s6-lessons-delta.md", body + "\n")


def generate_design_docs(repo_root: Path, run_root: Path) -> Dict[str, Path]:
    """基于真实生成器产出 workflow-view.md 与 workflow-maintenance.md。"""

    spec_path = run_root / "workflow-spec.yaml"
    script_root = repo_root / ".claude" / "scripts"
    outputs = {
        "workflow_spec": spec_path,
        "workflow_view": run_root / "workflow-view.md",
        "workflow_maintenance": run_root / "workflow-maintenance.md",
    }
    for script_name, out_path in (
        ("generate-workflow-view.py", outputs["workflow_view"]),
        ("generate-workflow-maintenance.py", outputs["workflow_maintenance"]),
    ):
        completed = subprocess.run(
            [
                sys.executable,
                str(script_root / script_name),
                "--spec",
                str(spec_path),
                "--out",
                str(out_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"{script_name} failed")
    return outputs


def generate_target_runtime_assets(repo_root: Path, spec_path: Path, out_root: Path) -> Dict[str, Path]:
    """基于真实生成器产出 target-side runtime 资产。"""

    script_path = repo_root / ".claude" / "scripts" / "generate-target-runtime.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--spec",
            str(spec_path),
            "--out-root",
            str(out_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "generate-target-runtime.py failed")
    payload = json.loads(completed.stdout)
    files = payload.get("files", {})
    return {
        "entry_script": Path(str(files.get("entry_script", ""))).resolve(),
        "runner_script": Path(str(files.get("runner_script", ""))).resolve(),
        "state_validator_script": Path(str(files.get("state_validator_script", ""))).resolve(),
        "runtime_manifest": Path(str(files.get("runtime_manifest", ""))).resolve(),
    }


def apply_target_claude_guard(repo_root: Path, spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    """Apply the same target CLAUDE.md guard that real develop applies."""

    script_path = repo_root / ".claude" / "scripts" / "apply-target-claude-guard.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout.strip()) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "apply-target-claude-guard.py failed"
        if isinstance(payload, dict) and payload.get("reason"):
            message = str(payload.get("reason"))
        raise RuntimeError(message)
    return payload if isinstance(payload, dict) else {}


def stage_design_source_archive(run_root: Path, spec_path: Path, destination_root: Path) -> Dict[str, str]:
    """Copy target design source files to a managed destination root."""

    try:
        spec_payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except Exception:
        spec_payload = {}
    if not isinstance(spec_payload, dict):
        spec_payload = {}
    resolved = resolve_target_design_refs(spec_payload)
    persistent_refs = dict(PERSISTENT_DEFAULTS)
    persistent_refs.update(resolved.persistent_refs)

    copied: Dict[str, str] = {}
    for key, rel_path in resolve_existing_run_refs(run_root, spec_payload).items():
        target_rel = persistent_refs.get(key)
        source = run_root / rel_path
        if not target_rel or not source.exists() or not source.is_file():
            continue
        target = destination_root / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[key] = target.relative_to(destination_root).as_posix()

    for node_id, rel_path in iter_existing_node_design_refs(run_root, spec_payload).items():
        source = run_root / rel_path
        if not source.exists() or not source.is_file():
            continue
        target_rel = resolved.persistent_node_designs.get(
            node_id,
            f".workflowprogram/design/source/target-node-designs/{node_id}.md",
        )
        target = destination_root / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[f"node_design:{node_id}"] = target.relative_to(destination_root).as_posix()
    return copied


def write_progress_outputs(
    run_root: Path,
    stage_history: List[str],
    result: str,
    category: str,
    *,
    current_stage: str,
    next_action: str,
    approval_status: str = "approved",
) -> None:
    """写出后续校验步骤所需的 progress 产物。"""
    outputs = run_root / "outputs"
    write_json(
        outputs / "progress" / "current-progress.json",
        {
            "run_id": run_root.name,
            "updated_at": iso_now(),
            "current_stage": current_stage,
            "current_node": current_stage,
            "percent": 100 if result == "PASS" else 80,
            "last_status": "ok" if result == "PASS" else "error",
            "last_verdict": result,
            "next_action": next_action,
            "approval_status": approval_status,
            "stage_history": stage_history,
            "result": result,
            "category": category or None,
        },
    )
    append_jsonl(
        outputs / "progress" / "milestones.jsonl",
        {
            "ts": iso_now(),
            "stage_history": stage_history,
            "result": result,
        },
    )
    write_text(
        outputs / "progress" / "user-progress.md",
        "# Workflow Progress\n\n"
        f"- run_id: `{run_root.name}`\n"
        f"- current_stage: `{current_stage}`\n"
        f"- current_node: `{current_stage}`\n"
        f"- percent: `{100 if result == 'PASS' else 80}`\n"
        f"- last_status: `{'ok' if result == 'PASS' else 'error'}`\n"
        f"- last_verdict: `{result}`\n"
        f"- approval_status: `{approval_status}`\n"
        f"- updated_at: `{iso_now()}`\n\n"
        "## 历史关键节点结果\n\n"
        f"- Stage history: `{', '.join(stage_history) or 'none'}`\n"
        f"- Result: `{result}`\n\n"
        "## Next Action\n\n"
        f"- {next_action}\n",
    )


def write_runner_evidence(
    run_root: Path,
    target_root: Path,
    intent: str,
    entry_skill: str,
    stage_history: List[str],
    result: str,
    category: str,
) -> None:
    """产出由 runner 负责、供 S5 校验消费的最小证据集。"""
    outputs = run_root / "outputs"
    write_json(
        outputs / "stages" / "s0-route.json",
        {
            "intent": intent,
            "entry_skill": entry_skill,
            "target_root": str(target_root),
            "routed_at": iso_now(),
        },
    )
    write_json(
        outputs / "stages" / "runner-summary.json",
        {
            "run_id": run_root.name,
            "status": result,
            "entry_skill": entry_skill,
            "transition_count": len(stage_history),
            "failure_code": category or None,
        },
    )


def write_managed_outputs(run_root: Path, target_root: Path, conflict: bool) -> None:
    """产出确定性的 managed-apply 结果，并可选生成冲突副本。"""
    outputs = run_root / "outputs"
    settings_path = target_root / ".claude" / "settings.json"
    manifest_path = manifest_path_for(target_root)
    candidate_root = run_root / "outputs" / "candidate"
    candidate_source = candidate_root / ".claude" / "settings.json"
    write_text(candidate_source, '{\n  "commands": ["example"],\n  "managed": true\n}\n')
    rules_source = run_root / "outputs" / "candidate" / ".claude" / "rules" / "constraints.md"
    command_source = run_root / "outputs" / "candidate" / ".claude" / "commands" / "example.md"
    skill_source = run_root / "outputs" / "candidate" / ".claude" / "skills" / "example" / "SKILL.md"
    design_spec_source = run_root / "outputs" / "candidate" / ".workflowprogram" / "design" / "workflow-spec.yaml"
    design_view_source = run_root / "outputs" / "candidate" / ".workflowprogram" / "design" / "workflow-view.md"
    design_maintenance_source = run_root / "outputs" / "candidate" / ".workflowprogram" / "design" / "workflow-maintenance.md"
    runtime_root = run_root / "outputs" / "candidate" / ".workflowprogram" / "runtime"
    write_text(rules_source, "# Constraints\n\n- Keep workflow assets managed.\n")
    write_text(command_source, managed_runtime_command_text())
    write_text(skill_source, "---\nname: example-skill\ndescription: Example skill declared by fixture workflow-spec\n---\n")
    design_spec_source.parent.mkdir(parents=True, exist_ok=True)
    for source_path, run_path in (
        (design_spec_source, run_root / "workflow-spec.yaml"),
        (design_view_source, run_root / "workflow-view.md"),
        (design_maintenance_source, run_root / "workflow-maintenance.md"),
    ):
        source_path.write_text(run_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    source_archive = stage_design_source_archive(run_root, run_root / "workflow-spec.yaml", candidate_root)
    runtime_files = generate_target_runtime_assets(Path(__file__).resolve().parents[1], run_root / "workflow-spec.yaml", runtime_root)
    source_plan_entries = [
        {
            "relative_path": rel_path,
            "source_path": str(candidate_root / rel_path),
            "target_path": str(target_root / rel_path),
            "decision": "create",
        }
        for rel_path in sorted(source_archive.values())
    ]
    plan_entries = [
        {
            "relative_path": ".claude/settings.json",
            "source_path": str(candidate_source),
            "target_path": str(settings_path),
            "decision": "conflict-managed-drift" if conflict else "update",
        },
        {
            "relative_path": ".claude/rules/constraints.md",
            "source_path": str(rules_source),
            "target_path": str(target_root / ".claude" / "rules" / "constraints.md"),
            "decision": "create",
        },
        {
            "relative_path": ".claude/commands/example.md",
            "source_path": str(command_source),
            "target_path": str(target_root / ".claude" / "commands" / "example.md"),
            "decision": "create",
        },
        {
            "relative_path": ".workflowprogram/design/workflow-spec.yaml",
            "source_path": str(design_spec_source),
            "target_path": str(target_root / ".workflowprogram" / "design" / "workflow-spec.yaml"),
            "decision": "create",
        },
        {
            "relative_path": ".workflowprogram/design/workflow-view.md",
            "source_path": str(design_view_source),
            "target_path": str(target_root / ".workflowprogram" / "design" / "workflow-view.md"),
            "decision": "create",
        },
        {
            "relative_path": ".workflowprogram/design/workflow-maintenance.md",
            "source_path": str(design_maintenance_source),
            "target_path": str(target_root / ".workflowprogram" / "design" / "workflow-maintenance.md"),
            "decision": "create",
        },
        {
            "relative_path": ".workflowprogram/runtime/workflow-entry.py",
            "source_path": str(runtime_files["entry_script"]),
            "target_path": str(target_root / ".workflowprogram" / "runtime" / "workflow-entry.py"),
            "decision": "create",
        },
        {
            "relative_path": ".workflowprogram/runtime/workflow-runner.py",
            "source_path": str(runtime_files["runner_script"]),
            "target_path": str(target_root / ".workflowprogram" / "runtime" / "workflow-runner.py"),
            "decision": "create",
        },
        {
            "relative_path": ".workflowprogram/runtime/validate-run-state.py",
            "source_path": str(runtime_files["state_validator_script"]),
            "target_path": str(target_root / ".workflowprogram" / "runtime" / "validate-run-state.py"),
            "decision": "create",
        },
        {
            "relative_path": ".workflowprogram/runtime/runtime-manifest.json",
            "source_path": str(runtime_files["runtime_manifest"]),
            "target_path": str(target_root / ".workflowprogram" / "runtime" / "runtime-manifest.json"),
            "decision": "create",
        },
        *source_plan_entries,
    ]
    managed_summary = {
        "create": sum(1 for entry in plan_entries if entry["decision"] == "create"),
        "update": sum(1 for entry in plan_entries if entry["decision"] == "update"),
        "conflict": sum(1 for entry in plan_entries if str(entry["decision"]).startswith("conflict")),
    }
    write_json(
        outputs / "managed-change-plan.json",
        with_report_fields(
            {
                "generated_at": iso_now(),
                "entries": plan_entries,
                "summary": managed_summary,
            },
            schema_name="managed-change-plan",
            error_code="CONFLICT" if conflict else None,
            failure_kind="conflict" if conflict else "none",
            remediation=[{"code": "RESOLVE_MANAGED_CONFLICTS", "summary": "Review conflict copies."}] if conflict else [],
        ),
    )
    result_payload: Dict[str, Any] = {
        "generated_at": iso_now(),
        "target_root": str(target_root),
            "run_root": str(run_root),
            "manifest_path": str(manifest_path),
            "summary": managed_summary,
            "applied": [],
        "conflicts": [],
    }
    if conflict:
        # 冲突模式要模拟真实 managed-apply 语义：保留 RUN_ROOT 下的候选副本，
        # 且不直接改动被管理的目标文件。
        conflict_copy = run_root / "outputs" / "conflicts" / ".claude" / "settings.json"
        write_text(conflict_copy, '{"conflict": true}\n')
        result_payload["conflicts"].append(
            {
                "relative_path": ".claude/settings.json",
                "target_path": str(settings_path),
                "decision": "conflict-managed-drift",
                "conflict_copy": str(conflict_copy),
            }
        )
    else:
        for entry in plan_entries:
            result_payload["applied"].append(
                {
                    "relative_path": entry["relative_path"],
                    "action": entry["decision"],
                    "target_path": entry["target_path"],
                    "applied_sha256": "mock-managed-applied-hash",
                    "before_sha256": "mock-managed-before-hash" if entry["decision"] == "update" else None,
                    "before_snapshot": None,
                    "run_id": run_root.name,
                }
            )
    source_manifest_entries = [
        {
            "relative_path": entry["relative_path"],
            "last_applied_hash": "mock-managed-hash-design-source",
            "ownership": "workflowprogram",
            "producer_version": "mock-runtime-host",
            "updated_at": iso_now(),
        }
        for entry in source_plan_entries
    ]
    write_json(
        manifest_path,
        {
            "manifest_version": 1,
            "updated_at": iso_now(),
            "entries": (
                []
                if conflict
                else [
                    {
                        "relative_path": ".claude/commands/example.md",
                        "last_applied_hash": "mock-managed-hash-command",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".claude/rules/constraints.md",
                        "last_applied_hash": "mock-managed-hash-rules",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".claude/settings.json",
                        "last_applied_hash": "mock-managed-hash",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".workflowprogram/design/workflow-maintenance.md",
                        "last_applied_hash": "mock-managed-hash-lowlevel",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".workflowprogram/design/workflow-spec.yaml",
                        "last_applied_hash": "mock-managed-hash-spec",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".workflowprogram/design/workflow-view.md",
                        "last_applied_hash": "mock-managed-hash-view",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".workflowprogram/runtime/runtime-manifest.json",
                        "last_applied_hash": "mock-managed-hash-runtime-manifest",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".workflowprogram/runtime/validate-run-state.py",
                        "last_applied_hash": "mock-managed-hash-runtime-validator",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".workflowprogram/runtime/workflow-entry.py",
                        "last_applied_hash": "mock-managed-hash-runtime-entry",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    {
                        "relative_path": ".workflowprogram/runtime/workflow-runner.py",
                        "last_applied_hash": "mock-managed-hash-runtime-runner",
                        "ownership": "workflowprogram",
                        "producer_version": "mock-runtime-host",
                        "updated_at": iso_now(),
                    },
                    *source_manifest_entries,
                ]
            ),
        },
    )
    result_payload = with_report_fields(
        result_payload,
        schema_name="managed-change-result",
        error_code="CONFLICT" if conflict else None,
        failure_kind="conflict" if conflict else "none",
        remediation=[{"code": "REVIEW_MANAGED_CONFLICTS", "summary": "Resolve conflicts before re-running."}] if conflict else [],
    )
    write_json(outputs / "managed-change-result.json", result_payload)
    rollback_entries: List[Dict[str, Any]] = []
    for item in result_payload.get("applied", []) if isinstance(result_payload.get("applied"), list) else []:
        rollback_entries.append(
            {
                "relative_path": item.get("relative_path"),
                "target_path": item.get("target_path"),
                "action": item.get("action"),
                "rollback_action": "restore_before_snapshot" if item.get("action") == "update" else "delete_created_file",
                "safe_if_current_sha256_equals": item.get("applied_sha256"),
                "before_sha256": item.get("before_sha256"),
            }
        )
    for item in result_payload.get("conflicts", []) if isinstance(result_payload.get("conflicts"), list) else []:
        rollback_entries.append(
            {
                "relative_path": item.get("relative_path"),
                "target_path": item.get("target_path"),
                "action": "conflict",
                "rollback_action": "none",
                "conflict_copy": item.get("conflict_copy"),
            }
        )
    write_json(
        outputs / "managed-rollback-manifest.json",
        with_report_fields(
            {
                "generated_at": iso_now(),
                "target_root": str(target_root),
                "run_root": str(run_root),
                "entries": rollback_entries,
            },
            schema_name="managed-rollback-manifest",
            error_code="CONFLICT" if conflict else None,
            failure_kind="conflict" if conflict else "none",
            remediation=[{"code": "MANUAL_CONFLICT_REVIEW", "summary": "Review conflict_copy before applying."}] if conflict else [],
        ),
    )
    write_text(
        outputs / "managed-recover-instructions.md",
        "# Managed Asset Recovery Instructions\n\n"
        "- Created files: delete only if current hash matches applied hash.\n"
        "- Updated files: restore only if current hash matches applied hash.\n"
        "- Conflicts: no target change was made; review conflict copies manually.\n",
    )


def create_target_outputs(run_root: Path, target_root: Path, *, include_claude_assets: bool = True) -> List[str]:
    """为 PASS 路径 smoke 测试创建一个最小可用的目标树。"""
    files: List[str] = []
    if include_claude_assets:
        settings_path = target_root / ".claude" / "settings.json"
        write_text(settings_path, '{\n  "commands": ["example"]\n}\n')
        files.append(".claude/settings.json")
        constraints_path = target_root / ".claude" / "rules" / "constraints.md"
        write_text(constraints_path, "# Constraints\n\n- Keep workflow assets managed.\n")
        files.append(".claude/rules/constraints.md")
        command_path = target_root / ".claude" / "commands" / "example.md"
        write_text(command_path, managed_runtime_command_text())
        files.append(".claude/commands/example.md")
        skill_path = target_root / ".claude" / "skills" / "example" / "SKILL.md"
        write_text(skill_path, "---\nname: example-skill\ndescription: Example skill declared by fixture workflow-spec\n---\n")
        files.append(".claude/skills/example/SKILL.md")
    design_root = target_root / ".workflowprogram" / "design"
    design_root.mkdir(parents=True, exist_ok=True)
    for name in ("workflow-spec.yaml", "workflow-view.md", "workflow-maintenance.md"):
        source_path = run_root / name
        target_path = design_root / name
        target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        files.append(f".workflowprogram/design/{name}")
    source_archive = stage_design_source_archive(run_root, run_root / "workflow-spec.yaml", target_root)
    files.extend(source_archive.values())
    runtime_root = target_root / ".workflowprogram" / "runtime"
    runtime_files = generate_target_runtime_assets(Path(__file__).resolve().parents[1], run_root / "workflow-spec.yaml", runtime_root)
    files.extend(
        [
            ".workflowprogram/runtime/workflow-entry.py",
            ".workflowprogram/runtime/workflow-runner.py",
            ".workflowprogram/runtime/validate-run-state.py",
            ".workflowprogram/runtime/runtime-manifest.json",
        ]
    )
    apply_target_claude_guard(Path(__file__).resolve().parents[1], run_root / "workflow-spec.yaml", target_root, run_root)
    files.extend(["CLAUDE.md", ".workflowprogram/claude-guard-manifest.json"])
    return files


def ensure_target_runtime_reference_assets(target_root: Path) -> List[str]:
    """补齐 managed runtime 校验需要的目标入口引用，不覆盖已有 managed 文件。"""
    files: List[str] = []
    command_path = target_root / ".claude" / "commands" / "example.md"
    if not command_path.exists():
        write_text(command_path, managed_runtime_command_text())
        files.append(".claude/commands/example.md")
    skill_path = target_root / ".claude" / "skills" / "example" / "SKILL.md"
    if not skill_path.exists():
        write_text(skill_path, "---\nname: example-skill\ndescription: Example skill declared by fixture workflow-spec\n---\n")
        files.append(".claude/skills/example/SKILL.md")
    return files


def write_validation_report(target_root: Path, title: str, bullets: List[str]) -> None:
    """向目标项目写入简洁的 validation Markdown 报告。"""
    body = "\n".join(bullets)
    write_text(target_root / "validation-report.md", f"# {title}\n\n{body}\n")


def parse_args() -> argparse.Namespace:
    """解析 `command_adapter` smoke 运行使用的 provider 协议参数。"""
    parser = argparse.ArgumentParser(description="Reference command-provider runtime host")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe")
    probe.add_argument("--json", action="store_true")

    invoke = sub.add_parser("invoke")
    invoke.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    invoke.add_argument("--plugin-root", required=True)
    invoke.add_argument("--target-root", required=True)
    invoke.add_argument("--run-root", required=True)
    invoke.add_argument("--fixture", required=True)
    invoke.add_argument("--entry-skill", required=True)
    invoke.add_argument("--request", default="")
    invoke.add_argument("--timeout", default="90")
    invoke.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    """实现 runtime_host.py 所期望的最小 probe/invoke 协议。"""
    args = parse_args()
    if args.command == "probe":
        payload = {
            "available": True,
            "ready": True,
            "message": "mock_runtime_host is ready.",
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["message"])
        return 0

    repo_root = Path(args.repo_root).resolve()
    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    intent = infer_intent(args.entry_skill)

    if args.entry_skill.startswith("missing-"):
        # 未知入口技能用于模拟 workflow 注册层面的结构性错误。
        copy_runtime_spec(
            repo_root,
            run_root,
            "invalid-entry.yaml",
            entry_skill=args.entry_skill,
            deliverables=[],
        )
        stage_history: List[str] = []
        write_progress_outputs(
            run_root,
            stage_history,
            "FAIL",
            "STRUCTURE_FAILURE",
            current_stage="requirement",
            next_action="register the missing entry and rerun",
        )
        write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "FAIL", "STRUCTURE_FAILURE")
        payload = {
            "result": "FAIL",
            "failure_code": "STRUCTURE_FAILURE",
            "message": "Mock host rejected an unknown workflow entry.",
            "is_error": True,
            "stage_history": stage_history,
            "current_stage": "requirement",
            "next_action": "register the missing entry and rerun",
        }
    elif not args.request.strip():
        # 空请求要在 requirement 阶段提前失败，用来模拟“缺少必需参数”，
        # 并确保在任何生成资产之前就终止。
        copy_runtime_spec(
            repo_root,
            run_root,
            "valid-minimal.yaml",
            entry_skill=args.entry_skill,
            deliverables=[],
        )
        stage_history = ["requirement"]
        write_progress_outputs(
            run_root,
            stage_history,
            "FAIL",
            "MISSING_ARGUMENT",
            current_stage="requirement",
            next_action="provide the required request arguments",
            approval_status="pending",
        )
        write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "FAIL", "MISSING_ARGUMENT")
        payload = {
            "result": "FAIL",
            "failure_code": "MISSING_ARGUMENT",
            "message": "Mock host rejected an empty request payload.",
            "is_error": True,
            "stage_history": stage_history,
            "stage_status": "failed",
            "current_stage": "requirement",
            "next_action": "provide the required request arguments",
        }
    elif args.fixture == "broken-workflow":
        # broken fixture 仍然会产出看起来完整的证据，便于 S5 judge 证明
        # “失败是因为检测到了正确的问题”，而不是流程本身没跑起来。
        copy_runtime_spec(
            repo_root,
            run_root,
            "valid-minimal.yaml",
            entry_skill=args.entry_skill,
            deliverables=["validation-report.md"],
            target_root_allow=["validation-report.md"],
        )
        stage_history = stage_history_for_intent(intent)
        write_validation_report(
            target_root,
            "Broken Workflow Validation",
            [
                "- Result: `FAIL`",
                "- Failure code: `EVIDENCE_FAILURE`",
                "- Finding: broken workflow assets were detected in `.claude/`.",
            ],
        )
        if "requirement" in stage_history:
            write_workflow_spec_draft(run_root, args.entry_skill, args.request)
        if "lessons" in stage_history:
            write_lessons_delta(run_root, intent, derive_failure_kind("EVIDENCE_FAILURE"), args.request)
        write_progress_outputs(
            run_root,
            stage_history,
            "FAIL",
            "EVIDENCE_FAILURE",
            current_stage=stage_history[-1] if stage_history else "validate",
            next_action="repair broken workflow assets and rerun validate",
        )
        write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "FAIL", "EVIDENCE_FAILURE")
        payload = {
            "result": "FAIL",
            "failure_code": "EVIDENCE_FAILURE",
            "message": "Mock host detected broken workflow assets and stopped validation.",
            "is_error": True,
            "stage_history": stage_history,
            "stage_status": "failed",
            "current_stage": stage_history[-1] if stage_history else "validate",
            "next_action": "repair broken workflow assets and rerun validate",
            "generated_files": [],
        }
    else:
        stage_history = stage_history_for_intent(intent)
        request_lower = args.request.lower()
        if "managed-conflict" in request_lower:
            # 冲突请求用于模拟 managed drift：在进入 S5/S6 之前就停止，
            # 只保留冲突证据。
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
            )
            generate_design_docs(repo_root, run_root)
            generated_files = [
                ".claude/settings.json",
                ".claude/rules/constraints.md",
            ]
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            write_progress_outputs(
                run_root,
                stage_history[:-1],
                "FAIL",
                "CONFLICT",
                current_stage="generate",
                next_action="resolve managed conflicts and rerun generate",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history[:-1], "FAIL", "CONFLICT")
            write_managed_outputs(run_root, target_root, conflict=True)
            payload = {
                "result": "FAIL",
                "failure_code": "CONFLICT_FAILURE",
                "message": "Mock host detected a managed asset conflict and kept candidate copies.",
                "is_error": True,
                "stage_history": stage_history[:-1],
                "stage_status": "failed",
                "current_stage": "generate",
                "next_action": "resolve managed conflicts and rerun generate",
                "generated_files": generated_files,
            }
        elif args.fixture in {
            "design-review-closed-pass",
            "design-review-missing-fail",
            "design-review-blocker-fail",
            "design-review-accepted-risk-pass",
        }:
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            if args.fixture == "design-review-missing-fail":
                write_design_review_evidence(repo_root, run_root, request=args.request, mode="missing")
                result = "FAIL"
                failure_code = "DESIGN_REVIEW_MISSING"
                generated_files = []
            elif args.fixture == "design-review-blocker-fail":
                write_design_review_evidence(repo_root, run_root, request=args.request, mode="blocker")
                result = "FAIL"
                failure_code = "DESIGN_REVIEW_UNRESOLVED"
                generated_files = []
            else:
                review_mode = "accepted_risk" if args.fixture == "design-review-accepted-risk-pass" else "closed"
                write_design_review_evidence(repo_root, run_root, request=args.request, mode=review_mode)
                generated_files = create_target_outputs(run_root, target_root)
                write_managed_outputs(run_root, target_root, conflict=False)
                result = "PASS"
                failure_code = ""
            if result != "PASS":
                write_json(
                    run_root / "outputs" / "stages" / "entry-orchestration-summary.json",
                    {
                        "generated_at": iso_now(),
                        "status": "BLOCKED",
                        "failure_kind": "design",
                        "block_reason": "design_review_unresolved",
                        "design_review_gate": load_json(
                            run_root / "outputs" / "stages" / "design-review" / "gate-validation.json"
                        ),
                    },
                )
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, derive_failure_kind(failure_code), args.request)
            effective_history = stage_history if result == "PASS" else stage_history[:-1]
            write_progress_outputs(
                run_root,
                effective_history,
                result,
                failure_code,
                current_stage="lessons" if result == "PASS" else "design",
                next_action="complete" if result == "PASS" else "resolve design-review issues before implementation",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, effective_history, result, failure_code)
            payload = {
                "result": result,
                "failure_code": failure_code,
                "message": "Mock host completed design-review fixture.",
                "is_error": result != "PASS",
                "stage_history": effective_history,
                "stage_status": "done" if result == "PASS" else "blocked",
                "current_stage": "lessons" if result == "PASS" else "design",
                "next_action": "complete" if result == "PASS" else "resolve design-review issues before implementation",
                "generated_files": generated_files,
            }
        elif args.fixture == "host-capability-missing-develop":
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                host_capabilities=host_capability_missing_contract(),
                runtime_capabilities=["state_transitions", "run_state_validation", "host_capability_probe"],
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            host_outputs = write_host_capability_outputs(repo_root, run_root, target_root, apply_project_local=False)
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(
                    run_root,
                    intent,
                    "environment",
                    args.request,
                    extra_candidates=["Add host_capability bootstrap guidance for missing_binary."],
                )
            write_progress_outputs(
                run_root,
                stage_history,
                "FAIL",
                "HOST_CAPABILITY_MISSING",
                current_stage=stage_history[-1] if stage_history else "lessons",
                next_action="resolve required host capabilities and rerun",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "FAIL", "HOST_CAPABILITY_MISSING")
            payload = {
                "result": "FAIL",
                "failure_code": "HOST_CAPABILITY_MISSING",
                "message": "Mock host completed workflow generation, but required host capabilities are missing.",
                "is_error": True,
                "stage_history": stage_history,
                "stage_status": "failed",
                "current_stage": stage_history[-1] if stage_history else "lessons",
                "next_action": "resolve required host capabilities and rerun",
                "generated_files": generated_files,
                "metadata": {"host_capability_report": host_outputs.get("report", {})},
            }
        elif args.fixture == "host-capability-project-local-bootstrap":
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                host_capabilities=host_capability_project_local_contract(),
                runtime_capabilities=["state_transitions", "run_state_validation", "host_capability_probe"],
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            host_outputs = write_host_capability_outputs(repo_root, run_root, target_root, apply_project_local=True)
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "none", args.request)
            write_progress_outputs(
                run_root,
                stage_history,
                "PASS",
                "",
                current_stage=stage_history[-1] if stage_history else "lessons",
                next_action="complete",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "PASS", "")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host applied project-local bootstrap and satisfied host capability requirements.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1] if stage_history else "lessons",
                "next_action": "complete",
                "generated_files": generated_files,
                "metadata": {"host_capability_report": host_outputs.get("report", {})},
            }
        elif args.fixture == "host-capability-host-global-bootstrap":
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                host_capabilities=host_capability_host_global_contract(target_root),
                runtime_capabilities=["state_transitions", "run_state_validation", "host_capability_probe"],
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            host_outputs = write_host_capability_outputs(
                repo_root,
                run_root,
                target_root,
                apply_project_local=False,
            )
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "none", args.request)
            write_progress_outputs(
                run_root,
                stage_history,
                "PASS",
                "",
                current_stage=stage_history[-1] if stage_history else "lessons",
                next_action="complete",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "PASS", "")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host applied approved host-global bootstrap and satisfied host capability requirements.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1] if stage_history else "lessons",
                "next_action": "complete",
                "generated_files": generated_files,
                "metadata": {"host_capability_report": host_outputs.get("report", {})},
            }
        elif args.fixture == "capability-discovery-reverse-engineering":
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                capability_discovery=capability_discovery_reverse_engineering(),
                runtime_capabilities=["state_transitions", "run_state_validation", "capability_discovery"],
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            discovery_outputs = write_capability_discovery_outputs(repo_root, run_root, target_root, args.request)
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "none", args.request)
            write_progress_outputs(
                run_root,
                stage_history,
                "PASS",
                "",
                current_stage=stage_history[-1] if stage_history else "lessons",
                next_action="review capability candidates and finalize host requirements",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "PASS", "")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host generated capability discovery recommendations for reverse engineering.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1] if stage_history else "lessons",
                "next_action": "review capability candidates and finalize host requirements",
                "generated_files": generated_files,
                "metadata": {"capability_discovery_report": discovery_outputs.get("report", {})},
            }
        elif args.fixture in {"host-capability-validate", "host-capability-audit"}:
            host_entry_skill = "workflowprogram-validate" if args.fixture == "host-capability-validate" else "workflowprogram-audit"
            intent = infer_intent(host_entry_skill)
            stage_history = stage_history_for_intent(intent)
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=host_entry_skill,
                deliverables=["validation-report.md"],
                target_root_allow=["validation-report.md"],
                host_capabilities=[
                    {
                        "id": "python3_runtime",
                        "kind": "external_binary",
                        "name": "Python 3",
                        "required": True,
                        "probe": {"binary": "python3", "args": ["--version"]},
                        "bootstrap": {"scope": "manual_only", "summary": "Python 3 should already exist", "project_local_outputs": []},
                        "approval_required": True,
                    }
                ],
                runtime_capabilities=["state_transitions", "run_state_validation", "host_capability_probe"],
            )
            generate_design_docs(repo_root, run_root)
            generated_files = create_target_outputs(run_root, target_root, include_claude_assets=False)
            generated_files.extend(ensure_target_runtime_reference_assets(target_root))
            host_outputs = write_host_capability_outputs(repo_root, run_root, target_root, apply_project_local=False)
            write_validation_report(
                target_root,
                "Workflow Validation",
                [
                    "- Result: `PASS`",
                    f"- Entry skill: `{host_entry_skill}`",
                    "- Host capabilities were probed successfully.",
                ],
            )
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, host_entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "none", args.request)
            write_progress_outputs(
                run_root,
                stage_history,
                "PASS",
                "",
                current_stage=stage_history[-1] if stage_history else "validate",
                next_action="complete",
            )
            write_runner_evidence(run_root, target_root, intent, host_entry_skill, stage_history, "PASS", "")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host validated host capabilities successfully.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1] if stage_history else "validate",
                "next_action": "complete",
                "generated_files": generated_files,
                "metadata": {"host_capability_report": host_outputs.get("report", {})},
            }
        elif args.fixture == "host-capability-iterate":
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                host_capabilities=host_capability_missing_contract(),
                runtime_capabilities=["state_transitions", "run_state_validation", "host_capability_probe"],
            )
            generate_design_docs(repo_root, run_root)
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            host_outputs = write_host_capability_outputs(repo_root, run_root, target_root, apply_project_local=False)
            seed_prior_host_capability_failure(target_root, host_outputs.get("report", {}))
            write_lessons_delta(
                run_root,
                intent,
                "environment",
                args.request,
                extra_candidates=["Add host_capability bootstrap coverage for missing_binary recurring failures."],
            )
            write_progress_outputs(
                run_root,
                stage_history,
                "FAIL",
                "HOST_CAPABILITY_MISSING",
                current_stage=stage_history[-1] if stage_history else "lessons",
                next_action="add host capability bootstrap guidance",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "FAIL", "HOST_CAPABILITY_MISSING")
            payload = {
                "result": "FAIL",
                "failure_code": "HOST_CAPABILITY_MISSING",
                "message": "Mock host identified recurring host capability failures during iterate.",
                "is_error": True,
                "stage_history": stage_history,
                "stage_status": "failed",
                "current_stage": stage_history[-1] if stage_history else "lessons",
                "next_action": "add host capability bootstrap guidance",
                "generated_files": generated_files,
                "metadata": {"host_capability_report": host_outputs.get("report", {})},
            }
        elif args.fixture == "agent-team-develop-pass":
            team_contract = agent_team_contract_fixture(max_fan_out=2)
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                agent_team_contract=team_contract,
                runtime_capabilities=["state_transitions", "run_state_validation", "team_orchestration"],
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            write_team_evidence(run_root, team_contract, overflow=False, join_satisfied=True)
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "none", args.request)
            write_progress_outputs(run_root, stage_history, "PASS", "", current_stage=stage_history[-1], next_action="complete")
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "PASS", "")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host completed deterministic team orchestration successfully.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1],
                "next_action": "complete",
                "generated_files": generated_files,
            }
        elif args.fixture == "agent-team-fanout-fail":
            team_contract = agent_team_contract_fixture(max_fan_out=2)
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                agent_team_contract=team_contract,
                runtime_capabilities=["state_transitions", "run_state_validation", "team_orchestration"],
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            write_team_evidence(run_root, team_contract, overflow=True, join_satisfied=True)
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "implementation", args.request)
            write_progress_outputs(run_root, stage_history, "FAIL", "TEAM_ORCHESTRATION_FAILURE", current_stage=stage_history[-1], next_action="reduce team fan-out and rerun")
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "FAIL", "TEAM_ORCHESTRATION_FAILURE")
            payload = {
                "result": "FAIL",
                "failure_code": "TEAM_ORCHESTRATION_FAILURE",
                "message": "Mock host exceeded agent team max_fan_out.",
                "is_error": True,
                "stage_history": stage_history,
                "stage_status": "failed",
                "current_stage": stage_history[-1],
                "next_action": "reduce team fan-out and rerun",
                "generated_files": generated_files,
            }
        elif args.fixture in {"agent-team-validate", "agent-team-audit"}:
            team_contract = agent_team_contract_fixture(max_fan_out=2)
            team_entry_skill = "workflowprogram-validate" if args.fixture == "agent-team-validate" else "workflowprogram-audit"
            intent = infer_intent(team_entry_skill)
            stage_history = stage_history_for_intent(intent)
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=team_entry_skill,
                deliverables=["validation-report.md"],
                target_root_allow=["validation-report.md"],
                agent_team_contract=team_contract,
                runtime_capabilities=["state_transitions", "run_state_validation", "team_orchestration"],
            )
            generate_design_docs(repo_root, run_root)
            generated_files = create_target_outputs(run_root, target_root, include_claude_assets=False)
            generated_files.extend(ensure_target_runtime_reference_assets(target_root))
            write_team_evidence(run_root, team_contract, overflow=False, join_satisfied=True)
            write_validation_report(
                target_root,
                "Workflow Team Validation",
                [
                    "- Result: `PASS`",
                    f"- Entry skill: `{team_entry_skill}`",
                    "- Team orchestration evidence was captured.",
                ],
            )
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, team_entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "none", args.request)
            write_progress_outputs(run_root, stage_history, "PASS", "", current_stage=stage_history[-1], next_action="complete")
            write_runner_evidence(run_root, target_root, intent, team_entry_skill, stage_history, "PASS", "")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host validated team orchestration successfully.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1],
                "next_action": "complete",
                "generated_files": generated_files,
            }
        elif args.fixture == "node-loop-develop-pass":
            loop_policy = node_loop_policy_fixture(max_iterations=3)
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                node_loop_policy=loop_policy,
                runtime_capabilities=["state_transitions", "run_state_validation", "node_loop_execution"],
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Loop success requires verifier evidence.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            write_loop_evidence(run_root, node_id="implement", iterations=2, final_status="PASS", verifier_passed=True)
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "none", args.request)
            write_progress_outputs(run_root, stage_history, "PASS", "", current_stage=stage_history[-1], next_action="complete")
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "PASS", "")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host completed deterministic node loop successfully.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1],
                "next_action": "complete",
                "generated_files": generated_files,
            }
        elif args.fixture == "node-loop-max-iterations-fail":
            loop_policy = node_loop_policy_fixture(max_iterations=2)
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                node_loop_policy=loop_policy,
                runtime_capabilities=["state_transitions", "run_state_validation", "node_loop_execution"],
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Stop loop at max_iterations.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            write_managed_outputs(run_root, target_root, conflict=False)
            write_loop_evidence(run_root, node_id="implement", iterations=3, final_status="FAIL", verifier_passed=False, stop_reason="max_iterations")
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, "implementation", args.request)
            write_progress_outputs(run_root, stage_history, "FAIL", "NODE_LOOP_MAX_ITERATIONS", current_stage=stage_history[-1], next_action="tighten loop feedback or raise max_iterations")
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "FAIL", "NODE_LOOP_MAX_ITERATIONS")
            payload = {
                "result": "FAIL",
                "failure_code": "NODE_LOOP_MAX_ITERATIONS",
                "message": "Mock host exceeded node loop max_iterations.",
                "is_error": True,
                "stage_history": stage_history,
                "stage_status": "failed",
                "current_stage": stage_history[-1],
                "next_action": "tighten loop feedback or raise max_iterations",
                "generated_files": generated_files,
            }
        elif args.fixture in {
            "change-policy-incremental-pass",
            "change-policy-redesign-pass",
            "change-policy-missing-fail",
            "change-policy-undeclared-write-fail",
            "change-policy-stale-context-fail",
        }:
            write_existing_managed_seed(target_root)
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")

            if args.fixture == "change-policy-missing-fail":
                write_change_policy_inputs(
                    repo_root,
                    run_root,
                    target_root,
                    args.request,
                    include_policy=False,
                )
                write_design_review_evidence(repo_root, run_root, request=args.request, mode="missing")
                write_progress_outputs(
                    run_root,
                    stage_history[:-1],
                    "FAIL",
                    "CHANGE_POLICY_REQUIRED",
                    current_stage="generate",
                    next_action="generate change-policy.json and impact-analysis.json",
                )
                write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history[:-1], "FAIL", "CHANGE_POLICY_REQUIRED")
                payload = {
                    "result": "FAIL",
                    "failure_code": "CHANGE_POLICY_REQUIRED",
                    "message": "Mock host blocked before managed apply because change policy is missing.",
                    "is_error": True,
                    "stage_history": stage_history[:-1],
                    "stage_status": "blocked",
                    "current_stage": "generate",
                    "next_action": "generate change-policy evidence",
                    "generated_files": [],
                }
            elif args.fixture == "change-policy-stale-context-fail":
                write_change_policy_inputs(
                    repo_root,
                    run_root,
                    target_root,
                    args.request,
                    stale=True,
                )
                write_design_review_evidence(repo_root, run_root, request=args.request, mode="closed")
                write_progress_outputs(
                    run_root,
                    stage_history[:-1],
                    "FAIL",
                    "CHANGE_CONTEXT_STALE",
                    current_stage="generate",
                    next_action="rerun change-context resolution and impact analysis",
                )
                write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history[:-1], "FAIL", "CHANGE_CONTEXT_STALE")
                payload = {
                    "result": "FAIL",
                    "failure_code": "CHANGE_CONTEXT_STALE",
                    "message": "Mock host blocked before managed apply because change context is stale.",
                    "is_error": True,
                    "stage_history": stage_history[:-1],
                    "stage_status": "blocked",
                    "current_stage": "generate",
                    "next_action": "refresh change context",
                    "generated_files": [],
                }
            else:
                mode = "redesign_from_existing" if args.fixture == "change-policy-redesign-pass" else "incremental"
                allowed_extra = [] if args.fixture != "change-policy-undeclared-write-fail" else []
                if args.fixture != "change-policy-undeclared-write-fail":
                    allowed_extra = []
                write_change_policy_inputs(
                    repo_root,
                    run_root,
                    target_root,
                    args.request,
                    mode=mode,
                    allowed_extra=allowed_extra,
                )
                write_design_review_evidence(repo_root, run_root, request=args.request, mode="closed")
                if args.fixture == "change-policy-undeclared-write-fail":
                    # Narrow the declared scope after validation so S5 proves actual managed writes exceed policy.
                    policy_path = run_root / "outputs" / "stages" / "change-policy.json"
                    policy_payload = json.loads(policy_path.read_text(encoding="utf-8"))
                    policy_payload["affected_artifacts"] = [".claude/settings.json"]
                    policy_payload["allowed_derived_artifacts"] = []
                    write_json(policy_path, policy_payload)
                generated_files = create_target_outputs(run_root, target_root)
                if "requirement" in stage_history:
                    write_workflow_spec_draft(run_root, args.entry_skill, args.request)
                if "lessons" in stage_history:
                    write_lessons_delta(run_root, intent, derive_failure_kind(""), args.request)
                write_progress_outputs(
                    run_root,
                    stage_history,
                    "PASS",
                    "",
                    current_stage=stage_history[-1] if stage_history else "lessons",
                    next_action="complete",
                )
                write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "PASS", "")
                write_managed_outputs(run_root, target_root, conflict=False)
                result = "FAIL" if args.fixture == "change-policy-undeclared-write-fail" else "PASS"
                payload = {
                    "result": result,
                    "failure_code": "" if result == "PASS" else "CHANGE_POLICY_FAILURE",
                    "message": "Mock host completed change-policy fixture.",
                    "is_error": result == "FAIL",
                    "stage_history": stage_history,
                    "stage_status": "done" if result == "PASS" else "failed",
                    "current_stage": stage_history[-1] if stage_history else "lessons",
                    "next_action": "complete" if result == "PASS" else "repair change policy scope",
                    "generated_files": generated_files,
                }
        elif args.fixture == "existing-workflow":
            # audit/iterate 类流程复用已有 target，主要生成验证产物，
            # 而不是创建新的 managed 资产。
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
                deliverables=["validation-report.md"],
                target_root_allow=["validation-report.md"],
            )
            write_validation_report(
                target_root,
                "Workflow Audit Report",
                [
                    "- Result: `PASS`",
                    f"- Entry skill: `{args.entry_skill}`",
                    "- Audit summary: existing workflow assets were reviewed successfully.",
                ],
            )
            generated_files = ["validation-report.md"]
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, derive_failure_kind(""), args.request)
            write_progress_outputs(
                run_root,
                stage_history,
                "PASS",
                "",
                current_stage=stage_history[-1] if stage_history else "lessons",
                next_action="complete",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "PASS", "")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host completed workflow audit successfully.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1] if stage_history else "lessons",
                "next_action": "complete",
                "generated_files": generated_files,
            }
        else:
            # 默认 PASS 路径会写入 managed 资产，以及真实 validator 链所需的
            # runner/progress 证据。
            copy_runtime_spec(
                repo_root,
                run_root,
                "valid-minimal.yaml",
                entry_skill=args.entry_skill,
            )
            design_docs = generate_design_docs(repo_root, run_root)
            candidate_root = run_root / "outputs" / "candidate"
            write_text(candidate_root / ".claude" / "rules" / "constraints.md", "# Constraints\n\n- Keep workflow assets managed.\n")
            write_text(candidate_root / ".claude" / "commands" / "example.md", managed_runtime_command_text())
            for source_name, target_name in (
                ("workflow_spec", "workflow-spec.yaml"),
                ("workflow_view", "workflow-view.md"),
                ("workflow_maintenance", "workflow-maintenance.md"),
            ):
                destination = candidate_root / ".workflowprogram" / "design" / target_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(design_docs[source_name].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            generate_target_runtime_assets(repo_root, run_root / "workflow-spec.yaml", candidate_root / ".workflowprogram" / "runtime")
            generated_files = create_target_outputs(run_root, target_root)
            if "requirement" in stage_history:
                write_workflow_spec_draft(run_root, args.entry_skill, args.request)
            if "lessons" in stage_history:
                write_lessons_delta(run_root, intent, derive_failure_kind(""), args.request)
            write_progress_outputs(
                run_root,
                stage_history,
                "PASS",
                "",
                current_stage=stage_history[-1] if stage_history else "lessons",
                next_action="complete",
            )
            write_runner_evidence(run_root, target_root, intent, args.entry_skill, stage_history, "PASS", "")
            write_managed_outputs(run_root, target_root, conflict=False)
            if "external-write" in request_lower:
                # 这里故意违反 target_root_allow，用于证明 boundary 检查能抓住意外写入。
                write_text(target_root / "rogue-output.txt", "unexpected external write\n")
            payload = {
                "result": "PASS",
                "failure_code": "",
                "message": "Mock host completed workflow execution successfully.",
                "is_error": False,
                "stage_history": stage_history,
                "stage_status": "done",
                "current_stage": stage_history[-1] if stage_history else "lessons",
                "next_action": "complete",
                "generated_files": generated_files,
            }

    write_text(run_root / "outputs" / "mock-runtime-host.log", f"fixture={args.fixture}\nentry={args.entry_skill}\nrequest={args.request}\n")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["message"])
    return 0 if payload["result"] in {"PASS", "WARN", "ENVIRONMENT-SKIP"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
