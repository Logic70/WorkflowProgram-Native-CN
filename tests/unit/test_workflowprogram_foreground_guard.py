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


def test_record_accepts_workflow_task_output_and_persists_latest_result(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    task_output = tmp_path / "task.output"
    task_output.write_text(
        json.dumps(
            {
                "summary": "Workflow completed",
                "result": {
                    "status": "READY_FOR_CONFIRMATION",
                    "workflow": "workflowprogram-develop",
                    "runId": "migration-001",
                    "nextAction": "REINVOKE_WITH_CONFIRMATION",
                },
            }
        ),
        encoding="utf-8",
    )

    completed = run_guard(
        "record",
        "--target-root",
        str(target),
        "--run-root",
        str(run_root),
        "--workflow-task-output",
        str(task_output),
        "--json",
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    workflow_result_path = Path(payload["workflowResultPath"])
    assert workflow_result_path == run_root.resolve() / "outputs" / "stages" / "latest-workflow-result.json"
    latest = json.loads(workflow_result_path.read_text(encoding="utf-8"))
    assert latest["status"] == "READY_FOR_CONFIRMATION"
    assert latest["workflow"] == "workflowprogram-develop"
    assert "result" not in latest
    state = json.loads((target / ".workflowprogram" / "session-state.json").read_text(encoding="utf-8"))
    assert state["workflowStatus"] == "READY_FOR_CONFIRMATION"


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


def append_structured_output_success(path: Path, *, agent_id: str = "agent-dfd") -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "agentId": agent_id,
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "call_structured",
                                "content": "Structured output provided successfully",
                            }
                        ],
                    },
                },
                ensure_ascii=False,
            )
            + "\n"
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


def test_guard_blocks_plan_mode_exit_for_wpn_intent(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "继续 WPN / WorkflowProgram Native 对 FreeSTRIDE 的迁移")

    completed = run_guard(
        "check",
        payload={
            "tool_name": "ExitPlanMode",
            "cwd": str(tmp_path),
            "transcript_path": str(transcript),
            "tool_input": {
                "plan": "Call Workflow after confirmation.",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["status"] == "BLOCKED"
    assert "must not enter Claude Code plan mode" in payload["reason"]


def test_guard_blocks_claude_plan_file_write_for_wpn_intent(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "继续 WPN / WorkflowProgram Native 对 FreeSTRIDE 的迁移")
    plan_file = tmp_path / ".claude" / "plans" / "workflowprogram-develop-plan.md"

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Write",
            "cwd": str(tmp_path),
            "transcript_path": str(transcript),
            "tool_input": {
                "file_path": str(plan_file),
                "content": "Plan instead of invoking Workflow.",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["status"] == "BLOCKED"
    assert "plan-mode files" in payload["reason"]


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


def test_guard_allows_workflow_subagent_shell_write_for_wpn_intent(tmp_path: Path) -> None:
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
            "isSidechain": True,
            "attributionAgent": "workflow-subagent",
            "agentId": "agent-dfd",
            "tool_input": {
                "command": "mkdir -p outputs/stride-audit",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout or completed.stderr


def test_guard_allows_workflow_subagent_shell_write_from_transcript_path(tmp_path: Path) -> None:
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-dfd.jsonl"
    transcript.parent.mkdir(parents=True)
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
                "command": "cppcheck --version 2>&1",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout or completed.stderr


def test_guard_allows_workflow_subagent_file_write_for_wpn_intent(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    target.mkdir()

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Write",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "isSidechain": True,
            "attributionAgent": "workflow-subagent",
            "agentId": "agent-dfd",
            "tool_input": {
                "file_path": str(target / "outputs" / "stride-audit" / "dfd.yaml"),
                "content": "dfd_version: 1.0\n",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout or completed.stderr


def test_guard_blocks_workflow_subagent_shell_after_structured_output_success(tmp_path: Path) -> None:
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-dfd.jsonl"
    transcript.parent.mkdir(parents=True)
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    append_structured_output_success(transcript, agent_id="agent-dfd")
    target = tmp_path / "target"
    target.mkdir()

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "isSidechain": True,
            "attributionAgent": "workflow-subagent",
            "agentId": "agent-dfd",
            "tool_input": {
                "command": "python -c \"open('outputs/stride-audit/parse_result.json', 'w').write('{}')\"",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["status"] == "BLOCKED"
    assert "already completed StructuredOutput" in payload["reason"]
    assert "Respond exactly DONE" in payload["reason"]


def test_guard_blocks_structured_phase_runner_after_success_from_session_transcript(tmp_path: Path) -> None:
    session = tmp_path / "projects" / "repo" / "session-123.jsonl"
    session.parent.mkdir(parents=True)
    write_transcript(session, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    agent_transcript = session.with_suffix("") / "subagents" / "workflows" / "wf_123" / "agent-a84f1800.jsonl"
    agent_transcript.parent.mkdir(parents=True)
    write_transcript(agent_transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    append_structured_output_success(agent_transcript, agent_id="a84f1800")
    target = tmp_path / "target"
    target.mkdir()

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "cwd": str(target),
            "transcript_path": str(session),
            "agent_type": "workflowprogram-native-cn:structured-phase-runner",
            "agent_id": "a84f1800",
            "tool_input": {
                "command": "cat > outputs/stride-audit/parse_result.json << 'EOF'\n{}\nEOF",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["status"] == "BLOCKED"
    assert "already completed StructuredOutput" in payload["reason"]
    assert "Respond exactly DONE" in payload["reason"]


def test_guard_blocks_workflow_subagent_structured_output_retry_after_success(tmp_path: Path) -> None:
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-dfd.jsonl"
    transcript.parent.mkdir(parents=True)
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    append_structured_output_success(transcript, agent_id="agent-dfd")

    completed = run_guard(
        "check",
        payload={
            "tool_name": "StructuredOutput",
            "transcript_path": str(transcript),
            "isSidechain": True,
            "attributionAgent": "workflow-subagent",
            "agentId": "agent-dfd",
            "tool_input": {"status": "PASS"},
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "already completed StructuredOutput" in payload["reason"]
    assert "Respond exactly DONE" in payload["reason"]


def test_guard_blocks_workflow_subagent_read_after_structured_output_success(tmp_path: Path) -> None:
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-dfd.jsonl"
    transcript.parent.mkdir(parents=True)
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    append_structured_output_success(transcript, agent_id="agent-dfd")

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Read",
            "transcript_path": str(transcript),
            "isSidechain": True,
            "attributionAgent": "workflow-subagent",
            "agentId": "agent-dfd",
            "tool_input": {"file_path": str(tmp_path / "target" / "outputs" / "stride-audit" / "parse_result.json")},
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "already completed StructuredOutput" in payload["reason"]
    assert "Respond exactly DONE" in payload["reason"]


def artifact_writer_prompt(command: str) -> str:
    return (
        "You are a deterministic artifact command runner. Run exactly the Bash command between "
        "the command markers once.\n"
        "Artifact operation: write\n"
        "File path: D:/Code/FreeSTRIDE/outputs/stride-audit/dfd.yaml\n"
        "Chunk index: 1\n"
        "Chunk count: 1\n"
        "Content base64:\n"
        "---BEGIN_ARTIFACT_BASE64---\n"
        "e30=\n"
        "---END_ARTIFACT_BASE64---\n"
        "---BEGIN_ARTIFACT_COMMAND---\n"
        f"{command}\n"
        "---END_ARTIFACT_COMMAND---\n"
    )


def artifact_file_writer_prompt(commands: list[str]) -> str:
    blocks = []
    for index, command in enumerate(commands, start=1):
        blocks.append(
            f"---BEGIN_ARTIFACT_COMMAND {index}/{len(commands)} {'write' if index == 1 else 'append'}---\n"
            f"{command}\n"
            f"---END_ARTIFACT_COMMAND {index}/{len(commands)} {'write' if index == 1 else 'append'}---"
        )
    return (
        "You are a deterministic artifact file command runner. Run every Bash command between "
        "the command markers exactly once, in ascending chunk order.\n"
        "Artifact operation: write\n"
        "File path: D:/Code/FreeSTRIDE/outputs/stride-audit/dfd.yaml\n"
        f"Chunk count: {len(commands)}\n"
        "Artifact payloads are embedded only in payload markers for the helper.\n"
        + "\n".join(blocks)
        + "\n"
    )


def artifact_helper_command(payload_id: str = "apw-1-0-test", operation: str = "write", offset: int = 0) -> str:
    return (
        "workflowprogram-artifact-writer "
        f"--payload-id '{payload_id}' "
        "--target-file 'D:/Code/FreeSTRIDE/outputs/stride-audit/dfd.yaml' "
        f"--operation '{operation}' "
        f"--byte-offset {offset} --mask-key 173"
    )


def test_guard_blocks_artifact_writer_write_tool_before_structured_output(tmp_path: Path) -> None:
    command = "python3 -c 'import base64,pathlib; pathlib.Path(\"out\").write_bytes(base64.b64decode(\"e30=\"))'"
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-artifact.jsonl"
    transcript.parent.mkdir(parents=True)
    write_transcript(transcript, artifact_writer_prompt(command))

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Write",
            "transcript_path": str(transcript),
            "agent_type": "workflowprogram-native-cn:structured-phase-runner",
            "agent_id": "artifact",
            "tool_input": {
                "file_path": str(tmp_path / "target" / "outputs" / "stride-audit" / "write_chunk1.py"),
                "content": "helper",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "Artifact writer workflow subagents may only call Bash" in payload["reason"]


def test_guard_blocks_artifact_writer_modified_bash_command(tmp_path: Path) -> None:
    command = "python3 -c 'import base64,pathlib; pathlib.Path(\"out\").write_bytes(base64.b64decode(\"e30=\"))'"
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-artifact.jsonl"
    transcript.parent.mkdir(parents=True)
    write_transcript(transcript, artifact_writer_prompt(command))

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "transcript_path": str(transcript),
            "agent_type": "workflowprogram-native-cn:structured-phase-runner",
            "agent_id": "artifact",
            "tool_input": {
                "command": "python3 D:/Code/FreeSTRIDE/outputs/stride-audit/write_chunk1.py",
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "must run exactly one generated command" in payload["reason"]
    assert "Do not retry rewritten commands" in payload["reason"]
    assert "StructuredOutput with status BLOCKED" in payload["reason"]


def test_guard_allows_artifact_writer_exact_bash_command(tmp_path: Path) -> None:
    command = artifact_helper_command()
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-artifact.jsonl"
    transcript.parent.mkdir(parents=True)
    write_transcript(transcript, artifact_writer_prompt(command))

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "transcript_path": str(transcript),
            "agent_type": "workflowprogram-native-cn:structured-phase-runner",
            "agent_id": "artifact",
            "tool_input": {
                "command": command,
            },
        },
    )

    assert completed.returncode == 0, completed.stdout or completed.stderr


def test_guard_allows_artifact_file_writer_marker_command(tmp_path: Path) -> None:
    commands = [
        artifact_helper_command("apw-1-0-test", "write", 0),
        artifact_helper_command("apw-2-10-test", "append", 16),
    ]
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-artifact.jsonl"
    transcript.parent.mkdir(parents=True)
    write_transcript(transcript, artifact_file_writer_prompt(commands))

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "transcript_path": str(transcript),
            "agent_type": "workflowprogram-native-cn:structured-phase-runner",
            "agent_id": "artifact",
            "tool_input": {
                "command": commands[1],
            },
        },
    )

    assert completed.returncode == 0, completed.stdout or completed.stderr


def test_guard_blocks_artifact_file_writer_combined_bash_command(tmp_path: Path) -> None:
    commands = [
        artifact_helper_command("apw-1-0-test", "write", 0),
        artifact_helper_command("apw-2-10-test", "append", 16),
    ]
    transcript = tmp_path / "projects" / "repo" / "subagents" / "workflows" / "wf_123" / "agent-artifact.jsonl"
    transcript.parent.mkdir(parents=True)
    write_transcript(transcript, artifact_file_writer_prompt(commands))

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Bash",
            "transcript_path": str(transcript),
            "agent_type": "workflowprogram-native-cn:structured-phase-runner",
            "agent_id": "artifact",
            "tool_input": {
                "command": " && ".join(commands),
            },
        },
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert "combined commands" in payload["reason"]
    assert "StructuredOutput with status BLOCKED" in payload["reason"]


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


def test_guard_allows_product_output_shell_write_before_wpn_state(tmp_path: Path) -> None:
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
                "command": "mkdir -p outputs/stride-audit",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def test_guard_allows_dev_null_redirection_before_wpn_state(tmp_path: Path) -> None:
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
                "command": "ls targets/security_device_auth 2>/dev/null | head -20",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


def test_guard_allows_product_output_file_write_before_wpn_state(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, "WPN / WorkflowProgram Native regression for FreeSTRIDE")
    target = tmp_path / "target"
    target.mkdir()

    completed = run_guard(
        "check",
        payload={
            "tool_name": "Write",
            "cwd": str(target),
            "transcript_path": str(transcript),
            "tool_input": {
                "file_path": str(target / "outputs" / "stride-audit" / "parse_result.json"),
                "content": "{}\n",
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


def test_guard_does_not_apply_unbound_state_without_run_reference_or_intent(tmp_path: Path) -> None:
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
            "sessionId": "fresh-session",
            "tool_input": {
                "command": "mkdir scratch",
            },
        },
    )

    assert completed.returncode == 0, completed.stdout


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
    assert "Read" in matcher_text
    assert "Glob" in matcher_text
    assert "Grep" in matcher_text
    assert "StructuredOutput" in matcher_text
    assert "ExitPlanMode" in matcher_text


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
