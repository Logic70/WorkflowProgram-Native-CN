#!/usr/bin/env python3
"""
WorkflowProgram 的确定性产品入口封装器。

它负责弥合“提示词层阶段说明”和“真正要执行的脚本链”之间的落差。
一次产品级入口执行至少要完成：

- 解析入口意图
- 校验 workflow-spec.yaml
- 生成 workflow-view.md
- 对 develop 流程执行 managed assets 计划与应用
- 运行控制面 runner
- 校验落盘后的运行状态
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lib.io_utils import utc_now, write_json
from lib.target_design_refs import PERSISTENT_DEFAULTS, iter_existing_node_design_refs, resolve_existing_run_refs
from lib.yaml_utils import try_load_yaml_mapping


ENTRY_TO_INTENT = {
    "workflowprogram-develop": "develop",
    "workflowprogram-audit": "audit",
    "workflowprogram-iterate": "iterate",
    "workflowprogram-validate": "validate",
}


def parse_args() -> argparse.Namespace:
    """解析确定性产品入口封装器的命令行参数。"""

    parser = argparse.ArgumentParser(description="Deterministic WorkflowProgram product entry wrapper")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run deterministic product entry orchestration")
    run.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    run.add_argument("--run-root", required=True, help="RUN_ROOT path")
    run.add_argument("--target-root", required=True, help="TARGET_ROOT path")
    run.add_argument("--request", default="", help="Original user request text")
    run.add_argument("--entry-skill", default="", help="Explicit workflowprogram-* entry skill")
    run.add_argument("--candidate-root", default="", help="Candidate .claude root for develop flows")
    run.add_argument("--plugin-root", default="", help="Explicit PLUGIN_ROOT path")
    run.add_argument("--route-evidence", default="", help="Optional precomputed route-intent.json evidence")
    run.add_argument("--change-context", default="", help="Optional precomputed change-context.json evidence")
    run.add_argument("--auto-approve", action="store_true", help="Resolve approval gates automatically")
    run.add_argument("--approve-host-global-bootstrap", action="store_true", help="Deprecated no-op; host-global bootstrap is plan-only")
    run.add_argument(
        "--approval-status",
        default="",
        choices=["approved"],
        help="Resolve approval gates as manually approved",
    )
    run.add_argument("--strict-route", action="store_true", help="Block on route mismatch or ambiguity")
    run.add_argument("--runtime-provider", default="", help="Runtime host provider override")
    run.add_argument("--provider-command", default="", help="External provider command for command_adapter")
    run.add_argument("--claude-bin", default="claude", help="Claude binary for claude_cli")
    run.add_argument("--json", action="store_true", help="Print JSON summary")
    return parser.parse_args()


def script_dir() -> Path:
    """返回当前脚本目录，便于解析同级辅助脚本。"""

    return Path(__file__).resolve().parent


def resolve_plugin_root(explicit: str) -> Path:
    """根据显式参数或安装布局解析 PLUGIN_ROOT。"""

    if explicit:
        return Path(explicit).resolve()
    return script_dir().parents[1]


def parse_json_output(text: str) -> Dict[str, Any]:
    """从混合的 stdout/stderr 文本中提取最后一个 JSON 对象。

    一些辅助脚本虽然会输出结构化 JSON，但前后仍可能夹带 banner 或 traceback。
    这里通过扫描最后一个合法 JSON 对象，保证入口编排仍然保持确定性。
    """

    if not text.strip():
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass

    lines = [line for line in text.splitlines() if line.strip()]
    for idx in range(len(lines)):
        candidate = "\n".join(lines[idx:])
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def run_command(cmd: List[str]) -> Tuple[int, Dict[str, Any], str]:
    """执行子进程，并返回退出码、解析后的 JSON 以及原始文本。"""

    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode, parse_json_output(text), text


def load_json_file(path: Path) -> Dict[str, Any]:
    """尽力读取本地 JSON 证据文件。"""

    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def entry_intent_for(entry_skill: str) -> str:
    """把显式 workflowprogram-* 入口技能映射为逻辑 intent。"""

    if entry_skill not in ENTRY_TO_INTENT:
        raise RuntimeError(f"unsupported explicit entry skill '{entry_skill}'")
    return ENTRY_TO_INTENT[entry_skill]


def resolve_requested_entry(
    *,
    request: str,
    target_root: Path,
    explicit_entry_skill: str,
    strict_route: bool,
    route_evidence_path: Path,
) -> Dict[str, Any]:
    """解析本次调用实际应使用的入口技能和 intent。

    即使调用方给了显式叶子入口，这里仍会经过 `route-intent.py`，
    这样严格模式才能发现“用户请求和入口不匹配”，并把原始路由证据保存在编排摘要里。
    """

    precomputed_payload = load_json_file(route_evidence_path)
    cmd = [
        sys.executable,
        str(script_dir() / "route-intent.py"),
        "--request",
        request or "设计一个基础工作流",
        "--target-root",
        str(target_root),
        "--json",
    ]
    if not precomputed_payload:
        cmd.extend(["--out", str(route_evidence_path)])
    if strict_route:
        cmd.append("--strict")
    code, payload, text = run_command(cmd)
    if code not in {0, 2}:
        raise RuntimeError(f"route-intent.py failed: {text}")
    if code == 2:
        raise RuntimeError("route-intent.py blocked on ambiguous request under strict mode")

    if precomputed_payload:
        fresh_payload = payload
        comparable_keys = ("intent", "entry_skill", "request_kind", "target_root")
        evidence_mismatch = any(
            str(precomputed_payload.get(key, "")).strip() != str(fresh_payload.get(key, "")).strip()
            for key in comparable_keys
            if fresh_payload
        )
        if evidence_mismatch and strict_route:
            raise RuntimeError("provided route evidence does not match fresh route-intent.py result under strict mode")
        payload = precomputed_payload
    else:
        evidence_mismatch = False

    # 显式叶子入口可以覆盖路由结果，但原始路由载荷仍要保留，
    # 这样后续审计才能看见是否存在不匹配。
    if explicit_entry_skill and explicit_entry_skill != "workflowprogram-orchestrate":
        explicit_intent = entry_intent_for(explicit_entry_skill)
        mismatch = (
            bool(payload)
            and str(payload.get("intent", "")).strip()
            and str(payload.get("intent", "")).strip() != explicit_intent
        )
        if mismatch and strict_route:
            raise RuntimeError(
                "explicit entry skill does not match route-intent.py result under strict mode: "
                f"entry_skill={explicit_entry_skill}, routed_intent={payload.get('intent')}"
            )
        return {
            "intent": explicit_intent,
            "entry_skill": explicit_entry_skill,
            "route_payload": payload,
            "route_source": "explicit-entry-skill",
            "route_mismatch": mismatch,
            "route_evidence_path": str(route_evidence_path),
            "route_evidence_mismatch": evidence_mismatch,
        }

    if not payload:
        raise RuntimeError("route-intent.py did not return a JSON payload")
    return {
        "intent": str(payload.get("intent", "")).strip(),
        "entry_skill": str(payload.get("entry_skill", "")).strip(),
        "route_payload": payload,
        "route_source": "route-intent",
        "route_mismatch": False,
        "route_evidence_path": str(route_evidence_path),
        "route_evidence_mismatch": evidence_mismatch,
    }


def resolve_change_context(
    *,
    request: str,
    target_root: Path,
    route_evidence_path: Path,
    context_path: Path,
    use_existing: bool,
) -> Dict[str, Any]:
    """解析或加载 change-context 证据。"""

    if use_existing and context_path.exists():
        payload = load_json_file(context_path)
        if payload:
            return payload
    return run_required_json_command(
        "resolve-change-context.py",
        [
            sys.executable,
            str(script_dir() / "resolve-change-context.py"),
            "--request",
            request,
            "--target-root",
            str(target_root),
            "--route",
            str(route_evidence_path),
            "--out",
            str(context_path),
            "--json",
        ],
    )


def validate_change_policy(
    *,
    run_root: Path,
    target_root: Path,
    context_path: Path,
    current_context_path: Path,
    auto_approve: bool,
    approval_status: str,
) -> Dict[str, Any]:
    """调用 change-policy validator，并允许它用退出码 2 表达阻断。"""

    cmd = [
        sys.executable,
        str(script_dir() / "validate-change-policy.py"),
        "--policy",
        str(run_root / "outputs" / "stages" / "change-policy.json"),
        "--impact",
        str(run_root / "outputs" / "stages" / "impact-analysis.json"),
        "--change-context",
        str(context_path),
        "--current-context",
        str(current_context_path),
        "--readback",
        str(run_root / "outputs" / "stages" / "existing-workflow-readback.json"),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
        "--out",
        str(run_root / "outputs" / "stages" / "validate-change-policy.json"),
        "--json",
    ]
    if auto_approve:
        cmd.append("--auto-approve")
    if approval_status:
        cmd.extend(["--approval-status", approval_status])
    code, payload, text = run_command(cmd)
    if code not in {0, 2}:
        raise RuntimeError(f"validate-change-policy.py failed: {text}")
    if not payload:
        raise RuntimeError("validate-change-policy.py did not return JSON output")
    return payload


def validate_design_review_gate(run_root: Path) -> Dict[str, Any]:
    """调用 design-review gate validator，并允许它用退出码 2 表达阻断。"""

    cmd = [
        sys.executable,
        str(script_dir() / "validate-design-review-gate.py"),
        "--run-root",
        str(run_root),
        "--json",
    ]
    code, payload, text = run_command(cmd)
    if code not in {0, 2}:
        raise RuntimeError(f"validate-design-review-gate.py failed: {text}")
    if not payload:
        raise RuntimeError("validate-design-review-gate.py did not return JSON output")
    return payload


def run_required_json_command(name: str, cmd: List[str]) -> Dict[str, Any]:
    """运行一个“必须成功且必须返回 JSON”的辅助脚本。"""

    code, payload, text = run_command(cmd)
    if code != 0:
        raise RuntimeError(f"{name} failed: {text}")
    if not payload:
        raise RuntimeError(f"{name} did not return JSON output")
    return payload


def validate_spec(spec_path: Path) -> Dict[str, Any]:
    """在尝试任何变更前，先校验控制面 spec。"""

    payload = run_required_json_command(
        "validate-workflow-spec.py",
        [
            sys.executable,
            str(script_dir() / "validate-workflow-spec.py"),
            "--spec",
            str(spec_path),
            "--json",
        ],
    )
    if payload.get("status") != "PASS":
        raise RuntimeError(f"workflow spec is not valid: {payload}")
    return payload


def generate_view(spec_path: Path, out_path: Path) -> Dict[str, Any]:
    """根据 workflow-spec.yaml 生成人类可读的 workflow 视图。"""

    payload = run_required_json_command(
        "generate-workflow-view.py",
        [
            sys.executable,
            str(script_dir() / "generate-workflow-view.py"),
            "--spec",
            str(spec_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )
    if payload.get("status") != "PASS":
        raise RuntimeError(f"workflow view generation failed: {payload}")
    return payload


def generate_maintenance(spec_path: Path, out_path: Path) -> Dict[str, Any]:
    """根据 workflow-spec.yaml 生成维护说明。"""

    payload = run_required_json_command(
        "generate-workflow-maintenance.py",
        [
            sys.executable,
            str(script_dir() / "generate-workflow-maintenance.py"),
            "--spec",
            str(spec_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )
    if payload.get("status") != "PASS":
        raise RuntimeError(f"workflow maintenance generation failed: {payload}")
    return payload


# Deprecated compatibility name for older internal callers.
generate_lowlevel = generate_maintenance


def generate_target_runtime(spec_path: Path, out_root: Path) -> Dict[str, Any]:
    """根据 workflow-spec.yaml 生成目标侧 deterministic runtime 资产。"""

    payload = run_required_json_command(
        "generate-target-runtime.py",
        [
            sys.executable,
            str(script_dir() / "generate-target-runtime.py"),
            "--spec",
            str(spec_path),
            "--out-root",
            str(out_root),
            "--json",
        ],
    )
    if payload.get("status") != "PASS":
        raise RuntimeError(f"target runtime generation failed: {payload}")
    return payload


def resolve_candidate_layout(candidate_root: Path) -> Tuple[Path, Path]:
    """兼容旧的 `candidate/.claude` 和新的 `candidate/` 传参形式。"""

    if candidate_root.name == ".claude":
        return candidate_root.parent, candidate_root
    return candidate_root, candidate_root / ".claude"


def stage_persistent_design_assets(
    *,
    candidate_stage_root: Path,
    run_root: Path,
    spec_path: Path,
    view_path: Path,
    maintenance_path: Path,
) -> Dict[str, Any]:
    """把本轮设计资产复制到 candidate/.workflowprogram/design/，供 managed apply 持久化。"""

    design_root = candidate_stage_root / ".workflowprogram" / "design"
    design_root.mkdir(parents=True, exist_ok=True)
    target_spec = design_root / "workflow-spec.yaml"
    target_view = design_root / "workflow-view.md"
    target_maintenance = design_root / "workflow-maintenance.md"
    shutil.copy2(spec_path, target_spec)
    shutil.copy2(view_path, target_view)
    shutil.copy2(maintenance_path, target_maintenance)
    spec_payload = try_load_yaml_mapping(spec_path)
    copied_sources: Dict[str, str] = {}
    for key, rel_path in resolve_existing_run_refs(run_root, spec_payload).items():
        source = run_root / rel_path
        persistent_rel = PERSISTENT_DEFAULTS.get(key)
        if not persistent_rel or not source.exists() or not source.is_file():
            continue
        target = candidate_stage_root / persistent_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_sources[key] = str(target)
    for node_id, rel_path in iter_existing_node_design_refs(run_root, spec_payload).items():
        source = run_root / rel_path
        if not source.exists() or not source.is_file():
            continue
        target = candidate_stage_root / ".workflowprogram" / "design" / "source" / "target-node-designs" / f"{node_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_sources[f"node_design:{node_id}"] = str(target)
    return {
        "design_root": str(design_root),
        "workflow_spec": str(target_spec),
        "workflow_view": str(target_view),
        "workflow_maintenance": str(target_maintenance),
        "source_archive": copied_sources,
    }


def stage_target_runtime_assets(
    *,
    candidate_stage_root: Path,
    spec_path: Path,
) -> Dict[str, Any]:
    """把目标工作流自己的 deterministic runtime 资产落到 candidate/.workflowprogram/runtime/。"""

    runtime_root = candidate_stage_root / ".workflowprogram" / "runtime"
    generated = generate_target_runtime(spec_path, runtime_root)
    return {
        "runtime_root": str(runtime_root),
        "files": generated.get("files", {}),
    }


def run_managed_apply(target_root: Path, run_root: Path, candidate_root: Path) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
    """为 develop 流程执行候选资产的规划与应用。

    这里同时返回 plan 和最终 result，因为入口摘要需要保留完整的变更过程，
    而不只是应用后的结果。
    """

    plan = run_required_json_command(
        "managed-assets.py plan",
        [
            sys.executable,
            str(script_dir() / "managed-assets.py"),
            "plan",
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--source-root",
            str(candidate_root),
            "--json",
        ],
    )
    code, payload, text = run_command(
        [
            sys.executable,
            str(script_dir() / "managed-assets.py"),
            "apply-staged",
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--source-root",
            str(candidate_root),
            "--json",
        ]
    )
    if code not in {0, 2}:
        raise RuntimeError(f"managed-assets.py apply-staged failed: {text}")
    if not payload:
        raise RuntimeError("managed-assets.py apply-staged did not return JSON output")
    return plan, payload, bool(payload.get("conflicts"))


def run_runner(
    *,
    spec_path: Path,
    run_root: Path,
    target_root: Path,
    plugin_root: Path,
    request: str,
    intent: str,
    entry_skill: str,
    auto_approve: bool,
    approval_status: str,
    strict_route: bool,
    runtime_provider: str,
    provider_command: str,
    claude_bin: str,
) -> Tuple[int, Dict[str, Any]]:
    """调用控制面 runner，并保留非 PASS 的终态结果。"""

    cmd = [
        sys.executable,
        str(script_dir() / "workflow-runner.py"),
        "run",
        "--spec",
        str(spec_path),
        "--run-root",
        str(run_root),
        "--target-root",
        str(target_root),
        "--plugin-root",
        str(plugin_root),
        "--request",
        request,
        "--intent",
        intent,
        "--entry-skill",
        entry_skill,
        "--runtime-provider",
        runtime_provider,
        "--provider-command",
        provider_command,
        "--claude-bin",
        claude_bin,
        "--json",
    ]
    if auto_approve:
        cmd.append("--auto-approve")
    if approval_status:
        cmd.extend(["--approval-status", approval_status])
    if strict_route:
        cmd.append("--strict-route")
    code, payload, text = run_command(cmd)
    if code not in {0, 2, 3}:
        raise RuntimeError(f"workflow-runner.py failed: {text}")
    if not payload:
        raise RuntimeError("workflow-runner.py did not return JSON output")
    return code, payload


def validate_run_state(run_root: Path) -> Dict[str, Any]:
    """在 runner 完成后校验落盘的 state.json。"""

    payload = run_required_json_command(
        "validate-run-state.py",
        [
            sys.executable,
            str(script_dir() / "validate-run-state.py"),
            "--state",
            str(run_root / "state.json"),
            "--json",
        ],
    )
    if payload.get("status") != "PASS":
        raise RuntimeError(f"run state is not valid: {payload}")
    return payload


def discover_host_capabilities(spec_path: Path, target_root: Path, run_root: Path, request: str) -> Dict[str, Any]:
    """执行能力搜索与推荐，并返回结构化候选报告。"""

    payload = run_required_json_command(
        "discover-host-capabilities.py",
        [
            sys.executable,
            str(script_dir() / "discover-host-capabilities.py"),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--request",
            request,
            "--json",
        ],
    )
    report = payload.get("report", {})
    if not isinstance(report, dict):
        raise RuntimeError("discover-host-capabilities.py did not return a report object")
    return report


def probe_host_capabilities(spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    """执行宿主能力探测，并返回结构化报告。"""

    payload = run_required_json_command(
        "probe-host-capabilities.py",
        [
            sys.executable,
            str(script_dir() / "probe-host-capabilities.py"),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--json",
        ],
    )
    report = payload.get("report", {})
    if not isinstance(report, dict):
        raise RuntimeError("probe-host-capabilities.py did not return a report object")
    return report


def apply_host_bootstrap(spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    """执行允许自动化的 project-local host bootstrap。"""

    cmd = [
        sys.executable,
        str(script_dir() / "apply-host-bootstrap.py"),
        "--spec",
        str(spec_path),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
        "--json",
    ]
    payload = run_required_json_command("apply-host-bootstrap.py", cmd)
    return payload


def apply_target_claude_guard(spec_path: Path, target_root: Path, run_root: Path) -> Tuple[Dict[str, Any], bool]:
    """Apply target project CLAUDE.md runtime guard and report whether it conflicted."""

    code, payload, text = run_command(
        [
            sys.executable,
            str(script_dir() / "apply-target-claude-guard.py"),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--json",
        ]
    )
    if code not in {0, 2}:
        raise RuntimeError(f"apply-target-claude-guard.py failed: {text}")
    if not payload:
        raise RuntimeError("apply-target-claude-guard.py did not return JSON output")
    return payload, code == 2 or str(payload.get("status", "")).strip() == "CONFLICT"


def generate_environment_remediation(spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    """根据当前 host 证据和历史运行生成环境修复提案。"""

    payload = run_required_json_command(
        "generate-environment-remediation.py",
        [
            sys.executable,
            str(script_dir() / "generate-environment-remediation.py"),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--json",
        ],
    )
    report = payload.get("report", {})
    if not isinstance(report, dict):
        raise RuntimeError("generate-environment-remediation.py did not return a report object")
    return report


def command_run(args: argparse.Namespace) -> int:
    """执行确定性的 WorkflowProgram 产品入口流水线。

    它负责把提示词层的产品技能桥接到真实脚本级控制面：
    - 解析有效入口和 intent
    - 校验并渲染 spec
    - 在 develop 流程中按需执行 managed apply
    - 运行控制面 runner
    - 校验持久化状态
    - 写出单一的入口编排摘要，供后续审计使用
    """

    spec_path = Path(args.spec).resolve()
    run_root = Path(args.run_root).resolve()
    target_root = Path(args.target_root).resolve()
    plugin_root = resolve_plugin_root(args.plugin_root)
    candidate_root = Path(args.candidate_root).resolve() if args.candidate_root else (run_root / "outputs" / "candidate")
    run_root.mkdir(parents=True, exist_ok=True)
    stages_root = run_root / "outputs" / "stages"
    stages_root.mkdir(parents=True, exist_ok=True)
    route_evidence_path = Path(args.route_evidence).resolve() if args.route_evidence else stages_root / "route-intent.json"
    change_context_path = Path(args.change_context).resolve() if args.change_context else stages_root / "change-context.json"

    # 在碰 spec 之前先固化路由证据，保证每次运行都能回答“为什么执行了这个入口”。
    resolved = resolve_requested_entry(
        request=args.request,
        target_root=target_root,
        explicit_entry_skill=args.entry_skill.strip(),
        strict_route=bool(args.strict_route),
        route_evidence_path=route_evidence_path,
    )
    intent = str(resolved["intent"])
    entry_skill = str(resolved["entry_skill"])
    change_context = resolve_change_context(
        request=args.request,
        target_root=target_root,
        route_evidence_path=route_evidence_path,
        context_path=change_context_path,
        use_existing=bool(args.change_context),
    )

    spec_validation = validate_spec(spec_path)
    spec_payload = try_load_yaml_mapping(spec_path)
    view_path = run_root / "workflow-view.md"
    view_generation = generate_view(spec_path, view_path)
    maintenance_path = run_root / "workflow-maintenance.md"
    maintenance_generation = generate_maintenance(spec_path, maintenance_path)

    managed_plan: Dict[str, Any] | None = None
    managed_result: Dict[str, Any] | None = None
    capability_discovery_report: Dict[str, Any] | None = None
    host_capability_report: Dict[str, Any] | None = None
    host_bootstrap_result: Dict[str, Any] | None = None
    environment_remediation_report: Dict[str, Any] | None = None
    target_claude_guard_result: Dict[str, Any] | None = None
    runner_code: int | None = None
    runner_summary: Dict[str, Any] | None = None
    state_validation: Dict[str, Any] | None = None
    stopped_before_runner = False
    final_status = "PASS"
    design_assets: Dict[str, Any] | None = None
    target_runtime_assets: Dict[str, Any] | None = None
    change_policy_validation: Dict[str, Any] | None = None
    design_review_validation: Dict[str, Any] | None = None
    block_reason: str | None = None

    # 只有 develop 流程允许修改 TARGET_ROOT。
    # audit/iterate/validate 流程会直接进入控制面 runner。
    if intent == "develop":
        if bool(change_context.get("change_policy_required", False)):
            current_context_path = stages_root / "change-context-current.json"
            resolve_change_context(
                request=args.request,
                target_root=target_root,
                route_evidence_path=route_evidence_path,
                context_path=current_context_path,
                use_existing=False,
            )
            change_policy_validation = validate_change_policy(
                run_root=run_root,
                target_root=target_root,
                context_path=change_context_path,
                current_context_path=current_context_path,
                auto_approve=bool(args.auto_approve),
                approval_status=args.approval_status,
            )
            if change_policy_validation.get("status") != "PASS":
                stopped_before_runner = True
                final_status = "BLOCKED"
                block_reason = str(change_policy_validation.get("block_reason", "")).strip() or "change_policy_invalid"

        if final_status != "BLOCKED":
            candidate_stage_root, candidate_claude_root = resolve_candidate_layout(candidate_root)
            s3_design_markers = [run_root / rel_path for rel_path in resolve_existing_run_refs(run_root, spec_payload).values()]
            design_review_required = candidate_stage_root.exists() or any(path.exists() for path in s3_design_markers)
            if design_review_required:
                design_review_validation = validate_design_review_gate(run_root)
                if design_review_validation.get("status") != "PASS":
                    stopped_before_runner = True
                    final_status = "BLOCKED"
                    block_reason = str(design_review_validation.get("block_reason", "")).strip() or "design_review_unresolved"

        if final_status != "BLOCKED":
            if not candidate_stage_root.exists():
                raise RuntimeError(f"develop flow requires candidate root before orchestration: {candidate_stage_root}")
            if not candidate_stage_root.is_dir():
                raise RuntimeError(f"candidate root must be a directory: {candidate_stage_root}")
            if not candidate_claude_root.exists() or not candidate_claude_root.is_dir():
                raise RuntimeError(f"develop flow requires candidate .claude root before orchestration: {candidate_claude_root}")
            design_assets = stage_persistent_design_assets(
                candidate_stage_root=candidate_stage_root,
                run_root=run_root,
                spec_path=spec_path,
                view_path=view_path,
                maintenance_path=maintenance_path,
            )
            target_runtime_assets = stage_target_runtime_assets(
                candidate_stage_root=candidate_stage_root,
                spec_path=spec_path,
            )
            managed_plan, managed_result, conflicts = run_managed_apply(target_root, run_root, candidate_stage_root)
            # managed apply 冲突要在 runner 之前中止。
            # 这样既能保持 S4 归属清晰，也避免在写入门禁未打开时假装控制面已经执行。
            if conflicts:
                stopped_before_runner = True
                final_status = "CONFLICT"
            else:
                target_claude_guard_result, guard_conflict = apply_target_claude_guard(spec_path, target_root, run_root)
                if guard_conflict:
                    stopped_before_runner = True
                    final_status = "CONFLICT"
        if final_status not in {"CONFLICT", "BLOCKED"}:
            capability_discovery_report = discover_host_capabilities(spec_path, target_root, run_root, args.request)
            host_capability_report = probe_host_capabilities(spec_path, target_root, run_root)
            auto_project_local = [
                item
                for item in host_capability_report.get("bootstrap_plan", [])
                if isinstance(item, dict)
                and str(item.get("scope", "")).strip() == "project_local"
                and bool(item.get("approval_required", False)) is False
            ]
            if auto_project_local:
                host_bootstrap_result = apply_host_bootstrap(
                    spec_path,
                    target_root,
                    run_root,
                )
                host_capability_report = probe_host_capabilities(spec_path, target_root, run_root)
            if isinstance(host_capability_report, dict) and isinstance(host_capability_report.get("capabilities"), list):
                environment_remediation_report = generate_environment_remediation(spec_path, target_root, run_root)
            runner_code, runner_summary = run_runner(
                spec_path=spec_path,
                run_root=run_root,
                target_root=target_root,
                plugin_root=plugin_root,
                request=args.request,
                intent=intent,
                entry_skill=entry_skill,
                auto_approve=bool(args.auto_approve),
                approval_status=args.approval_status,
                strict_route=bool(args.strict_route),
                runtime_provider=args.runtime_provider,
                provider_command=args.provider_command,
                claude_bin=args.claude_bin,
            )
            state_validation = validate_run_state(run_root)
    else:
        capability_discovery_report = discover_host_capabilities(spec_path, target_root, run_root, args.request)
        host_capability_report = probe_host_capabilities(spec_path, target_root, run_root)
        auto_project_local = [
            item
            for item in host_capability_report.get("bootstrap_plan", [])
            if isinstance(item, dict)
            and str(item.get("scope", "")).strip() == "project_local"
            and bool(item.get("approval_required", False)) is False
        ]
        if auto_project_local:
            host_bootstrap_result = apply_host_bootstrap(
                spec_path,
                target_root,
                run_root,
            )
            host_capability_report = probe_host_capabilities(spec_path, target_root, run_root)
        if isinstance(host_capability_report, dict) and isinstance(host_capability_report.get("capabilities"), list):
            environment_remediation_report = generate_environment_remediation(spec_path, target_root, run_root)
        runner_code, runner_summary = run_runner(
            spec_path=spec_path,
            run_root=run_root,
            target_root=target_root,
            plugin_root=plugin_root,
            request=args.request,
            intent=intent,
            entry_skill=entry_skill,
            auto_approve=bool(args.auto_approve),
            approval_status=args.approval_status,
            strict_route=bool(args.strict_route),
            runtime_provider=args.runtime_provider,
            provider_command=args.provider_command,
            claude_bin=args.claude_bin,
        )
        state_validation = validate_run_state(run_root)

    # 如果已经进入 runner，则最终入口 verdict 以 runner 结果为准；
    # 否则保留进入 runner 之前的编排状态，例如 managed conflict。
    if runner_summary is not None:
        final_status = str(runner_summary.get("status", "PASS")).strip() or final_status
    required_host_missing = False
    if isinstance(host_capability_report, dict):
        required_host_missing = any(
            isinstance(item, dict)
            and bool(item.get("required", False))
            and str(item.get("status", "")).strip() != "ready"
            for item in host_capability_report.get("capabilities", [])
            if isinstance(host_capability_report.get("capabilities", []), list)
        )
        if required_host_missing and final_status not in {"CONFLICT", "BLOCKED"}:
            final_status = "FAIL"

    summary = {
        "generated_at": utc_now(),
        "run_id": run_root.name,
        "request": args.request,
        "spec": str(spec_path),
        "run_root": str(run_root),
        "target_root": str(target_root),
        "plugin_root": str(plugin_root),
        "resolved_intent": intent,
        "resolved_entry_skill": entry_skill,
        "route_source": resolved["route_source"],
        "route_mismatch": resolved["route_mismatch"],
        "route_evidence_path": str(route_evidence_path),
        "route_evidence_mismatch": resolved.get("route_evidence_mismatch", False),
        "route_payload": resolved["route_payload"],
        "change_context_path": str(change_context_path),
        "change_context": change_context,
        "change_policy_validation": change_policy_validation,
        "design_review_validation": design_review_validation,
        "block_reason": block_reason,
        "failure_kind": "design" if final_status == "BLOCKED" else ("conflict" if final_status == "CONFLICT" else ("environment" if required_host_missing else "none")),
        "view_path": str(view_path),
        "maintenance_path": str(maintenance_path),
        "candidate_root": str(resolve_candidate_layout(candidate_root)[0]) if intent == "develop" else None,
        "persistent_design_assets": design_assets,
        "target_runtime_assets": target_runtime_assets,
        "spec_validation": {
            "status": spec_validation.get("status"),
            "error_count": len(spec_validation.get("errors", [])),
            "warning_count": len(spec_validation.get("warnings", [])),
        },
        "view_generation": view_generation,
        "maintenance_generation": maintenance_generation,
        "managed_plan_path": str(run_root / "outputs" / "managed-change-plan.json") if managed_plan else None,
        "managed_result_path": str(run_root / "outputs" / "managed-change-result.json") if managed_result else None,
        "managed_conflict_count": len(managed_result.get("conflicts", [])) if managed_result else 0,
        "capability_discovery_report": capability_discovery_report,
        "host_capability_report": host_capability_report,
        "host_bootstrap_result": host_bootstrap_result,
        "environment_remediation_report": environment_remediation_report,
        "target_claude_guard_result": target_claude_guard_result,
        "required_host_capability_missing": required_host_missing,
        "runner_status_code": runner_code,
        "runner_summary": runner_summary,
        "state_validation": state_validation,
        "stopped_before_runner": stopped_before_runner,
        "status": final_status,
    }
    summary_path = run_root / "outputs" / "stages" / "entry-orchestration-summary.json"
    write_json(summary_path, summary)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"[{summary['status']}] entry={entry_skill} intent={intent} "
            f"run={run_root.name} summary={summary_path}"
        )

    if final_status == "CONFLICT":
        return 2
    if final_status == "BLOCKED":
        return 2
    if final_status == "FAIL":
        return 1
    if final_status == "ENVIRONMENT-SKIP":
        return 3
    return 0


def main() -> int:
    """带统一错误整形逻辑的 CLI 入口。"""

    args = parse_args()
    try:
        if args.command == "run":
            return command_run(args)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
