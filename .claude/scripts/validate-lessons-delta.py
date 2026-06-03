#!/usr/bin/env python3
"""
校验 WorkflowProgram 的 S6 lessons delta 和面向用户的进度摘要。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


NO_NEW_CONSTRAINT_RE = re.compile(r"无新增约束|no new constraint", re.IGNORECASE)
CONSTRAINT_HEADING_RE = re.compile(r"^##\s+(Constraint Candidates|约束候选)\s*$", re.MULTILINE)
HISTORY_HEADING = "历史关键节点结果"
HOST_CAPABILITY_RE = re.compile(r"host[_ -]?capabilit|宿主能力", re.IGNORECASE)
REMEDIATION_RE = re.compile(r"remediat|bootstrap|manual step|recheck|repair|修复|引导", re.IGNORECASE)


def load_text(path: Path) -> str:
    """S6 校验器使用的尽力而为文本加载器。"""

    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_json(path: Path) -> Dict[str, Any]:
    """尽力而为的 JSON 加载器。

    S6 校验应报告契约失败，而不是因损坏的 state 文件直接崩溃，
    因此非法 JSON 会退化为空映射。
    """

    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def find_constraint_candidates(text: str) -> List[str]:
    """从 lessons delta 中提取约束候选 bullet。

    校验器接受两种形态：
    - 显式写出“无新增约束”
    - 在“约束候选”区段下给出一个或多个 bullet
    """

    if NO_NEW_CONSTRAINT_RE.search(text):
        return ["<explicit-no-new-constraint>"]
    match = CONSTRAINT_HEADING_RE.search(text)
    block = text[match.end():] if match else text
    candidates: List[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            break
        if stripped.startswith("- "):
            candidates.append(stripped)
    return candidates


def validate_lessons(run_root: Path, run_id: str, failure_kind: str) -> Dict[str, object]:
    """校验一次完成运行所需的最小 S6 闭环契约。"""

    errors: List[str] = []
    warnings: List[str] = []
    delta_path = run_root / "outputs" / "stages" / "s6-lessons-delta.md"
    user_progress_path = run_root / "outputs" / "progress" / "user-progress.md"

    if not delta_path.exists():
        errors.append(f"lessons delta not found: {delta_path}")
    if not user_progress_path.exists():
        errors.append(f"user progress not found: {user_progress_path}")

    delta_text = load_text(delta_path)
    user_progress_text = load_text(user_progress_path)
    # lessons delta 必须能够追溯到产出它的那次运行，否则后续迭代提炼无法安全复用。
    if delta_text:
        if run_id and run_id not in delta_text:
            errors.append("s6-lessons-delta.md is missing the current run_id")
        if failure_kind and failure_kind not in delta_text:
            errors.append("s6-lessons-delta.md is missing the current failure_kind")
        candidates = find_constraint_candidates(delta_text)
        if not candidates:
            errors.append("s6-lessons-delta.md must contain at least one constraint candidate or an explicit no-new-constraint statement")
        host_report_present = any(
            (run_root / rel_path).exists()
            for rel_path in (
                "outputs/stages/host-capability-report.json",
                "outputs/stages/host-capability-probe.json",
            )
        )
        if failure_kind == "environment" and host_report_present:
            remediation_report = load_json(run_root / "outputs" / "stages" / "environment-remediation-report.json")
            if not remediation_report:
                errors.append("environment-remediation-report.json must exist when environment failures include host capability evidence")
            if not any(HOST_CAPABILITY_RE.search(item) for item in candidates):
                errors.append("s6-lessons-delta.md must include at least one host capability improvement candidate when environment failures include host capability evidence")
            repeated_failures = remediation_report.get("repeated_failure_count", 0) if isinstance(remediation_report, dict) else 0
            if int(repeated_failures or 0) > 0 and not any(REMEDIATION_RE.search(item) for item in candidates):
                errors.append("s6-lessons-delta.md must include at least one remediation/bootstrap candidate when repeated environment failures are present")
    # progress summary 是里程碑流的用户侧镜像。
    # 强制要求历史标题，能让 S6 输出保持可读、可审阅。
    if user_progress_text:
        if HISTORY_HEADING not in user_progress_text:
            errors.append("user-progress.md is missing the '历史关键节点结果' summary section")
        else:
            history_block = user_progress_text.split(HISTORY_HEADING, 1)[1]
            if "- " not in history_block:
                errors.append("user-progress.md history section must include at least one milestone summary bullet")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "run_root": str(run_root),
        "run_id": run_id,
        "failure_kind": failure_kind,
        "delta": str(delta_path),
        "user_progress": str(user_progress_path),
    }


def parse_args() -> argparse.Namespace:
    """解析独立执行 S6 校验所需的命令行参数。"""

    parser = argparse.ArgumentParser(description="Validate WorkflowProgram S6 lessons outputs")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT path")
    parser.add_argument("--run-id", default="", help="Current run identifier")
    parser.add_argument("--failure-kind", default="", help="Current failure kind")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def main() -> int:
    """运行 S6 校验器，并在需要时从 state.json 推导默认值。"""

    args = parse_args()
    run_root = Path(args.run_root).resolve()
    run_id = args.run_id.strip()
    failure_kind = args.failure_kind.strip()
    # 该校验器通常在流水线后段调用，因此当调用方未显式传值时，
    # 它会尝试从 state.json 恢复当前运行标识。
    if not run_id or not failure_kind:
        state = load_json(run_root / "state.json")
        values = state.get("values", {}) if isinstance(state.get("values"), dict) else {}
        run_id = run_id or str(values.get("request_id", run_root.name)).strip()
        failure_kind = failure_kind or str(values.get("failure_kind", "")).strip()
    payload = validate_lessons(run_root, run_id, failure_kind)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] {payload['delta']}")
        for item in payload["errors"]:
            print(f"- ERROR: {item}")
        for item in payload["warnings"]:
            print(f"- WARN: {item}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
