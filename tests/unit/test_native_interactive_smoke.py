from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "build-native-interactive-smoke.py"
WORKFLOW = "workflowprogram-native-smoke"
SCRIPT_PATH = "/tmp/.claude/workflows/workflowprogram-native-smoke.js"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"invalid JSON\nstdout={completed.stdout}\nstderr={completed.stderr}"
        ) from exc


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


# ── packet ──────────────────────────────────────────────────────


def test_packet_generates_minimal_smoke_packet(tmp_path: Path) -> None:
    out = tmp_path / "packet.json"
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--out", str(out),
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    payload = load_json(completed)
    assert payload["schema_name"] == "native-workflow-interactive-smoke"
    assert payload["command"] == "packet"
    assert payload["workflow"] == WORKFLOW
    assert payload["scriptPath"] == SCRIPT_PATH
    assert payload["expectedStatus"] == "PASS"
    assert "executionPrerequisites" in payload
    assert "suggestedPrompt" in payload
    assert "expectedEvidenceTypes" in payload
    assert "manualReviewHints" in payload
    assert "This packet has NOT been executed" in payload["disclaimer"]
    assert "computerUseBoundary" in payload
    assert payload["computerUseBoundary"] == "manual-wsl-execution-supported"
    assert out.exists()


def test_packet_generates_blocked_smoke_packet(tmp_path: Path) -> None:
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "BLOCKED",
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    payload = load_json(completed)
    assert payload["expectedStatus"] == "BLOCKED"


def test_packet_includes_scenario_id(tmp_path: Path) -> None:
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--scenario-id", "pass-smoke-001",
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    payload = load_json(completed)
    assert payload["scenarioId"] == "pass-smoke-001"


def test_packet_includes_args_json(tmp_path: Path) -> None:
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--args", '{"runId":"run-001","targetRoot":"/tmp/target"}',
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    payload = load_json(completed)
    assert payload["args"] == {"runId": "run-001", "targetRoot": "/tmp/target"}


def test_packet_rejects_missing_workflow() -> None:
    completed = run_script("packet", "--script-path", SCRIPT_PATH, "--expected-status", "PASS")
    assert completed.returncode != 0


def test_packet_rejects_missing_script_path() -> None:
    completed = run_script("packet", "--workflow", WORKFLOW, "--expected-status", "PASS")
    assert completed.returncode != 0


def test_packet_rejects_invalid_expected_status() -> None:
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "INVALID",
    )
    assert completed.returncode != 0


def test_packet_expected_evidence_types_vary_by_status() -> None:
    pass_completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--json",
    )
    pass_payload = load_json(pass_completed)
    blocked_completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "BLOCKED",
        "--json",
    )
    blocked_payload = load_json(blocked_completed)

    pass_types = set(pass_payload["expectedEvidenceTypes"])
    blocked_types = set(blocked_payload["expectedEvidenceTypes"])
    assert "completed_pass" in pass_types
    assert "completed_blocked" in blocked_types


# ── evaluate: PASS evidence ─────────────────────────────────────


def _build_pass_jsonl_lines(script_path: str = SCRIPT_PATH) -> list[dict]:
    return [
        {
            "type": "user",
            "message": f"Run the {WORKFLOW} workflow.",
        },
        {
            "type": "skill_listing",
            "skills": [WORKFLOW],
        },
        {
            "type": "assistant",
            "tool": "Workflow",
            "input": {
                "scriptPath": script_path,
                "args": {"runId": "run-001"},
            },
        },
        {
            "type": "tool_result",
            "status": "async_launched",
            "run_id": "wf_c719aa99-826",
        },
        {
            "type": "subagent_start",
            "run_id": "wf_c719aa99-826",
            "subagent_id": "agent-1",
        },
        {
            "type": "subagent_output",
            "run_id": "wf_c719aa99-826",
            "subagent_id": "agent-1",
            "output": json.dumps(
                {"status": "PASS", "wroteFiles": False, "message": "Probe OK"}
            ),
        },
        {
            "type": "subagent_stop",
            "run_id": "wf_c719aa99-826",
            "subagent_id": "agent-1",
        },
        {
            "type": "notification",
            "content": (
                f'<workflow-result>{{"status":"PASS","workflow":"{WORKFLOW}",'
                f'"blockingIssues":[]}}</workflow-result>'
            ),
        },
    ]


def test_evaluate_classifies_complete_pass_evidence(tmp_path: Path) -> None:
    jsonl = tmp_path / "pass.jsonl"
    write_jsonl(jsonl, _build_pass_jsonl_lines())

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    assert completed.returncode == 0, f"stderr={completed.stderr}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["return_code"] == 0
    assert payload["evidence"]["skill_listing"] is True
    assert payload["evidence"]["workflow_invoked"] is True
    assert payload["evidence"]["async_launched"] is True
    assert payload["evidence"]["agent_started"] is True
    assert payload["evidence"]["schema_result"] is True
    assert payload["evidence"]["completed_pass"] is True
    assert payload["evidence"]["completed_blocked"] is False
    assert payload["evidence"]["environment_disabled"] is False
    assert "wf_c719aa99-826" in payload["runIds"]
    assert len(payload["matching_lines"]["skill_listing"]) > 0
    assert len(payload["matching_lines"]["completed_pass"]) > 0


def test_evaluate_binds_script_path_and_writes_report(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate"
    script = candidate_root / ".claude" / "workflows" / f"{WORKFLOW}.js"
    script.parent.mkdir(parents=True)
    script.write_text("return { status: 'PASS' }\n", encoding="utf-8")
    jsonl = tmp_path / "pass.jsonl"
    out = tmp_path / "evaluation.json"
    write_jsonl(jsonl, _build_pass_jsonl_lines(str(script.resolve())))

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--script-path", str(script.resolve()),
        "--candidate-root", str(candidate_root.resolve()),
        "--expected-status", "PASS",
        "--out", str(out),
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    payload = load_json(completed)
    assert payload["scriptPath"] == str(script.resolve())
    assert payload["scriptHash"].startswith("sha256:")
    assert payload["candidateHash"].startswith("sha256:")
    assert json.loads(out.read_text(encoding="utf-8"))["scriptPath"] == str(script.resolve())


def test_evaluate_binds_expected_script_path_without_candidate_root(tmp_path: Path) -> None:
    jsonl = tmp_path / "pass.jsonl"
    write_jsonl(jsonl, _build_pass_jsonl_lines())

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--scenario-id", "product-pass",
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    payload = load_json(completed)
    assert payload["scriptPath"] == SCRIPT_PATH
    assert payload["expectedStatus"] == "PASS"
    assert "candidateHash" not in payload


def test_evaluate_rejects_different_script_path(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate"
    script = candidate_root / ".claude" / "workflows" / f"{WORKFLOW}.js"
    script.parent.mkdir(parents=True)
    script.write_text("return { status: 'PASS' }\n", encoding="utf-8")
    jsonl = tmp_path / "pass.jsonl"
    write_jsonl(jsonl, _build_pass_jsonl_lines())

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--script-path", str(script.resolve()),
        "--candidate-root", str(candidate_root.resolve()),
        "--expected-status", "PASS",
        "--json",
    )

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["evidence"]["workflow_invoked"] is False
    assert any("workflow_invoked" in issue for issue in payload["blockingIssues"])


def test_evaluate_passes_with_required_agent_attribution(tmp_path: Path) -> None:
    jsonl = tmp_path / "pass-attribution.jsonl"
    records = _build_pass_jsonl_lines()
    records[4]["agentType"] = "workflowprogram-native-cn:requirement-clarification-lead"
    write_jsonl(jsonl, records)

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--required-agent-attribution", "workflowprogram-native-cn:requirement-clarification-lead",
        "--json",
    )

    assert completed.returncode == 0, f"stderr={completed.stderr}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["agentAttributions"] == ["workflowprogram-native-cn:requirement-clarification-lead"]
    assert payload["missingAgentAttributions"] == []


def test_evaluate_blocks_missing_required_agent_attribution(tmp_path: Path) -> None:
    jsonl = tmp_path / "missing-attribution.jsonl"
    write_jsonl(jsonl, _build_pass_jsonl_lines())

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--required-agent-attribution", "workflowprogram-native-cn:requirement-clarification-lead",
        "--json",
    )

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "INCONCLUSIVE"
    assert payload["missingAgentAttributions"] == [
        "workflowprogram-native-cn:requirement-clarification-lead"
    ]
    assert any("required agent attribution" in issue for issue in payload["blockingIssues"])


def test_evaluate_classifies_complete_blocked_evidence(tmp_path: Path) -> None:
    jsonl = tmp_path / "blocked.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_blocked"},
            {"type": "subagent_start", "run_id": "wf_blocked", "subagent_id": "agent-1"},
            {
                "type": "subagent_output",
                "run_id": "wf_blocked",
                "subagent_id": "agent-1",
                "output": json.dumps(
                    {"status": "BLOCKED_PROBE", "blockingIssues": ["Probe failed"]}
                ),
            },
            {
                "type": "notification",
                "content": (
                    f'<workflow-result>{{"status":"BLOCKED_PROBE",'
                    f'"workflow":"{WORKFLOW}",'
                    f'"blockingIssues":["Probe failed"]}}</workflow-result>'
                ),
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "BLOCKED",
        "--json",
    )

    assert completed.returncode == 0, f"stderr={completed.stderr}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["return_code"] == 0
    assert payload["evidence"]["completed_blocked"] is True
    assert payload["evidence"]["completed_pass"] is False
    assert payload["evidence"]["agent_started"] is True
    assert payload["evidence"]["schema_result"] is True


def test_evaluate_reports_inconclusive_for_missing_agent_evidence(tmp_path: Path) -> None:
    jsonl = tmp_path / "inconclusive.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_missing"},
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    assert completed.returncode == 1, f"stdout={completed.stdout}"
    payload = load_json(completed)
    assert payload["status"] == "INCONCLUSIVE"
    assert payload["evidence"]["skill_listing"] is True
    assert payload["evidence"]["workflow_invoked"] is True
    assert payload["evidence"]["async_launched"] is True
    assert payload["evidence"]["agent_started"] is False
    assert payload["evidence"]["completed_pass"] is False
    assert len(payload["blockingIssues"]) > 0


def test_evaluate_reports_unavailable_for_disabled_context(tmp_path: Path) -> None:
    jsonl = tmp_path / "unavailable.jsonl"
    write_jsonl(
        jsonl,
        [
            {
                "type": "tool_result",
                "error": "Workflow exists but is not enabled in this context.",
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    assert completed.returncode == 2, f"stdout={completed.stdout}"
    payload = load_json(completed)
    assert payload["status"] == "UNAVAILABLE"
    assert payload["evidence"]["environment_disabled"] is True
    assert len(payload["blockingIssues"]) > 0


def test_evaluate_uses_journal_jsonl_for_auxiliary_evidence(tmp_path: Path) -> None:
    main_jsonl = tmp_path / "main.jsonl"
    journal_jsonl = tmp_path / "journal.jsonl"

    write_jsonl(
        main_jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_journal"},
        ],
    )
    write_jsonl(
        journal_jsonl,
        [
            {
                "type": "subagent_start",
                "run_id": "wf_journal",
                "subagent_id": "agent-1",
            },
            {
                "type": "subagent_output",
                "run_id": "wf_journal",
                "subagent_id": "agent-1",
                "output": json.dumps(
                    {"status": "PASS", "wroteFiles": False, "message": "OK"}
                ),
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(main_jsonl),
        "--journal-jsonl", str(journal_jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["agent_started"] is True
    assert payload["evidence"]["schema_result"] is True


def test_evaluate_reports_mismatch_for_wrong_expected_status(tmp_path: Path) -> None:
    jsonl = tmp_path / "mismatch.jsonl"
    write_jsonl(jsonl, _build_pass_jsonl_lines())

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "BLOCKED",
        "--json",
    )

    payload = load_json(completed)
    assert ("completed_pass" in payload.get("blockingIssues", [""])[0]
            or payload["status"] != "PASS"
            or payload["return_code"] != 0)


def test_evaluate_rejects_missing_jsonl() -> None:
    completed = run_script(
        "evaluate",
        "--jsonl", "/nonexistent/file.jsonl",
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "INCONCLUSIVE"


def test_evaluate_rejects_invalid_expected_status() -> None:
    completed = run_script(
        "evaluate",
        "--jsonl", "/tmp/test.jsonl",
        "--workflow", WORKFLOW,
        "--expected-status", "INVALID",
    )
    assert completed.returncode != 0


def test_evaluate_includes_scenario_id_in_output(tmp_path: Path) -> None:
    jsonl = tmp_path / "scenario.jsonl"
    write_jsonl(jsonl, _build_pass_jsonl_lines())

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--scenario-id", "pass-smoke-001",
        "--json",
    )

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload.get("scenario") == "pass-smoke-001"


def test_evaluate_schema_result_requires_structured_output(tmp_path: Path) -> None:
    """A subagent that returned text but no structured JSON should not set schema_result."""
    jsonl = tmp_path / "no-schema.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_no_schema"},
            {
                "type": "subagent_start",
                "run_id": "wf_no_schema",
                "subagent_id": "agent-1",
            },
            {
                "type": "subagent_output",
                "run_id": "wf_no_schema",
                "subagent_id": "agent-1",
                "output": "just some text, not JSON",
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["agent_started"] is True
    assert payload["evidence"]["schema_result"] is False


def test_evaluate_does_not_match_pass_string_outside_workflow_context(tmp_path: Path) -> None:
    """Arbitrary 'PASS' strings without workflow context should not trigger completed_pass."""
    jsonl = tmp_path / "false-positive.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_fp"},
            {"type": "subagent_start", "subagent_id": "agent-1"},
            {
                "type": "subagent_output",
                "subagent_id": "agent-1",
                "output": json.dumps({"status": "PASS", "message": "OK"}),
            },
            # No workflow-level completion notification
            {
                "type": "user",
                "message": "This test PASS is just a word in a user message.",
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["completed_pass"] is False


def test_evaluate_reports_blocking_issues_from_evidence(tmp_path: Path) -> None:
    jsonl = tmp_path / "blocking.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {"type": "assistant", "tool": "Workflow", "input": {"scriptPath": SCRIPT_PATH}},
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_issues"},
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["status"] == "INCONCLUSIVE"
    assert len(payload["blockingIssues"]) > 0
    assert any("completion" in issue.lower() or "agent" in issue.lower()
               for issue in payload["blockingIssues"])


def test_evaluate_output_includes_schema_version_and_name(tmp_path: Path) -> None:
    jsonl = tmp_path / "envelope.jsonl"
    write_jsonl(jsonl, _build_pass_jsonl_lines())

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["schema_version"] == 1
    assert payload["schema_name"] == "native-workflow-interactive-smoke"


# ── evidence-profile ────────────────────────────────────────────


def test_packet_evidence_profile_full(tmp_path: Path) -> None:
    """Default evidence-profile is 'full'."""
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--json",
    )
    payload = load_json(completed)
    assert payload.get("evidenceProfile") == "full"


def test_packet_evidence_profile_early_blocker(tmp_path: Path) -> None:
    """Evidence-profile early-blocker is recorded in packet."""
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "BLOCKED",
        "--evidence-profile", "early-blocker",
        "--json",
    )
    payload = load_json(completed)
    assert payload.get("evidenceProfile") == "early-blocker"


def test_packet_rejects_early_blocker_with_pass_expected(tmp_path: Path) -> None:
    """early-blocker with PASS expected-status is rejected."""
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--evidence-profile", "early-blocker",
    )
    assert completed.returncode != 0


def test_packet_early_blocker_omits_agent_evidence_types(tmp_path: Path) -> None:
    """early-blocker expected evidence types exclude agent_started and schema_result."""
    full_completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--evidence-profile", "full",
        "--json",
    )
    early_completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "BLOCKED",
        "--evidence-profile", "early-blocker",
        "--json",
    )

    full_types = set(load_json(full_completed)["expectedEvidenceTypes"])
    early_types = set(load_json(early_completed)["expectedEvidenceTypes"])

    assert "agent_started" in full_types
    assert "schema_result" in full_types
    assert "agent_started" not in early_types
    assert "schema_result" not in early_types


def test_evaluate_early_blocker_success(tmp_path: Path) -> None:
    """early-blocker BLOCKED passes without agent/schema evidence."""
    jsonl = tmp_path / "early-blocker.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_early"},
            # No subagent lines – blocked before agent
            {
                "type": "notification",
                "content": (
                    f'<workflow-result>{{"status":"BLOCKED_INPUT",'
                    f'"workflow":"{WORKFLOW}",'
                    f'"blockingIssues":["Missing input"]}}</workflow-result>'
                ),
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "BLOCKED",
        "--evidence-profile", "early-blocker",
        "--json",
    )

    assert completed.returncode == 0, f"stderr={completed.stderr}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["evidence"]["completed_blocked"] is True
    assert payload["evidence"]["agent_started"] is False
    assert payload["evidence"]["schema_result"] is False


def test_evaluate_product_scriptpath_counts_plugin_skill_listing(tmp_path: Path) -> None:
    """Product scriptPath smoke uses WorkflowProgram plugin skills as discovery evidence."""
    jsonl = tmp_path / "product-scriptpath-blocked.jsonl"
    write_jsonl(
        jsonl,
        [
            {
                "type": "attachment",
                "attachment": {
                    "type": "skill_listing",
                    "content": (
                        "- workflowprogram-cn:workflowprogram-orchestrate: Route natural-language workflow requests\n"
                        "- workflowprogram-cn:validate-file: Validate generated workflow files"
                    ),
                },
            },
            {
                "type": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Workflow",
                        "input": {
                            "scriptPath": (
                                "D:\\Code\\WorkflowProgram-CN\\dist\\plugin\\workflows\\"
                                "workflowprogram-validate.js"
                            )
                        },
                    }
                ],
            },
            {
                "type": "user",
                "toolUseResult": {
                    "status": "async_launched",
                    "runId": "wf_product_blocked",
                },
            },
            {
                "type": "queue-operation",
                "content": (
                    '<result>{"status":"BLOCKED_INPUT",'
                    '"workflow":"workflowprogram-validate",'
                    '"blockingIssues":["Missing input"]}</result>'
                ),
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", "workflowprogram-validate",
        "--expected-status", "BLOCKED",
        "--evidence-profile", "early-blocker",
        "--json",
    )

    assert completed.returncode == 0, f"stdout={completed.stdout}\nstderr={completed.stderr}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["evidence"]["skill_listing"] is True
    assert payload["evidence"]["workflow_invoked"] is True
    assert payload["evidence"]["completed_blocked"] is True


def test_evaluate_agent_schema_profile_passes_without_completion(tmp_path: Path) -> None:
    """agent-schema profile proves subagent/schema coverage without a final completion status."""
    jsonl = tmp_path / "agent-schema.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Workflow",
                        "input": {"scriptPath": SCRIPT_PATH},
                    }
                ],
            },
            {
                "type": "user",
                "toolUseResult": {"status": "async_launched", "runId": "wf_agent_schema"},
            },
            {"type": "subagent_start", "run_id": "wf_agent_schema", "subagent_id": "agent-1"},
            {
                "type": "subagent_output",
                "run_id": "wf_agent_schema",
                "subagent_id": "agent-1",
                "output": json.dumps({"status": "PASS", "message": "schema ok"}),
            },
            {
                "type": "queue-operation",
                "content": f'<result>{{"status":"READY_FOR_GENERATION","workflow":"{WORKFLOW}"}}</result>',
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--evidence-profile", "agent-schema",
        "--json",
    )

    assert completed.returncode == 0, f"stdout={completed.stdout}\nstderr={completed.stderr}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["evidence"]["agent_started"] is True
    assert payload["evidence"]["schema_result"] is True
    assert payload["evidence"]["completed_pass"] is False
    assert payload["evidence"]["completed_blocked"] is False


def test_evaluate_completion_profile_passes_without_agent_schema(tmp_path: Path) -> None:
    """completion profile proves workflow completion without requiring subagent evidence."""
    jsonl = tmp_path / "completion-pass.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Workflow",
                        "input": {"scriptPath": SCRIPT_PATH},
                    }
                ],
            },
            {
                "type": "user",
                "toolUseResult": {"status": "async_launched", "runId": "wf_completion"},
            },
            {
                "type": "queue-operation",
                "content": f'<result>{{"status":"PASS","workflow":"{WORKFLOW}"}}</result>',
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--evidence-profile", "completion",
        "--json",
    )

    assert completed.returncode == 0, f"stdout={completed.stdout}\nstderr={completed.stderr}"
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["evidence"]["completed_pass"] is True
    assert payload["evidence"]["agent_started"] is False
    assert payload["evidence"]["schema_result"] is False


def test_evaluate_completion_profile_still_requires_completion(tmp_path: Path) -> None:
    """completion profile does not pass from launch evidence alone."""
    jsonl = tmp_path / "completion-missing.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Workflow",
                        "input": {"scriptPath": SCRIPT_PATH},
                    }
                ],
            },
            {
                "type": "user",
                "toolUseResult": {"status": "async_launched", "runId": "wf_completion_missing"},
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--evidence-profile", "completion",
        "--json",
    )

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "INCONCLUSIVE"
    assert any("completed_pass" in issue for issue in payload["blockingIssues"])


def test_evaluate_early_blocker_rejected_for_pass_expected(tmp_path: Path) -> None:
    """early-blocker with PASS expected-status is rejected."""
    completed = run_script(
        "evaluate",
        "--jsonl", str(tmp_path / "dummy.jsonl"),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--evidence-profile", "early-blocker",
    )
    assert completed.returncode != 0


def test_evaluate_output_includes_evidence_profile(tmp_path: Path) -> None:
    """Evaluate output includes evidenceProfile field."""
    jsonl = tmp_path / "profile.jsonl"
    write_jsonl(jsonl, _build_pass_jsonl_lines())

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--evidence-profile", "full",
        "--json",
    )
    payload = load_json(completed)
    assert payload.get("evidenceProfile") == "full"


# ── real journal format (started / result) ──────────────────────


def test_evaluate_real_journal_started_result_format(tmp_path: Path) -> None:
    """Journal JSONL with started/result types is correctly classified."""
    main_jsonl = tmp_path / "main.jsonl"
    journal_jsonl = tmp_path / "journal.jsonl"

    write_jsonl(
        main_jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_real_j"},
            {
                "type": "notification",
                "content": (
                    f'<workflow-result>{{"status":"PASS","workflow":"{WORKFLOW}",'
                    f'"blockingIssues":[]}}</workflow-result>'
                ),
            },
        ],
    )
    write_jsonl(
        journal_jsonl,
        [
            {"type": "started", "run_id": "wf_real_j", "agent_id": "agent-1"},
            {
                "type": "result",
                "run_id": "wf_real_j",
                "agent_id": "agent-1",
                "result": {"status": "PASS", "wroteFiles": False, "message": "OK"},
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(main_jsonl),
        "--journal-jsonl", str(journal_jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["agent_started"] is True, "started type should set agent_started"
    assert payload["evidence"]["schema_result"] is True, "result type with status should set schema_result"


# ── ultrawork in suggestedPrompt ────────────────────────────────


def test_packet_suggested_prompt_includes_ultrawork(tmp_path: Path) -> None:
    """suggestedPrompt includes ultrawork trigger keyword."""
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--json",
    )
    payload = load_json(completed)
    assert "ultrawork" in payload["suggestedPrompt"]


# ── absolute scriptPath validation ──────────────────────────────


def test_packet_rejects_relative_script_path() -> None:
    """--script-path must be absolute (POSIX or Windows)."""
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", "relative/path/workflow.js",
        "--expected-status", "PASS",
    )
    assert completed.returncode != 0
    assert "absolute" in completed.stdout.lower() or "absolute" in completed.stderr.lower()


def test_packet_accepts_windows_absolute_script_path() -> None:
    """Windows-style absolute path like C:\\... should be accepted."""
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", "C:\\Users\\test\\.claude\\workflows\\test.js",
        "--expected-status", "PASS",
        "--json",
    )
    assert completed.returncode == 0, f"stderr={completed.stderr}"


# ── packet stability (no generated_at) ──────────────────────────


def test_packet_no_generated_at(tmp_path: Path) -> None:
    """Packet does not contain generated_at for stable replay."""
    completed = run_script(
        "packet",
        "--workflow", WORKFLOW,
        "--script-path", SCRIPT_PATH,
        "--expected-status", "PASS",
        "--json",
    )
    payload = load_json(completed)
    assert "generated_at" not in payload


# ── missing journal returns INCONCLUSIVE ─────────────────────────


def test_evaluate_explicit_missing_journal_returns_inconclusive(tmp_path: Path) -> None:
    """Explicit --journal-jsonl to non-existent file returns INCONCLUSIVE, not silent."""
    jsonl = tmp_path / "main.jsonl"
    write_jsonl(jsonl, [{"type": "skill_listing", "skills": [WORKFLOW]}])

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--journal-jsonl", str(tmp_path / "nonexistent" / "journal.jsonl"),
    )

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "INCONCLUSIVE"
    assert any("journal" in issue.lower() for issue in payload.get("blockingIssues", []))


# ── structural evidence classification ──────────────────────────


def test_evaluate_structured_evidence_takes_precedence(tmp_path: Path) -> None:
    """Structural JSON parsing detects evidence, not just user prompt text."""
    jsonl = tmp_path / "structured.jsonl"
    write_jsonl(
        jsonl,
        [
            # Real JSON structures for evidence
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Workflow",
                        "input": {"scriptPath": SCRIPT_PATH},
                    }
                ],
            },
            {
                "type": "user",
                "message": {"role": "user", "content": [{"type": "tool_result"}]},
                "toolUseResult": {
                    "status": "async_launched",
                    "runId": "wf_structured",
                },
            },
            {
                "type": "subagent_start",
                "run_id": "wf_structured",
                "subagent_id": "agent-1",
            },
            {
                "type": "subagent_output",
                "run_id": "wf_structured",
                "subagent_id": "agent-1",
                "output": json.dumps({"status": "PASS", "message": "ok"}),
            },
            {
                "type": "notification",
                "content": f'<workflow-result>{{"status":"PASS","workflow":"{WORKFLOW}"}}</workflow-result>',
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["skill_listing"] is True
    assert payload["evidence"]["workflow_invoked"] is True
    assert payload["evidence"]["async_launched"] is True
    assert payload["evidence"]["agent_started"] is True
    assert payload["evidence"]["schema_result"] is True
    assert payload["evidence"]["completed_pass"] is True
    assert payload["return_code"] == 0


def test_evaluate_does_not_false_positive_on_user_text(tmp_path: Path) -> None:
    """User prompt text with PASS/Workflow/scriptPath must not trigger evidence."""
    jsonl = tmp_path / "user-text.jsonl"
    write_jsonl(
        jsonl,
        [
            # User mentions all trigger words – structurally not evidence
            {
                "type": "user",
                "message": f"PASS the {WORKFLOW} using Workflow with scriptPath {SCRIPT_PATH}",
            },
            # Only tool result with disabled context
            {
                "type": "tool_result",
                "error": "Workflow exists but is not enabled in this context.",
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["skill_listing"] is False, "user text must not trigger skill_listing"
    assert payload["evidence"]["workflow_invoked"] is False, "user text must not trigger workflow_invoked"
    assert payload["evidence"]["async_launched"] is False, "user text must not trigger async_launched"
    assert payload["evidence"]["completed_pass"] is False, "user text PASS must not trigger completed_pass"
    assert payload["evidence"]["environment_disabled"] is True


def test_evaluate_skill_listing_content_requires_exact_workflow_name(tmp_path: Path) -> None:
    """Structured skill listing content must not match workflow names as substrings."""
    jsonl = tmp_path / "skill-listing-substring.jsonl"
    write_jsonl(
        jsonl,
        [
            {
                "type": "skill_listing",
                "content": "development workflow catalog includes skill_listing metadata",
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", "develop",
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["skill_listing"] is False


def test_evaluate_structured_completion_from_queue_operation(tmp_path: Path) -> None:
    """Completion evidence from queue-operation type with result content."""
    jsonl = tmp_path / "queue-completion.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "skill_listing", "skills": [WORKFLOW]},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_queue"},
            {
                "type": "subagent_start",
                "run_id": "wf_queue",
                "subagent_id": "agent-1",
            },
            {
                "type": "subagent_output",
                "run_id": "wf_queue",
                "subagent_id": "agent-1",
                "output": json.dumps({"status": "PASS", "message": "ok"}),
            },
            {
                "type": "queue-operation",
                "content": f'<result>{{"status":"PASS","workflow":"{WORKFLOW}"}}</result>',
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["completed_pass"] is True


# ── enhanced run ID extraction ──────────────────────────────────


def test_evaluate_extracts_run_id_from_text(tmp_path: Path) -> None:
    """Run ID: wf_... text pattern is extracted."""
    jsonl = tmp_path / "runid-text.jsonl"
    write_jsonl(
        jsonl,
        [
            {"type": "user", "message": "Run ID: wf_c719aa99-826"},
            {
                "type": "assistant",
                "tool": "Workflow",
                "input": {"scriptPath": SCRIPT_PATH},
            },
            {"type": "tool_result", "status": "async_launched", "run_id": "wf_c719aa99-826"},
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert "wf_c719aa99-826" in payload["runIds"]


def test_evaluate_extracts_clean_run_id_from_escaped_tool_result_text(tmp_path: Path) -> None:
    """Escaped newlines after a textual Run ID must not become part of the ID."""
    jsonl = tmp_path / "runid-escaped-text.jsonl"
    write_jsonl(
        jsonl,
        [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "Workflow launched. Run ID: wf_c719aa99-826\\nTo resume after editing.",
                },
                "toolUseResult": {
                    "status": "async_launched",
                    "runId": "wf_c719aa99-826",
                },
            },
        ],
    )

    completed = run_script(
        "evaluate",
        "--jsonl", str(jsonl),
        "--workflow", WORKFLOW,
        "--expected-status", "PASS",
        "--json",
    )

    payload = load_json(completed)
    assert payload["evidence"]["async_launched"] is True
    assert payload["runIds"] == ["wf_c719aa99-826"]


# ── --args - stdin mode ─────────────────────────────────────────


def test_packet_stdin_args_suggested_prompt(tmp_path: Path) -> None:
    """--args - with stdin uses parsed JSON in suggestedPrompt, not raw '-'."""
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "packet",
         "--workflow", WORKFLOW,
         "--script-path", SCRIPT_PATH,
         "--expected-status", "PASS",
         "--args", "-",
         "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        input='{"runId":"run-001","targetRoot":"/tmp"}',
    )

    assert completed.returncode == 0, f"stderr={completed.stderr}"
    payload = load_json(completed)
    assert payload["args"] == {"runId": "run-001", "targetRoot": "/tmp"}
    assert "args: -" not in payload["suggestedPrompt"]
    assert '"runId"' in payload["suggestedPrompt"]
    assert '"targetRoot"' in payload["suggestedPrompt"]
