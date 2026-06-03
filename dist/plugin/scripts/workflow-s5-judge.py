#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
为 WorkflowProgram RUN_ROOT 生成具备 contract 感知能力的 S5 校验结果。

该 judge 刻意保持确定性：
- 输入：RUN_ROOT 证据、TARGET_ROOT 资产、可选的 workflow-spec.yaml
- 输出：validation-runtime-report.md + outputs/stages/s5-validation-summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.capability_discovery import capability_discovery_from_spec
from lib.failure_codes import failure_kind_for_result
from lib.host_team_utils import (
    LOOP_EVENT_TYPES,
    TEAM_EVENT_TYPES,
    agent_team_contract_from_spec,
    agent_team_enabled,
    host_capabilities_from_spec,
)
from lib.reporting import with_report_fields
from lib.spec_utils import path_matches_any, stage_slot_id_map
from lib.target_design_refs import (
    artifact_kind_for_path,
    iter_existing_node_design_refs,
    resolve_existing_run_refs,
    resolve_target_design_refs,
)
from lib.yaml_utils import try_load_yaml_mapping


RESULTS = {"PASS", "WARN", "FAIL", "ENVIRONMENT-SKIP"}
CATEGORY_ORDER = ("entry", "boundary", "flow", "artifacts", "failure")
SELF_GENERATED_FILES = {
    "validation-runtime-report.md",
    "outputs/stages/s5-validation-summary.json",
}
FAILURE_KIND_BY_CATEGORY = {
    "entry": "design",
    "flow": "design",
    "failure": "design",
    "boundary": "implementation",
    "artifacts": "implementation",
}


def load_json(path: Path) -> Dict[str, Any]:
    """供确定性 judge 使用的尽力而为 JSON 加载器。"""

    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_yaml(path: Path) -> Dict[str, Any]:
    """供 workflow-spec.yaml 使用的尽力而为 YAML 加载器。"""

    return try_load_yaml_mapping(path)


def load_snapshot(path: Path) -> List[Dict[str, Any]]:
    """加载由 runtime_smoke.py 产出的标准化快照格式。"""

    payload = load_json(path)
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        if not rel_path:
            continue
        normalized.append(
            {
                "path": rel_path,
                "sha256": str(item.get("sha256", "")).strip(),
                "size": item.get("size"),
            }
        )
    return normalized


def validate_managed_manifest(path: Path) -> List[str]:
    errors: List[str] = []
    payload = load_json(path)
    if not payload:
        return [f"managed manifest is missing or invalid JSON: {path}"]
    updated_at = str(payload.get("updated_at", "")).strip()
    entries = payload.get("entries")
    if not updated_at:
        errors.append("managed manifest is missing updated_at")
    if not isinstance(entries, list):
        errors.append("managed manifest entries must be a list")
    return errors


def is_managed_target_path(path: str) -> bool:
    return (
        path.startswith(".claude/")
        or path.startswith(".workflowprogram/design/")
        or path.startswith(".workflowprogram/runtime/")
    )


def snapshot_index(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """按相对路径为快照条目建立索引，便于快速 diff 查询。"""

    return {str(item["path"]): item for item in entries if str(item.get("path", "")).strip()}


def diff_snapshot_paths(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> List[str]:
    """返回两份快照之间发生变化的相对路径集合。"""

    before_index = snapshot_index(before)
    after_index = snapshot_index(after)
    changed: List[str] = []
    for rel_path in sorted(set(before_index) | set(after_index)):
        before_item = before_index.get(rel_path)
        after_item = after_index.get(rel_path)
        if before_item is None or after_item is None:
            changed.append(rel_path)
            continue
        if before_item.get("sha256") != after_item.get("sha256"):
            changed.append(rel_path)
    return changed


def matching_paths(paths: List[str], pattern: str) -> List[str]:
    """按单个 glob 模式过滤路径列表。"""

    import fnmatch

    return [path for path in paths if fnmatch.fnmatch(path, pattern)]


def string_list(value: Any) -> List[str]:
    """Normalize a JSON value to a list of non-empty strings."""

    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def managed_plan_paths(managed_plan: Dict[str, Any], managed_result: Dict[str, Any]) -> List[str]:
    """Collect target relative paths from managed plan/result evidence."""

    paths: set[str] = set()
    entries = managed_plan.get("entries", []) if isinstance(managed_plan.get("entries"), list) else []
    for item in entries:
        if isinstance(item, dict) and str(item.get("relative_path", "")).strip():
            paths.add(str(item.get("relative_path", "")).strip())
    for section in ("applied", "conflicts"):
        values = managed_result.get(section, []) if isinstance(managed_result.get(section), list) else []
        for item in values:
            if isinstance(item, dict) and str(item.get("relative_path", "")).strip():
                paths.add(str(item.get("relative_path", "")).strip())
    return sorted(paths)


def find_first_status(
    checks: Dict[str, List[Dict[str, str]]],
    statuses: set[str],
) -> Optional[Dict[str, str]]:
    """按 category 顺序返回首个命中目标状态的检查项。"""

    for category in CATEGORY_ORDER:
        for item in checks.get(category, []):
            if item.get("status") in statuses:
                return {"category": category, **item}
    return None


def failure_kind_for_check(category: str, name: str) -> str:
    """把失败/警告检查映射回粗粒度 failure_kind 分类。"""

    lowered_name = name.lower()
    if "conflict" in lowered_name:
        return "conflict"
    if "host_capability" in lowered_name:
        return "environment"
    if "environment" in lowered_name:
        return "environment"
    if "change_policy" in lowered_name or "change_context" in lowered_name or "change_approval" in lowered_name:
        return "design"
    if "design_review" in lowered_name:
        return "design"
    if "team_fan_out" in lowered_name or "team_join" in lowered_name or "team_execution" in lowered_name:
        return "implementation"
    if "team_contract" in lowered_name or "team_evidence" in lowered_name:
        return "design"
    if "design_lineage" in lowered_name or "design_ref" in lowered_name or "node_design" in lowered_name:
        return "design"
    if "node_loop" in lowered_name or "loop_iteration" in lowered_name:
        return "implementation"
    return FAILURE_KIND_BY_CATEGORY.get(category, "implementation")


def failure_code_for_check(category: str, name: str) -> str:
    """根据检查项身份生成稳定的机器可读 failure code。"""

    slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{category}_{name}").strip("_").upper()
    return f"S5_{slug or 'CHECK_FAILED'}"


def infer_expected_intent(entry_skill: str) -> str:
    """根据入口技能名推断期望的逻辑 intent。"""

    if entry_skill.endswith("-audit"):
        return "audit"
    if entry_skill.endswith("-validate"):
        return "validate"
    if entry_skill.endswith("-iterate"):
        return "iterate"
    if entry_skill.endswith("-orchestrate"):
        return "orchestrate"
    if entry_skill.endswith("-publish"):
        return "publish"
    return "develop"


def is_workflowprogram_product_entry(entry_skill: str) -> bool:
    """判断当前入口是否是 WorkflowProgram 自身的产品命令。"""

    return entry_skill.startswith("workflowprogram-")


def registered_entry_names(spec: Dict[str, Any]) -> set[str]:
    """从 workflow spec 中提取目标工作流已注册的 commands/skills 名称。"""

    registry = spec.get("registry", {})
    if not isinstance(registry, dict):
        return set()

    names: set[str] = set()
    for section in ("commands", "skills"):
        items = registry.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                text = str(item.get("name", "")).strip()
            else:
                text = str(item).strip()
            if text:
                names.add(text)
    return names


def registered_asset_paths(spec: Dict[str, Any]) -> set[str]:
    """从 registry 中提取所有目标资产路径。"""

    registry = spec.get("registry", {})
    if not isinstance(registry, dict):
        return set()
    paths: set[str] = set()
    for section in ("commands", "skills", "agents", "hooks", "runtime_assets"):
        items = registry.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                path = str(item.get("file", "")).strip()
                if path:
                    paths.add(path)
    return paths


def declared_artifact_patterns(spec: Dict[str, Any]) -> set[str]:
    """收集 test_contract 中声明的交付物和可选输出 pattern。"""

    test_contract = spec.get("test_contract", {}) if isinstance(spec, dict) else {}
    artifacts = test_contract.get("artifacts", {}) if isinstance(test_contract, dict) else {}
    if not isinstance(artifacts, dict):
        return set()
    values: set[str] = set()
    for field in ("deliverables", "optional_outputs"):
        items = artifacts.get(field, [])
        if isinstance(items, list):
            values.update(str(item).strip() for item in items if str(item).strip())
    return values


def is_declared_target_asset(path: str, registry_paths: set[str], artifact_patterns: set[str]) -> bool:
    """判断 target asset 是否被 registry 或 artifact contract 声明。"""

    if path in registry_paths or path in artifact_patterns:
        return True
    return any(path_matches_any(path, [pattern]) for pattern in artifact_patterns)


def report_schema_errors(payload: Dict[str, Any], expected_schema_name: str) -> List[str]:
    """校验 JSON 报告的公共字段。"""

    errors: List[str] = []
    if not payload:
        errors.append("missing or invalid JSON")
        return errors
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    schema_name = str(payload.get("schema_name", "")).strip()
    if schema_name != expected_schema_name:
        errors.append(f"schema_name must be {expected_schema_name}, got {schema_name or '<missing>'}")
    if "error_code" not in payload:
        errors.append("error_code is required")
    if "failure_kind" not in payload:
        errors.append("failure_kind is required")
    if "remediation" not in payload:
        errors.append("remediation is required")
    return errors


def expected_flow_for_intent(spec: Dict[str, Any], intent: str) -> tuple[List[str], List[str], List[str], str] | None:
    """解析某个 intent flow 对应的 required/optional/allowed stage id。"""

    intent_flows = spec.get("intent_flows", {})
    if not isinstance(intent_flows, dict):
        return None
    flow = intent_flows.get(intent, {})
    if not isinstance(flow, dict):
        return None
    slot_map = stage_slot_id_map(spec.get("stages", []))
    required_slots = flow.get("required_stage_slots", [])
    optional_slots = flow.get("optional_stage_slots", [])
    if not isinstance(required_slots, list):
        return None
    required_ids = [slot_map[slot] for slot in required_slots if str(slot).strip() in slot_map]
    optional_ids = [slot_map[slot] for slot in optional_slots if isinstance(optional_slots, list) and str(slot).strip() in slot_map] if isinstance(optional_slots, list) else []
    allowed_slots = [
        slot
        for slot in ("S1", "S2", "S3", "S4", "S5", "S6")
        if slot in {
            str(item).strip()
            for item in ([*required_slots, *optional_slots] if isinstance(optional_slots, list) else required_slots)
            if str(item).strip()
        }
    ]
    allowed_ids = [slot_map[slot] for slot in allowed_slots if slot in slot_map]
    if not required_ids:
        return None
    return required_ids, optional_ids, allowed_ids, f"intent_flows.{intent}"


def add_check(bucket: List[Dict[str, str]], name: str, status: str, detail: str, source: str) -> None:
    """向某个 category bucket 追加一条结构化检查结果。"""

    bucket.append(
        {
            "name": name,
            "status": status,
            "detail": detail,
            "source": source,
        }
    )


def design_ref_path_is_safe(path_text: str, *, node_design: bool = False) -> bool:
    """S5 的防御性路径检查；schema 校验仍是主入口。"""

    if not path_text or Path(path_text).is_absolute():
        return False
    parts = Path(path_text).parts
    if any(part in {"", ".", ".."} for part in parts):
        return False
    if node_design:
        return (
            path_text.startswith("outputs/stages/target-node-designs/")
            or path_text.startswith("outputs/stages/node-designs/")
            or path_text.startswith(".workflowprogram/design/node-designs/")
        )
    return path_text.startswith("outputs/stages/")


def design_ref_path_root(path_text: str, run_root: Path, target_root: Path) -> Path:
    if path_text.startswith(".workflowprogram/"):
        return target_root / path_text
    return run_root / path_text


def workflow_graph_node_ids(spec: Dict[str, Any]) -> set[str]:
    graph = spec.get("workflow_graph", {}) if isinstance(spec, dict) else {}
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    return {
        str(node.get("id", "")).strip()
        for node in nodes
        if isinstance(node, dict) and str(node.get("id", "")).strip()
    }


def requirement_ids_from_index(path: Path) -> List[str]:
    payload = load_yaml(path)
    requirements = payload.get("requirements", []) if isinstance(payload, dict) else []
    if isinstance(requirements, dict):
        iterable = requirements.values()
    elif isinstance(requirements, list):
        iterable = requirements
    else:
        iterable = []
    ids: List[str] = []
    for item in iterable:
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("id", "")).strip()
        if requirement_id and requirement_id not in ids:
            ids.append(requirement_id)
    return ids


def add_design_lineage_checks(
    checks: Dict[str, List[Dict[str, str]]],
    spec: Dict[str, Any],
    run_root: Path,
    target_root: Path,
    stage_history: List[str],
    result: str,
) -> None:
    """校验 design_refs 声明的设计源证据是否能被运行证据追踪到。"""

    design_refs = spec.get("design_refs", {}) if isinstance(spec, dict) else {}
    if not isinstance(design_refs, dict) or not design_refs:
        return
    resolved = resolve_target_design_refs(spec)
    strict_governance = resolved.canonical

    lineage_stage_reached = result in {"PASS", "WARN"} or any(
        stage in stage_history for stage in ["design", "generate", "validate", "lessons"]
    )
    if not lineage_stage_reached:
        add_check(
            checks["artifacts"],
            "design_lineage_deferred",
            "INFO",
            f"design_refs declared but stage_history={stage_history or ['<none>']} has not reached S3+.",
            "workflow-spec.yaml.design_refs",
        )
        return

    resolved_paths: Dict[str, Path] = {}
    for warning in resolved.warnings:
        add_check(checks["artifacts"], "target_design_refs_migration_warning", "INFO", warning, "workflow-spec.yaml.design_refs")
    for error in resolved.errors:
        add_check(checks["artifacts"], "target_design_refs_invalid", "FAIL", error, "workflow-spec.yaml.design_refs")
    for key, rel_path in sorted(resolved.run_refs.items()):
        safe = design_ref_path_is_safe(rel_path)
        exists = safe and (run_root / rel_path).exists()
        resolved_paths[key] = run_root / rel_path
        add_check(
            checks["artifacts"],
            f"target_design_ref_{key}_exists",
            "PASS" if exists else "FAIL",
            f"{key}={rel_path or '<missing>'}; safe={safe}; exists={exists}",
            f"workflow-spec.yaml.design_refs.{key}",
        )
    if strict_governance:
        for key in ("requirements", "context_findings", "design_overview", "design_detail", "implementation_plan", "acceptance_tests", "traceability_matrix"):
            add_check(
                checks["artifacts"],
                f"target_design_ref_{key}_declared",
                "PASS" if key in resolved.run_refs else "FAIL",
                f"{key} declared={key in resolved.run_refs}",
                f"workflow-spec.yaml.design_refs.{key}",
            )

    node_designs = resolved.node_designs
    if node_designs:
        declared_nodes = workflow_graph_node_ids(spec)
        for node_id, raw_path in node_designs.items():
            node_key = str(node_id).strip()
            rel_path = str(raw_path).strip()
            safe = design_ref_path_is_safe(rel_path, node_design=True)
            node_design_path = design_ref_path_root(rel_path, run_root, target_root)
            spec_for_node_design = target_root / ".workflowprogram" / "design" / "workflow-spec.yaml" if rel_path.startswith(".workflowprogram/") else run_root / "workflow-spec.yaml"
            exists = safe and node_design_path.exists()
            node_declared = node_key in declared_nodes
            add_check(
                checks["artifacts"],
                f"target_design_ref_node_design_{node_key or 'missing'}",
                "PASS" if safe and exists and node_declared else "FAIL",
                f"node={node_key or '<missing>'}; declared={node_declared}; path={rel_path or '<missing>'}; safe={safe}; exists={exists}",
                f"workflow-spec.yaml.design_refs.node_designs.{node_key or '<missing>'}",
            )
            if safe and exists and node_declared:
                node_design_validation = run_validator(
                    "validate-target-node-design.py",
                    "--node-design",
                    str(node_design_path),
                    "--spec",
                    str(spec_for_node_design),
                    "--node-id",
                    node_key,
                )
                add_check(
                    checks["artifacts"],
                    f"target_node_design_{node_key}_content_valid",
                    "PASS" if node_design_validation.get("status") == "PASS" else "FAIL",
                    f"errors={node_design_validation.get('errors', [])}; warnings={node_design_validation.get('warnings', [])}",
                    rel_path,
                )

    existing_refs = resolve_existing_run_refs(run_root, spec)
    requirements_path = resolved_paths.get("requirements") or (run_root / existing_refs["requirements"] if "requirements" in existing_refs else None)
    traceability_path = resolved_paths.get("traceability_matrix") or (run_root / existing_refs["traceability_matrix"] if "traceability_matrix" in existing_refs else None)
    if requirements_path and traceability_path and requirements_path.exists() and traceability_path.exists():
        requirement_ids = requirement_ids_from_index(requirements_path)
        try:
            traceability_text = traceability_path.read_text(encoding="utf-8")
        except Exception:
            traceability_text = ""
        missing = [requirement_id for requirement_id in requirement_ids if requirement_id not in traceability_text]
        add_check(
            checks["artifacts"],
            "design_lineage_requirement_traceability",
            "PASS" if requirement_ids and not missing else "FAIL",
            f"requirements={requirement_ids or ['<none>']}; missing_in_traceability={missing or ['<none>']}",
            str(traceability_path.relative_to(run_root)),
        )
        graph_nodes = sorted(workflow_graph_node_ids(spec))
        missing_nodes = [node_id for node_id in graph_nodes if node_id not in traceability_text]
        add_check(
            checks["artifacts"],
            "target_traceability_covers_graph_nodes",
            "PASS" if not missing_nodes else ("FAIL" if strict_governance else "WARN"),
            f"workflow_graph_nodes={graph_nodes or ['<none>']}; missing_in_traceability={missing_nodes or ['<none>']}",
            str(traceability_path.relative_to(run_root)),
        )
    acceptance_path = resolved_paths.get("acceptance_tests") or (run_root / existing_refs["acceptance_tests"] if "acceptance_tests" in existing_refs else None)
    if requirements_path and acceptance_path and requirements_path.exists() and acceptance_path.exists():
        requirement_ids = requirement_ids_from_index(requirements_path)
        acceptance_payload = load_yaml(acceptance_path)
        tests = acceptance_payload.get("tests", acceptance_payload.get("acceptance_tests", [])) if isinstance(acceptance_payload, dict) else []
        if not isinstance(tests, list):
            tests = []
        covered: set[str] = set()
        malformed: List[str] = []
        for idx, test in enumerate(tests):
            if not isinstance(test, dict):
                malformed.append(f"index:{idx}")
                continue
            test_id = str(test.get("id", f"index:{idx}")).strip()
            raw_refs = test.get("requirement_ids", test.get("covers", test.get("requirement", [])))
            if isinstance(raw_refs, str):
                refs = [raw_refs]
            elif isinstance(raw_refs, list):
                refs = [str(item).strip() for item in raw_refs if str(item).strip()]
            else:
                refs = []
            if not refs:
                malformed.append(test_id)
            covered.update(refs)
        missing_acceptance = [requirement_id for requirement_id in requirement_ids if requirement_id not in covered]
        add_check(
            checks["artifacts"],
            "target_acceptance_tests_cover_requirements",
            "PASS" if tests and not malformed and not missing_acceptance else ("FAIL" if strict_governance else "WARN"),
            f"tests={len(tests)}; malformed={malformed or ['<none>']}; missing_requirements={missing_acceptance or ['<none>']}",
            str(acceptance_path.relative_to(run_root)),
        )
    graph = spec.get("workflow_graph", {}) if isinstance(spec, dict) else {}
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    if isinstance(nodes, list):
        missing_complex_designs: List[str] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", "")).strip()
            if not node_id:
                continue
            loop_policy = node.get("loop_policy", {})
            requires_design = (
                node.get("node_design_required") is True
                or str(node.get("complexity", "")).strip() == "complex"
                or str(node.get("design_intensity", "")).strip() == "detailed"
                or (isinstance(loop_policy, dict) and loop_policy.get("enabled") is True)
            )
            exemption = node.get("node_design_exemption")
            exempted = isinstance(exemption, dict) and str(exemption.get("reason", "")).strip() and str(exemption.get("accepted_by", "")).strip()
            if requires_design and node_id not in node_designs and not exempted:
                missing_complex_designs.append(node_id)
        if missing_complex_designs or strict_governance:
            add_check(
                checks["artifacts"],
                "target_complex_nodes_have_design_or_exemption",
                "PASS" if not missing_complex_designs else "FAIL",
                f"missing_node_designs={missing_complex_designs or ['<none>']}",
                "workflow-spec.yaml.workflow_graph.nodes",
            )


def run_validator(script_name: str, *args: str) -> Dict[str, Any]:
    """运行确定性的辅助校验器，并归一化其 JSON 输出。"""

    script_path = Path(__file__).resolve().parent / script_name
    cmd = [sys.executable, str(script_path), *args, "--json"]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "status": "FAIL",
            "errors": [completed.stderr.strip() or completed.stdout.strip() or f"{script_name} returned invalid JSON"],
            "warnings": [],
        }
    if completed.returncode != 0 and payload.get("status") == "PASS":
        payload["status"] = "FAIL"
        payload.setdefault("errors", []).append(f"{script_name} exited with code {completed.returncode}")
    return payload if isinstance(payload, dict) else {"status": "FAIL", "errors": [f"{script_name} returned non-object payload"], "warnings": []}


def run_host_probe(spec_path: Path, target_root: Path, run_root: Path, output_name: str) -> Dict[str, Any]:
    """复用标准 host probe 脚本，生成当前宿主的实时就绪报告。"""

    payload = run_validator(
        "probe-host-capabilities.py",
        "--spec",
        str(spec_path),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
    )
    report = payload.get("report", {}) if isinstance(payload, dict) else {}
    if isinstance(report, dict) and report:
        target_path = run_root / "outputs" / "stages" / output_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report if isinstance(report, dict) else {}


def run_environment_remediation(spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    """基于当前 run 证据与历史失败生成环境修复提案。"""

    payload = run_validator(
        "generate-environment-remediation.py",
        "--spec",
        str(spec_path),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
    )
    report = payload.get("report", {}) if isinstance(payload, dict) else {}
    return report if isinstance(report, dict) else {}


def load_event_types(path: Path) -> List[str]:
    if not path.exists():
        return []
    event_types: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            text = str(payload.get("type", "")).strip()
            if text:
                event_types.append(text)
    return event_types


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL evidence stream, ignoring malformed lines for deterministic judging."""

    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def loop_enabled_nodes(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return target workflow graph nodes with loop_policy.enabled=true."""

    graph = spec.get("workflow_graph", {}) if isinstance(spec, dict) else {}
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        return []
    enabled: List[Dict[str, Any]] = []
    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            continue
        policy = raw_node.get("loop_policy", {})
        if isinstance(policy, dict) and policy.get("enabled") is True:
            enabled.append(raw_node)
    return enabled


def derive_contract(run_root: Path, fallback_categories: List[str]) -> Dict[str, Any]:
    """推导当前运行实际生效的 contract 上下文。

    如果 workflow-spec.yaml 存在，judge 会直接读取 runtime_contract 和 test_contract。
    否则回退到 fixture 提供的 category 期望值，这样即使是负例 smoke，
    也仍然能产出结构化检查项。
    """

    spec_path = run_root / "workflow-spec.yaml"
    spec = load_yaml(spec_path)
    if spec:
        runtime_contract = spec.get("runtime_contract", {})
        test_contract = spec.get("test_contract", {})
        if isinstance(runtime_contract, dict) and isinstance(test_contract, dict) and test_contract:
            categories = [name for name in CATEGORY_ORDER if name in test_contract]
            failure = test_contract.get("failure", {}) if isinstance(test_contract.get("failure"), dict) else {}
            env_skip = runtime_contract.get("environment_skip", [])
            env_codes: List[str] = []
            if isinstance(env_skip, list):
                for item in env_skip:
                    if isinstance(item, dict) and item.get("code"):
                        env_codes.append(str(item["code"]))
            implemented_now = failure.get("implemented_now", [])
            if not isinstance(implemented_now, list):
                implemented_now = []
            return {
                "contract_source": "workflow-spec.yaml.test_contract",
                "contract_categories": categories,
                "implemented_failure_kinds": [str(item) for item in implemented_now if str(item).strip()],
                "environment_skip_codes": env_codes,
                "runtime_contract": runtime_contract,
                "test_contract": test_contract,
                "spec_path": str(spec_path),
            }
    return {
        "contract_source": "fixture_preset",
        "contract_categories": fallback_categories,
        "implemented_failure_kinds": [],
        "environment_skip_codes": [],
        "runtime_contract": {},
        "test_contract": {},
        "spec_path": str(spec_path) if spec_path.exists() else None,
    }


def target_matches(target_root: Path, pattern: str) -> bool:
    """检查 target-root 的 glob 模式是否至少命中一个路径。"""

    return any(target_root.glob(pattern))


def build_checks(
    run_root: Path,
    target_root: Path,
    result: str,
    failure_code: str,
    summary_message: str,
    entry_skill: str,
    request: str,
    checked_files: List[str],
    contract: Dict[str, Any],
    provider_name: str,
) -> Dict[str, List[Dict[str, str]]]:
    """构建完整的、按 category 组织的 S5 检查矩阵。

    这是 judge 的核心。它会把以下信息合并起来：
    - 观测到的运行时证据
    - workflow-spec 中的 runtime_contract/test_contract
    - target 的前后快照
    - 辅助校验器结果
    最终收敛为一组确定性的 entry/boundary/flow/artifacts/failure 检查。
    """

    checks: Dict[str, List[Dict[str, str]]] = {name: [] for name in CATEGORY_ORDER}
    spec = load_yaml(run_root / "workflow-spec.yaml")
    s0_route_payload = load_json(run_root / "outputs" / "stages" / "s0-route.json")
    route_intent_payload = load_json(run_root / "outputs" / "stages" / "route-intent.json")
    route_payload = s0_route_payload or route_intent_payload
    change_context = load_json(run_root / "outputs" / "stages" / "change-context.json")
    change_policy = load_json(run_root / "outputs" / "stages" / "change-policy.json")
    impact_analysis = load_json(run_root / "outputs" / "stages" / "impact-analysis.json")
    policy_validation = load_json(run_root / "outputs" / "stages" / "validate-change-policy.json")
    existing_readback = load_json(run_root / "outputs" / "stages" / "existing-workflow-readback.json")
    design_review_root = run_root / "outputs" / "stages" / "design-review"
    design_review_packet = load_json(design_review_root / "design-review-packet.json")
    design_review_issues = load_json(design_review_root / "issues.json")
    design_review_closure = load_json(design_review_root / "closure.json")
    design_review_gate = load_json(design_review_root / "gate-validation.json")
    entry_summary = load_json(run_root / "outputs" / "stages" / "entry-orchestration-summary.json")
    runtime_contract = contract.get("runtime_contract", {})
    test_contract = contract.get("test_contract", {})
    derived_failure_kind = failure_kind_for_result(result, failure_code)
    provider_result = load_json(run_root / "outputs" / "runtime-provider-result.json")
    parsed_provider = provider_result.get("parsed", {}) if isinstance(provider_result.get("parsed"), dict) else {}
    before_target = load_snapshot(run_root / "outputs" / "target-root-before.json")
    after_target = load_snapshot(run_root / "outputs" / "target-root-files.json")
    before_target_index = snapshot_index(before_target)
    changed_target_paths = diff_snapshot_paths(before_target, after_target) if before_target or after_target else []
    after_target_paths = [str(item.get("path", "")).strip() for item in after_target if str(item.get("path", "")).strip()]
    expected_intent = infer_expected_intent(entry_skill)
    observed_intent = route_payload.get("intent") if isinstance(route_payload, dict) else ""
    observed_intent_text = str(observed_intent).strip() or expected_intent
    generated_registry_entries = registered_entry_names(spec)
    declared_host_capabilities = host_capabilities_from_spec(spec) if isinstance(spec, dict) else []
    declared_capability_discovery = capability_discovery_from_spec(spec) if isinstance(spec, dict) else {}
    capability_discovery_enabled = bool(declared_capability_discovery.get("enabled", False))
    declared_agent_team = agent_team_contract_from_spec(spec) if isinstance(spec, dict) else {}
    team_enabled = agent_team_enabled(declared_agent_team)
    loop_nodes = loop_enabled_nodes(spec)
    event_types = load_event_types(run_root / "events.jsonl")

    # entry 检查先回答“是不是用正确的产品入口、以正确的请求形态触发了执行”，
    # 再继续看更深层的运行时行为。
    entry = test_contract.get("entry", {}) if isinstance(test_contract.get("entry"), dict) else {}
    if entry:
        add_check(
            checks["entry"],
            "smoke_entry_invoked",
            "PASS" if entry_skill else "FAIL",
            f"Observed smoke entry skill: {entry_skill or '<missing>'}",
            "smoke.invocation",
        )
        declared_entry = str(entry.get("main_entry", "")).strip()
        if declared_entry:
            if is_workflowprogram_product_entry(entry_skill):
                registered = declared_entry in generated_registry_entries
                add_check(
                    checks["entry"],
                    "declared_generated_main_entry_registered",
                    "PASS" if registered else "FAIL",
                    (
                        f"WorkflowProgram product entry={entry_skill}; generated workflow main_entry={declared_entry}; "
                        f"registered_entries={sorted(generated_registry_entries) or ['<none>']}"
                    ),
                    "test_contract.entry.main_entry",
                )
                add_check(
                    checks["entry"],
                    "workflowprogram_product_entry_wraps_generated_entry",
                    "PASS",
                    f"WorkflowProgram product entry {entry_skill} is allowed to wrap generated workflow main_entry={declared_entry}.",
                    "workflowprogram.product_entry",
                )
            else:
                status = "PASS" if declared_entry == entry_skill else "FAIL"
                detail = f"Declared main_entry={declared_entry}; smoke entry={entry_skill}"
                add_check(checks["entry"], "declared_main_entry", status, detail, "test_contract.entry.main_entry")
        required_args = entry.get("required_args", [])
        requires_arguments = isinstance(required_args, list) and any(str(item).strip() == "$ARGUMENTS" for item in required_args)
        if requires_arguments:
            add_check(
                checks["entry"],
                "required_arguments_present",
                "PASS" if request.strip() else "FAIL",
                "Request payload is non-empty." if request.strip() else "Request payload is empty while $ARGUMENTS is required.",
                "test_contract.entry.required_args",
            )
            missing_arg_verdict = str(entry.get("missing_arg_verdict", "")).strip()
            if not request.strip() and missing_arg_verdict:
                observed = result
                status = "PASS" if observed == missing_arg_verdict else "FAIL"
                add_check(
                    checks["entry"],
                    "missing_argument_behavior",
                    status,
                    f"Observed verdict={observed}; expected missing_arg_verdict={missing_arg_verdict}; raw failure_code={failure_code or 'none'}",
                    "test_contract.entry.missing_arg_verdict",
                )
        invalid_verdict = str(entry.get("invalid_entry_verdict", "")).strip()
        if invalid_verdict and failure_code == "STRUCTURE_FAILURE":
            status = "PASS" if invalid_verdict == "FAIL" else "WARN"
            add_check(
                checks["entry"],
                "invalid_entry_behavior",
                status,
                f"Observed invalid-entry style failure via code={failure_code}",
                "test_contract.entry.invalid_entry_verdict",
            )
    elif "entry" in contract.get("contract_categories", []):
        add_check(checks["entry"], "contract_source_fallback", "INFO", "Entry checks derived from fixture preset.", "fixture_preset")

    # boundary 检查会把观测到的文件系统变更，与 runtime contract 及 managed-write 策略做比较。
    boundary = test_contract.get("boundary", {}) if isinstance(test_contract.get("boundary"), dict) else {}
    write_boundaries = runtime_contract.get("write_boundaries", {}) if isinstance(runtime_contract, dict) else {}
    if boundary:
        has_ref = str(boundary.get("write_boundaries_ref", "")).strip() == "runtime_contract.write_boundaries"
        add_check(
            checks["boundary"],
            "write_boundaries_reference",
            "PASS" if has_ref else "FAIL",
            "Boundary contract must reference runtime_contract.write_boundaries.",
            "test_contract.boundary.write_boundaries_ref",
        )
        run_root_allow = write_boundaries.get("run_root_allow", []) if isinstance(write_boundaries, dict) else []
        allow_spec = isinstance(run_root_allow, list) and "workflow-spec.yaml" in [str(item) for item in run_root_allow]
        add_check(
            checks["boundary"],
            "run_root_spec_boundary",
            "PASS" if allow_spec else "FAIL",
            "workflow-spec.yaml should be allowed in RUN_ROOT for control-plane execution.",
            "runtime_contract.write_boundaries.run_root_allow",
        )
        target_root_allow = write_boundaries.get("target_root_allow", []) if isinstance(write_boundaries, dict) else []
        target_patterns = [str(item).strip() for item in target_root_allow if str(item).strip()]
        disallowed_changes = [item for item in changed_target_paths if not path_matches_any(item, target_patterns)]
        if before_target or after_target:
            add_check(
                checks["boundary"],
                "target_root_boundary_changes",
                "PASS" if not disallowed_changes else "FAIL",
                f"Changed target-root paths={changed_target_paths or ['<none>']}; disallowed={disallowed_changes or ['<none>']}",
                "runtime_contract.write_boundaries.target_root_allow",
            )
        external_write_policy = str(boundary.get("external_write_policy", "")).strip()
        if external_write_policy:
            status = "PASS" if external_write_policy != "deny" or not disallowed_changes else "FAIL"
            add_check(
                checks["boundary"],
                "external_write_policy",
                status,
                f"external_write_policy={external_write_policy}; disallowed_changes={disallowed_changes or ['<none>']}",
                "test_contract.boundary.external_write_policy",
            )
        managed_plan = load_json(run_root / "outputs" / "managed-change-plan.json")
        managed_entries = managed_plan.get("entries", []) if isinstance(managed_plan.get("entries"), list) else []
        managed_rel_paths = [str(item.get("relative_path", "")).strip() for item in managed_entries if str(item.get("relative_path", "")).strip()]
        managed_result = load_json(run_root / "outputs" / "managed-change-result.json")
        managed_conflicts = managed_result.get("conflicts", []) if isinstance(managed_result.get("conflicts"), list) else []
        managed_rollback = load_json(run_root / "outputs" / "managed-rollback-manifest.json")
        managed_recover_path = run_root / "outputs" / "managed-recover-instructions.md"
        if managed_entries or managed_result:
            for report_name, payload, schema_name in (
                ("managed-change-plan", managed_plan, "managed-change-plan"),
                ("managed-change-result", managed_result, "managed-change-result"),
            ):
                schema_errors = report_schema_errors(payload, schema_name)
                add_check(
                    checks["boundary"],
                    f"{report_name}_schema_fields",
                    "PASS" if not schema_errors else "FAIL",
                    "; ".join(schema_errors) or f"{report_name} has common report schema fields.",
                    f"outputs/{report_name}.json",
                )
            rollback_schema_errors = report_schema_errors(managed_rollback, "managed-rollback-manifest")
            add_check(
                checks["boundary"],
                "managed_recovery_evidence_present",
                "PASS" if managed_rollback and managed_recover_path.exists() and not rollback_schema_errors else "FAIL",
                (
                    f"rollback_manifest={'present' if managed_rollback else 'missing'}; "
                    f"recover_instructions={'present' if managed_recover_path.exists() else 'missing'}; "
                    f"schema_errors={rollback_schema_errors or ['<none>']}"
                ),
                "outputs/managed-rollback-manifest.json",
            )
            expected_recovery_paths = {
                str(item.get("relative_path", "")).strip()
                for item in [*managed_result.get("applied", []), *managed_conflicts]
                if isinstance(item, dict) and str(item.get("relative_path", "")).strip()
            }
            rollback_entries = managed_rollback.get("entries", []) if isinstance(managed_rollback.get("entries"), list) else []
            rollback_paths = {
                str(item.get("relative_path", "")).strip()
                for item in rollback_entries
                if isinstance(item, dict) and str(item.get("relative_path", "")).strip()
            }
            missing_recovery_paths = sorted(expected_recovery_paths - rollback_paths)
            add_check(
                checks["boundary"],
                "managed_recovery_paths_covered",
                "PASS" if not missing_recovery_paths else "FAIL",
                f"missing rollback coverage={missing_recovery_paths or ['<none>']}",
                "outputs/managed-rollback-manifest.json",
            )
            registry_paths = registered_asset_paths(spec)
            artifact_patterns = declared_artifact_patterns(spec)
            undeclared_assets = [
                path
                for path in managed_rel_paths
                if is_managed_target_path(path) and not is_declared_target_asset(path, registry_paths, artifact_patterns)
            ]
            add_check(
                checks["boundary"],
                "managed_target_assets_declared",
                "PASS" if not undeclared_assets else "FAIL",
                f"undeclared managed target assets={undeclared_assets or ['<none>']}",
                "workflow-spec.yaml.registry",
            )
        managed_policy = str(boundary.get("managed_overwrite_policy", "")).strip()
        changed_managed_paths = [
            item for item in changed_target_paths if is_managed_target_path(item) and item in before_target_index
        ]
        unexpected_managed_changes = [item for item in changed_managed_paths if item not in managed_rel_paths]
        if managed_entries:
            missing_candidate_sources = []
            for item in managed_entries:
                source_path = str(item.get("source_path", "")).strip()
                if not source_path:
                    missing_candidate_sources.append("<missing>")
                    continue
                if not Path(source_path).exists():
                    missing_candidate_sources.append(source_path)
            add_check(
                checks["boundary"],
                "managed_candidate_sources_present",
                "PASS" if not missing_candidate_sources else "FAIL",
                f"Missing managed candidate source_path={missing_candidate_sources or ['<none>']}",
                "outputs/managed-change-plan.json",
            )
        if managed_policy:
            if unexpected_managed_changes:
                add_check(
                    checks["boundary"],
                    "managed_overwrite_policy_observed",
                    "FAIL",
                    f"managed_overwrite_policy={managed_policy}; unexpected managed changes={unexpected_managed_changes}",
                    "test_contract.boundary.managed_overwrite_policy",
                )
            elif managed_conflicts:
                add_check(
                    checks["boundary"],
                    "managed_overwrite_policy_observed",
                    "PASS" if managed_policy == "reject-unmanaged-overwrite" else "WARN",
                    f"managed_overwrite_policy={managed_policy}; observed conflicts={len(managed_conflicts)}",
                    "test_contract.boundary.managed_overwrite_policy",
                )
            elif managed_rel_paths:
                add_check(
                    checks["boundary"],
                    "managed_overwrite_policy_observed",
                    "PASS",
                    f"managed_overwrite_policy={managed_policy}; planned managed paths={managed_rel_paths}",
                    "test_contract.boundary.managed_overwrite_policy",
                )
            else:
                add_check(
                    checks["boundary"],
                    "managed_overwrite_policy_observed",
                    "INFO",
                    f"managed_overwrite_policy={managed_policy}; no managed conflicts were observed.",
                    "test_contract.boundary.managed_overwrite_policy",
                )
        conflict_expectation = str(boundary.get("conflict_expectation", "")).strip()
        if conflict_expectation:
            if managed_conflicts:
                missing_conflict_copy = []
                missing_candidate_source = []
                plan_entries_by_path = {
                    str(item.get("relative_path", "")).strip(): item for item in managed_entries if str(item.get("relative_path", "")).strip()
                }
                for item in managed_conflicts:
                    conflict_copy = str(item.get("conflict_copy", "")).strip()
                    if not conflict_copy:
                        missing_conflict_copy.append("<missing>")
                        continue
                    if not Path(conflict_copy).exists():
                        missing_conflict_copy.append(conflict_copy)
                    plan_entry = plan_entries_by_path.get(str(item.get("relative_path", "")).strip())
                    source_path = str(plan_entry.get("source_path", "")).strip() if isinstance(plan_entry, dict) else ""
                    if not source_path:
                        missing_candidate_source.append("<missing>")
                    elif not Path(source_path).exists():
                        missing_candidate_source.append(source_path)
                add_check(
                    checks["boundary"],
                    "conflict_artifacts_preserved",
                    "PASS" if not missing_conflict_copy and not missing_candidate_source else "FAIL",
                    f"conflict_expectation={conflict_expectation}; missing_conflict_copy={missing_conflict_copy or ['<none>']}; missing_candidate_source={missing_candidate_source or ['<none>']}",
                    "test_contract.boundary.conflict_expectation",
                )
            else:
                add_check(
                    checks["boundary"],
                    "conflict_artifacts_preserved",
                    "INFO",
                    f"conflict_expectation={conflict_expectation}; no conflicts were observed.",
                    "test_contract.boundary.conflict_expectation",
                )
    elif "boundary" in contract.get("contract_categories", []):
        add_check(checks["boundary"], "contract_source_fallback", "INFO", "Boundary checks derived from fixture preset.", "fixture_preset")

    # flow 检查会结合 provider 证据和 state.json 兜底信息，
    # 推断 stage history、审批门禁和失败恢复路径。
    flow = test_contract.get("flow", {}) if isinstance(test_contract.get("flow"), dict) else {}
    state = load_json(run_root / "state.json")
    if state:
        state_schema_errors = []
        if state.get("schema_version") != 1:
            state_schema_errors.append("schema_version must be 1")
        if not str(state.get("schema_name", "")).strip():
            state_schema_errors.append("schema_name is required")
        add_check(
            checks["flow"],
            "state_schema_fields",
            "PASS" if not state_schema_errors else "FAIL",
            "; ".join(state_schema_errors) or "state.json has common schema fields.",
            "state.json",
        )
    stage_history = []
    if isinstance(provider_result.get("stage_history"), list):
        stage_history = [str(item) for item in provider_result.get("stage_history", []) if str(item).strip()]
    elif isinstance(parsed_provider.get("stage_history"), list):
        stage_history = [str(item) for item in parsed_provider.get("stage_history", []) if str(item).strip()]
    values = state.get("values")
    if not stage_history and isinstance(values, dict):
        raw_history = values.get("stage_history", [])
        if isinstance(raw_history, list):
            stage_history = [str(item) for item in raw_history]
    pre_run_change_blocked = (
        str(entry_summary.get("status", "")).strip() == "BLOCKED"
        and str(entry_summary.get("block_reason", "")).strip().startswith("change_")
    )
    pre_run_design_blocked = (
        (
            str(entry_summary.get("status", "")).strip() == "BLOCKED"
            and str(entry_summary.get("block_reason", "")).strip().startswith("design_review")
        )
        or failure_code.startswith("DESIGN_REVIEW")
    )
    pre_run_blocked = pre_run_change_blocked or pre_run_design_blocked
    if flow:
        intent_flow = expected_flow_for_intent(spec, observed_intent_text)
        required_stage_source = "test_contract.flow.required_stages"
        skippable_stage_source = "test_contract.flow.skippable_stages"
        required_stages = flow.get("required_stages", [])
        skippable_stages = flow.get("skippable_stages", [])
        allowed_stages: List[str] = []
        if intent_flow is not None:
            required_stages, skippable_stages, allowed_stages, flow_source = intent_flow
            required_stage_source = f"{flow_source}.required_stage_slots"
            skippable_stage_source = f"{flow_source}.optional_stage_slots"
        if result in {"PASS", "WARN"}:
            add_check(
                checks["flow"],
                "stage_history_available",
                "PASS" if stage_history else "FAIL",
                f"Observed stage_history={stage_history or ['<none>']}",
                "runtime-provider.stage_history",
            )
        if isinstance(required_stages, list) and required_stages:
            if stage_history:
                missing = [str(item) for item in required_stages if str(item) not in stage_history]
                add_check(
                    checks["flow"],
                    "required_stages_executed",
                    "PASS" if not missing else ("INFO" if pre_run_blocked else "FAIL"),
                    f"Observed stage_history={stage_history}; missing={missing or 'none'}",
                    required_stage_source,
                )
            else:
                add_check(
                    checks["flow"],
                    "required_stages_executed",
                    "FAIL" if result in {"PASS", "WARN"} else "INFO",
                    "No runner stage_history found in provider/state evidence; flow could not be fully judged.",
                    required_stage_source,
                )
        if allowed_stages and stage_history:
            unexpected = [stage for stage in stage_history if stage not in allowed_stages]
            add_check(
                checks["flow"],
                "unexpected_stages_absent",
                "PASS" if not unexpected else "FAIL",
                f"Observed stage_history={stage_history}; allowed={allowed_stages}; unexpected={unexpected or ['<none>']}",
                f"{required_stage_source}+{skippable_stage_source}",
            )
            if not unexpected:
                observed_positions = [allowed_stages.index(stage) for stage in stage_history]
                ordered = observed_positions == sorted(observed_positions)
                add_check(
                    checks["flow"],
                    "stage_order_valid",
                    "PASS" if ordered else "FAIL",
                    f"Observed stage_history={stage_history}; allowed_order={allowed_stages}",
                    f"{required_stage_source}+{skippable_stage_source}",
                )
        terminal_conditions = flow.get("terminal_conditions", {})
        provider_stage_status = str(parsed_provider.get("stage_status", "")).strip() or str(provider_result.get("stage_status", "")).strip()
        if isinstance(terminal_conditions, dict) and result in terminal_conditions:
            if result in {"PASS", "WARN"}:
                add_check(
                    checks["flow"],
                    "stage_status_available",
                    "PASS" if provider_stage_status else "FAIL",
                    f"Observed stage_status={provider_stage_status or '<missing>'}",
                    "runtime-provider.stage_status",
                )
            if provider_stage_status:
                expected_stage_status = str(terminal_conditions.get(result, "")).strip()
                add_check(
                    checks["flow"],
                    "terminal_condition_observed",
                    "PASS" if provider_stage_status == expected_stage_status else ("INFO" if pre_run_blocked else "FAIL"),
                    f"Observed stage_status={provider_stage_status}; expected={expected_stage_status}",
                    "test_contract.flow.terminal_conditions",
                )
            else:
                add_check(
                    checks["flow"],
                    "terminal_condition_declared",
                    "FAIL" if result in {"PASS", "WARN"} else "INFO",
                    f"Verdict {result} maps to terminal state {terminal_conditions.get(result)}, but provider did not expose stage_status.",
                    "test_contract.flow.terminal_conditions",
                )
        if isinstance(skippable_stages, list) and stage_history:
            present = [str(item) for item in skippable_stages if str(item) in stage_history]
            absent = [str(item) for item in skippable_stages if str(item) not in stage_history]
            add_check(
                checks["flow"],
                "skippable_stages_observed",
                "PASS",
                f"Present skippable stages={present or ['<none>']}; absent skippable stages={absent or ['<none>']}",
                skippable_stage_source,
            )
        failure_recovery = flow.get("failure_recovery", {})
        provider_recovery = str(parsed_provider.get("next_stage_on_failure", "")).strip() or str(provider_result.get("next_stage_on_failure", "")).strip()
        if result == "FAIL" and isinstance(failure_recovery, dict) and failure_recovery:
            expected_recovery = str(failure_recovery.get(derived_failure_kind, "")).strip()
            if expected_recovery and provider_recovery:
                add_check(
                    checks["flow"],
                    "failure_recovery_target",
                    "PASS" if provider_recovery == expected_recovery else "FAIL",
                    f"Observed next_stage_on_failure={provider_recovery}; expected={expected_recovery}",
                    "test_contract.flow.failure_recovery",
                )
            elif expected_recovery:
                add_check(
                    checks["flow"],
                    "failure_recovery_target",
                    "INFO",
                    f"Expected recovery target={expected_recovery}, but provider did not expose next_stage_on_failure.",
                    "test_contract.flow.failure_recovery",
                )
    elif "flow" in contract.get("contract_categories", []):
        add_check(checks["flow"], "contract_source_fallback", "INFO", "Flow checks derived from fixture preset.", "fixture_preset")

    # artifact 检查确保“最小证据集”和“面向用户的交付物”
    # 都与 spec 对本次运行后的期望一致。
    artifacts = test_contract.get("artifacts", {}) if isinstance(test_contract.get("artifacts"), dict) else {}
    evidence_paths: List[str] = []
    for rel_path in checked_files + sorted(SELF_GENERATED_FILES):
        if rel_path not in evidence_paths:
            evidence_paths.append(rel_path)
    for rel_path in evidence_paths:
        if rel_path in SELF_GENERATED_FILES:
            status = "PASS"
            detail = f"{rel_path} is generated by the S5 judge."
        else:
            status = "PASS" if (run_root / rel_path).exists() else "FAIL"
            detail = f"{rel_path} {'exists' if status == 'PASS' else 'is missing'} in RUN_ROOT."
        add_check(checks["artifacts"], f"evidence:{rel_path}", status, detail, "runtime_smoke.evidence")
    if artifacts:
        evidence_ref = str(artifacts.get("evidence_ref", "")).strip()
        if evidence_ref:
            add_check(
                checks["artifacts"],
                "evidence_reference",
                "PASS" if evidence_ref == "runtime_contract.required_evidence" else "FAIL",
                f"evidence_ref={evidence_ref}",
                "test_contract.artifacts.evidence_ref",
            )
        required_evidence = runtime_contract.get("required_evidence", []) if isinstance(runtime_contract, dict) else []
        if isinstance(required_evidence, list):
            missing_required = []
            for rel_path in [str(item).strip() for item in required_evidence if str(item).strip()]:
                if not (run_root / rel_path).exists():
                    missing_required.append(rel_path)
            add_check(
                checks["artifacts"],
                "required_runtime_evidence",
                "PASS" if not missing_required else "FAIL",
                f"Missing required_evidence={missing_required or ['<none>']}",
                "runtime_contract.required_evidence",
            )
        if route_payload:
            route_entry = str(route_payload.get("entry_skill", "")).strip()
            route_intent = str(route_payload.get("intent", "")).strip()
            add_check(
                checks["artifacts"],
                "route_evidence_matches_invocation",
                "PASS" if route_entry == entry_skill and route_intent == expected_intent else "FAIL",
                f"Observed route entry_skill={route_entry or '<missing>'}; intent={route_intent or '<missing>'}; expected entry_skill={entry_skill}; intent={expected_intent}",
                "outputs/stages/s0-route.json",
            )
        if route_intent_payload and s0_route_payload:
            mismatched_keys = [
                key
                for key in ("intent", "entry_skill", "request_kind")
                if key in route_intent_payload
                and key in s0_route_payload
                and str(route_intent_payload.get(key, "")).strip() != str(s0_route_payload.get(key, "")).strip()
            ]
            add_check(
                checks["artifacts"],
                "route_context_consistent",
                "PASS" if not mismatched_keys else "FAIL",
                f"route-intent vs s0-route mismatched keys={mismatched_keys or ['<none>']}",
                "outputs/stages/route-intent.json",
            )
        change_policy_required = bool(change_context.get("change_policy_required", False)) if change_context else False
        managed_plan_for_review = load_json(run_root / "outputs" / "managed-change-plan.json")
        managed_result_for_review = load_json(run_root / "outputs" / "managed-change-result.json")
        managed_paths_for_review = managed_plan_paths(managed_plan_for_review, managed_result_for_review)
        if change_context:
            add_check(
                checks["artifacts"],
                "change_context_present",
                "PASS",
                (
                    f"target_state={change_context.get('target_state', '<missing>')}; "
                    f"request_kind={change_context.get('request_kind', '<missing>')}; "
                    f"required={change_context.get('change_policy_required', False)}"
                ),
                "outputs/stages/change-context.json",
            )
        if change_policy_required:
            add_check(
                checks["artifacts"],
                "change_policy_present_when_required",
                "PASS" if change_policy else "FAIL",
                "change-policy.json present." if change_policy else "change-policy.json missing while change_policy_required=true.",
                "outputs/stages/change-policy.json",
            )
            add_check(
                checks["artifacts"],
                "impact_analysis_present_when_required",
                "PASS" if impact_analysis else "FAIL",
                "impact-analysis.json present." if impact_analysis else "impact-analysis.json missing while change_policy_required=true.",
                "outputs/stages/impact-analysis.json",
            )
            validation_status = str(policy_validation.get("status", "")).strip()
            add_check(
                checks["artifacts"],
                "change_policy_schema_valid",
                "PASS" if validation_status == "PASS" else "FAIL",
                f"validate-change-policy status={validation_status or '<missing>'}; errors={policy_validation.get('errors', ['<missing>'])}",
                "outputs/stages/validate-change-policy.json",
            )
            stale = policy_validation.get("stale_fingerprints", []) if isinstance(policy_validation.get("stale_fingerprints"), list) else []
            add_check(
                checks["artifacts"],
                "change_context_not_stale",
                "PASS" if not stale else "FAIL",
                f"stale_fingerprints={stale or ['<none>']}",
                "outputs/stages/validate-change-policy.json",
            )
            entry_status = str(entry_summary.get("status", "")).strip()
            entry_block_reason = str(entry_summary.get("block_reason", "")).strip()
            if validation_status and validation_status != "PASS":
                add_check(
                    checks["flow"],
                    "pre_run_blocked_status_explained",
                    "PASS" if entry_status == "BLOCKED" and entry_block_reason else "FAIL",
                    f"entry_status={entry_status or '<missing>'}; block_reason={entry_block_reason or '<missing>'}",
                    "outputs/stages/entry-orchestration-summary.json",
                )
            approval_required = bool(change_policy.get("requires_approval", False)) if change_policy else False
            approval_mode = str(policy_validation.get("approval_mode", "")).strip()
            if approval_required:
                add_check(
                    checks["flow"],
                    "change_approval_recorded",
                    "PASS" if approval_mode in {"approved", "auto-approved"} or entry_block_reason == "change_approval_missing" else "FAIL",
                    f"approval_mode={approval_mode or '<missing>'}; entry_block_reason={entry_block_reason or '<none>'}",
                    "outputs/stages/validate-change-policy.json",
                )
            managed_paths = managed_paths_for_review
            affected = string_list(change_policy.get("affected_artifacts")) if change_policy else []
            derived = string_list(change_policy.get("allowed_derived_artifacts")) if change_policy else []
            allowed_patterns = [*affected, *derived]
            disallowed = [path for path in managed_paths if not path_matches_any(path, allowed_patterns)] if allowed_patterns else managed_paths
            if managed_paths or validation_status == "PASS":
                add_check(
                    checks["boundary"],
                    "managed_changes_within_affected_artifacts",
                    "PASS" if not disallowed else "FAIL",
                    f"managed_paths={managed_paths or ['<none>']}; allowed={allowed_patterns or ['<none>']}; disallowed={disallowed or ['<none>']}",
                    "outputs/managed-change-plan.json",
                )
            if str(change_policy.get("mode", "")).strip() == "redesign_from_existing":
                add_check(
                    checks["artifacts"],
                    "redesign_from_existing_has_readback",
                    "PASS" if existing_readback else "FAIL",
                    "existing-workflow-readback.json present." if existing_readback else "redesign_from_existing missing readback evidence.",
                    "outputs/stages/existing-workflow-readback.json",
                )
            semantic_paths = [
                path
                for path in managed_paths
                if path.startswith(".claude/") or path.startswith(".workflowprogram/runtime/")
            ]
            if semantic_paths and str(change_policy.get("scope", "")).strip() != "docs":
                spec_in_change = ".workflowprogram/design/workflow-spec.yaml" in managed_paths
                spec_justified = impact_analysis.get("spec_change_required") is False and bool(str(impact_analysis.get("spec_change_reason", "")).strip())
                test_justified = (
                    impact_analysis.get("test_contract_change_required") is not False
                    or bool(str(impact_analysis.get("test_contract_change_reason", "")).strip())
                )
                add_check(
                    checks["flow"],
                    "no_spec_bypass_for_semantic_change",
                    "PASS" if spec_in_change or spec_justified else "FAIL",
                    f"semantic_paths={semantic_paths}; spec_in_change={spec_in_change}; spec_justified={spec_justified}",
                    "outputs/stages/impact-analysis.json",
                )
                add_check(
                    checks["flow"],
                    "no_test_contract_bypass_for_semantic_change",
                    "PASS" if test_justified else "FAIL",
                    f"test_contract_change_required={impact_analysis.get('test_contract_change_required', '<missing>')}; reason_present={bool(str(impact_analysis.get('test_contract_change_reason', '')).strip())}",
                    "outputs/stages/impact-analysis.json",
                )
        active_design_refs = resolve_existing_run_refs(run_root, spec)
        s3_design_paths = [run_root / rel_path for rel_path in active_design_refs.values()]
        s3_design_present = any(path.exists() for path in s3_design_paths)
        semantic_managed_paths = [
            path
            for path in managed_paths_for_review
            if path.startswith(".claude/") or path.startswith(".workflowprogram/runtime/")
        ]
        design_review_required = observed_intent_text == "develop" and (s3_design_present or bool(managed_paths_for_review))
        if design_review_required:
            add_check(
                checks["artifacts"],
                "design_review_packet_present",
                "PASS" if design_review_packet else "FAIL",
                "design-review-packet.json present." if design_review_packet else "design-review-packet.json missing before S4 implementation.",
                "outputs/stages/design-review/design-review-packet.json",
            )
            issues = design_review_issues.get("issues", []) if isinstance(design_review_issues.get("issues"), list) else []
            open_blockers = [
                item
                for item in issues
                if isinstance(item, dict)
                and bool(item.get("blocking", False))
                and str(item.get("status", "")).strip() == "open"
            ]
            accepted_risks = [
                item
                for item in issues
                if isinstance(item, dict) and str(item.get("status", "")).strip() == "accepted_risk"
            ]
            add_check(
                checks["artifacts"],
                "design_review_issues_ledger_present",
                "PASS" if design_review_issues else "FAIL",
                f"issues={len(issues)}; open_blockers={[item.get('id') for item in open_blockers] or ['<none>']}",
                "outputs/stages/design-review/issues.json",
            )
            add_check(
                checks["artifacts"],
                "design_review_closure_present",
                "PASS" if design_review_closure else "FAIL",
                "closure.json present." if design_review_closure else "closure.json missing before managed apply.",
                "outputs/stages/design-review/closure.json",
            )
            closure_status = str(design_review_closure.get("status", "")).strip()
            gate_status = str(design_review_gate.get("status", "")).strip()
            add_check(
                checks["artifacts"],
                "design_review_gate_valid",
                "PASS" if gate_status == "PASS" and closure_status == "PASS" and not open_blockers else "FAIL",
                (
                    f"gate_status={gate_status or '<missing>'}; closure_status={closure_status or '<missing>'}; "
                    f"open_blockers={[item.get('id') for item in open_blockers] or ['<none>']}"
                ),
                "outputs/stages/design-review/gate-validation.json",
            )
            if accepted_risks:
                add_check(
                    checks["flow"],
                    "design_review_accepted_risks_recorded",
                    "INFO",
                    f"accepted_risks={[item.get('id') for item in accepted_risks]}",
                    "outputs/stages/design-review/issues.json",
                )
            if gate_status and gate_status != "PASS":
                entry_status = str(entry_summary.get("status", "")).strip()
                entry_block_reason = str(entry_summary.get("block_reason", "")).strip()
                add_check(
                    checks["flow"],
                    "design_review_pre_run_blocked_status_explained",
                    "PASS" if entry_status == "BLOCKED" and entry_block_reason == "design_review_unresolved" else "FAIL",
                    f"entry_status={entry_status or '<missing>'}; block_reason={entry_block_reason or '<missing>'}",
                    "outputs/stages/entry-orchestration-summary.json",
                )
            if semantic_managed_paths:
                active_traceability = active_design_refs.get("traceability_matrix", "outputs/stages/traceability-matrix.json")
                traceability_path = run_root / active_traceability
                add_check(
                    checks["flow"],
                    "design_review_semantic_changes_have_traceability",
                    "PASS" if traceability_path.exists() and gate_status == "PASS" else "FAIL",
                    f"semantic_paths={semantic_managed_paths}; traceability_exists={traceability_path.exists()}; gate_status={gate_status or '<missing>'}",
                    active_traceability,
                )
        runner_summary = load_json(run_root / "outputs" / "stages" / "runner-summary.json")
        if runner_summary:
            summary_entry = str(runner_summary.get("entry_skill", "")).strip()
            summary_status = str(runner_summary.get("status", "")).strip()
            summary_matches = (
                summary_entry == entry_skill
                and (
                    summary_status == result
                    or (
                        summary_status == "PASS"
                        and derived_failure_kind == "environment"
                        and declared_host_capabilities
                    )
                )
            )
            add_check(
                checks["artifacts"],
                "runner_summary_matches_observed",
                "PASS" if summary_matches else "FAIL",
                f"Observed runner-summary entry_skill={summary_entry or '<missing>'}; status={summary_status or '<missing>'}; expected entry_skill={entry_skill}; status={result}",
                "outputs/stages/runner-summary.json",
            )
        add_design_lineage_checks(checks, spec, run_root, target_root, stage_history, result)
        if isinstance(spec.get("design_refs"), dict) and spec.get("design_refs"):
            target_design_validation = run_validator(
                "validate-target-design-governance.py",
                "--run-root",
                str(run_root),
                "--spec",
                str(run_root / "workflow-spec.yaml"),
            )
            add_check(
                checks["artifacts"],
                "target_design_governance_validator",
                "PASS" if target_design_validation.get("status") == "PASS" else "FAIL",
                f"errors={target_design_validation.get('errors', [])}; warnings={target_design_validation.get('warnings', [])}",
                "outputs/stages/target-design-governance-validation.json",
            )
        requires_s1_draft = observed_intent_text == "develop" and (
            result in {"PASS", "WARN"} or any(stage in stage_history for stage in ["context", "design", "generate", "validate", "lessons"])
        )
        draft_path = run_root / "workflow-spec.md"
        if requires_s1_draft:
            add_check(
                checks["artifacts"],
                "workflow_spec_draft_exists",
                "PASS" if draft_path.exists() else "FAIL",
                f"workflow-spec.md {'exists' if draft_path.exists() else 'is missing'} at {draft_path}",
                "S1.workflow-spec.md",
            )
            if draft_path.exists():
                clarification_package = run_validator(
                    "generate-clarification-package.py",
                    "--spec",
                    str(draft_path),
                    "--run-root",
                    str(run_root),
                )
                package_detail = "; ".join(
                    [*clarification_package.get("errors", []), *clarification_package.get("warnings", [])]
                ) or "Structured clarification package generated."
                add_check(
                    checks["artifacts"],
                    "clarification_package_generated",
                    "PASS" if clarification_package.get("status") == "PASS" else "FAIL",
                    package_detail,
                    "generate-clarification-package.py",
                )
                clarification_review = run_validator(
                    "generate-clarification-review.py",
                    "--spec",
                    str(draft_path),
                    "--run-root",
                    str(run_root),
                )
                review_detail = "; ".join(
                    [*clarification_review.get("errors", []), *clarification_review.get("warnings", [])]
                ) or "Internal challenge review and downstream handoff artifacts generated."
                add_check(
                    checks["artifacts"],
                    "clarification_review_generated",
                    "PASS" if clarification_review.get("status") == "PASS" else "FAIL",
                    review_detail,
                    "generate-clarification-review.py",
                )
                for rel_path, check_name in (
                    ("outputs/stages/clarification-record.json", "clarification_record_exists"),
                    ("outputs/stages/open-questions.json", "clarification_open_questions_exists"),
                    ("outputs/stages/assumption-log.md", "clarification_assumption_log_exists"),
                    ("outputs/stages/design-readiness-report.json", "clarification_design_readiness_exists"),
                    ("outputs/stages/question-backlog.json", "clarification_question_backlog_exists"),
                    ("outputs/stages/requirement-logic-map.json", "clarification_requirement_logic_map_exists"),
                    ("outputs/stages/clarification-challenge-report.json", "clarification_challenge_report_exists"),
                    ("outputs/stages/clarification-handoff.json", "clarification_handoff_exists"),
                    ("outputs/stages/clarification-evidence.json", "clarification_evidence_exists"),
                ):
                    artifact_path = run_root / rel_path
                    add_check(
                        checks["artifacts"],
                        check_name,
                        "PASS" if artifact_path.exists() else "FAIL",
                        f"{rel_path} {'exists' if artifact_path.exists() else 'is missing'} at {artifact_path}",
                        rel_path,
                    )
                draft_validation = run_validator(
                    "validate-workflow-draft.py",
                    "--spec",
                    str(draft_path),
                    "--run-root",
                    str(run_root),
                )
                detail = "; ".join(
                    [*draft_validation.get("errors", []), *draft_validation.get("warnings", [])]
                ) or "workflow-spec.md passed deterministic S1 quality validation."
                add_check(
                    checks["artifacts"],
                    "workflow_spec_draft_valid",
                    "PASS" if draft_validation.get("status") == "PASS" else "FAIL",
                    detail,
                    "validate-workflow-draft.py",
                )
        environment_remediation_report: Dict[str, Any] = {}
        if declared_host_capabilities:
            remediation_spec_for_s6 = run_root / "workflow-spec.yaml"
            target_spec_for_s6 = target_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
            if observed_intent_text in {"validate", "audit"} and target_spec_for_s6.exists():
                remediation_spec_for_s6 = target_spec_for_s6
            environment_remediation_report = run_environment_remediation(remediation_spec_for_s6, target_root, run_root)
        requires_s6_delta = "lessons" in stage_history or (observed_intent_text in {"develop", "audit", "iterate"} and result in {"PASS", "WARN"})
        optional_s6_delta = observed_intent_text == "validate"
        delta_path = run_root / "outputs" / "stages" / "s6-lessons-delta.md"
        if requires_s6_delta or (optional_s6_delta and delta_path.exists()):
            add_check(
                checks["artifacts"],
                "s6_lessons_delta_exists",
                "PASS" if delta_path.exists() else "FAIL",
                f"s6-lessons-delta.md {'exists' if delta_path.exists() else 'is missing'} at {delta_path}",
                "S6.outputs/stages/s6-lessons-delta.md",
            )
            if delta_path.exists():
                lessons_validation = run_validator(
                    "validate-lessons-delta.py",
                    "--run-root",
                    str(run_root),
                    "--run-id",
                    run_root.name,
                    "--failure-kind",
                    derived_failure_kind,
                )
                detail = "; ".join(
                    [*lessons_validation.get("errors", []), *lessons_validation.get("warnings", [])]
                ) or "S6 lessons delta and user progress passed deterministic validation."
                add_check(
                    checks["artifacts"],
                    "s6_lessons_delta_valid",
                    "PASS" if lessons_validation.get("status") == "PASS" else "FAIL",
                    detail,
                    "validate-lessons-delta.py",
                )
        deliverables = artifacts.get("deliverables", [])
        if isinstance(deliverables, list):
            for pattern in deliverables:
                text = str(pattern).strip()
                if not text:
                    continue
                matched_paths = matching_paths(after_target_paths, text)
                changed_matches = matching_paths(changed_target_paths, text)
                if result in {"PASS", "WARN"}:
                    status = "PASS" if changed_matches else "FAIL"
                else:
                    status = "INFO"
                add_check(
                    checks["artifacts"],
                    f"deliverable:{text}",
                    status,
                    f"Deliverable pattern {text}; matched_paths={matched_paths or ['<none>']}; changed_matches={changed_matches or ['<none>']}",
                    "test_contract.artifacts.deliverables",
                )
                if text == ".workflowprogram/managed-files.json":
                    manifest_path = target_root / ".workflowprogram" / "managed-files.json"
                    manifest_errors = validate_managed_manifest(manifest_path) if manifest_path.exists() else [f"managed manifest not found: {manifest_path}"]
                    add_check(
                        checks["artifacts"],
                        "managed_manifest_valid",
                        "PASS" if not manifest_errors else "FAIL",
                        "managed-files.json passed deterministic validation." if not manifest_errors else "; ".join(manifest_errors),
                        "TARGET_ROOT/.workflowprogram/managed-files.json",
                    )
                    managed_result = load_json(run_root / "outputs" / "managed-change-result.json")
                    manifest_ref = str(managed_result.get("manifest_path", "")).strip() if isinstance(managed_result, dict) else ""
                    add_check(
                        checks["artifacts"],
                        "managed_manifest_path_matches_result",
                        "PASS" if manifest_ref == str(manifest_path) else "FAIL",
                        f"managed-change-result manifest_path={manifest_ref or '<missing>'}; expected={manifest_path}",
                        "outputs/managed-change-result.json",
                    )
                if text == ".workflowprogram/design/workflow-spec.yaml":
                    target_spec_path = target_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
                    target_spec = load_yaml(target_spec_path)
                    run_spec = load_yaml(run_root / "workflow-spec.yaml")
                    add_check(
                        checks["artifacts"],
                        "persistent_workflow_spec_valid",
                        "PASS" if target_spec else "FAIL",
                        f"Persistent workflow-spec.yaml {'parsed successfully' if target_spec else 'is missing or invalid'} at {target_spec_path}",
                        "TARGET_ROOT/.workflowprogram/design/workflow-spec.yaml",
                    )
                    if target_spec and run_spec:
                        add_check(
                            checks["artifacts"],
                            "persistent_workflow_spec_matches_run_spec",
                            "PASS" if target_spec == run_spec else "FAIL",
                            "Persistent workflow-spec.yaml should match RUN_ROOT/workflow-spec.yaml for this develop run.",
                            "TARGET_ROOT/.workflowprogram/design/workflow-spec.yaml",
                        )
                if text == ".workflowprogram/design/workflow-view.md":
                    target_view_path = target_root / ".workflowprogram" / "design" / "workflow-view.md"
                    view_exists = target_view_path.exists()
                    view_content = target_view_path.read_text(encoding="utf-8") if view_exists else ""
                    add_check(
                        checks["artifacts"],
                        "persistent_workflow_view_valid",
                        "PASS" if view_exists and "Generated at" in view_content and "workflow-spec.yaml" in view_content else "FAIL",
                        f"Persistent workflow-view.md {'exists and points back to workflow-spec.yaml' if view_exists else 'is missing'} at {target_view_path}",
                        "TARGET_ROOT/.workflowprogram/design/workflow-view.md",
                    )
                if text in {".workflowprogram/design/workflow-maintenance.md", ".workflowprogram/design/workflow-lowlevel.md"}:
                    target_spec_path = target_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
                    target_maintenance_path = target_root / ".workflowprogram" / "design" / Path(text).name
                    maintenance_validation = run_validator(
                        "validate-workflow-maintenance.py",
                        "--spec",
                        str(target_spec_path),
                        "--maintenance",
                        str(target_maintenance_path),
                    )
                    maintenance_errors = [str(item) for item in maintenance_validation.get("errors", [])]
                    maintenance_warnings = [str(item) for item in maintenance_validation.get("warnings", [])]
                    add_check(
                        checks["artifacts"],
                        "persistent_workflow_maintenance_valid",
                        "PASS" if not maintenance_errors else "FAIL",
                        "workflow-maintenance.md passed deterministic validation."
                        if not maintenance_errors
                        else "; ".join([*maintenance_errors, *maintenance_warnings[:3]]),
                        f"TARGET_ROOT/{text}",
                    )
        generated_runtime_contract = spec.get("generated_runtime_contract", {}) if isinstance(spec, dict) else {}
        runtime_root_rel = str(generated_runtime_contract.get("runtime_root", "")).strip() if isinstance(generated_runtime_contract, dict) else ""
        runtime_root_path = target_root / runtime_root_rel if runtime_root_rel else None
        should_validate_generated_runtime = (
            isinstance(generated_runtime_contract, dict)
            and bool(generated_runtime_contract)
            and (
                observed_intent_text == "develop"
                or (runtime_root_path is not None and runtime_root_path.exists())
            )
        )
        if should_validate_generated_runtime:
            target_spec_path = target_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
            runtime_validation = run_validator(
                "validate-generated-runtime.py",
                "--spec",
                str(target_spec_path),
                "--target-root",
                str(target_root),
            )
            runtime_errors = [str(item) for item in runtime_validation.get("errors", [])]
            runtime_warnings = [str(item) for item in runtime_validation.get("warnings", [])]
            add_check(
                checks["artifacts"],
                "persistent_generated_runtime_valid",
                "PASS" if not runtime_errors else "FAIL",
                "generated target runtime assets passed deterministic validation."
                if not runtime_errors
                else "; ".join([*runtime_errors, *runtime_warnings[:3]]),
                "TARGET_ROOT/.workflowprogram/runtime/",
            )
        if capability_discovery_enabled:
            discovery_report_path = run_root / "outputs" / "stages" / "host-capability-candidates.json"
            discovery_instructions_path = run_root / "outputs" / "stages" / "host-bootstrap-instructions.md"
            discovery_report = load_json(discovery_report_path)
            discovery_candidates = discovery_report.get("candidates", []) if isinstance(discovery_report.get("candidates"), list) else []
            discovery_profiles = discovery_report.get("profiles", []) if isinstance(discovery_report.get("profiles"), list) else []
            effective_domains = discovery_report.get("effective_domains", []) if isinstance(discovery_report.get("effective_domains"), list) else []
            instructions_text = discovery_instructions_path.read_text(encoding="utf-8") if discovery_instructions_path.exists() else ""
            unresolved_candidates = [
                item
                for item in discovery_candidates
                if isinstance(item, dict) and str(item.get("status", "")).strip() in {"missing", "recommended"}
            ]
            structured_guidance_errors = [
                str(item.get("id", "<unknown>")).strip() or "<unknown>"
                for item in unresolved_candidates
                if not isinstance(item.get("manual_steps"), list)
                or not item.get("manual_steps")
                or not isinstance(item.get("expected_outputs"), list)
                or not item.get("expected_outputs")
                or not str(item.get("recheck_hint", "")).strip()
            ]
            add_check(
                checks["artifacts"],
                "capability_discovery_report_present",
                "PASS" if discovery_report else "FAIL",
                f"capability discovery report path={discovery_report_path}; candidates={len(discovery_candidates)}; domains={effective_domains or ['<none>']}",
                "capability_discovery",
            )
            add_check(
                checks["artifacts"],
                "capability_discovery_instructions_present",
                "PASS" if discovery_instructions_path.exists() and "## Manual Follow-Up" in instructions_text else "FAIL",
                f"bootstrap instructions path={discovery_instructions_path}; present={discovery_instructions_path.exists()}",
                "capability_discovery",
            )
            add_check(
                checks["artifacts"],
                "capability_discovery_manual_guidance_structured",
                "PASS" if not structured_guidance_errors else "FAIL",
                f"unresolved candidates missing manual guidance={structured_guidance_errors or ['<none>']}",
                "capability_discovery",
            )
            add_check(
                checks["artifacts"],
                "capability_discovery_profiles_present",
                "PASS" if not effective_domains or discovery_profiles else "FAIL",
                f"profile domains={[str(item.get('domain', '')).strip() for item in discovery_profiles if isinstance(item, dict)] or ['<none>']}",
                "capability_discovery",
            )
            reverse_profiles = [
                item
                for item in discovery_profiles
                if isinstance(item, dict) and str(item.get("domain", "")).strip() == "reverse_engineering"
            ]
            reverse_team_missing = [
                "reverse_engineering"
                for item in reverse_profiles
                if bool(item.get("team_default_recommended", False)) and not isinstance(item.get("suggested_agent_team_contract"), dict)
            ]
            add_check(
                checks["artifacts"],
                "capability_discovery_team_defaults_present",
                "PASS" if not reverse_team_missing else "FAIL",
                f"profiles missing suggested team defaults={reverse_team_missing or ['<none>']}",
                "capability_discovery",
            )
            add_check(
                checks["artifacts"],
                "capability_discovery_candidates_status",
                "PASS" if discovery_candidates else "INFO",
                f"candidate ids={[str(item.get('id', '')).strip() for item in discovery_candidates if isinstance(item, dict)] or ['<none>']}",
                "capability_discovery",
            )
        if declared_host_capabilities:
            host_report_path = run_root / "outputs" / "stages" / "host-capability-report.json"
            if observed_intent_text in {"validate", "audit"}:
                target_spec_path = target_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
                spec_for_probe = target_spec_path if target_spec_path.exists() else (run_root / "workflow-spec.yaml")
                host_report = run_host_probe(spec_for_probe, target_root, run_root, "host-capability-probe.json")
                host_report_source = str(spec_for_probe)
            else:
                host_report = load_json(host_report_path)
                if not host_report:
                    host_report = run_host_probe(run_root / "workflow-spec.yaml", target_root, run_root, "host-capability-probe.json")
                    host_report_source = "probe-host-capabilities.py"
                else:
                    host_report_source = str(host_report_path)
            remediation_spec_path = spec_for_probe if observed_intent_text in {"validate", "audit"} else (run_root / "workflow-spec.yaml")
            remediation_report = run_environment_remediation(remediation_spec_path, target_root, run_root)
            environment_remediation_report = remediation_report if remediation_report else environment_remediation_report
            remediation_guide_path = run_root / "outputs" / "stages" / "environment-remediation-guide.md"
            host_items = host_report.get("capabilities", []) if isinstance(host_report.get("capabilities"), list) else []
            host_schema_errors = report_schema_errors(host_report, "host-capability-report")
            add_check(
                checks["artifacts"],
                "host_capability_report_present",
                "PASS" if host_items else "FAIL",
                f"host capability report source={host_report_source}; items={len(host_items)}",
                "host_capabilities",
            )
            add_check(
                checks["artifacts"],
                "host_capability_report_schema_fields",
                "PASS" if not host_schema_errors else "FAIL",
                "; ".join(host_schema_errors) or "host capability report has common report schema fields.",
                "outputs/stages/host-capability-report.json",
            )
            required_missing = [
                str(item.get("id", "")).strip()
                for item in host_items
                if isinstance(item, dict) and bool(item.get("required", False)) and str(item.get("status", "")).strip() != "ready"
            ]
            optional_missing = [
                str(item.get("id", "")).strip()
                for item in host_items
                if isinstance(item, dict) and not bool(item.get("required", False)) and str(item.get("status", "")).strip() != "ready"
            ]
            add_check(
                checks["artifacts"],
                "host_capability_required_ready",
                "PASS" if not required_missing else "FAIL",
                f"required missing={required_missing or ['<none>']}",
                "host_capabilities",
            )
            add_check(
                checks["artifacts"],
                "host_capability_optional_status",
                "PASS" if not optional_missing else "INFO",
                f"optional not-ready={optional_missing or ['<none>']}",
                "host_capabilities",
            )
            remediation_payload = remediation_report or environment_remediation_report
            remediation_schema_errors = report_schema_errors(remediation_payload, "environment-remediation-report") if remediation_payload else []
            user_followups = remediation_payload.get("user_followups", []) if isinstance(remediation_payload.get("user_followups"), list) else []
            repeated_missing = remediation_payload.get("repeated_missing_capabilities", []) if isinstance(remediation_payload.get("repeated_missing_capabilities"), list) else []
            if remediation_payload:
                add_check(
                    checks["artifacts"],
                    "environment_remediation_report_schema_fields",
                    "PASS" if not remediation_schema_errors else "FAIL",
                    "; ".join(remediation_schema_errors) or "environment remediation report has common report schema fields.",
                    "outputs/stages/environment-remediation-report.json",
                )
            prior_environment_run_count = int(remediation_payload.get("prior_environment_run_count", 0) or 0)
            add_check(
                checks["artifacts"],
                "host_capability_remediation_report_present",
                "PASS" if remediation_payload else "FAIL",
                f"remediation report present={bool(remediation_payload)}; prior_environment_run_count={prior_environment_run_count}",
                "environment_remediation",
            )
            guide_text = remediation_guide_path.read_text(encoding="utf-8") if remediation_guide_path.exists() else ""
            add_check(
                checks["artifacts"],
                "host_capability_remediation_guide_present",
                "PASS" if remediation_guide_path.exists() and "## Remediation Actions" in guide_text else "FAIL",
                f"guide path={remediation_guide_path}; present={remediation_guide_path.exists()}",
                "environment_remediation",
            )
            add_check(
                checks["artifacts"],
                "host_capability_manual_steps_visible",
                "PASS" if not required_missing or user_followups else "FAIL",
                f"user followups={[str(item.get('capability_id', '')).strip() for item in user_followups if isinstance(item, dict)] or ['<none>']}",
                "environment_remediation",
            )
            if observed_intent_text == "iterate":
                repeated_status = "PASS" if repeated_missing else ("INFO" if prior_environment_run_count == 0 else "FAIL")
                add_check(
                    checks["artifacts"],
                    "host_capability_repeated_failures_promoted",
                    repeated_status,
                    f"repeated blockers={[str(item.get('capability_id', '')).strip() for item in repeated_missing if isinstance(item, dict)] or ['<none>']}; prior_environment_run_count={prior_environment_run_count}",
                    "environment_remediation",
                )
            project_local_items = [
                item for item in host_items if isinstance(item, dict) and str(item.get("bootstrap_scope", "")).strip() == "project_local"
            ]
            if project_local_items:
                apply_payload = load_json(run_root / "outputs" / "stages" / "host-bootstrap-apply.json")
                bootstrap_manifest_path = target_root / ".workflowprogram" / "bootstrap" / "bootstrap-assets-manifest.json"
                apply_entries = apply_payload.get("applied", []) if isinstance(apply_payload.get("applied"), list) else []
                add_check(
                    checks["artifacts"],
                    "host_bootstrap_apply_recorded",
                    "PASS" if apply_payload or bootstrap_manifest_path.exists() else "FAIL",
                    f"apply_payload={bool(apply_payload)}; bootstrap_manifest={bootstrap_manifest_path.exists()}",
                    "host_capabilities.bootstrap",
                )
                add_check(
                    checks["artifacts"],
                    "host_bootstrap_manifest_present",
                    "PASS" if bootstrap_manifest_path.exists() else "FAIL",
                    f"bootstrap manifest path={bootstrap_manifest_path}; present={bootstrap_manifest_path.exists()}",
                    "host_capabilities.bootstrap",
                )
                expected_outputs = [
                    output
                    for item in project_local_items
                    for output in item.get("project_local_outputs", [])
                    if isinstance(output, str) and output.strip()
                ]
                missing_outputs = [rel for rel in expected_outputs if not (target_root / rel).exists()]
                add_check(
                    checks["artifacts"],
                    "host_bootstrap_outputs_present",
                    "PASS" if not missing_outputs else "FAIL",
                    f"missing outputs={missing_outputs or ['<none>']}",
                    "host_capabilities.bootstrap.project_local_outputs",
                )
                failed_rechecks = [
                    str(entry.get("capability_id", "")).strip()
                    for entry in apply_entries
                    if isinstance(entry, dict) and entry.get("ready_after_apply") is False
                ]
                add_check(
                    checks["artifacts"],
                    "host_bootstrap_recheck_ready",
                    "PASS" if not failed_rechecks else "FAIL",
                    f"failed rechecks={failed_rechecks or ['<none>']}",
                    "host_capabilities.bootstrap",
                )
            host_global_items = [
                item for item in host_items if isinstance(item, dict) and str(item.get("bootstrap_scope", "")).strip() == "host_global"
            ]
            if host_global_items:
                execution_payload = load_json(run_root / "outputs" / "stages" / "host-bootstrap-execution.json")
                attempts = execution_payload.get("attempts", []) if isinstance(execution_payload.get("attempts"), list) else []
                attempted_ids = [str(item.get("capability_id", "")).strip() for item in attempts if isinstance(item, dict)]
                succeeded_ids = [
                    str(item.get("capability_id", "")).strip()
                    for item in attempts
                    if isinstance(item, dict) and str(item.get("status", "")).strip() == "succeeded"
                ]
                add_check(
                    checks["artifacts"],
                    "host_global_bootstrap_execution_recorded",
                    "PASS" if not attempts or execution_payload else "FAIL",
                    f"host_global declared={len(host_global_items)}; attempted={attempted_ids or ['<none>']}",
                    "host_capabilities.bootstrap.adapter",
                )
                add_check(
                    checks["artifacts"],
                    "host_global_bootstrap_attempt_status",
                    "PASS" if not attempts or succeeded_ids else "FAIL",
                    f"succeeded host-global attempts={succeeded_ids or ['<none>']}",
                    "host_capabilities.bootstrap.adapter",
                )
        if team_enabled:
            team_plan = load_json(run_root / "outputs" / "stages" / "team-plan.json")
            team_results = load_json(run_root / "outputs" / "stages" / "team-results.json")
            team_join = load_json(run_root / "outputs" / "stages" / "team-join-summary.json")
            structured_evidence = bool(team_plan) and bool(team_results) and bool(team_join)
            deterministic_provider = provider_name in {"fixture_host", "command_adapter"}
            expected_events_present = TEAM_EVENT_TYPES.issubset(set(event_types))
            evidence_status = "PASS" if structured_evidence and expected_events_present else ("FAIL" if deterministic_provider else "WARN")
            add_check(
                checks["flow"],
                "team_evidence_present",
                evidence_status,
                f"provider={provider_name or '<unknown>'}; structured={structured_evidence}; events={sorted(TEAM_EVENT_TYPES & set(event_types))}",
                "agent_team_contract",
            )
            max_fan_out = int(declared_agent_team.get("max_fan_out", 0) or 0)
            observed_fan_out = int(team_plan.get("fan_out_count", 0) or 0) if team_plan else 0
            add_check(
                checks["flow"],
                "team_fan_out_within_limit",
                "PASS" if not observed_fan_out or observed_fan_out <= max_fan_out else "FAIL",
                f"observed_fan_out={observed_fan_out or 0}; max_fan_out={max_fan_out or 0}",
                "agent_team_contract.max_fan_out",
            )
            join_policy = str(declared_agent_team.get("join_policy", "")).strip()
            join_satisfied = bool(team_join.get("satisfied", False)) if team_join else False
            join_status = "PASS" if (not team_join or join_satisfied) else "FAIL"
            if team_join:
                add_check(
                    checks["flow"],
                    "team_join_policy_satisfied",
                    join_status,
                    f"join_policy={join_policy or '<missing>'}; satisfied={join_satisfied}",
                    "agent_team_contract.join_policy",
                )
        if loop_nodes:
            deterministic_provider = provider_name in {"fixture_host", "command_adapter"}
            expected_loop_events_present = LOOP_EVENT_TYPES.issubset(set(event_types))
            for node in loop_nodes:
                node_id = str(node.get("id", "")).strip()
                loop_policy = node.get("loop_policy", {}) if isinstance(node.get("loop_policy"), dict) else {}
                loop_root = run_root / "outputs" / "stages" / "loops" / node_id
                loop_plan = load_json(loop_root / "loop-plan.json")
                final_verdict = load_json(loop_root / "final-verdict.json")
                iteration_entries = load_jsonl(loop_root / "iteration-summary.jsonl")
                structured_evidence = bool(loop_plan) and bool(final_verdict) and bool(iteration_entries)
                evidence_status = "PASS" if structured_evidence and expected_loop_events_present else ("FAIL" if deterministic_provider else "WARN")
                add_check(
                    checks["flow"],
                    "node_loop_evidence_present",
                    evidence_status,
                    (
                        f"node={node_id}; provider={provider_name or '<unknown>'}; structured={structured_evidence}; "
                        f"events={sorted(LOOP_EVENT_TYPES & set(event_types))}"
                    ),
                    f"workflow_graph.nodes.{node_id}.loop_policy",
                )

                max_iterations = int(loop_policy.get("max_iterations", 0) or 0)
                observed_iterations = len(iteration_entries)
                add_check(
                    checks["flow"],
                    "node_loop_iteration_limit_observed",
                    "PASS" if not observed_iterations or not max_iterations or observed_iterations <= max_iterations else "FAIL",
                    f"node={node_id}; observed_iterations={observed_iterations}; max_iterations={max_iterations}",
                    f"workflow_graph.nodes.{node_id}.loop_policy.max_iterations",
                )

                final_status = str(final_verdict.get("status", "")).strip().upper() if final_verdict else ""
                verifier_passed = bool(final_verdict.get("verifier_passed", False)) if final_verdict else False
                if final_verdict:
                    add_check(
                        checks["flow"],
                        "node_loop_verifier_gate_observed",
                        "PASS" if final_status != "PASS" or verifier_passed else "FAIL",
                        f"node={node_id}; final_status={final_status or '<missing>'}; verifier_passed={verifier_passed}",
                        f"outputs/stages/loops/{node_id}/final-verdict.json",
                    )
                    stop_reason = str(final_verdict.get("stop_reason", "")).strip()
                    add_check(
                        checks["flow"],
                        "node_loop_stop_reason_valid",
                        "PASS" if stop_reason else "FAIL",
                        f"node={node_id}; stop_reason={stop_reason or '<missing>'}",
                        f"outputs/stages/loops/{node_id}/final-verdict.json",
                    )

                if str(loop_policy.get("goal_source", "user")).strip() == "model_subgoal":
                    plan_parent_goal = str(loop_plan.get("parent_goal_ref", "")).strip() if loop_plan else ""
                    add_check(
                        checks["flow"],
                        "node_loop_model_subgoal_trace_present",
                        "PASS" if plan_parent_goal else ("FAIL" if deterministic_provider else "WARN"),
                        f"node={node_id}; parent_goal_ref={plan_parent_goal or '<missing>'}",
                        f"workflow_graph.nodes.{node_id}.loop_policy.parent_goal_ref",
                    )

                tdd_policy = loop_policy.get("tdd_policy", {}) if isinstance(loop_policy.get("tdd_policy"), dict) else {}
                if tdd_policy.get("enabled") is True and tdd_policy.get("test_first_required") is True:
                    test_first_observed = bool(loop_plan.get("test_first_observed", False)) if loop_plan else False
                    add_check(
                        checks["flow"],
                        "node_loop_tdd_trace_observed",
                        "PASS" if test_first_observed else ("FAIL" if deterministic_provider else "WARN"),
                        f"node={node_id}; test_first_observed={test_first_observed}",
                        f"workflow_graph.nodes.{node_id}.loop_policy.tdd_policy",
                    )
    elif "artifacts" in contract.get("contract_categories", []):
        add_check(checks["artifacts"], "contract_source_fallback", "INFO", "Artifact checks derived from fixture preset.", "fixture_preset")

    # failure 检查会把观测到的失败回连到 declared implemented_now
    # 覆盖范围以及 environment skip 引用。
    failure = test_contract.get("failure", {}) if isinstance(test_contract.get("failure"), dict) else {}
    implemented_now = contract.get("implemented_failure_kinds", [])
    add_check(
        checks["failure"],
        "derived_failure_kind",
        "PASS" if derived_failure_kind in {"none", "design", "implementation", "environment", "conflict"} else "FAIL",
        f"Derived failure_kind={derived_failure_kind}; raw failure_code={failure_code or 'none'}",
        "judge.mapping",
    )
    if result == "ENVIRONMENT-SKIP":
        add_check(
            checks["failure"],
            "environment_skip_reason",
            "PASS",
            summary_message,
            "runtime_contract.environment_skip",
        )
    if failure:
        if implemented_now:
            status = "PASS" if derived_failure_kind in implemented_now else "WARN"
            add_check(
                checks["failure"],
                "implemented_now_coverage",
                status,
                f"implemented_now={implemented_now}; observed={derived_failure_kind}",
                "test_contract.failure.implemented_now",
            )
        failure_ref = str(failure.get("failure_kinds_ref", "")).strip()
        if failure_ref:
            add_check(
                checks["failure"],
                "failure_kinds_reference",
                "PASS" if failure_ref == "runtime_contract.failure_kinds" else "FAIL",
                f"failure_kinds_ref={failure_ref}",
                "test_contract.failure.failure_kinds_ref",
            )
        env_ref = str(failure.get("environment_skip_ref", "")).strip()
        if env_ref:
            add_check(
                checks["failure"],
                "environment_skip_reference",
                "PASS" if env_ref == "runtime_contract.environment_skip" else "FAIL",
                f"environment_skip_ref={env_ref}",
                "test_contract.failure.environment_skip_ref",
            )
        if result == "ENVIRONMENT-SKIP":
            declared_codes = contract.get("environment_skip_codes", [])
            if isinstance(declared_codes, list):
                add_check(
                    checks["failure"],
                    "environment_skip_code_declared",
                    "PASS" if failure_code in declared_codes else "FAIL",
                    f"Observed environment failure_code={failure_code or 'none'}; declared_codes={declared_codes or ['<none>']}",
                    "runtime_contract.environment_skip",
                )
    elif "failure" in contract.get("contract_categories", []):
        add_check(checks["failure"], "contract_source_fallback", "INFO", "Failure checks derived from fixture preset.", "fixture_preset")

    return checks


def compute_final_judgment(
    observed_result: str,
    observed_failure_code: str,
    checks: Dict[str, List[Dict[str, str]]],
) -> Dict[str, Any]:
    """把检查矩阵收敛为最终 S5 verdict。

    如果 judge 发现 contract 层面的失败，它会覆盖原始观测结果，
    因为产品契约比 provider 的局部判断更严格。
    """

    first_fail = find_first_status(checks, {"FAIL"})
    first_warn = find_first_status(checks, {"WARN"})

    if first_fail is not None:
        category = str(first_fail["category"])
        name = str(first_fail["name"])
        return {
            "verdict": "FAIL",
            "failure_kind": failure_kind_for_check(category, name),
            "failure_code": failure_code_for_check(category, name),
            "judge_basis": first_fail,
        }

    if observed_result == "FAIL":
        return {
            "verdict": "FAIL",
            "failure_kind": failure_kind_for_result(observed_result, observed_failure_code),
            "failure_code": observed_failure_code or "none",
            "judge_basis": None,
        }

    if observed_result == "ENVIRONMENT-SKIP":
        return {
            "verdict": "ENVIRONMENT-SKIP",
            "failure_kind": "environment",
            "failure_code": observed_failure_code or "none",
            "judge_basis": None,
        }

    if first_warn is not None or observed_result == "WARN":
        basis = first_warn
        failure_kind = failure_kind_for_check(str(basis["category"]), str(basis["name"])) if basis else "implementation"
        failure_code = failure_code_for_check(str(basis["category"]), str(basis["name"])) if basis else (observed_failure_code or "none")
        return {
            "verdict": "WARN",
            "failure_kind": failure_kind,
            "failure_code": failure_code,
            "judge_basis": basis,
        }

    return {
        "verdict": "PASS",
        "failure_kind": "none",
        "failure_code": "none",
        "judge_basis": None,
    }


def render_summary(
    summary_message: str,
    observed_result: str,
    observed_failure_code: str,
    final_result: str,
    final_failure_code: str,
    judge_basis: Optional[Dict[str, Any]],
) -> str:
    """渲染摘要区块，并在需要时带上 judge override 说明。"""

    summary = summary_message.strip() or "No runtime summary was provided."
    observed_code = observed_failure_code or "none"
    final_code = final_failure_code or "none"
    if observed_result == final_result and observed_code == final_code:
        return summary
    override = f"Judge override: observed `{observed_result}` / `{observed_code}`, final `{final_result}` / `{final_code}`."
    if judge_basis:
        override += (
            f" Triggered by `{judge_basis.get('category', 'unknown')}.{judge_basis.get('name', 'unknown')}`: "
            f"{judge_basis.get('detail', 'no detail')}"
        )
    return f"{summary}\n\n{override}"


def render_report(
    run_root: Path,
    target_root: Path,
    fixture: str,
    entry_skill: str,
    observed_result: str,
    observed_failure_kind: str,
    observed_failure_code: str,
    final_result: str,
    final_failure_kind: str,
    final_failure_code: str,
    summary_message: str,
    judge_basis: Optional[Dict[str, Any]],
    contract: Dict[str, Any],
    checks: Dict[str, List[Dict[str, str]]],
) -> str:
    """渲染人类可读的 validation-runtime-report.md 文档。"""

    summary_block = render_summary(
        summary_message,
        observed_result,
        observed_failure_code,
        final_result,
        final_failure_code,
        judge_basis,
    )
    lines = [
        "# Runtime Validation Report",
        "",
        f"- Run root: `{run_root}`",
        f"- Target root: `{target_root}`",
        f"- Fixture: `{fixture}`",
        f"- Entry skill: `{entry_skill}`",
        f"- Observed result: `{observed_result}`",
        f"- Observed failure kind: `{observed_failure_kind}`",
        f"- Observed failure code: `{observed_failure_code or 'none'}`",
        f"- Final verdict: `{final_result}`",
        f"- Final failure kind: `{final_failure_kind}`",
        f"- Final failure code: `{final_failure_code or 'none'}`",
        f"- Contract source: `{contract.get('contract_source', 'unknown')}`",
        f"- Contract categories: `{', '.join(contract.get('contract_categories', [])) or 'none'}`",
        "",
        "## Summary",
        "",
        summary_block,
        "",
    ]
    if contract.get("spec_path"):
        lines.extend(
            [
                "## Spec Source",
                "",
                f"- `{contract['spec_path']}`",
                "",
            ]
        )

    for category in CATEGORY_ORDER:
        lines.extend([f"## {category.title()} Checks", ""])
        bucket = checks.get(category, [])
        if not bucket:
            lines.append("- No checks were derived for this category.")
            lines.append("")
            continue
        for item in bucket:
            lines.append(
                f"- [{item['status']}] `{item['name']}`: {item['detail']} (source: `{item['source']}`)"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    """解析独立执行 S5 judgment 所需的命令行参数。"""

    parser = argparse.ArgumentParser(description="Write S5 validation outputs from RUN_ROOT evidence")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--result", required=True, choices=sorted(RESULTS))
    parser.add_argument("--failure-code", default="")
    parser.add_argument("--summary-message", default="")
    parser.add_argument("--entry-skill", default="")
    parser.add_argument("--request", default="")
    parser.add_argument("--fixture", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--fallback-contract-categories", default="")
    parser.add_argument("--checked-file", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    """运行确定性的 S5 judgment，并同时产出报告和 JSON 摘要。"""

    args = parse_args()
    run_root = Path(args.run_root).resolve()
    target_root = Path(args.target_root).resolve()
    fallback_categories = [item.strip() for item in args.fallback_contract_categories.split(",") if item.strip()]
    contract = derive_contract(run_root, fallback_categories)
    checks = build_checks(
        run_root,
        target_root,
        args.result,
        args.failure_code.strip(),
        args.summary_message.strip(),
        args.entry_skill.strip(),
        args.request,
        args.checked_file,
        contract,
        args.provider.strip(),
    )
    observed_failure_kind = failure_kind_for_result(args.result, args.failure_code.strip())
    final_judgment = compute_final_judgment(args.result, args.failure_code.strip(), checks)
    summary_path = run_root / "outputs" / "stages" / "s5-validation-summary.json"
    report_path = run_root / "validation-runtime-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    report_text = render_report(
        run_root,
        target_root,
        args.fixture.strip(),
        args.entry_skill.strip(),
        args.result,
        observed_failure_kind,
        args.failure_code.strip(),
        str(final_judgment["verdict"]),
        str(final_judgment["failure_kind"]),
        str(final_judgment["failure_code"]),
        args.summary_message.strip(),
        final_judgment.get("judge_basis"),
        contract,
        checks,
    )
    report_path.write_text(report_text, encoding="utf-8", newline="\n")

    payload = {
        "verdict": final_judgment["verdict"],
        "failure_kind": final_judgment["failure_kind"],
        "failure_code": final_judgment["failure_code"],
        "observed_verdict": args.result,
        "observed_failure_kind": observed_failure_kind,
        "observed_failure_code": args.failure_code.strip() or "none",
        "environment_reason": args.summary_message.strip() if args.result == "ENVIRONMENT-SKIP" else None,
        "contract_source": contract.get("contract_source"),
        "contract_categories": contract.get("contract_categories", []),
        "implemented_failure_kinds": contract.get("implemented_failure_kinds", []),
        "environment_skip_codes": contract.get("environment_skip_codes", []),
        "provider": args.provider.strip() or None,
        "checked_files": sorted({*args.checked_file, *SELF_GENERATED_FILES}),
        "checks_by_category": checks,
        "judge_basis": final_judgment.get("judge_basis"),
        "summary": args.summary_message.strip(),
        "report_path": str(report_path),
    }
    payload = with_report_fields(
        payload,
        schema_name="s5-validation-summary",
        error_code=None if str(final_judgment["failure_code"]) == "none" else str(final_judgment["failure_code"]),
        failure_kind=str(final_judgment["failure_kind"]),
        remediation=[],
    )
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['verdict']}] wrote {report_path} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
