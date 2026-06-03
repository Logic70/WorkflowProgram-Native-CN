#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "validate-target-node-design.py"


def run_json(*args: str, expect: int = 0) -> dict:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--json"],
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


def write_spec(path: Path, *, loop_enabled: bool = False) -> None:
    payload = {
        "workflow_graph": {
            "schema_version": 1,
            "nodes": [
                {
                    "id": "build_dfd",
                    "role": "build data flow diagram",
                    "template": "stride_dfd",
                    "owner": "dfd-builder",
                    "gate": "reviewer_approval",
                    "complexity": "complex",
                    "design_intensity": "detailed",
                    "node_design_required": True,
                    "input_refs": ["request.code", "outputs/context.md"],
                    "output_refs": ["outputs/dfd.md"],
                    "loop_policy": {"enabled": loop_enabled},
                }
            ],
        }
    }
    write_text(path, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))


def valid_design(*, owner: str = "dfd-builder", output_ref: str = "outputs/dfd.md", loop_allowed: str = "true") -> str:
    return f"""# Target Node Design: build_dfd

## 1. Node Metadata / 节点元信息

- Node ID: `build_dfd`
- Workflow spec path: `workflow_graph.nodes[id=build_dfd]`
- Owner: `{owner}`
- Template: `stride_dfd`
- Gate: `reviewer_approval`
- Complexity: `complex`
- Design intensity: `detailed`

## 2. Purpose And Boundary / 设计目的与职责边界

- Purpose: Build a DFD from repository evidence.
- In scope: Read code context and produce a reviewable DFD.
- Out of scope: Confirm vulnerabilities.
- Upstream assumptions: Context findings are available.

## 3. Input Contract / 输入契约

| Input ref | Required | Producer | Validation rule |
| --- | --- | --- | --- |
| `request.code` | yes | request | present |
| `outputs/context.md` | yes | context node | present |

## 4. Output Contract And Consumers / 输出契约与消费者

| Output ref | Required | Consumer | Pass criteria |
| --- | --- | --- | --- |
| `{output_ref}` | yes | threat node | DFD contains actors, processes, stores, and flows |

## 5. Context Read/Write Rules / 上下文读写规则

- Reads: `request.code` and `outputs/context.md`.
- Writes: `{output_ref}`.
- Must not mutate: source code.
- Persistence rule: output is runtime evidence.

## 6. Internal Execution Plan / 内部执行编排

1. Read code context.
2. Derive DFD elements.
3. Verify DFD completeness.
4. Record evidence.

Loop policy:

- Loop allowed: {loop_allowed}
- loop_policy evidence: loop-plan and final-verdict when enabled.

## 7. Agent / Skill / Script / Tool Calls / 调用关系

| Capability | Name | Purpose | Input | Output |
| --- | --- | --- | --- | --- |
| skill | `dfd-builder` | build DFD | context | DFD |

## 8. Data Field Contract / 数据字段契约

| Field | Type | Required | Source | Meaning |
| --- | --- | --- | --- | --- |
| `node_id` | string | yes | graph | identity |

## 9. Exit Gate / 准出目标

- Gate decision: `reviewer_approval`.
- Required evidence: `{output_ref}`.
- Human approval rule: reviewer approves DFD.
- Auto-approval rule: none.

## 10. Failure, Retry, And Degrade Strategy / 失败、重试与降级策略

- `FAIL` when `{output_ref}` is missing.
- `WARN` when non-blocking context is incomplete.
- `ENVIRONMENT-SKIP` when a required tool is unavailable.
- Retry limit: stage default.
- Degrade strategy: degrade only with evidence.

## 11. Verification And Tests / 验证与测试要求

- Unit or fixture test: DFD fixture test.
- Runtime verifier: S5 checks `{output_ref}`.
- Acceptance test refs: `AT-DFD`.
- Evidence paths: `state.json` and `events.jsonl`.

## 12. Observability And Debug Artifacts / 观测与调试产物

- Logs: `events.jsonl`.
- Reports: DFD report.
- State artifacts: `state.json`.
- Debug reproduction: rerun fixture.

## 13. Safety And Execution Constraints / 安全与执行约束

- Path boundary: do not write outside outputs.
- Approval boundary: reviewer approval is required.
- Host capability boundary: missing tools are environment failures.
- Secret handling: do not persist secrets.
- Destructive action policy: read-only analysis.

## 14. Open Tasks And Extension Points / 遗留任务与扩展点

- Open tasks: none
- Extension points: add domain-specific diagram renderer.
- Deferred decisions: none
"""


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="target-node-design-") as temp_dir:
        temp = Path(temp_dir)
        spec = temp / "workflow-spec.yaml"
        node_design = temp / "outputs" / "stages" / "target-node-designs" / "build_dfd.md"

        write_spec(spec)
        write_text(node_design, valid_design(loop_allowed="false"))
        passed = run_json("--spec", str(spec), "--node-design", str(node_design), "--node-id", "build_dfd")
        assert passed["status"] == "PASS"

        write_text(node_design, valid_design().replace("## 11. Verification And Tests / 验证与测试要求", "## 11. Verification Evidence"))
        failed = run_json("--spec", str(spec), "--node-design", str(node_design), "--node-id", "build_dfd", expect=1)
        assert any("Verification And Tests" in error for error in failed["errors"])

        write_text(node_design, valid_design(owner="different-owner"))
        failed = run_json("--spec", str(spec), "--node-design", str(node_design), "--node-id", "build_dfd", expect=1)
        assert any("Owner mismatch" in error for error in failed["errors"])

        write_text(node_design, valid_design(output_ref="outputs/other.md"))
        failed = run_json("--spec", str(spec), "--node-design", str(node_design), "--node-id", "build_dfd", expect=1)
        assert any("missing output ref" in error for error in failed["errors"])

        write_spec(spec, loop_enabled=True)
        write_text(node_design, valid_design(loop_allowed="false"))
        failed = run_json("--spec", str(spec), "--node-design", str(node_design), "--node-id", "build_dfd", expect=1)
        assert any("loop execution is disallowed" in error for error in failed["errors"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
