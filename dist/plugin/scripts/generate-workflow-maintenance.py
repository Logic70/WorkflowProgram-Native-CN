#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
根据 workflow-spec.yaml 生成目标工作流的派生维护说明。

定位：
- workflow-spec.yaml: 机器可执行真源
- workflow-view.md: 人类只读概览
- workflow-maintenance.md: derived target view，维护/迭代指导，不得覆盖 YAML 语义
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from lib.io_utils import utc_now
from lib.yaml_utils import load_yaml_mapping


REQUIRED_TOP_KEYS = [
    "meta",
    "stages",
    "intent_flows",
    "agent_refs",
    "skills",
    "registry",
    "constraints",
    "resource_limits",
    "runtime_contract",
    "generated_runtime_contract",
    "test_contract",
]

GENERATED_LINE_RE = re.compile(
    r"^_Generated at .* from workflow-spec\.yaml \(spec_sha256=([0-9a-f]{64})\)_$",
    re.MULTILINE,
)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate workflow-maintenance.md from workflow-spec.yaml")
    parser.add_argument("--spec", default="workflow-spec.yaml", help="Path to workflow-spec.yaml")
    parser.add_argument("--out", default="workflow-maintenance.md", help="Path to generated workflow-maintenance.md")
    parser.add_argument("--json", action="store_true", help="Print structured result")
    return parser.parse_args()


def load_spec(path: Path) -> Dict[str, Any]:
    return load_yaml_mapping(path)


def ensure_spec_shape(spec: Dict[str, Any]) -> List[str]:
    missing = [key for key in REQUIRED_TOP_KEYS if key not in spec]
    stages = spec.get("stages")
    if stages is None or not isinstance(stages, list):
        raise ValueError("workflow-spec.yaml field 'stages' must be a list")
    return missing


def format_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "-"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if value in (None, ""):
        return "-"
    return str(value)


def render_truth_hierarchy() -> List[str]:
    return [
        "## Truth Hierarchy",
        "",
        "- `workflow-spec.yaml`：唯一机器真源。任何影响执行、校验、阶段流转、输入输出边界的内容都必须先进入这里。",
        "- `workflow-view.md`：从 YAML 单向渲染出的 derived target view，便于快速审查，不允许反向改语义。",
        "- `workflow-maintenance.md`：derived target view，用于解释阶段职责、证据归属和修改方法；不得覆盖 YAML 语义。",
        "- `target-design-overview.md` / `target-design-detail.md`：target design source，负责保存完整设计推理。",
        "",
    ]


def render_meta(meta: Dict[str, Any]) -> List[str]:
    return [
        "## Workflow Identity",
        "",
        f"- name: `{format_value(meta.get('name'))}`",
        f"- version: `{format_value(meta.get('version'))}`",
        f"- target_platform: `{format_value(meta.get('target_platform'))}`",
        f"- source_design: `{format_value(meta.get('source_design'))}`",
        f"- complexity: `{format_value(meta.get('complexity'))}`",
        "",
    ]


def render_intent_flows(spec: Dict[str, Any]) -> List[str]:
    lines: List[str] = ["## Intent Flow Contract", ""]
    intent_flows = spec.get("intent_flows", {})
    if not isinstance(intent_flows, dict) or not intent_flows:
        return lines + ["- None", ""]
    for intent in ("develop", "audit", "iterate", "validate"):
        flow = intent_flows.get(intent, {})
        if not isinstance(flow, dict):
            lines.append(f"- {intent}: invalid")
            continue
        lines.append(
            f"- {intent}: required=`{format_value(flow.get('required_stage_slots', []))}` "
            f"optional=`{format_value(flow.get('optional_stage_slots', []))}`"
        )
    lines.extend(
        [
            "",
            "维护规则：修改某个意图的阶段流时，只能编辑 `workflow-spec.yaml.intent_flows`，再重新生成视图与维护说明。",
            "",
        ]
    )
    return lines


def render_workflow_graph_guide(spec: Dict[str, Any]) -> List[str]:
    graph = spec.get("workflow_graph", {})
    lines: List[str] = ["## Target Workflow Graph Contract", ""]
    if not isinstance(graph, dict) or not graph:
        return lines + [
            "- None",
            "",
            "维护规则：若目标工作流的业务节点不等同于 WorkflowProgram 的 S1-S6 控制面，必须在 `workflow-spec.yaml.workflow_graph` 中声明目标节点、入口、转移与输出资产。",
            "",
        ]
    lines.extend(
        [
            f"- schema_version: `{format_value(graph.get('schema_version'))}`",
            f"- templates_used: `{format_value(graph.get('templates_used', []))}`",
            "",
            "维护规则：`workflow_graph` 是生成后目标工作流的业务图；`stages` 和 `intent_flows` 仍然只描述 WorkflowProgram 自身的开发/审计/迭代/验证控制面。",
            "维护规则：任何会影响目标工作流入口、节点转移、输出资产或 gate 的调整，都必须先改 `workflow-spec.yaml.workflow_graph`，再重生成 view/maintenance。",
            "维护规则：目标资产输出必须能回到 `registry` 或 `test_contract.artifacts`，避免模型生成未声明文件。",
            "维护规则：若节点声明 `loop_policy.enabled=true`，它只代表目标业务节点持续执行策略，不改变 WorkflowProgram 自身 S1-S6；成功必须由 verifier/test 证据支撑。",
            "",
        ]
    )
    nodes = graph.get("nodes", [])
    if isinstance(nodes, list) and nodes:
        lines.append("### Graph Nodes")
        lines.append("")
        for node in nodes:
            if not isinstance(node, dict):
                continue
            lines.append(
                f"- `{format_value(node.get('id'))}` role=`{format_value(node.get('role'))}` "
                f"owner=`{format_value(node.get('owner'))}` "
                f"loop=`{format_value(node.get('loop_policy', {}).get('mode')) if isinstance(node.get('loop_policy'), dict) and node.get('loop_policy', {}).get('enabled') is True else 'disabled'}` "
                f"outputs=`{format_value(node.get('output_refs', []))}`"
            )
            loop_policy = node.get("loop_policy", {})
            if isinstance(loop_policy, dict) and loop_policy.get("enabled") is True:
                lines.append(
                    f"  - loop max_iterations=`{format_value(loop_policy.get('max_iterations'))}` "
                    f"goal_source=`{format_value(loop_policy.get('goal_source', 'user'))}` "
                    f"evidence=`{format_value(loop_policy.get('evidence_outputs', []))}`"
                )
        lines.append("")
    return lines


def render_stage_guidance(stages: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = ["## Stage Contracts", ""]
    for stage in stages:
        stage_slot = format_value(stage.get("stage_slot"))
        stage_id = format_value(stage.get("id"))
        stage_name = format_value(stage.get("name"))
        lines.extend(
            [
                f"### `{stage_slot}` · `{stage_id}` · {stage_name}",
                "",
                f"- pattern: `{format_value(stage.get('pattern'))}`",
                f"- agent_ref: `{format_value(stage.get('agent_ref'))}`",
                f"- input: `{format_value(stage.get('input'))}`",
                f"- output: `{format_value(stage.get('output'))}`",
                f"- gate: `{format_value(stage.get('gate'))}`",
                f"- on_approve: `{format_value(stage.get('on_approve'))}`",
                f"- on_reject: `{format_value(stage.get('on_reject'))}`",
                f"- max_retries: `{format_value(stage.get('max_retries'))}`",
                "- 维护说明：若某阶段的输入/输出/转移会影响执行或校验，必须先回写 `workflow-spec.yaml`，不得只改本文档。",
                "",
            ]
        )
    return lines


def render_contract_guide(spec: Dict[str, Any]) -> List[str]:
    runtime_contract = spec.get("runtime_contract", {})
    generated_runtime_contract = spec.get("generated_runtime_contract", {})
    target_publish_policy = spec.get("target_publish_policy", {})
    test_contract = spec.get("test_contract", {})
    write_boundaries = runtime_contract.get("write_boundaries", {}) if isinstance(runtime_contract, dict) else {}
    required_evidence = runtime_contract.get("required_evidence", []) if isinstance(runtime_contract, dict) else []
    failure_kinds = runtime_contract.get("failure_kinds", []) if isinstance(runtime_contract, dict) else []
    return [
        "## Runtime And Test Contract",
        "",
        f"- target_root_allow: `{format_value(write_boundaries.get('target_root_allow', []))}`",
        f"- run_root_allow: `{format_value(write_boundaries.get('run_root_allow', []))}`",
        f"- required_evidence: `{format_value(required_evidence)}`",
        f"- failure_kinds: `{format_value(failure_kinds)}`",
        f"- test_categories: `{format_value([name for name in ('entry', 'boundary', 'flow', 'artifacts', 'failure') if name in test_contract])}`",
        "",
        "维护规则：任何会改变 verdict、边界、证据或失败分类的调整，都必须更新 `workflow-spec.yaml.runtime_contract` 或 `workflow-spec.yaml.test_contract`，而不是只更新解释文字。",
        "",
        "## Generated Runtime Contract",
        "",
        f"- runtime_root: `{format_value(generated_runtime_contract.get('runtime_root', '-'))}`",
        f"- entry_script: `{format_value(generated_runtime_contract.get('entry_script', '-'))}`",
        f"- runner_script: `{format_value(generated_runtime_contract.get('runner_script', '-'))}`",
        f"- state_validator_script: `{format_value(generated_runtime_contract.get('state_validator_script', '-'))}`",
        f"- runtime_manifest: `{format_value(generated_runtime_contract.get('runtime_manifest', '-'))}`",
        f"- run_root_dir: `{format_value(generated_runtime_contract.get('run_root_dir', '-'))}`",
        f"- runtime_capabilities: `{format_value(generated_runtime_contract.get('runtime_capabilities', []))}`",
        "",
        "维护规则：若目标工作流声明了阶段流与 test_contract，则必须同时交付 `.workflowprogram/runtime/` 下的 deterministic runtime 资产，不得只保留命令和设计文档。",
        "",
        "## Target Publish Policy",
        "",
        f"- enabled: `{format_value(target_publish_policy.get('enabled', False) if isinstance(target_publish_policy, dict) else False)}`",
        f"- publish_root: `{format_value(target_publish_policy.get('publish_root', '-') if isinstance(target_publish_policy, dict) else '-')}`",
        f"- latest_marker: `{format_value(target_publish_policy.get('latest_marker', '-') if isinstance(target_publish_policy, dict) else '-')}`",
        f"- manifest_path: `{format_value(target_publish_policy.get('manifest_path', '-') if isinstance(target_publish_policy, dict) else '-')}`",
        "",
        "维护规则：启用 target_publish_policy 后，节点与报告脚本只能写当前 RUN_ROOT；最终输出、latest marker 与 manifest 由 `target-runtime-finalizer.py` 校验当前 run 证据后原子发布。",
        "",
    ]


def render_host_capability_guide(spec: Dict[str, Any]) -> List[str]:
    host_capabilities = spec.get("host_capabilities", [])
    lines = ["## Host Capability Contract", ""]
    if not isinstance(host_capabilities, list) or not host_capabilities:
        return lines + ["- None", "", "维护规则：若工作流依赖专业工具、MCP 或宿主 skill，应先在 `workflow-spec.yaml.host_capabilities` 中声明，再通过 probe/bootstrap 证据验证可用性。", ""]
    for item in host_capabilities:
        if not isinstance(item, dict):
            continue
        bootstrap = item.get("bootstrap", {}) if isinstance(item.get("bootstrap"), dict) else {}
        outputs = bootstrap.get("project_local_outputs", []) if isinstance(bootstrap.get("project_local_outputs"), list) else []
        assets = bootstrap.get("assets", []) if isinstance(bootstrap.get("assets"), list) else []
        lines.append(
            f"- `{item.get('id', 'unknown')}` kind=`{item.get('kind', '-')}` required=`{item.get('required', False)}` "
            f"scope=`{bootstrap.get('scope', '-')}` approval_required=`{item.get('approval_required', False)}` "
            f"project_local_outputs=`{format_value(outputs)}` assets=`{len(assets)}`"
        )
    lines.extend(
        [
            "",
            "维护规则：host capability 只影响宿主可用性，不是 TARGET_ROOT 业务资产。探测报告和 bootstrap plan 必须写入 RUN_ROOT，只有 project-local bootstrap 可以写入 `TARGET_ROOT/.workflowprogram/bootstrap/**`。",
            "若声明 `bootstrap.assets`，则这些资产必须是可复用的配置、wrapper 或 marker 文件，并在 apply 证据与 target bootstrap manifest 中同时留下记录。",
            "",
        ]
    )
    return lines


def render_agent_team_guide(spec: Dict[str, Any]) -> List[str]:
    contract = spec.get("agent_team_contract", {})
    lines = ["## Agent Team Contract", ""]
    if not isinstance(contract, dict) or not contract:
        return lines + ["- None", "", "维护规则：普通 subagent 并不等于 agent team。只有声明了 `agent_team_contract.enabled=true` 的 workflow 才应产出 team evidence。", ""]
    lines.append(
        f"- enabled=`{format_value(contract.get('enabled'))}` max_fan_out=`{format_value(contract.get('max_fan_out'))}` "
        f"join_policy=`{format_value(contract.get('join_policy'))}`"
    )
    roles = contract.get("roles", [])
    if isinstance(roles, list) and roles:
        for role in roles:
            if not isinstance(role, dict):
                continue
            lines.append(
                f"- role `{role.get('id', 'unknown')}` stages=`{format_value(role.get('ownership_stage_slots', []))}` outputs=`{format_value(role.get('output_patterns', []))}`"
            )
    lines.extend(
        [
            "",
            "维护规则：team orchestration 的 join/fan-out 语义以 YAML 契约为准；维护说明只负责解释如何维护和审计 team 证据，不得单独扩展执行规则。",
            "",
        ]
    )
    return lines


def render_delivery_rules() -> List[str]:
    return [
        "## Persistent Design Assets",
        "",
        "- develop 成功后，应把 `workflow-spec.yaml`、`workflow-view.md`、`workflow-maintenance.md` 持久化到 `TARGET_ROOT/.workflowprogram/design/`。",
        "- develop 成功后，应把 target design source 归档到 `TARGET_ROOT/.workflowprogram/design/source/**`，用于后续修改、审计和发布。",
        "- develop 成功后，应把 `workflow-entry.py`、`workflow-runner.py`、`validate-run-state.py`、`runtime-manifest.json` 持久化到 `TARGET_ROOT/.workflowprogram/runtime/`。",
        "- 持久化副本属于 WorkflowProgram 托管资产，必须走 managed apply / manifest，而不是直接裸写目标目录。",
        "- 目标侧副本用于后续 audit / iterate / 人工维护理解当前工作流；当前运行的控制面输入仍以 `RUN_ROOT/workflow-spec.yaml` 为准。",
        "",
    ]


def render_maintenance_rules() -> List[str]:
    return [
        "## Maintenance Rules",
        "",
        "- 修改执行语义：先改 `workflow-spec.yaml`，再重新生成 `workflow-view.md` 与 `workflow-maintenance.md`。",
        "- 修改设计解释：可重生成 `workflow-maintenance.md`，但不得引入与 YAML 冲突的新约束。",
        "- 修改目标项目资产：必须通过 WorkflowProgram 的 develop / iterate 流程，避免手工破坏 manifest 与边界契约。",
        "- 排查运行问题：先看 `TARGET_ROOT/.workflowprogram/design/`，再看 `RUN_ROOT/state.json`、`events.jsonl`、`validation-runtime-report.md`。",
        "",
    ]


def normalize_maintenance_content(content: str) -> str:
    normalized = content.replace("\r\n", "\n")
    return GENERATED_LINE_RE.sub(
        r"_Generated at <normalized> from workflow-spec.yaml (spec_sha256=\1)_",
        normalized,
    )


def render_maintenance(spec: Dict[str, Any], spec_sha256: str, generated_at: str | None = None) -> str:
    lines: List[str] = [
        "# Workflow Maintenance Guide",
        "",
        f"_Generated at {generated_at or utc_now()} from workflow-spec.yaml (spec_sha256={spec_sha256})_",
        "",
        "> 本文件用于维护与迭代指导，不得覆盖 workflow-spec.yaml 语义。",
        "",
    ]
    lines.extend(render_truth_hierarchy())
    lines.extend(render_meta(spec.get("meta", {})))
    lines.extend(render_intent_flows(spec))
    lines.extend(render_workflow_graph_guide(spec))
    lines.extend(render_stage_guidance(spec.get("stages", [])))
    lines.extend(render_contract_guide(spec))
    lines.extend(render_host_capability_guide(spec))
    lines.extend(render_agent_team_guide(spec))
    lines.extend(render_delivery_rules())
    lines.extend(render_maintenance_rules())
    return "\n".join(lines).rstrip() + "\n"


# Compatibility aliases for the deprecated workflow-lowlevel entry points.
normalize_lowlevel_content = normalize_maintenance_content
render_lowlevel = render_maintenance


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    out_path = Path(args.out).resolve()
    payload = {"status": "PASS", "spec": str(spec_path), "out": str(out_path), "missing_top_keys": []}
    try:
        spec = load_spec(spec_path)
        spec_sha256 = sha256_file(spec_path)
        payload["missing_top_keys"] = ensure_spec_shape(spec)
        payload["spec_sha256"] = spec_sha256
        render = render_maintenance(spec, spec_sha256)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render, encoding="utf-8", newline="\n")
    except Exception as exc:
        payload["status"] = "FAIL"
        payload["error"] = str(exc)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Error: {exc}")
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Generated {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
