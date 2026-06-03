#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = ROOT / ".claude" / "scripts"


def run_json(*args: str, expect: int = 0) -> dict:
    completed = subprocess.run(
        [sys.executable, *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"expected exit {expect}, got {completed.returncode}\nstdout={completed.stdout}\nstderr={completed.stderr}"
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise AssertionError("expected JSON object")
    return payload


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def valid_implement_node_design() -> str:
    return """# Target Node Design: implement

## 1. Node Metadata / 节点元信息

- Node ID: `implement`
- Workflow spec path: `workflow_graph.nodes[id=implement]`
- Owner: `example-skill`
- Template: `flexible-target-graph`
- Gate: `user_approval`
- Complexity: `complex`
- Design intensity: `standard`

## 2. Purpose And Boundary / 设计目的与职责边界

- Purpose: Implement target workflow assets.
- In scope: Generate declared workflow assets.
- Out of scope: Modify unmanaged target files.
- Upstream assumptions: intake summary exists.

## 3. Input Contract / 输入契约

| Input ref | Required | Producer | Validation rule |
| --- | --- | --- | --- |
| `outputs/target-workflow/intake-summary.md` | yes | intake | file exists |

## 4. Output Contract And Consumers / 输出契约与消费者

| Output ref | Required | Consumer | Pass criteria |
| --- | --- | --- | --- |
| `.claude/skills/example/SKILL.md` | yes | runtime | managed asset exists |

## 5. Context Read/Write Rules / 上下文读写规则

- Reads: `outputs/target-workflow/intake-summary.md`.
- Writes: `.claude/skills/example/SKILL.md`.
- Must not mutate: unmanaged files.
- Persistence rule: managed apply records file ownership.

## 6. Internal Execution Plan / 内部执行编排

1. Read intake summary.
2. Generate skill asset.
3. Record managed result.
4. Verify S5 evidence.

Loop policy:

- Loop allowed: false

## 7. Agent / Skill / Script / Tool Calls / 调用关系

| Capability | Name | Purpose | Input | Output |
| --- | --- | --- | --- | --- |
| skill | `example-skill` | implement asset | intake | skill file |

## 8. Data Field Contract / 数据字段契约

| Field | Type | Required | Source | Meaning |
| --- | --- | --- | --- | --- |
| `node_id` | string | yes | workflow_graph | node identity |

## 9. Exit Gate / 准出目标

- Gate decision: `user_approval`.
- Required evidence: `.claude/skills/example/SKILL.md`.
- Human approval rule: user approval required.
- Auto-approval rule: only explicit auto approve.

## 10. Failure, Retry, And Degrade Strategy / 失败、重试与降级策略

- `FAIL` when the skill file is missing.
- `WARN` when optional evidence is incomplete.
- `ENVIRONMENT-SKIP` when runtime host is unavailable.
- Retry limit: stage default.
- Degrade strategy: only with explicit evidence.

## 11. Verification And Tests / 验证与测试要求

- Unit or fixture test: target governance unit test.
- Runtime verifier: S5 checks managed assets.
- Acceptance test refs: `AT-001`.
- Evidence paths: `state.json`, `events.jsonl`.

## 12. Observability And Debug Artifacts / 观测与调试产物

- Logs: `events.jsonl`.
- Reports: `outputs/stages/s5-validation-summary.json`.
- State artifacts: `state.json`.
- Debug reproduction: rerun governance test.

## 13. Safety And Execution Constraints / 安全与执行约束

- Path boundary: managed output only.
- Approval boundary: user approval.
- Host capability boundary: missing host capability is environment failure.
- Secret handling: do not persist secrets.
- Destructive action policy: none.

## 14. Open Tasks And Extension Points / 遗留任务与扩展点

- Open tasks: none
- Extension points: add domain-specific checks.
- Deferred decisions: none
"""


def seed_canonical_run(
    run_root: Path,
    *,
    missing_acceptance_ref: bool = False,
    complex_node: bool = False,
    with_node_design: bool = False,
) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tests" / "spec-fixtures" / "valid-minimal.yaml", run_root / "workflow-spec.yaml")
    if complex_node:
        spec = yaml.safe_load((run_root / "workflow-spec.yaml").read_text(encoding="utf-8"))
        spec["workflow_graph"]["nodes"][1]["complexity"] = "complex"
        if with_node_design:
            spec.setdefault("design_refs", {}).setdefault("node_designs", {})["implement"] = "outputs/stages/target-node-designs/implement.md"
        (run_root / "workflow-spec.yaml").write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    stages = run_root / "outputs" / "stages"
    write_text(
        stages / "target-requirements.yaml",
        "requirements:\n  - id: REQ-001\n    statement: demo\n",
    )
    write_text(stages / "target-context-findings.yaml", "findings:\n  - id: CTX-001\n    requirement_refs: [REQ-001]\n")
    write_text(stages / "target-design-overview.md", "# Target Design Overview\n\nREQ-001 intake implement.\n")
    write_text(stages / "target-design-detail.md", "# Target Design Detail\n\nREQ-001 intake implement.\n")
    write_text(stages / "target-implementation-plan.md", "# Target Implementation Plan\n")
    write_text(
        stages / "target-acceptance-tests.yaml",
        yaml.safe_dump(
            {
                "tests": [
                    {
                        "id": "AT-001",
                        "requirement_ids": [] if missing_acceptance_ref else ["REQ-001"],
                        "expected_evidence": ["state.json"],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    write_json(
        stages / "target-traceability-matrix.json",
        {
            "schema_version": 1,
            "requirements": [
                {
                    "requirement_id": "REQ-001",
                    "workflow_graph_nodes": ["intake", "implement"],
                    "acceptance_tests": ["AT-001"],
                    "runtime_evidence": ["state.json"],
                }
            ],
        },
    )
    if with_node_design:
        write_text(stages / "target-node-designs" / "implement.md", valid_implement_node_design())


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="target-design-governance-") as temp_dir:
        temp = Path(temp_dir)
        good = temp / "good"
        seed_canonical_run(good)
        assert run_json(str(SCRIPT_ROOT / "validate-target-design-governance.py"), "--run-root", str(good))["status"] == "PASS"

        bad_acceptance = temp / "bad-acceptance"
        seed_canonical_run(bad_acceptance, missing_acceptance_ref=True)
        failed = run_json(str(SCRIPT_ROOT / "validate-target-design-governance.py"), "--run-root", str(bad_acceptance), expect=1)
        assert failed["status"] == "FAIL"
        assert any("acceptance tests missing" in error for error in failed["errors"])

        complex_missing = temp / "complex-missing"
        seed_canonical_run(complex_missing, complex_node=True)
        failed = run_json(str(SCRIPT_ROOT / "validate-target-design-governance.py"), "--run-root", str(complex_missing), expect=1)
        assert any("complex nodes missing" in error for error in failed["errors"])

        complex_valid = temp / "complex-valid"
        seed_canonical_run(complex_valid, complex_node=True, with_node_design=True)
        assert run_json(str(SCRIPT_ROOT / "validate-target-design-governance.py"), "--run-root", str(complex_valid))["status"] == "PASS"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
