#!/usr/bin/env python3
"""
从 S1 的 workflow-spec.md 生成结构化澄清包。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.clarification_utils import (
    assumption_log_from_data,
    clarification_record_from_data,
    draft_data_from_text,
    load_text,
    open_questions_from_data,
    question_backlog_from_data,
    readiness_report_from_data,
    requirement_logic_map_from_data,
)
from lib.io_utils import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate WorkflowProgram clarification package from workflow-spec.md")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.md")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT path")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    run_root = Path(args.run_root).resolve()
    text = load_text(spec_path)
    if not text:
        payload = {
            "status": "FAIL",
            "errors": [f"workflow draft not found or empty: {spec_path}"],
            "warnings": [],
            "spec": str(spec_path),
            "run_root": str(run_root),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"[FAIL] {spec_path}")
        return 1

    data = draft_data_from_text(text)
    stages_root = run_root / "outputs" / "stages"
    clarification_record_path = stages_root / "clarification-record.json"
    open_questions_path = stages_root / "open-questions.json"
    assumption_log_path = stages_root / "assumption-log.md"
    readiness_report_path = stages_root / "design-readiness-report.json"
    question_backlog_path = stages_root / "question-backlog.json"
    requirement_logic_map_path = stages_root / "requirement-logic-map.json"
    target_question_backlog_path = stages_root / "target-question-backlog.json"
    target_requirement_logic_map_path = stages_root / "target-requirement-logic-map.json"

    clarification_record = clarification_record_from_data(data)
    open_questions = open_questions_from_data(data)
    readiness_report = readiness_report_from_data(data)
    question_backlog = question_backlog_from_data(data, readiness_report)
    requirement_logic_map = requirement_logic_map_from_data(data, readiness_report)
    assumption_log = assumption_log_from_data(data)

    write_json(clarification_record_path, clarification_record)
    write_json(open_questions_path, open_questions)
    write_json(readiness_report_path, readiness_report)
    write_json(question_backlog_path, question_backlog)
    write_json(requirement_logic_map_path, requirement_logic_map)
    write_json(target_question_backlog_path, question_backlog)
    write_json(target_requirement_logic_map_path, requirement_logic_map)
    assumption_log_path.parent.mkdir(parents=True, exist_ok=True)
    assumption_log_path.write_text(assumption_log, encoding="utf-8", newline="\n")

    payload = {
        "status": "PASS",
        "errors": [],
        "warnings": [],
        "spec": str(spec_path),
        "run_root": str(run_root),
        "clarification_record": str(clarification_record_path),
        "open_questions": str(open_questions_path),
        "assumption_log": str(assumption_log_path),
        "design_readiness_report": str(readiness_report_path),
        "question_backlog": str(question_backlog_path),
        "requirement_logic_map": str(requirement_logic_map_path),
        "target_question_backlog": str(target_question_backlog_path),
        "target_requirement_logic_map": str(target_requirement_logic_map_path),
        "ready": readiness_report.get("ready", False),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[PASS] {clarification_record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
