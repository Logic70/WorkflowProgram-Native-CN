from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "workflowprogram-foreground-guard.py"
HOOKS = ROOT / ".claude-plugin" / "root" / "hooks" / "hooks.json"


def run_guard(*args: str, payload: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        input=json.dumps(payload or {}),
        capture_output=True,
        text=True,
        check=False,
    )


def record_state(target: Path, run_root: Path, result: dict) -> dict:
    completed = run_guard(
        "record",
        "--target-root",
        str(target),
        "--run-root",
        str(run_root),
        "--workflow-result-json",
        json.dumps(result),
        "--json",
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout)


def test_guard_blocks_direct_write_to_managed_target_after_blocked_state(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    (target / ".claude" / "workflows").mkdir(parents=True)
    run_root.mkdir()
    record_state(
        target,
        run_root,
        {
            "status": "BLOCKED_GENERATION",
            "workflow": "workflowprogram-develop",
            "nextAction": "FIX_DESIGN_AND_REINVOKE",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target / ".claude" / "workflows" / "stride.js"),
                "content": "export const meta = {}",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["workflowStatus"] == "BLOCKED_GENERATION"


def test_guard_allows_candidate_write_under_run_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    (target / ".workflowprogram").mkdir(parents=True)
    (run_root / "outputs" / "candidate" / ".claude" / "workflows").mkdir(parents=True)
    record_state(
        target,
        run_root,
        {
            "status": "READY_FOR_GENERATION",
            "workflow": "workflowprogram-develop",
            "nextAction": "RUN_CONTROLLED_GENERATION",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(run_root / "outputs" / "candidate" / ".claude" / "workflows" / "probe.js"),
                "content": "candidate",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def write_transcript(path: Path, prompt: str) -> None:
    path.write_text(
        json.dumps(
            {
                "message": {
                    "role": "user",
                    "content": prompt,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_guard_blocks_foreground_agent_for_wpn_intent(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "继续 WPN / WorkflowProgram Native 对 Free STRIDE 的迁移回归")

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Agent",
            "transcript_path": str(transcript),
            "tool_input": {
                "subagent_type": "Explore",
                "prompt": "Explore FreeSTRIDE project structure",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["status"] == "BLOCKED"
    assert "product Workflow" in payload["reason"]


def test_guard_allows_foreground_agent_for_non_wpn_intent(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "Summarize the current repository structure")

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Agent",
            "transcript_path": str(transcript),
            "tool_input": {
                "subagent_type": "Explore",
                "prompt": "Explore project structure",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def test_guard_blocks_shell_write_before_wpn_state(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    target.mkdir()

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "tool_input": {
                "command": "mkdir -p .workflowprogram/runs/regression/outputs/stages",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "foreground shell write" in payload["reason"]
    assert "foreground shell write" in completed.stderr


def test_guard_allows_read_only_shell_before_wpn_state(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    target.mkdir()

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "tool_input": {
                "command": "git branch --show-current",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def test_guard_allows_record_command_before_wpn_state(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    target.mkdir()

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "tool_input": {
                "command": (
                    "workflowprogram-python /plugin/scripts/workflowprogram-foreground-guard.py "
                    "record --target-root target --run-root run --workflow-result latest.json --json"
                ),
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def test_guard_ignores_stale_unbound_state_for_new_wpn_intent(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    run_root = target / ".workflowprogram" / "runs" / "old"
    run_root.mkdir(parents=True)
    state = record_state(
        target,
        run_root,
        {
            "status": "BLOCKED_GENERATION",
            "workflow": "workflowprogram-develop",
            "nextAction": "FIX_DESIGN_AND_REINVOKE",
        },
    )["state"]
    state["updatedAt"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    state["transcriptPath"] = ""
    state["sessionId"] = ""
    (target / ".workflowprogram" / "session-state.json").write_text(json.dumps(state), encoding="utf-8")

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "tool_input": {
                "command": "mkdir -p .workflowprogram/runs/new/outputs/stages",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "must launch the product Workflow" in payload["reason"]


def test_guard_ignores_recent_unbound_state_without_run_reference(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    run_root = target / ".workflowprogram" / "runs" / "active"
    run_root.mkdir(parents=True)
    record_state(
        target,
        run_root,
        {
            "status": "BLOCKED_GENERATION",
            "workflow": "workflowprogram-develop",
            "nextAction": "FIX_DESIGN_AND_REINVOKE",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "tool_input": {
                "command": "mkdir -p .workflowprogram/runs/new/outputs/stages",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "must launch the product Workflow" in payload["reason"]


def test_guard_keeps_recent_unbound_state_active_for_run_reference(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    run_root = target / ".workflowprogram" / "runs" / "active"
    run_root.mkdir(parents=True)
    record_state(
        target,
        run_root,
        {
            "status": "BLOCKED_GENERATION",
            "workflow": "workflowprogram-develop",
            "nextAction": "FIX_DESIGN_AND_REINVOKE",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "tool_input": {
                "command": f"mkdir -p {run_root / 'outputs' / 'stages'}",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "current WorkflowProgram state" in payload["reason"]


def test_guard_blocks_file_write_before_wpn_state(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    (target / ".claude" / "workflows").mkdir(parents=True)

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Write",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "tool_input": {
                "file_path": str(target / ".claude" / "workflows" / "stride.js"),
                "content": "export const meta = {}",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "foreground file edit" in payload["reason"]
    assert "foreground file edit" in completed.stderr


def test_guard_blocks_python_embedded_write_to_managed_workflow(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    (target / ".claude" / "workflows").mkdir(parents=True)
    run_root.mkdir()
    record_state(
        target,
        run_root,
        {
            "status": "BLOCKED_DESIGN_REVIEW",
            "workflow": "workflowprogram-develop",
            "nextAction": "FIX_DESIGN_AND_REINVOKE",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "tool_input": {
                "command": "python3 -c \"open('.claude/workflows/stride.js','w').write('bad')\"",
            },
        },
    )

    assert completed.returncode == 2
    assert "Foreground shell writes are blocked" in completed.stdout


def test_guard_blocks_python_embedded_write_to_managed_manifest(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    (target / ".workflowprogram").mkdir(parents=True)
    run_root.mkdir()
    record_state(
        target,
        run_root,
        {
            "status": "BLOCKED_DESIGN_REVIEW",
            "workflow": "workflowprogram-develop",
            "nextAction": "FIX_DESIGN_AND_REINVOKE",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "tool_input": {
                "command": (
                    "python3 -c \"from pathlib import Path; "
                    "Path('.workflowprogram/managed-files.json').write_text('{}')\""
                ),
            },
        },
    )

    assert completed.returncode == 2
    assert "Foreground shell writes are blocked" in completed.stdout


def test_guard_allows_python_read_from_managed_path(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    (target / ".claude" / "workflows").mkdir(parents=True)
    run_root.mkdir()
    record_state(
        target,
        run_root,
        {
            "status": "BLOCKED_DESIGN_REVIEW",
            "workflow": "workflowprogram-develop",
            "nextAction": "FIX_DESIGN_AND_REINVOKE",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "tool_input": {
                "command": "python3 -c \"open('.claude/workflows/stride.js').read()\"",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def test_guard_allows_python_write_under_run_root_candidate(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir(parents=True)
    (run_root / "outputs" / "candidate" / ".claude" / "workflows").mkdir(parents=True)
    record_state(
        target,
        run_root,
        {
            "status": "BLOCKED_DESIGN_REVIEW",
            "workflow": "workflowprogram-develop",
            "nextAction": "FIX_DESIGN_AND_REINVOKE",
        },
    )

    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "stride.js"
    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "tool_input": {
                "command": f"python3 -c \"open('{candidate.as_posix()}','w').write('candidate')\"",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def test_record_unwraps_workflow_tool_result_envelope(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    run_root.mkdir(parents=True)

    recorded = record_state(
        target,
        run_root,
        {
            "summary": "outer wrapper",
            "result": {
                "status": "READY_FOR_GENERATION",
                "workflow": "workflowprogram-develop",
                "runId": "run-001",
                "nextAction": "RUN_CONTROLLED_GENERATION",
            },
        },
    )

    assert recorded["state"]["workflowStatus"] == "READY_FOR_GENERATION"
    assert recorded["state"]["writeMode"] == "controlled-generation"
    assert recorded["state"]["nextAction"] == "RUN_CONTROLLED_GENERATION"


def test_guard_blocks_direct_generator_script_after_ready_for_generation(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir(parents=True)
    run_root.mkdir()
    record_state(
        target,
        run_root,
        {
            "status": "READY_FOR_GENERATION",
            "workflow": "workflowprogram-develop",
            "nextAction": "RUN_CONTROLLED_GENERATION",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "PowerShell",
            "cwd": str(target),
            "tool_input": {
                "command": "python .claude/scripts/generate-native-workflow.py --spec spec.json --json",
            },
        },
    )

    assert completed.returncode == 2
    assert "follow nextAction" in completed.stdout


def test_guard_allows_generation_continuation_script_after_ready_for_generation(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir(parents=True)
    run_root.mkdir()
    record_state(
        target,
        run_root,
        {
            "status": "READY_FOR_GENERATION",
            "workflow": "workflowprogram-develop",
            "nextAction": "RUN_CONTROLLED_GENERATION",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "PowerShell",
            "cwd": str(target),
            "tool_input": {
                "command": (
                    "python .claude/scripts/workflowprogram-continue.py "
                    "--workflow-result latest-workflow-result.json "
                    f"--target-root {target} --run-root {run_root} --json"
                ),
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def test_hook_matcher_covers_powershell_and_shell() -> None:
    payload = json.loads(HOOKS.read_text(encoding="utf-8"))
    matchers = [
        item.get("matcher", "")
        for item in payload.get("hooks", {}).get("PreToolUse", [])
        if isinstance(item, dict)
    ]
    matcher_text = "|".join(matchers)
    assert "PowerShell" in matcher_text
    assert "Shell" in matcher_text


def test_guard_blocks_commit_until_managed_apply_pass(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    (target / ".workflowprogram").mkdir(parents=True)
    run_root.mkdir()
    record_state(
        target,
        run_root,
        {
            "status": "PASS",
            "workflow": "workflowprogram-develop",
            "deliveryMode": "candidate-only",
            "nextAction": "DELIVER",
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "tool_input": {"command": "git commit -m test"},
        },
    )

    assert completed.returncode == 2
    assert "Git commit is allowed only after PASS" in completed.stdout


def test_guard_allows_commit_after_managed_apply_manifest(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    (target / ".workflowprogram").mkdir(parents=True)
    run_root.mkdir()
    record_state(
        target,
        run_root,
        {
            "status": "PASS",
            "workflow": "workflowprogram-develop",
            "deliveryMode": "managed-apply",
            "nextAction": "DELIVER",
            "applyManifest": {
                "entries": [
                    {
                        "path": ".claude/workflows/probe.js",
                        "action": "create",
                        "sha256": "sha256:abc",
                    }
                ]
            },
        },
    )

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "tool_input": {"command": "git commit -m test"},
        },
    )

    assert completed.returncode == 0, completed.stdout
