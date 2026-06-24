from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / ".claude" / "scripts" / "probe-native-workflow-capability.py"
WORKFLOW = "workflowprogram-native-smoke"


def run_probe(jsonl: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROBE), "--jsonl", str(jsonl), "--workflow", WORKFLOW, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_probe_classifies_enabled_interactive_session(tmp_path: Path) -> None:
    jsonl = tmp_path / "enabled.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {"type": "assistant", "tool": "Workflow", "input": {"scriptPath": f"/tmp/{WORKFLOW}.js"}},
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_sample"},
            {"type": "notification", "content": f'<result>{{"status":"PASS","workflow":"{WORKFLOW}"}}</result>'},
        ],
    )

    completed = run_probe(jsonl)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "PASS"
    assert payload["evidence"]["completed_pass"] is True


def test_probe_detects_task_notification_completed_pass(tmp_path: Path) -> None:
    jsonl = tmp_path / "task-notification-pass.jsonl"
    result = json.dumps({"status": "PASS", "workflow": WORKFLOW, "blockingIssues": []})
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {"type": "assistant", "tool": "Workflow", "input": {"scriptPath": f"/tmp/{WORKFLOW}.js"}},
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_sample"},
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "content": (
                    "<task-notification>\n"
                    "<status>completed</status>\n"
                    f"<result>{result}</result>\n"
                    "</task-notification>"
                ),
            },
        ],
    )

    completed = run_probe(jsonl)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "PASS"
    assert payload["evidence"]["completed_pass"] is True


def test_probe_does_not_count_nested_pass_as_completed_pass(tmp_path: Path) -> None:
    jsonl = tmp_path / "task-notification-blocked-with-nested-pass.jsonl"
    result = json.dumps(
        {
            "status": "BLOCKED_GENERATION",
            "workflow": WORKFLOW,
            "authoringEvidence": {"status": "PASS"},
            "blockingIssues": ["Generation gate blocked."],
        }
    )
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {"type": "assistant", "tool": "Workflow", "input": {"scriptPath": f"/tmp/{WORKFLOW}.js"}},
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_sample"},
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "content": (
                    "<task-notification>\n"
                    "<status>completed</status>\n"
                    f"<result>{result}</result>\n"
                    "</task-notification>"
                ),
            },
        ],
    )

    completed = run_probe(jsonl)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "PASS"
    assert payload["evidence"]["completed_pass"] is False


def test_probe_classifies_disabled_context(tmp_path: Path) -> None:
    jsonl = tmp_path / "disabled.jsonl"
    write_jsonl(jsonl, [{"type": "tool_result", "error": "Workflow exists but is not enabled in this context."}])

    completed = run_probe(jsonl)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert payload["status"] == "UNAVAILABLE"


def test_probe_classifies_missing_evidence_as_inconclusive(tmp_path: Path) -> None:
    jsonl = tmp_path / "inconclusive.jsonl"
    write_jsonl(jsonl, [{"type": "user", "message": "probe"}])

    completed = run_probe(jsonl)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert payload["status"] == "INCONCLUSIVE"


def test_probe_classifies_sdk_cli_ultrawork_without_workflow_as_unavailable(tmp_path: Path) -> None:
    jsonl = tmp_path / "sdk-cli-no-workflow.jsonl"
    write_jsonl(
        jsonl,
        [
            {
                "type": "user",
                "entrypoint": "sdk-cli",
                "promptSource": "sdk",
                "message": {
                    "role": "user",
                    "content": f'ultrawork\n\nWorkflow({{ scriptPath: "/tmp/{WORKFLOW}.js" }})',
                },
            },
            {"type": "assistant", "message": {"content": "I can inspect the plan."}},
        ],
    )

    completed = run_probe(jsonl)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert payload["status"] == "UNAVAILABLE"
    assert payload["reason"] == "non-interactive-sdk-cli-did-not-expose-workflow-tool"
    assert payload["evidence"]["sdk_cli_print_mode"] is True
    assert payload["evidence"]["workflow_prompt_attempt"] is True
