from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set


PLACEHOLDER_RE = re.compile(r"\bTBD\b|待补", re.IGNORECASE)
NO_VALUE_RE = re.compile(r"^(无|none|n/?a|not applicable|已清空|无阻塞|无阻塞问题|无新增|无修正)$", re.IGNORECASE)
CONFIRMED_STATUS_RE = re.compile(r"^(confirmed|corrected-confirmed|已确认|修正后确认)$", re.IGNORECASE)

REQUIRED_SECTIONS: Dict[str, List[str]] = {
    "User Intent": ["用户诉求", "最终目的", "成功标准"],
    "Clarification Summary": ["澄清轮次", "已确认事项", "已消解歧义"],
    "Requirement Logic Interview": [
        "复杂度",
        "Purpose Lens",
        "Object Lens",
        "Process Lens",
        "Decision Lens",
        "Evidence Lens",
        "Acceptance Lens",
        "Boundary Lens",
        "关键追问",
        "候选节点",
        "负向/停止场景",
    ],
    "Trigger Model": ["调用方式", "触发细节"],
    "Inputs": ["必需输入", "可选输入", "所需外部上下文"],
    "Outputs": ["主交付物", "次级产物", "输出格式"],
    "Quality Gates": ["阻塞条件", "必需验证", "完成定义"],
    "Open Questions": ["阻塞未决问题", "可延后问题", "问题处理策略"],
    "Assumptions and Boundaries": ["当前假设", "外部依赖", "关键边界场景", "明确不做"],
    "Target Workflow Graph Readback": ["目标 workflow_graph 节点", "目标 workflow_graph 入口与转移", "目标输出是否已映射到 `registry` 或 `test_contract.artifacts`"],
    "File Plan": ["需要创建的文件", "需要修改的文件"],
    "Readback Confirmation": ["回读摘要", "用户确认状态", "最近修正"],
}

CHALLENGE_ROLE_SPECS: List[Dict[str, str]] = [
    {
        "id": "scenario-extractor",
        "focus": "Identify missing scenarios, edge cases, and workflow output expectations.",
    },
    {
        "id": "assumption-auditor",
        "focus": "Challenge hidden assumptions, dependency gaps, and unclear non-goals.",
    },
    {
        "id": "constraint-reviewer",
        "focus": "Challenge quality gates, stop conditions, and definition-of-done gaps.",
    },
]

COMPLEXITY_ORDER = {"S": 1, "M": 2, "L": 3, "XL": 4}
LOGIC_LENSES: List[Dict[str, str]] = [
    {
        "key": "purpose",
        "draft_key": "lens_purpose",
        "title": "Purpose Lens",
        "task": "Convert the request from desired artifact into observable purpose and success signal.",
        "question": "What decision or action should become easier after this workflow runs?",
    },
    {
        "key": "object_model",
        "draft_key": "lens_object_model",
        "title": "Object Lens",
        "task": "Identify input, intermediate, and output objects plus source-of-truth rules.",
        "question": "What intermediate object must exist before the workflow can make the next decision?",
    },
    {
        "key": "process_model",
        "draft_key": "lens_process_model",
        "title": "Process Lens",
        "task": "Decompose the work into meaningful target workflow steps or node candidates.",
        "question": "Before the next major step starts, what must already be known or produced?",
    },
    {
        "key": "decision_model",
        "draft_key": "lens_decision_model",
        "title": "Decision Lens",
        "task": "Expose branching choices, decision inputs, fallbacks, confidence, and owners.",
        "question": "How should the workflow choose between plausible strategies or next actions?",
    },
    {
        "key": "evidence_model",
        "draft_key": "lens_evidence_model",
        "title": "Evidence Lens",
        "task": "Define evidence required to trust outputs, decisions, and intermediate models.",
        "question": "What evidence should a reviewer see before trusting this output?",
    },
    {
        "key": "acceptance_model",
        "draft_key": "lens_acceptance_model",
        "title": "Acceptance Lens",
        "task": "Turn clarified logic into concrete scenarios and expected outputs.",
        "question": "Give one example input where the workflow should pass and one where it should stop.",
    },
    {
        "key": "boundary_model",
        "draft_key": "lens_boundary_model",
        "title": "Boundary Lens",
        "task": "Define non-goals, stop conditions, manual confirmations, and degradation rules.",
        "question": "What must the workflow never modify or infer automatically?",
    },
]
LOGIC_LENS_KEYS = [lens["key"] for lens in LOGIC_LENSES]
CORE_LOGIC_LENS_KEYS = {"purpose", "object_model", "acceptance_model", "boundary_model"}
GENERIC_QUESTION_RE = re.compile(
    r"(边界场景|输入输出|约束|需求|还有什么|还有哪些|是否还有|"
    r"edge cases|inputs? and outputs?|constraints?|anything else)",
    re.IGNORECASE,
)
DESIGN_CONSEQUENCE_RE = re.compile(
    r"(节点|步骤|对象|证据|验收|停止|阻塞|分支|选择|策略|置信|失败|通过|"
    r"DFD|数据流|威胁|测试|工具|MCP|skill|CLI|node|evidence|acceptance|stop|branch|decision)",
    re.IGNORECASE,
)


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def extract_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current = ""
    buffer: List[str] = []
    for line in text.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = match.group(1).strip()
            buffer = []
            continue
        if current:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    return sections


def section_value(section_text: str, label: str) -> str:
    pattern = re.compile(rf"^- {re.escape(label)}[：:]\s*(.*)$", re.MULTILINE)
    match = pattern.search(section_text)
    if not match:
        return ""
    return match.group(1).strip()


def is_no_value(value: str) -> bool:
    return not value.strip() or bool(NO_VALUE_RE.match(value.strip()))


def split_items(value: str) -> List[str]:
    stripped = value.strip()
    if is_no_value(stripped):
        return []

    items: List[str] = []
    for line in stripped.splitlines():
        line = re.sub(r"^\s*-\s*", "", line).strip()
        if not line:
            continue
        for part in re.split(r"[；;]+", line):
            candidate = part.strip()
            if candidate and not is_no_value(candidate):
                items.append(candidate)
    if not items and stripped:
        items.append(stripped)
    return items


def normalize_complexity(value: Any) -> str:
    """把 S1 草案复杂度归一化为 S/M/L/XL，缺省按 M 处理。"""

    text = str(value or "").strip().upper()
    if text in COMPLEXITY_ORDER:
        return text
    if "XL" in text:
        return "XL"
    if "L" in text or "复杂" in text:
        return "L"
    if "S" in text or "简单" in text:
        return "S"
    return "M"


def complexity_rank(value: Any) -> int:
    return COMPLEXITY_ORDER.get(normalize_complexity(value), 2)


def required_lens_keys_for_complexity(complexity: str) -> Set[str]:
    if normalize_complexity(complexity) == "S":
        return set(CORE_LOGIC_LENS_KEYS)
    return set(LOGIC_LENS_KEYS)


def is_design_consequential_question(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if DESIGN_CONSEQUENCE_RE.search(stripped):
        return True
    if GENERIC_QUESTION_RE.search(stripped):
        return False
    return len(stripped) >= 18


def infer_lens_for_question(text: str) -> str:
    lowered = str(text or "").lower()
    keyword_map = [
        ("evidence_model", ("证据", "trust", "evidence", "可信", "reviewer")),
        ("acceptance_model", ("验收", "测试", "acceptance", "pass", "fail", "通过", "失败")),
        ("decision_model", ("选择", "决策", "分支", "策略", "confidence", "置信", "decision")),
        ("process_model", ("节点", "步骤", "顺序", "node", "step", "workflow_graph")),
        ("object_model", ("对象", "模型", "dfd", "数据流", "artifact", "object")),
        ("boundary_model", ("停止", "阻塞", "边界", "不做", "never", "stop", "manual")),
        ("purpose", ("目的", "价值", "结果", "goal", "outcome", "useful")),
    ]
    for lens_key, keywords in keyword_map:
        if any(keyword in lowered for keyword in keywords):
            return lens_key
    return "purpose"


def lens_label_map() -> Dict[str, str]:
    return {lens["key"]: lens["title"] for lens in LOGIC_LENSES}


def parse_rounds(value: str) -> int | None:
    try:
        return int(value.strip())
    except Exception:
        return None


def draft_data_from_text(text: str) -> Dict[str, Any]:
    sections = extract_sections(text)

    def field(section: str, label: str) -> str:
        return section_value(sections.get(section, ""), label)

    rounds = parse_rounds(field("Clarification Summary", "澄清轮次"))
    blocking_questions = split_items(field("Open Questions", "阻塞未决问题"))
    deferred_questions = split_items(field("Open Questions", "可延后问题"))
    edge_cases = split_items(field("Assumptions and Boundaries", "关键边界场景"))
    assumptions = split_items(field("Assumptions and Boundaries", "当前假设"))
    external_dependencies = split_items(field("Assumptions and Boundaries", "外部依赖"))
    non_goals = split_items(field("Assumptions and Boundaries", "明确不做"))
    complexity = normalize_complexity(field("Requirement Logic Interview", "复杂度"))

    return {
        "sections": sections,
        "workflow_name": field("Workflow Identity", "工作流名称"),
        "trigger_command": field("Workflow Identity", "触发命令"),
        "workflow_summary": field("Workflow Identity", "简要描述"),
        "user_goal": field("User Intent", "用户诉求"),
        "business_purpose": field("User Intent", "最终目的"),
        "success_criteria": split_items(field("User Intent", "成功标准")),
        "clarification_rounds": rounds,
        "confirmed_decisions": split_items(field("Clarification Summary", "已确认事项")),
        "resolved_ambiguities": split_items(field("Clarification Summary", "已消解歧义")),
        "complexity": complexity,
        "lens_purpose": split_items(field("Requirement Logic Interview", "Purpose Lens")),
        "lens_object_model": split_items(field("Requirement Logic Interview", "Object Lens")),
        "lens_process_model": split_items(field("Requirement Logic Interview", "Process Lens")),
        "lens_decision_model": split_items(field("Requirement Logic Interview", "Decision Lens")),
        "lens_evidence_model": split_items(field("Requirement Logic Interview", "Evidence Lens")),
        "lens_acceptance_model": split_items(field("Requirement Logic Interview", "Acceptance Lens")),
        "lens_boundary_model": split_items(field("Requirement Logic Interview", "Boundary Lens")),
        "logic_questions": split_items(field("Requirement Logic Interview", "关键追问")),
        "workflow_node_candidates": split_items(field("Requirement Logic Interview", "候选节点")),
        "negative_or_stop_scenarios": split_items(field("Requirement Logic Interview", "负向/停止场景")),
        "trigger_mode": field("Trigger Model", "调用方式"),
        "trigger_details": field("Trigger Model", "触发细节"),
        "primary_inputs": split_items(field("Inputs", "必需输入")),
        "optional_inputs": split_items(field("Inputs", "可选输入")),
        "external_context": split_items(field("Inputs", "所需外部上下文")),
        "primary_outputs": split_items(field("Outputs", "主交付物")),
        "secondary_outputs": split_items(field("Outputs", "次级产物")),
        "output_formats": split_items(field("Outputs", "输出格式")),
        "blocking_conditions": split_items(field("Quality Gates", "阻塞条件")),
        "required_validations": split_items(field("Quality Gates", "必需验证")),
        "definition_of_done": split_items(field("Quality Gates", "完成定义")),
        "blocking_questions": blocking_questions,
        "deferred_questions": deferred_questions,
        "question_resolution_strategy": field("Open Questions", "问题处理策略"),
        "assumptions": assumptions,
        "external_dependencies": external_dependencies,
        "edge_cases": edge_cases,
        "non_goals": non_goals,
        "readback_summary": field("Readback Confirmation", "回读摘要"),
        "readback_confirmation_status": field("Readback Confirmation", "用户确认状态"),
        "readback_corrections": split_items(field("Readback Confirmation", "最近修正")),
    }


def logic_gaps_from_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    complexity = normalize_complexity(data.get("complexity"))
    required_lenses = required_lens_keys_for_complexity(complexity)
    gaps: List[Dict[str, Any]] = []
    for lens in LOGIC_LENSES:
        key = lens["key"]
        items = data.get(lens["draft_key"], [])
        if key in required_lenses and not items:
            gaps.append(
                {
                    "lens": key,
                    "severity": "blocking",
                    "message": f"{lens['title']} has no captured design logic for complexity {complexity}.",
                    "suggested_question": lens["question"],
                }
            )

    if complexity_rank(complexity) >= 3:
        logic_questions = data.get("logic_questions", [])
        if not any(is_design_consequential_question(question) for question in logic_questions):
            gaps.append(
                {
                    "lens": "decision_model",
                    "severity": "blocking",
                    "message": f"Complexity {complexity} requires at least one design-consequential follow-up question.",
                    "suggested_question": "Which answer would change workflow nodes, evidence, acceptance, or stop behavior?",
                }
            )

    if complexity == "XL":
        if not data.get("workflow_node_candidates"):
            gaps.append(
                {
                    "lens": "process_model",
                    "severity": "blocking",
                    "message": "XL requests must identify candidate target workflow nodes before readback.",
                    "suggested_question": "Which target workflow nodes are needed, and which node is complex enough for node-design detail?",
                }
            )
        if not data.get("negative_or_stop_scenarios"):
            gaps.append(
                {
                    "lens": "boundary_model",
                    "severity": "blocking",
                    "message": "XL requests must include negative or stop scenarios before readback.",
                    "suggested_question": "Give one input where the workflow must stop instead of guessing.",
                }
            )
    return gaps


def question_backlog_from_data(data: Dict[str, Any], readiness: Dict[str, Any]) -> Dict[str, Any]:
    questions = data.get("logic_questions", [])
    gaps = logic_gaps_from_data(data)
    gap_lenses = {str(gap.get("lens", "")) for gap in gaps}
    records: List[Dict[str, Any]] = []

    for idx, question in enumerate(questions, start=1):
        lens_key = infer_lens_for_question(question)
        records.append(
            {
                "id": f"Q-{idx:03d}",
                "lens": lens_key,
                "question": question,
                "why_it_matters": "Different answers can alter workflow nodes, decisions, evidence, acceptance tests, or boundaries.",
                "blocking": lens_key in gap_lenses,
                "expected_answer_shape": "Concrete object/process/decision/evidence/acceptance/boundary rule, not a generic preference.",
                "linked_requirement_ids": ["REQ-001"],
                "design_consequence": is_design_consequential_question(question),
                "source": "draft",
                "status": "resolved" if readiness.get("ready") else "open",
            }
        )

    for gap in gaps:
        question = str(gap.get("suggested_question", "")).strip()
        if not question or any(item.get("question") == question for item in records):
            continue
        records.append(
            {
                "id": f"Q-{len(records) + 1:03d}",
                "lens": str(gap.get("lens", "")),
                "question": question,
                "why_it_matters": str(gap.get("message", "")),
                "blocking": True,
                "expected_answer_shape": "Specific design fact that clears the blocking lens gap.",
                "linked_requirement_ids": ["REQ-001"],
                "design_consequence": True,
                "source": "gap_suggestion",
                "status": "open",
            }
        )

    return {
        "schema_version": 1,
        "complexity": normalize_complexity(data.get("complexity")),
        "lead_role": "requirement-clarification-lead",
        "questions": records,
        "selected_next_question_id": next((item["id"] for item in records if item.get("status") == "open"), None),
        "blocking_count": len([item for item in records if item.get("blocking")]),
        "design_consequential_count": len(
            [
                item
                for item in records
                if item.get("source") == "draft" and item.get("design_consequence")
            ]
        ),
    }


def _element_records(prefix: str, items: List[str]) -> List[Dict[str, str]]:
    return [
        {"id": f"{prefix}-{idx:03d}", "summary": item}
        for idx, item in enumerate(items, start=1)
    ]


def requirement_logic_map_from_data(data: Dict[str, Any], readiness: Dict[str, Any]) -> Dict[str, Any]:
    complexity = normalize_complexity(data.get("complexity"))
    labels = lens_label_map()
    gaps = logic_gaps_from_data(data)
    gap_lens_keys = {str(gap.get("lens", "")) for gap in gaps}
    lenses: Dict[str, Dict[str, Any]] = {}
    for lens in LOGIC_LENSES:
        key = lens["key"]
        items = data.get(lens["draft_key"], [])
        required = key in required_lens_keys_for_complexity(complexity)
        if items:
            status = "complete"
        elif required:
            status = "blocking"
        else:
            status = "deferred"
        lenses[key] = {
            "title": labels[key],
            "task": lens["task"],
            "status": status,
            "required": required,
            "items": items,
            "exit_criteria_met": bool(items) or not required,
        }

    process_items = data.get("lens_process_model", []) or data.get("workflow_node_candidates", [])
    evidence_items = data.get("lens_evidence_model", []) or data.get("required_validations", [])
    acceptance_items = data.get("lens_acceptance_model", []) or data.get("success_criteria", [])
    boundary_items = (
        data.get("lens_boundary_model", [])
        or [*data.get("blocking_conditions", []), *data.get("edge_cases", []), *data.get("non_goals", [])]
    )
    elements = {
        "process": _element_records("PROC", process_items),
        "decisions": _element_records("DEC", data.get("lens_decision_model", [])),
        "evidence": _element_records("EVD", evidence_items),
        "acceptance": _element_records("ACC", acceptance_items),
        "boundaries": _element_records("BND", boundary_items),
    }

    requirement_links = [
        {
            "requirement_id": "REQ-001",
            "priority": "must",
            "process_refs": [item["id"] for item in elements["process"]],
            "decision_refs": [item["id"] for item in elements["decisions"]],
            "evidence_refs": [item["id"] for item in elements["evidence"]],
            "acceptance_refs": [item["id"] for item in elements["acceptance"]],
            "boundary_refs": [item["id"] for item in elements["boundaries"]],
        }
    ]

    return {
        "schema_version": 1,
        "complexity": complexity,
        "status": "READY" if readiness.get("ready") and not any(gap.get("severity") == "blocking" for gap in gaps) else "BLOCKED",
        "lenses": lenses,
        "elements": elements,
        "workflow_node_candidates": data.get("workflow_node_candidates", []),
        "negative_or_stop_scenarios": data.get("negative_or_stop_scenarios", []),
        "requirement_links": requirement_links,
        "open_logic_gaps": gaps,
        "coverage": {
            "all_required_lenses_present": not any(key in gap_lens_keys for key in required_lens_keys_for_complexity(complexity)),
            "has_process_refs": bool(requirement_links[0]["process_refs"]),
            "has_evidence_refs": bool(requirement_links[0]["evidence_refs"]),
            "has_acceptance_refs": bool(requirement_links[0]["acceptance_refs"]),
            "has_design_consequential_questions": any(
                is_design_consequential_question(question)
                for question in data.get("logic_questions", [])
            ),
        },
    }


def readiness_report_from_data(data: Dict[str, Any]) -> Dict[str, Any]:
    logic_gaps = logic_gaps_from_data(data)
    checks = {
        "goal_defined": bool(data.get("user_goal")),
        "purpose_defined": bool(data.get("business_purpose")),
        "success_criteria_defined": bool(data.get("success_criteria")),
        "trigger_defined": bool(data.get("trigger_mode")) and bool(data.get("trigger_details")),
        "inputs_defined": bool(data.get("primary_inputs")),
        "outputs_defined": bool(data.get("primary_outputs")),
        "quality_gates_defined": bool(data.get("blocking_conditions")) and bool(data.get("required_validations")) and bool(data.get("definition_of_done")),
        "dependencies_defined": bool(data.get("external_dependencies")) or bool(data.get("external_context")),
        "edge_cases_covered": len(data.get("edge_cases", [])) >= 3,
        "readback_confirmed": bool(CONFIRMED_STATUS_RE.match(str(data.get("readback_confirmation_status", "")).strip())),
        "no_blocking_open_questions": len(data.get("blocking_questions", [])) == 0,
        "clarification_rounds_sufficient": isinstance(data.get("clarification_rounds"), int) and int(data.get("clarification_rounds", 0) or 0) >= 2,
        "logic_lenses_sufficient": not any(gap.get("severity") == "blocking" for gap in logic_gaps),
    }
    blocking_reasons = [
        name for name, passed in checks.items() if not passed
    ]
    ready = not blocking_reasons
    return {
        "status": "READY" if ready else "BLOCKED",
        "ready": ready,
        "clarification_rounds": data.get("clarification_rounds"),
        "readback_confirmation_status": data.get("readback_confirmation_status"),
        "blocking_checks": checks,
        "blocking_reasons": blocking_reasons,
        "blocking_questions": data.get("blocking_questions", []),
        "deferred_questions": data.get("deferred_questions", []),
        "complexity": normalize_complexity(data.get("complexity")),
        "open_logic_gaps": logic_gaps,
    }


def clarification_record_from_data(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "workflow_name": data.get("workflow_name", ""),
        "trigger_command": data.get("trigger_command", ""),
        "workflow_summary": data.get("workflow_summary", ""),
        "user_goal": data.get("user_goal", ""),
        "business_purpose": data.get("business_purpose", ""),
        "success_criteria": data.get("success_criteria", []),
        "clarification_rounds": data.get("clarification_rounds"),
        "complexity": data.get("complexity", "M"),
        "logic_lenses": {
            lens["key"]: data.get(lens["draft_key"], [])
            for lens in LOGIC_LENSES
        },
        "logic_questions": data.get("logic_questions", []),
        "workflow_node_candidates": data.get("workflow_node_candidates", []),
        "negative_or_stop_scenarios": data.get("negative_or_stop_scenarios", []),
        "confirmed_decisions": data.get("confirmed_decisions", []),
        "resolved_ambiguities": data.get("resolved_ambiguities", []),
        "trigger_mode": data.get("trigger_mode", ""),
        "trigger_details": data.get("trigger_details", ""),
        "primary_inputs": data.get("primary_inputs", []),
        "optional_inputs": data.get("optional_inputs", []),
        "external_context": data.get("external_context", []),
        "primary_outputs": data.get("primary_outputs", []),
        "secondary_outputs": data.get("secondary_outputs", []),
        "output_formats": data.get("output_formats", []),
        "blocking_conditions": data.get("blocking_conditions", []),
        "required_validations": data.get("required_validations", []),
        "definition_of_done": data.get("definition_of_done", []),
        "external_dependencies": data.get("external_dependencies", []),
        "edge_cases": data.get("edge_cases", []),
        "non_goals": data.get("non_goals", []),
        "readback_summary": data.get("readback_summary", ""),
        "readback_confirmation_status": data.get("readback_confirmation_status", ""),
        "readback_corrections": data.get("readback_corrections", []),
    }


def open_questions_from_data(data: Dict[str, Any]) -> Dict[str, Any]:
    blocking = data.get("blocking_questions", [])
    deferred = data.get("deferred_questions", [])
    return {
        "blocking_questions": blocking,
        "deferred_questions": deferred,
        "resolution_strategy": data.get("question_resolution_strategy", ""),
        "blocking_count": len(blocking),
        "deferred_count": len(deferred),
    }


def assumption_log_from_data(data: Dict[str, Any]) -> str:
    def lines_for(title: str, items: List[str]) -> List[str]:
        if not items:
            return [f"## {title}", "", "- 无", ""]
        return [f"## {title}", "", *[f"- {item}" for item in items], ""]

    lines: List[str] = [
        "# Assumption Log",
        "",
        f"- workflow_name: `{data.get('workflow_name', '')}`",
        f"- trigger_command: `{data.get('trigger_command', '')}`",
        "",
    ]
    for title, items in (
        ("Current Assumptions", data.get("assumptions", [])),
        ("External Dependencies", data.get("external_dependencies", [])),
        ("Edge Cases", data.get("edge_cases", [])),
        ("Non-Goals", data.get("non_goals", [])),
    ):
        lines.extend(lines_for(title, items))
    return "\n".join(lines).rstrip() + "\n"


def challenge_questions_for_role(role_id: str, data: Dict[str, Any], readiness: Dict[str, Any]) -> List[str]:
    questions: List[str] = []

    if role_id == "scenario-extractor":
        if len(data.get("edge_cases", [])) < 3:
            questions.append("还缺哪些失败路径、边界场景或明确不自动化的情形？")
        if not data.get("primary_outputs"):
            questions.append("最终要交付哪些主要输出，它们各自的使用者是谁？")
        if not data.get("primary_inputs"):
            questions.append("工作流每次执行时必需输入是什么，哪些输入只在特殊场景下出现？")
    elif role_id == "assumption-auditor":
        if not data.get("external_dependencies") and not data.get("external_context"):
            questions.append("是否依赖外部工具、MCP、skill、权限或上下文文档？")
        if not data.get("non_goals"):
            questions.append("有哪些看起来相关但明确不做的范围，避免后续设计误扩张？")
        if not data.get("assumptions"):
            questions.append("当前设计还在依赖哪些默认假设，需要用户显式确认或修正？")
    elif role_id == "constraint-reviewer":
        if not data.get("blocking_conditions"):
            questions.append("什么情况下工作流必须停止、阻塞或升级给用户处理？")
        if not data.get("required_validations"):
            questions.append("最终必须通过哪些验证或检查，才能算设计完成？")
        if not data.get("definition_of_done"):
            questions.append("完成定义是什么，哪些信号表示工作流已经真的可用？")

    for item in data.get("deferred_questions", []):
        text = str(item).strip()
        if text:
            questions.append(text)

    if readiness.get("ready") and not questions:
        return []
    return questions


def weak_logic_lenses_from_map(logic_map: Dict[str, Any]) -> List[str]:
    lenses = logic_map.get("lenses", {}) if isinstance(logic_map, dict) else {}
    if not isinstance(lenses, dict):
        return list(LOGIC_LENS_KEYS)
    weak: List[str] = []
    for key in LOGIC_LENS_KEYS:
        lens = lenses.get(key, {})
        if not isinstance(lens, dict) or lens.get("status") in {"blocking", "deferred"}:
            weak.append(key)
    return weak


def clarification_challenge_report_from_data(
    data: Dict[str, Any],
    readiness: Dict[str, Any],
    logic_map: Dict[str, Any] | None = None,
    question_backlog: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    review_roles: List[Dict[str, Any]] = []
    lead_backlog: List[str] = []
    logic_map = logic_map or requirement_logic_map_from_data(data, readiness)
    question_backlog = question_backlog or question_backlog_from_data(data, readiness)
    weakest_lenses = weak_logic_lenses_from_map(logic_map)

    for role in CHALLENGE_ROLE_SPECS:
        role_questions = challenge_questions_for_role(role["id"], data, readiness)
        for question in question_backlog.get("questions", []):
            if not isinstance(question, dict):
                continue
            if not question.get("blocking"):
                continue
            text = str(question.get("question", "")).strip()
            if text and text not in role_questions:
                role_questions.append(text)
        review_roles.append(
            {
                "id": role["id"],
                "focus": role["focus"],
                "direct_user_contact": False,
                "status": "PASS" if not role_questions else "CHALLENGE",
                "weak_logic_lenses": weakest_lenses,
                "proposed_questions": role_questions,
            }
        )
        for question in role_questions:
            if question not in lead_backlog:
                lead_backlog.append(question)

    return {
        "lead_role": "requirement-clarification-lead",
        "review_roles": review_roles,
        "lead_question_backlog": lead_backlog,
        "weakest_logic_lenses": weakest_lenses,
        "logic_lens_review": [
            {
                "lens": key,
                "status": (logic_map.get("lenses", {}).get(key, {}) or {}).get("status", "missing"),
                "question_count": len(
                    [
                        question
                        for question in question_backlog.get("questions", [])
                        if isinstance(question, dict) and question.get("lens") == key
                    ]
                ),
            }
            for key in LOGIC_LENS_KEYS
        ],
        "ready_for_handoff": bool(readiness.get("ready")),
        "blocking_questions_cleared": len(data.get("blocking_questions", [])) == 0,
        "deferred_questions": data.get("deferred_questions", []),
    }


def clarification_handoff_from_data(
    data: Dict[str, Any],
    readiness: Dict[str, Any],
    challenge_report: Dict[str, Any],
    *,
    spec_path: Path,
    run_root: Path,
    logic_map: Dict[str, Any] | None = None,
    question_backlog: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    stages_root = run_root / "outputs" / "stages"
    focus_questions = challenge_report.get("lead_question_backlog", [])
    logic_map = logic_map or requirement_logic_map_from_data(data, readiness)
    question_backlog = question_backlog or question_backlog_from_data(data, readiness)
    logic_map_path = stages_root / "requirement-logic-map.json"
    question_backlog_path = stages_root / "question-backlog.json"
    return {
        "ready": bool(readiness.get("ready")),
        "logic_map_path": str(logic_map_path),
        "question_backlog_path": str(question_backlog_path),
        "source_files": {
            "draft": str(spec_path),
            "clarification_record": str(stages_root / "clarification-record.json"),
            "open_questions": str(stages_root / "open-questions.json"),
            "question_backlog": str(question_backlog_path),
            "requirement_logic_map": str(logic_map_path),
            "challenge_report": str(stages_root / "clarification-challenge-report.json"),
        },
        "s2_inputs": {
            "research_scope": data.get("primary_outputs", []),
            "external_dependencies": data.get("external_dependencies", []),
            "assumptions": data.get("assumptions", []),
            "edge_cases": data.get("edge_cases", []),
            "focus_questions": focus_questions,
            "non_goals": data.get("non_goals", []),
            "logic_lenses": logic_map.get("lenses", {}),
            "logic_map_summary": {
                "complexity": logic_map.get("complexity"),
                "weakest_logic_lenses": challenge_report.get("weakest_logic_lenses", []),
                "open_logic_gaps": logic_map.get("open_logic_gaps", []),
            },
        },
        "s3_inputs": {
            "success_criteria": data.get("success_criteria", []),
            "trigger_model": {
                "mode": data.get("trigger_mode", ""),
                "details": data.get("trigger_details", ""),
            },
            "io_contract": {
                "primary_inputs": data.get("primary_inputs", []),
                "optional_inputs": data.get("optional_inputs", []),
                "primary_outputs": data.get("primary_outputs", []),
                "secondary_outputs": data.get("secondary_outputs", []),
                "output_formats": data.get("output_formats", []),
            },
            "quality_gates": {
                "blocking_conditions": data.get("blocking_conditions", []),
                "required_validations": data.get("required_validations", []),
                "definition_of_done": data.get("definition_of_done", []),
            },
            "design_constraints": [
                *data.get("blocking_conditions", []),
                *data.get("non_goals", []),
            ],
            "workflow_node_candidates": data.get("workflow_node_candidates", []),
            "acceptance_scenarios": logic_map.get("elements", {}).get("acceptance", []),
            "requirement_logic_links": logic_map.get("requirement_links", []),
            "question_backlog": question_backlog.get("questions", []),
            "deferred_questions": data.get("deferred_questions", []),
        },
    }


def clarification_evidence_from_data(
    data: Dict[str, Any],
    readiness: Dict[str, Any],
    challenge_report: Dict[str, Any],
    handoff: Dict[str, Any],
    logic_map: Dict[str, Any] | None = None,
    question_backlog: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    review_roles = challenge_report.get("review_roles", [])
    logic_map = logic_map or requirement_logic_map_from_data(data, readiness)
    question_backlog = question_backlog or question_backlog_from_data(data, readiness)
    return {
        "clarification_rounds": data.get("clarification_rounds"),
        "challenge_rounds": 1,
        "readback_confirmed": bool(readiness.get("blocking_checks", {}).get("readback_confirmed")),
        "blocking_questions_cleared": bool(challenge_report.get("blocking_questions_cleared")),
        "challenge_roles_executed": [role.get("id") for role in review_roles if role.get("id")],
        "lead_role": challenge_report.get("lead_role"),
        "evidence_checks": {
            "clarification_rounds_sufficient": bool(readiness.get("blocking_checks", {}).get("clarification_rounds_sufficient")),
            "challenge_roles_executed": len([role.get("id") for role in review_roles if role.get("id")]) >= len(CHALLENGE_ROLE_SPECS),
            "readback_confirmed": bool(readiness.get("blocking_checks", {}).get("readback_confirmed")),
            "blocking_questions_cleared": bool(challenge_report.get("blocking_questions_cleared")),
            "logic_map_ready": logic_map.get("status") == "READY",
            "question_backlog_design_consequential": question_backlog.get("design_consequential_count", 0) > 0
            or complexity_rank(data.get("complexity")) < 3,
            "s2_handoff_ready": bool(handoff.get("ready")) and bool(handoff.get("s2_inputs")),
            "s3_handoff_ready": bool(handoff.get("ready")) and bool(handoff.get("s3_inputs")),
        },
    }
