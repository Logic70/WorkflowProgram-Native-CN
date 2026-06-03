#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""从 S1 草案和结构化澄清包生成内部 challenge / handoff / evidence 工件。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.clarification_utils import (
    clarification_challenge_report_from_data,
    clarification_evidence_from_data,
    clarification_handoff_from_data,
    draft_data_from_text,
    load_json,
    load_text,
    readiness_report_from_data,
)
from lib.io_utils import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate WorkflowProgram clarification review outputs")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.md")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT path")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    run_root = Path(args.run_root).resolve()
    stages_root = run_root / "outputs" / "stages"
    stages_root.mkdir(parents=True, exist_ok=True)

    if not spec_path.exists():
        payload = {
            "status": "FAIL",
            "errors": [f"workflow draft not found: {spec_path}"],
            "warnings": [],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["errors"][0])
        return 1

    required_inputs = [
        stages_root / "clarification-record.json",
        stages_root / "open-questions.json",
        stages_root / "design-readiness-report.json",
        stages_root / "target-question-backlog.json",
        stages_root / "target-requirement-logic-map.json",
    ]
    if not required_inputs[3].exists():
        required_inputs[3] = stages_root / "question-backlog.json"
    if not required_inputs[4].exists():
        required_inputs[4] = stages_root / "requirement-logic-map.json"
    missing = [str(path) for path in required_inputs if not path.exists()]
    if missing:
        payload = {
            "status": "FAIL",
            "errors": [f"missing prerequisite clarification package files: {', '.join(missing)}"],
            "warnings": [],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["errors"][0])
        return 1

    data = draft_data_from_text(load_text(spec_path))
    readiness = readiness_report_from_data(data)
    question_backlog = load_json(required_inputs[3])
    requirement_logic_map = load_json(required_inputs[4])
    challenge_report = clarification_challenge_report_from_data(
        data,
        readiness,
        requirement_logic_map,
        question_backlog,
    )
    handoff = clarification_handoff_from_data(
        data,
        readiness,
        challenge_report,
        spec_path=spec_path,
        run_root=run_root,
        logic_map=requirement_logic_map,
        question_backlog=question_backlog,
    )
    evidence = clarification_evidence_from_data(
        data,
        readiness,
        challenge_report,
        handoff,
        requirement_logic_map,
        question_backlog,
    )

    challenge_path = stages_root / "clarification-challenge-report.json"
    handoff_path = stages_root / "clarification-handoff.json"
    evidence_path = stages_root / "clarification-evidence.json"

    write_json(challenge_path, challenge_report)
    write_json(handoff_path, handoff)
    write_json(evidence_path, evidence)

    payload = {
        "status": "PASS",
        "errors": [],
        "warnings": [],
        "challenge_report_path": str(challenge_path),
        "handoff_path": str(handoff_path),
        "evidence_path": str(evidence_path),
        "ready_for_handoff": bool(handoff.get("ready")),
        "challenge_backlog_size": len(challenge_report.get("lead_question_backlog", [])),
        "challenge_roles": [role.get("id") for role in challenge_report.get("review_roles", []) if role.get("id")],
        "clarification_record_path": str(required_inputs[0]),
        "open_questions_path": str(required_inputs[1]),
        "design_readiness_path": str(required_inputs[2]),
        "question_backlog_path": str(required_inputs[3]),
        "requirement_logic_map_path": str(required_inputs[4]),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[PASS] generated clarification review artifacts under {stages_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
