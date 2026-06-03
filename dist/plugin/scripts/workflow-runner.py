#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
WorkflowProgram 的控制面 runner。

程序职责：
- 校验 workflow-spec.yaml
- 执行确定性的阶段切换
- 持久化 RUN_ROOT 证据与状态
- 强制执行 artifact 枚举契约（kind/producer/status）
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from lib.control_plane import emit_stage_progress
from lib.io_utils import utc_now, write_json
from lib.spec_utils import path_matches_any, require_stage_slot, resolve_required_stage_slots, stage_slot_object_map
from lib.target_design_refs import artifact_kind_for_path
from lib.yaml_utils import load_yaml_mapping

from runtime_host import RuntimeHostConfig, probe_runtime_host, resolve_runtime_host_config


VALID_ROOT = {"PLUGIN_ROOT", "TARGET_ROOT", "RUN_ROOT", "TEMP_ROOT"}
VALID_PRODUCER = {"S0", "S1", "S2", "S3", "S4", "S5", "S6"}
VALID_FORMAT = {"md", "yaml", "json", "jsonl", "txt", "dir"}
VALID_LIFECYCLE = {"ephemeral", "evidence", "deliverable", "cache"}
VALID_STATUS = {"planned", "generated", "validated", "applied", "conflict", "archived"}
VALID_KIND = {
    "spec",
    "view",
    "agent",
    "skill",
    "command",
    "rule",
    "settings",
    "report",
    "test_scenario",
    "transcript",
    "event_log",
    "state_snapshot",
    "candidate_asset",
    "managed_manifest",
    "managed_plan",
    "managed_result",
    "build_manifest",
    "requirement_index",
    "question_backlog",
    "requirement_logic_map",
    "context_findings",
    "design_source",
    "node_design",
    "implementation_plan",
    "acceptance_tests",
    "traceability_matrix",
    "design_review_packet",
    "design_review_issue",
    "design_review_closure",
    "design_review_gate",
    "change_context",
    "existing_workflow_readback",
    "change_policy",
    "impact_analysis",
    "change_policy_validation",
    "change_traceability",
    "host_capability_report",
    "host_bootstrap_plan",
    "host_bootstrap_apply",
    "host_bootstrap_execution",
    "host_bootstrap_manifest",
    "host_capability_candidates",
    "host_bootstrap_instructions",
    "team_plan",
    "team_result",
    "team_join",
    "loop_plan",
    "loop_iteration",
    "loop_final",
}
TERMINALS = {"abort", "end", "done", "complete", "stop", "finish"}
DEFAULT_STAGE_SLOT_ORDER = ["S1", "S2", "S3", "S4", "S5", "S6"]


@dataclass
class RunnerContext:
    """在控制面循环中共享的不可变执行上下文。"""

    spec_path: Path
    run_root: Path
    target_root: Path
    plugin_root: Path
    request: str
    intent: str
    entry_skill: str
    auto_approve: bool
    strict_route: bool
    run_id: str
    runtime_contract: Dict[str, Any]
    runtime_host: RuntimeHostConfig
    target_root_preexisting: bool
    manual_approval: bool


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    """向 JSONL 文件追加一条 JSON 事件记录。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    """解析 runner 控制面所需的命令行参数。"""

    parser = argparse.ArgumentParser(description="WorkflowProgram control-plane runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run control-plane transition loop")
    run.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    run.add_argument("--run-root", required=True, help="RUN_ROOT path")
    run.add_argument("--target-root", default=".", help="TARGET_ROOT path")
    run.add_argument("--plugin-root", default="", help="PLUGIN_ROOT path (defaults from script location)")
    run.add_argument("--request", default="", help="Original user request")
    run.add_argument("--intent", default="", help="Override routed intent")
    run.add_argument("--entry-skill", default="", help="Override routed entry skill")
    run.add_argument("--auto-approve", action="store_true", help="Auto approve user_approval gates")
    run.add_argument(
        "--approval-status",
        default="",
        choices=["approved"],
        help="Resolve user_approval gates as manually approved",
    )
    run.add_argument("--strict-route", action="store_true", help="Enable strict deterministic routing")
    run.add_argument("--runtime-provider", default="", help="Runtime host provider (defaults from env or claude_cli)")
    run.add_argument("--provider-command", default="", help="External runtime host adapter command for command_adapter provider")
    run.add_argument("--claude-bin", default="claude", help="Claude binary for claude_cli provider")
    run.add_argument("--json", action="store_true", help="Print JSON summary")

    status = sub.add_parser("status", help="Read runner status from RUN_ROOT")
    status.add_argument("--run-root", required=True, help="RUN_ROOT path")
    status.add_argument("--json", action="store_true", help="Print JSON summary")
    return parser.parse_args()


def script_dir() -> Path:
    """返回辅助子进程脚本所在的同级目录。"""

    return Path(__file__).resolve().parent


def resolve_plugin_root(explicit: str) -> Path:
    """根据显式参数或安装布局解析 PLUGIN_ROOT。"""

    if explicit:
        return Path(explicit).resolve()
    return script_dir().resolve().parents[1]


def ensure_target_writable(target_root: Path) -> bool:
    """通过创建临时探针文件判断 TARGET_ROOT 是否可写。"""

    try:
        if not target_root.exists() or not target_root.is_dir():
            return False
        probe = target_root / ".workflowprogram" / ".write-probe"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def ensure_target_exists(target_root: Path) -> bool:
    """确保 TARGET_ROOT 存在，并返回它是否原本就存在。"""

    existed = target_root.exists()
    if existed:
        if not target_root.is_dir():
            raise RuntimeError(f"target_root exists but is not a directory: {target_root}")
        return True
    target_root.mkdir(parents=True, exist_ok=True)
    return False


def evaluate_skip_check(check: str, target_root: Path, runtime_host: RuntimeHostConfig) -> Tuple[bool, str]:
    """执行 runtime_contract 中的单个 environment skip 检查。"""

    probe = None
    if check in {"runtime_host_available", "runtime_host_ready", "claude_cli_available", "claude_cli_logged_in"}:
        probe = probe_runtime_host(runtime_host)
    if check == "runtime_host_available":
        return (bool(probe and probe.available), probe.message if probe else "runtime host probe unavailable")
    if check == "runtime_host_ready":
        return (bool(probe and probe.ready), probe.message if probe else "runtime host probe unavailable")
    if check == "claude_cli_available":
        if runtime_host.provider != "claude_cli":
            return True, f"skipped claude_cli_available because runtime_provider={runtime_host.provider}"
        return (bool(probe and probe.available), probe.message if probe else "runtime host probe unavailable")
    if check == "target_root_writable":
        writable = ensure_target_writable(target_root)
        return (writable, f"target_root {'is' if writable else 'is not'} writable")
    if check == "claude_cli_logged_in":
        if runtime_host.provider != "claude_cli":
            return True, f"skipped claude_cli_logged_in because runtime_provider={runtime_host.provider}"
        return (bool(probe and probe.ready), probe.message if probe else "runtime host probe unavailable")
    return True, f"unknown skip check '{check}' defaults to pass"


def evaluate_environment_skip(
    runtime_contract: Dict[str, Any],
    target_root: Path,
    runtime_host: RuntimeHostConfig,
) -> List[Dict[str, str]]:
    """执行 runtime_contract.environment_skip，并收集失败原因。"""

    failed: List[Dict[str, str]] = []
    env_skip = runtime_contract.get("environment_skip", [])
    if not isinstance(env_skip, list):
        return failed
    for item in env_skip:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        check = str(item.get("check", "")).strip()
        message = str(item.get("message", "")).strip()
        if not code or not check:
            continue
        ok, detail = evaluate_skip_check(check, target_root, runtime_host)
        if not ok:
            failed.append({"code": code, "check": check, "message": message or code, "detail": detail})
    return failed


def check_boundary(runtime_contract: Dict[str, Any], root: str, rel_path: str) -> bool:
    """按写入边界规则校验单个候选 artifact 路径。"""

    write_boundaries = runtime_contract.get("write_boundaries", {})
    if not isinstance(write_boundaries, dict):
        return True
    deny = [str(item).strip() for item in write_boundaries.get("deny", []) if str(item).strip()]
    if deny and path_matches_any(rel_path, deny):
        return False

    if root == "TARGET_ROOT":
        allow = [str(item).strip() for item in write_boundaries.get("target_root_allow", []) if str(item).strip()]
    elif root == "RUN_ROOT":
        allow = [str(item).strip() for item in write_boundaries.get("run_root_allow", []) if str(item).strip()]
    elif root == "TEMP_ROOT":
        allow = [str(item).strip() for item in write_boundaries.get("temp_root_allow", []) if str(item).strip()]
    else:
        return True
    return path_matches_any(rel_path, allow) if allow else False


def required_evidence_list(runtime_contract: Dict[str, Any]) -> List[str]:
    """返回从 runtime_contract 归一化得到的必需证据列表。"""

    evidence = runtime_contract.get("required_evidence", [])
    if not isinstance(evidence, list):
        return []
    return [str(item).strip() for item in evidence if str(item).strip()]


def validate_required_evidence(run_root: Path, required_files: List[str]) -> List[str]:
    """返回 RUN_ROOT 中仍然缺失的必需证据路径。"""

    missing: List[str] = []
    for rel_path in required_files:
        path = run_root / rel_path
        if not path.exists():
            missing.append(rel_path)
    return missing


def run_json_command(cmd: List[str]) -> Tuple[int, Dict[str, Any], str]:
    """运行辅助脚本，并在可能时恢复末尾 JSON 对象。"""

    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    payload: Dict[str, Any] = {}
    text = completed.stdout.strip() or completed.stderr.strip()
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            lines = [line for line in text.splitlines() if line.strip()]
            for idx in range(len(lines)):
                candidate = "\n".join(lines[idx:])
                try:
                    payload = json.loads(candidate)
                    break
                except json.JSONDecodeError:
                    continue
    return completed.returncode, payload, text


def validate_spec_with_script(spec_path: Path) -> Dict[str, Any]:
    """复用标准 schema 校验器，而不是在这里重复实现校验逻辑。"""

    cmd = [
        sys.executable,
        str(script_dir() / "validate-workflow-spec.py"),
        "--spec",
        str(spec_path),
        "--json",
    ]
    code, payload, text = run_json_command(cmd)
    if code != 0 or payload.get("status") != "PASS":
        raise RuntimeError(f"workflow spec validation failed: {text}")
    return payload


def route_intent(request: str, target_root: Path, strict: bool) -> Dict[str, Any]:
    """通过共享的 route-intent.py 脚本解析 intent。"""

    cmd = [
        sys.executable,
        str(script_dir() / "route-intent.py"),
        "--request",
        request or "设计一个基础工作流",
        "--target-root",
        str(target_root),
        "--json",
    ]
    if strict:
        cmd.append("--strict")
    code, payload, text = run_json_command(cmd)
    if code not in {0, 2}:
        raise RuntimeError(f"intent routing failed: {text}")
    if not payload:
        raise RuntimeError("intent routing did not return JSON payload")
    if code == 2:
        raise RuntimeError("intent routing blocked by strict mode due to ambiguous request")
    return payload


def call_stage_progress(
    ctx: RunnerContext,
    stage: str,
    node: str,
    event: str,
    status: str,
    percent: int,
    result: str,
    next_action: str = "",
    artifact_refs: Optional[List[str]] = None,
    verdict: str = "",
    approval_status: str = "",
) -> None:
    """把 runner 里程碑同步到共享 progress 产物。"""

    emit_stage_progress(
        python_executable=sys.executable,
        stage_progress_script=script_dir() / "stage-progress.py",
        run_root=ctx.run_root,
        stage=stage,
        node=node,
        event=event,
        status=status,
        percent=percent,
        result=result,
        next_action=next_action,
        artifact_refs=artifact_refs,
        verdict=verdict,
        approval_status=approval_status,
    )


def append_event(ctx: RunnerContext, event_type: str, stage: str, status: str, message: str, **extra: Any) -> None:
    """向 RUN_ROOT/events.jsonl 追加一条结构化控制面事件。"""

    append_jsonl(
        ctx.run_root / "events.jsonl",
        {
            "ts": utc_now(),
            "type": event_type,
            "stage": stage,
            "source": "workflow-runner",
            "status": status,
            "message": message,
            **extra,
        },
    )


def producer_for_stage(stage: Dict[str, Any]) -> str:
    """解析某个阶段定义显式声明的逻辑 stage slot。"""

    return require_stage_slot(stage)


def infer_root(path: str) -> str:
    """根据阶段输出路径推断 artifact root。

    Stage outputs are declared as relative paths in the spec. The runner
    converts them into normalized artifact records by inferring which root owns
    each output.
    """

    cleaned = path.strip()
    if cleaned.startswith(".claude/") or cleaned.startswith(".workflowprogram/"):
        return "TARGET_ROOT"
    if cleaned.startswith("outputs/") or cleaned.startswith("workflow-"):
        return "RUN_ROOT"
    if cleaned.startswith("scripts/") or cleaned.startswith("skills/") or cleaned.startswith("commands/"):
        return "TARGET_ROOT"
    return "RUN_ROOT"


def infer_format(path: str) -> str:
    """根据路径推断 artifact format 枚举值。"""

    cleaned = path.strip().rstrip("/")
    if not cleaned:
        return "txt"
    suffix = Path(cleaned).suffix.lower()
    if suffix == ".md":
        return "md"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".txt":
        return "txt"
    if "." not in Path(cleaned).name:
        return "dir"
    return "txt"


def infer_kind(path: str) -> str:
    """根据命名约定推断 artifact kind 枚举值。"""

    cleaned = path.strip().rstrip("/")
    name = Path(cleaned).name
    target_design_kind = artifact_kind_for_path(cleaned)
    if target_design_kind:
        return target_design_kind
    if cleaned.endswith("outputs/stages/design-review/design-review-packet.json"):
        return "design_review_packet"
    if cleaned.endswith("outputs/stages/design-review/issues.json") or cleaned.endswith("outputs/stages/design-review/round-1.json"):
        return "design_review_issue"
    if cleaned.endswith("outputs/stages/design-review/closure.json"):
        return "design_review_closure"
    if cleaned.endswith("outputs/stages/design-review/gate-validation.json"):
        return "design_review_gate"
    if cleaned.endswith("outputs/stages/change-context.json"):
        return "change_context"
    if cleaned.endswith("outputs/stages/existing-workflow-readback.json"):
        return "existing_workflow_readback"
    if cleaned.endswith("outputs/stages/change-policy.json"):
        return "change_policy"
    if cleaned.endswith("outputs/stages/impact-analysis.json"):
        return "impact_analysis"
    if cleaned.endswith("outputs/stages/validate-change-policy.json"):
        return "change_policy_validation"
    if cleaned.endswith("outputs/stages/change-traceability.json"):
        return "change_traceability"
    if cleaned.endswith("workflow-spec.md") or cleaned.endswith("workflow-spec.yaml"):
        return "spec"
    if cleaned.endswith("workflow-view.md"):
        return "view"
    if "/agents/" in cleaned or cleaned.startswith(".claude/agents/"):
        return "agent"
    if "/skills/" in cleaned and name == "SKILL.md":
        return "skill"
    if "/commands/" in cleaned:
        return "command"
    if "/rules/" in cleaned:
        return "rule"
    if name == "settings.json":
        return "settings"
    if cleaned.endswith("test-scenarios.md"):
        return "test_scenario"
    if cleaned.endswith("transcript.md"):
        return "transcript"
    if cleaned.endswith("events.jsonl"):
        return "event_log"
    if cleaned.endswith("state.json"):
        return "state_snapshot"
    if "outputs/candidate/" in cleaned:
        return "candidate_asset"
    if cleaned.endswith("managed-files.json"):
        return "managed_manifest"
    if cleaned.endswith("managed-change-plan.json"):
        return "managed_plan"
    if cleaned.endswith("managed-change-result.json"):
        return "managed_result"
    if cleaned.endswith("build-manifest.json"):
        return "build_manifest"
    if cleaned.endswith("host-capability-report.json"):
        return "host_capability_report"
    if cleaned.endswith("host-capability-candidates.json"):
        return "host_capability_candidates"
    if cleaned.endswith("host-bootstrap-instructions.md"):
        return "host_bootstrap_instructions"
    if cleaned.endswith("host-bootstrap-plan.json"):
        return "host_bootstrap_plan"
    if cleaned.endswith("host-bootstrap-apply.json"):
        return "host_bootstrap_apply"
    if cleaned.endswith("host-bootstrap-execution.json"):
        return "host_bootstrap_execution"
    if cleaned.endswith("bootstrap-assets-manifest.json"):
        return "host_bootstrap_manifest"
    if cleaned.endswith("team-plan.json"):
        return "team_plan"
    if cleaned.endswith("team-results.json"):
        return "team_result"
    if cleaned.endswith("team-join-summary.json"):
        return "team_join"
    if "/outputs/stages/loops/" in cleaned and cleaned.endswith("loop-plan.json"):
        return "loop_plan"
    if "/outputs/stages/loops/" in cleaned and cleaned.endswith("iteration-summary.jsonl"):
        return "loop_iteration"
    if "/outputs/stages/loops/" in cleaned and cleaned.endswith("final-verdict.json"):
        return "loop_final"
    return "report"


def artifact_path_relative(path: str, root: str) -> str:
    """把输出路径归一化为 state.json 中存储的相对形式。"""

    cleaned = path.strip()
    if cleaned.startswith("/"):
        return cleaned.lstrip("/")
    if root == "RUN_ROOT":
        return cleaned[1:] if cleaned.startswith("./") else cleaned
    if root == "TARGET_ROOT":
        if cleaned.startswith("./"):
            cleaned = cleaned[2:]
        return cleaned
    return cleaned


def parse_stage_outputs(output: Any) -> List[str]:
    """把阶段 output 声明归一化成路径列表。"""

    if output is None:
        return []
    if isinstance(output, list):
        return [str(item).strip() for item in output if str(item).strip()]
    text = str(output).strip()
    if not text:
        return []
    if "\n" in text:
        return [line.strip() for line in text.splitlines() if line.strip()]
    return [text]


def validate_artifact_entry(entry: Dict[str, Any]) -> List[str]:
    """按枚举与 root 不变量校验单条 artifact 记录。"""

    errors: List[str] = []
    if entry["kind"] not in VALID_KIND:
        errors.append(f"invalid kind: {entry['kind']}")
    if entry["root"] not in VALID_ROOT:
        errors.append(f"invalid root: {entry['root']}")
    if entry["producer"] not in VALID_PRODUCER:
        errors.append(f"invalid producer: {entry['producer']}")
    if entry["format"] not in VALID_FORMAT:
        errors.append(f"invalid format: {entry['format']}")
    if entry["lifecycle"] not in VALID_LIFECYCLE:
        errors.append(f"invalid lifecycle: {entry['lifecycle']}")
    if entry["status"] not in VALID_STATUS:
        errors.append(f"invalid status: {entry['status']}")
    if entry["managed"] and entry["root"] != "TARGET_ROOT":
        errors.append("managed=true requires root=TARGET_ROOT")
    if str(entry["path"]).startswith("/"):
        errors.append("path must be relative")
    return errors


def build_artifact_entries(
    stage: Dict[str, Any],
    producer: str,
    existing_ids: set[str],
    runtime_contract: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """把阶段输出展开成归一化 artifact 条目。

    This is where the runner turns high-level stage output declarations into the
    machine-readable artifact registry later validated by validate-run-state.py.
    """

    outputs = parse_stage_outputs(stage.get("output"))
    artifacts: List[Dict[str, Any]] = []
    for idx, output in enumerate(outputs):
        root = infer_root(output)
        fmt = infer_format(output)
        kind = infer_kind(output)
        lifecycle = "deliverable" if root == "TARGET_ROOT" else "evidence"
        managed = root == "TARGET_ROOT" and (
            output.strip().startswith(".claude/")
            or output.strip().startswith(".workflowprogram/design/")
            or output.strip().startswith(".workflowprogram/runtime/")
        )
        rel_path = artifact_path_relative(output, root)
        base_id = f"{producer}.{re.sub(r'[^A-Za-z0-9_]', '_', rel_path)}"
        artifact_id = base_id
        suffix = 1
        while artifact_id in existing_ids:
            suffix += 1
            artifact_id = f"{base_id}_{suffix}"
        existing_ids.add(artifact_id)

        entry = {
            "id": artifact_id,
            "kind": kind,
            "root": root,
            "path": rel_path,
            "producer": producer,
            "format": fmt,
            "lifecycle": lifecycle,
            "status": "generated",
            "managed": managed,
            "sha256": None,
        }
        # 必须在 artifact 写入 state.json 之前完成边界校验，
        # 这样非法写入会以控制面错误尽早失败。
        if not check_boundary(runtime_contract, root, rel_path):
            raise RuntimeError(
                f"write boundary violation: root={root}, path={rel_path}, "
                "not allowed by runtime_contract.write_boundaries"
            )
        validation_errors = validate_artifact_entry(entry)
        if validation_errors:
            raise RuntimeError(f"artifact enum validation failed for {artifact_id}: {validation_errors}")
        artifacts.append(entry)
    return artifacts


def load_spec(spec_path: Path) -> Dict[str, Any]:
    """加载 workflow-spec.yaml，并强制检查 runner 所需的最小前提。"""

    try:
        payload = load_yaml_mapping(spec_path)
    except Exception as exc:
        raise RuntimeError(f"failed to load workflow spec: {exc}") from exc
    if not isinstance(payload.get("stages"), list) or not payload["stages"]:
        raise RuntimeError("workflow spec must include non-empty stages list")
    return payload


def stage_slot_map_for_spec(stages: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """按逻辑 stage slot 为阶段定义建立索引。"""

    return stage_slot_object_map(stages, strict=True)


def pick_next_stage(
    stage: Dict[str, Any],
    stage_ids: List[str],
    current_idx: int,
    approval_granted: bool,
) -> Optional[str]:
    """在考虑审批门禁和终止态的前提下计算下一个执行阶段。"""

    gate = str(stage.get("gate", "")).strip()
    if gate == "user_approval":
        target = str(stage.get("on_approve", "")).strip() if approval_granted else ""
        if not approval_granted:
            return None
        if target and target not in TERMINALS:
            return target
        if target in TERMINALS:
            return None

    target = str(stage.get("on_approve", "")).strip()
    if target:
        if target in TERMINALS:
            return None
        return target

    if current_idx + 1 < len(stage_ids):
        return stage_ids[current_idx + 1]
    return None


def write_stage_summary(run_root: Path, stage_id: str, payload: Dict[str, Any]) -> str:
    """写出单阶段摘要文件，并返回其路径。"""

    path = run_root / "outputs" / "stages" / f"{stage_id.lower()}-summary.json"
    write_json(path, payload)
    return str(path)


def run_loop(
    ctx: RunnerContext,
    spec: Dict[str, Any],
    skip_reasons: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """按选定逻辑 intent 运行确定性阶段循环。

    The runner does not execute AI semantics itself. It only:
    - selects the stage path declared by intent_flows
    - enforces approval/environment/boundary contracts
    - records transitions, artifacts, and evidence locations
    """

    all_stages: List[Dict[str, Any]] = [stage for stage in spec.get("stages", []) if isinstance(stage, dict)]
    all_stage_slots = [producer_for_stage(stage) for stage in all_stages]
    if all_stage_slots != DEFAULT_STAGE_SLOT_ORDER:
        raise RuntimeError("workflow spec must declare stages in explicit S1..S6 stage_slot order")
    required_slots = resolve_required_stage_slots(spec, ctx.intent)
    slot_map = stage_slot_map_for_spec(all_stages)
    missing_slots = [slot for slot in required_slots if slot not in slot_map]
    if missing_slots:
        raise RuntimeError(f"workflow spec intent flow for {ctx.intent} references missing stage_slot values: {missing_slots}")
    stages = [slot_map[slot] for slot in required_slots]
    stage_ids = [str(stage.get("id", f"stage{idx+1}")).strip() or f"stage{idx+1}" for idx, stage in enumerate(stages)]
    stage_map = {sid: stages[idx] for idx, sid in enumerate(stage_ids)}
    stage_index = {sid: idx for idx, sid in enumerate(stage_ids)}
    transitions: List[Dict[str, Any]] = []
    artifact_ids: set[str] = set()
    artifacts: List[Dict[str, Any]] = []

    # 即使可执行阶段列表从 S1 开始，runner 也会合成 S0，
    # 这样路由证据和阶段历史才能与设计保持一致。
    route_payload = {
        "intent": ctx.intent,
        "target_root": str(ctx.target_root),
        "entry_skill": ctx.entry_skill,
        "request": ctx.request,
        "routed_at": utc_now(),
        "target_root_preexisting": ctx.target_root_preexisting,
        "target_root_created": not ctx.target_root_preexisting,
    }
    route_rel = "outputs/stages/s0-route.json"
    if not check_boundary(ctx.runtime_contract, "RUN_ROOT", route_rel):
        raise RuntimeError(f"write boundary violation for route evidence: {route_rel}")
    route_path = ctx.run_root / "outputs" / "stages" / "s0-route.json"
    write_json(route_path, route_payload)
    append_event(ctx, "RouteResolved", "S0", "ok", "Resolved request intent", intent=ctx.intent, entry_skill=ctx.entry_skill)
    call_stage_progress(
        ctx,
        stage="S0",
        node="route_intent",
        event="StageStarted",
        status="running",
        percent=1,
        result="routing started",
        next_action="execute stage graph",
        artifact_refs=[str(route_path)],
    )
    call_stage_progress(
        ctx,
        stage="S0",
        node="route_intent",
        event="StageCompleted",
        status="ok",
        percent=3,
        result=f"routed to {ctx.entry_skill}",
        next_action=f"start {stage_ids[0]}",
        artifact_refs=[str(route_path)],
    )

    route_artifact = {
        "id": "S0.outputs_stages_s0_route_json",
        "kind": "report",
        "root": "RUN_ROOT",
        "path": route_rel,
        "producer": "S0",
        "format": "json",
        "lifecycle": "evidence",
        "status": "generated",
        "managed": False,
        "sha256": None,
    }
    route_errors = validate_artifact_entry(route_artifact)
    if route_errors:
        raise RuntimeError(f"route artifact validation failed: {route_errors}")

    current_id = stage_ids[0]
    steps_guard = 0
    max_steps = max(10, len(stage_ids) * 4)
    blocked = False
    skip_reasons = skip_reasons or []

    # environment skip 被建模成一种 S5 风格的提前退出，
    # 因为工作流虽然没有进入正常执行，但仍需要结构化 verdict。
    if skip_reasons:
        message = "; ".join(f"{item['code']}: {item['message']}" for item in skip_reasons)
        append_event(
            ctx,
            "EnvironmentSkip",
            "S5",
            "warn",
            "Runtime skipped by environment contract",
            reasons=skip_reasons,
        )
        call_stage_progress(
            ctx,
            stage="S5",
            node="environment_precheck",
            event="StageCompleted",
            status="warn",
            percent=20,
            result=message,
            next_action="fix environment then rerun",
            artifact_refs=[str(route_path)],
            verdict="ENVIRONMENT-SKIP",
        )
        return {
            "verdict": "ENVIRONMENT-SKIP",
            "failure_kind": "environment",
            "stage_status": "done",
            "next_action": "修复环境后重试",
            "transitions": [{"from": "S0", "to": None, "reason": "environment-skip"}],
            "artifacts": [route_artifact],
            "blocked": False,
            "skip_reasons": skip_reasons,
        }

    while current_id is not None:
        steps_guard += 1
        if steps_guard > max_steps:
            raise RuntimeError("stage transition exceeded max steps; possible cycle")
        if current_id not in stage_map:
            raise RuntimeError(f"next stage not found in spec: {current_id}")

        idx = stage_index[current_id]
        stage = stage_map[current_id]
        producer = producer_for_stage(stage)
        percent_start = min(95, int((idx / max(1, len(stage_ids))) * 100))
        percent_end = min(98, int(((idx + 1) / max(1, len(stage_ids))) * 100))
        stage_label = f"{producer}"

        append_event(ctx, "StageStarted", stage_label, "running", f"Enter stage {current_id}", stage_id=current_id)
        call_stage_progress(
            ctx,
            stage=stage_label,
            node=current_id,
            event="StageStarted",
            status="running",
            percent=percent_start,
            result=f"stage {current_id} started",
            next_action="collect outputs",
        )

        # 提前推导 artifact 记录，这样即使阶段被 blocked，
        # 也能保留“原本打算产出什么”的规范化描述。
        stage_artifacts = build_artifact_entries(stage, producer, artifact_ids, ctx.runtime_contract)
        artifacts.extend(stage_artifacts)
        gate = str(stage.get("gate", "")).strip()
        approval_granted = ctx.auto_approve or ctx.manual_approval

        stage_summary = {
            "ts": utc_now(),
            "stage_id": current_id,
            "producer": producer,
            "gate": gate or None,
            "approval_mode": (
                "auto-approved" if gate == "user_approval" and ctx.auto_approve else
                "approved" if gate == "user_approval" and ctx.manual_approval else
                "pending" if gate == "user_approval" else
                "not-required"
            ),
            "output_count": len(stage_artifacts),
            "outputs": [item["path"] for item in stage_artifacts],
        }
        summary_path = write_stage_summary(ctx.run_root, current_id, stage_summary)

        if gate == "user_approval" and not approval_granted:
            blocked = True
            append_event(ctx, "StageBlocked", stage_label, "blocked", f"Blocked at approval gate: {current_id}")
            call_stage_progress(
                ctx,
                stage=stage_label,
                node=current_id,
                event="StageCheckpoint",
                status="blocked",
                percent=percent_end,
                result="waiting for user approval",
                next_action="rerun with --auto-approve or provide approval",
                artifact_refs=[summary_path],
                verdict="WARN",
                approval_status="pending",
            )
            transitions.append({"from": current_id, "to": None, "reason": "gate-blocked"})
            break

        next_stage = pick_next_stage(stage, stage_ids, idx, approval_granted)
        call_stage_progress(
            ctx,
            stage=stage_label,
            node=current_id,
            event="StageCompleted",
            status="ok",
            percent=percent_end,
            result=f"stage {current_id} completed",
            next_action=f"next={next_stage or 'end'}",
            artifact_refs=[summary_path],
            approval_status=(
                "auto-approved" if gate == "user_approval" and ctx.auto_approve else
                "approved" if gate == "user_approval" and ctx.manual_approval else
                ""
            ),
        )
        append_event(ctx, "StageCompleted", stage_label, "ok", f"Completed stage {current_id}", next_stage=next_stage)
        transitions.append({"from": current_id, "to": next_stage, "reason": "normal"})
        current_id = next_stage

    verdict = "WARN" if blocked else "PASS"
    failure_kind = "none"
    stage_status = "blocked" if blocked else "done"
    next_action = "等待审批后继续" if blocked else "进入后续验证/闭环"
    if blocked:
        approval_status = "pending"
    elif any(str(stage.get("gate", "")).strip() == "user_approval" for stage in stages):
        approval_status = "auto-approved" if ctx.auto_approve else ("approved" if ctx.manual_approval else "approved")
    else:
        approval_status = "approved"
    return {
        "verdict": verdict,
        "failure_kind": failure_kind,
        "stage_status": stage_status,
        "next_action": next_action,
        "transitions": transitions,
        "artifacts": [route_artifact, *artifacts],
        "blocked": blocked,
        "skip_reasons": [],
        "approval_status": approval_status,
    }


def persist_state(ctx: RunnerContext, loop_result: Dict[str, Any]) -> Path:
    """把规范 runner 状态快照持久化到 RUN_ROOT/state.json。"""

    state = {
        "schema_version": 1,
        "schema_name": "workflow-run-state",
        "values": {
            "request_id": ctx.run_id,
            "intent": ctx.intent,
            "target_root": str(ctx.target_root),
            "plugin_root": str(ctx.plugin_root),
            "run_root": str(ctx.run_root),
            "approval_status": loop_result["approval_status"],
            "stage_status": loop_result["stage_status"],
            "validation_verdict": loop_result["verdict"],
            "failure_kind": loop_result["failure_kind"],
            "next_action": loop_result["next_action"],
            "current_stage": loop_result["transitions"][-1]["from"] if loop_result["transitions"] else "S0",
            "stage_history": [item["from"] for item in loop_result["transitions"]],
        },
        "artifacts": loop_result["artifacts"],
        "transitions": loop_result["transitions"],
        "updated_at": utc_now(),
    }
    state_path = ctx.run_root / "state.json"
    write_json(state_path, state)
    return state_path


def validate_state_with_script(state_path: Path) -> Dict[str, Any]:
    """通过 validate-run-state.py 强制检查 artifact/state schema 不变量。"""

    cmd = [
        sys.executable,
        str(script_dir() / "validate-run-state.py"),
        "--state",
        str(state_path),
        "--json",
    ]
    code, payload, text = run_json_command(cmd)
    if code != 0 or payload.get("status") != "PASS":
        raise RuntimeError(f"run state validation failed: {text}")
    return payload


def command_run(args: argparse.Namespace) -> int:
    """执行完整的控制面 runner 命令。"""

    spec_path = Path(args.spec).resolve()
    run_root = Path(args.run_root).resolve()
    target_root = Path(args.target_root).resolve()
    plugin_root = resolve_plugin_root(args.plugin_root)
    run_root.mkdir(parents=True, exist_ok=True)
    target_root_preexisting = ensure_target_exists(target_root)

    # runner 总会把通过校验的 spec 复制进 RUN_ROOT，
    # 这样“实际执行过的控制面”会永久附着在运行证据上。
    spec = load_spec(spec_path)
    validate_spec_with_script(spec_path)
    runtime_contract = spec.get("runtime_contract", {})
    if not isinstance(runtime_contract, dict):
        raise RuntimeError("runtime_contract must be a mapping")
    copied_spec = run_root / "workflow-spec.yaml"
    if not check_boundary(runtime_contract, "RUN_ROOT", "workflow-spec.yaml"):
        raise RuntimeError("write boundary violation: workflow-spec.yaml not allowed in RUN_ROOT")
    shutil.copy2(spec_path, copied_spec)

    routed: Dict[str, Any] = {}
    if args.entry_skill.strip():
        routed = {
            "intent": args.intent.strip() or "develop",
            "entry_skill": args.entry_skill.strip(),
            "confidence": 1.0,
            "reason": "explicit-entry-skill",
            "scores": {},
            "ambiguous": False,
            "strict_mode": False,
            "target_root": str(target_root),
            "request": args.request,
        }
    else:
        routed = route_intent(args.request, target_root, bool(args.strict_route))
    intent = args.intent.strip() or str(routed["intent"])
    entry_skill = args.entry_skill.strip() or str(routed["entry_skill"])
    run_id = run_root.name

    ctx = RunnerContext(
        spec_path=copied_spec,
        run_root=run_root,
        target_root=target_root,
        plugin_root=plugin_root,
        request=args.request,
        intent=intent,
        entry_skill=entry_skill,
        auto_approve=bool(args.auto_approve),
        strict_route=bool(args.strict_route),
        run_id=run_id,
        runtime_contract=runtime_contract,
        runtime_host=resolve_runtime_host_config(
            provider=args.runtime_provider,
            claude_bin=args.claude_bin,
            provider_command=args.provider_command,
        ),
        target_root_preexisting=target_root_preexisting,
        manual_approval=args.approval_status == "approved",
    )

    # context.json 是本次运行不可变的“输入与环境”记录；
    # 后续工具应读取它，而不是自己猜执行参数。
    write_json(
        run_root / "context.json",
        {
            "run_id": run_id,
            "spec_path": str(copied_spec),
            "target_root": str(target_root),
            "plugin_root": str(plugin_root),
            "intent": intent,
            "entry_skill": entry_skill,
            "request": args.request,
            "strict_route": bool(args.strict_route),
            "auto_approve": bool(args.auto_approve),
            "runtime_provider": ctx.runtime_host.provider,
            "provider_command": ctx.runtime_host.provider_command or None,
            "target_root_preexisting": target_root_preexisting,
            "target_root_created": not target_root_preexisting,
            "manual_approval": ctx.manual_approval,
            "started_at": utc_now(),
        },
    )

    skip_reasons = evaluate_environment_skip(runtime_contract, target_root, ctx.runtime_host)
    loop_result = run_loop(ctx, spec, skip_reasons=skip_reasons)

    allowed_failure_kinds = {
        str(item).strip()
        for item in runtime_contract.get("failure_kinds", [])
        if str(item).strip()
    }
    if loop_result["failure_kind"] not in allowed_failure_kinds:
        raise RuntimeError(
            f"failure_kind '{loop_result['failure_kind']}' not declared in runtime_contract.failure_kinds"
        )

    state_path = persist_state(ctx, loop_result)
    validate_state_with_script(state_path)

    final_status = "BLOCKED" if loop_result["blocked"] else (
        "ENVIRONMENT-SKIP" if loop_result["verdict"] == "ENVIRONMENT-SKIP" else "PASS"
    )
    summary = {
        "run_id": run_id,
        "status": final_status,
        "intent": intent,
        "entry_skill": entry_skill,
        "run_root": str(run_root),
        "state": str(state_path),
        "transition_count": len(loop_result["transitions"]),
        "artifact_count": len(loop_result["artifacts"]),
        "skip_reasons": loop_result.get("skip_reasons", []),
    }
    write_json(run_root / "outputs" / "stages" / "runner-summary.json", summary)
    append_event(
        ctx,
        "RunnerFinished",
        "runner",
        "blocked" if loop_result["blocked"] else "ok",
        "Runner execution finished",
        summary=summary,
    )
    call_stage_progress(
        ctx,
        stage="S6" if not loop_result["blocked"] else "S3",
        node="runner_finalize",
        event="StageCompleted",
        status="warn" if loop_result["blocked"] or loop_result["verdict"] == "ENVIRONMENT-SKIP" else "ok",
        percent=100 if not loop_result["blocked"] else 80,
        result="runner finished",
        next_action=loop_result["next_action"],
        artifact_refs=[str(run_root / "outputs" / "stages" / "runner-summary.json")],
        verdict="ENVIRONMENT-SKIP" if loop_result["verdict"] == "ENVIRONMENT-SKIP" else ("WARN" if loop_result["blocked"] else "PASS"),
    )

    # 把必需证据检查放到最后，这样辅助脚本可以先完成各自产出，
    # 最终失败信息也能保持精确。
    missing_evidence = validate_required_evidence(run_root, required_evidence_list(runtime_contract))
    if missing_evidence:
        raise RuntimeError(f"missing required evidence files: {missing_evidence}")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"[{summary['status']}] run={run_id} transitions={summary['transition_count']} artifacts={summary['artifact_count']}")
    if loop_result["blocked"]:
        return 2
    if loop_result["verdict"] == "ENVIRONMENT-SKIP":
        return 3
    return 0


def command_status(args: argparse.Namespace) -> int:
    """在不重跑工作流的情况下读取已持久化的 runner 状态。"""

    run_root = Path(args.run_root).resolve()
    state_path = run_root / "state.json"
    summary_path = run_root / "outputs" / "stages" / "runner-summary.json"
    if not state_path.exists():
        print(f"Error: state not found: {state_path}", file=sys.stderr)
        return 1

    state = json.loads(state_path.read_text(encoding="utf-8"))
    summary: Dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    payload = {
        "run_root": str(run_root),
        "state": state.get("values", {}),
        "summary": summary,
        "transition_count": len(state.get("transitions", [])),
        "artifact_count": len(state.get("artifacts", [])),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"run_root={run_root} stage_status={payload['state'].get('stage_status')} "
            f"transitions={payload['transition_count']} artifacts={payload['artifact_count']}"
        )
    return 0


def main() -> int:
    """显式子命令分发的 CLI 入口。"""

    args = parse_args()
    try:
        if args.command == "run":
            return command_run(args)
        if args.command == "status":
            return command_status(args)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
