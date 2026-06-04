#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""M11 host-side interactive Native Workflow smoke harness.

Generates smoke execution packets and deterministically evaluates
Claude Code JSONL evidence without executing Claude or simulating
terminal interactions.

Usage:
    python build-native-interactive-smoke.py packet \
        --workflow <name> --script-path <path> --expected-status PASS|BLOCKED \
        [--args JSON] [--scenario-id ID] [--evidence-profile full|early-blocker|completion|agent-schema] \
        [--out PATH] [--json]

    python build-native-interactive-smoke.py evaluate \
        --jsonl <session.jsonl> --workflow <name> --expected-status PASS|BLOCKED \
        [--journal-jsonl <journal.jsonl>] [--scenario-id ID] \
        [--evidence-profile full|early-blocker|completion|agent-schema] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DISABLED_MESSAGE = "Workflow exists but is not enabled in this context."
VALID_EXPECTED_STATUSES = {"PASS", "BLOCKED"}
VALID_EVIDENCE_PROFILES = {"full", "early-blocker", "completion", "agent-schema"}
ULTRAWORK_TRIGGER = "ultrawork"
EVIDENCE_KEYS = [
    "skill_listing",
    "workflow_invoked",
    "async_launched",
    "agent_started",
    "schema_result",
    "completed_pass",
    "completed_blocked",
    "environment_disabled",
]

RUN_ID_EXPRS = [
    '"run_id":"',
    '"run_id": "',
    "'run_id':'",
    "'run_id': '",
    "run_id:",
]

SUBAGENT_START_MARKERS = [
    "subagent_start",
    "subagentStart",
    "SubagentStart",
]

SUBAGENT_OUTPUT_MARKERS = [
    "subagent_output",
    "subagentOutput",
    "SubagentOutput",
    "subagent_stop",
    "subagentStop",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M11 interactive Native Workflow smoke harness",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pkt = sub.add_parser("packet", help="Generate a smoke execution packet")
    pkt.add_argument("--workflow", required=True, help="Workflow name")
    pkt.add_argument("--script-path", required=True, help="Absolute path to the Native Workflow JS file")
    pkt.add_argument("--expected-status", required=True, choices=sorted(VALID_EXPECTED_STATUSES))
    pkt.add_argument("--args", default="{}", help='JSON args payload or "-" for stdin')
    pkt.add_argument("--scenario-id", default="", help="Optional scenario identifier")
    pkt.add_argument("--evidence-profile", default="full", choices=sorted(VALID_EVIDENCE_PROFILES),
                     help="Evidence classification profile (default: full)")
    pkt.add_argument("--required-agent-attribution", action="append", default=[],
                     help="Agent attribution that must be visible in evaluated JSONL")
    pkt.add_argument("--out", default="", help="Write packet JSON to file")
    pkt.add_argument("--json", action="store_true", help="Print packet JSON to stdout")

    ev = sub.add_parser("evaluate", help="Evaluate JSONL evidence")
    ev.add_argument("--jsonl", required=True, help="Claude Code session JSONL path")
    ev.add_argument("--journal-jsonl", default="", help="Optional journal JSONL for subagent evidence")
    ev.add_argument("--workflow", required=True, help="Workflow name")
    ev.add_argument("--expected-status", required=True, choices=sorted(VALID_EXPECTED_STATUSES))
    ev.add_argument("--scenario-id", default="", help="Optional scenario identifier")
    ev.add_argument("--evidence-profile", default="full", choices=sorted(VALID_EVIDENCE_PROFILES),
                    help="Evidence classification profile (default: full)")
    ev.add_argument("--required-agent-attribution", action="append", default=[],
                    help="Agent attribution that must be visible in session or journal JSONL")
    ev.add_argument("--json", action="store_true", help="Print JSON evaluation result")

    return parser.parse_args()


# ── validation ──────────────────────────────────────────────────


def _validate_absolute_path(path_str: str) -> None:
    """Raise ValueError if path is not absolute (POSIX or Windows)."""
    if not path_str:
        raise ValueError("scriptPath must not be empty")
    if path_str.startswith("/"):
        return  # POSIX absolute / or /mnt/...
    if len(path_str) >= 2 and path_str[1] == ":" and path_str[0].isalpha():
        return  # Windows absolute C:\... or D:\...
    raise ValueError(
        f"scriptPath must be an absolute path (POSIX /… or Windows X:\\…): {path_str}"
    )


# ── packet ─────────────────────────────────────────────────────


def _build_prerequisites(expected_status: str) -> List[str]:
    common = [
        "Claude Code installed and logged in (claude auth status reports loggedIn=true)",
        "CLAUDE_CODE_WORKFLOWS=1 or equivalent feature flag enabled",
        "Terminal with WSL or native Linux/macOS session (Windows native terminal in WSL login-shell mode)",
        "Target workflow JS file accessible at the specified absolute scriptPath",
    ]
    if expected_status == "BLOCKED":
        common.append(
            "Workflow is expected to produce BLOCKED status; "
            "capture both PASS and BLOCKED JSONL for comparison"
        )
    return common


def _build_suggested_prompt(workflow: str, script_path: str, args_payload: dict) -> str:
    args_part = ""
    if args_payload:
        args_part = f',\n  args: {json.dumps(args_payload, indent=2, ensure_ascii=False)}'
    return (
        f"{ULTRAWORK_TRIGGER}\n\n"
        f"Workflow({{\n"
        f'  scriptPath: "{script_path}"{args_part}\n'
        f"}})\n\n"
        f"# The '{ULTRAWORK_TRIGGER}' keyword triggers an ultrawork_request attachment so Claude\n"
        f"# invokes the Workflow tool with scriptPath/args directly. Do NOT manually type the\n"
        f"# Workflow call — let the attachment handle it.\n"
        f"# After completion, observe the /workflows panel.\n"
        f"# Save the session JSONL from:\n"
        f"#   ~/.claude/projects/<project-hash>/<session-id>.jsonl\n"
        f"# And optionally the journal from:\n"
        f"#   ~/.claude/projects/<project-hash>/<session-id>/subagents/workflows/<run-id>/journal.jsonl"
    )


def _build_expected_evidence_types(expected_status: str, profile: str = "full") -> List[str]:
    if profile in {"early-blocker", "completion"}:
        evidence: List[str] = [
            "skill_listing",
            "workflow_invoked",
            "async_launched",
        ]
    elif profile == "agent-schema":
        return [
            "skill_listing",
            "workflow_invoked",
            "async_launched",
            "agent_started",
            "schema_result",
        ]
    else:
        evidence = [
            "skill_listing",
            "workflow_invoked",
            "async_launched",
            "agent_started",
            "schema_result",
        ]
    if expected_status == "PASS":
        evidence.append("completed_pass")
    else:
        evidence.append("completed_blocked")
    return evidence


def _build_manual_review_hints() -> List[str]:
    return [
        "Verify the session JSONL was captured from a real interactive Claude Code session, not synthesized.",
        "Check that skill_listing includes the expected workflow name.",
        "Confirm the Workflow tool was invoked with a valid absolute scriptPath.",
        "Confirm async_launched was returned with a non-empty run_id.",
        "Verify subagent_start and subagent_output markers exist for at least one agent.",
        "Verify the subagent output contains structured JSON with a status field.",
        "Verify the workflow completion notification contains the expected workflow name and status.",
        "If expected-status is BLOCKED, confirm the final status is a BLOCKED_* variant, not PASS.",
    ]


def run_packet(args: argparse.Namespace) -> int:
    # Validate absolute path
    try:
        _validate_absolute_path(args.script_path)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    # Validate evidence-profile + expected-status compatibility
    if args.evidence_profile == "early-blocker" and args.expected_status != "BLOCKED":
        print(json.dumps({
            "error": "evidence-profile 'early-blocker' is only valid with expected-status BLOCKED"
        }), file=sys.stderr)
        return 1

    args_payload: Dict[str, Any] = {}
    read_from_stdin = args.args == "-"
    if read_from_stdin:
        try:
            args_payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"invalid JSON from stdin: {exc}"}), file=sys.stderr)
            return 1
    else:
        try:
            args_payload = json.loads(args.args)
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"invalid --args JSON: {exc}"}), file=sys.stderr)
            return 1

    if not isinstance(args_payload, dict):
        print(json.dumps({"error": "--args must be a JSON object"}), file=sys.stderr)
        return 1

    expected = args.expected_status.upper()
    packet = {
        "schema_version": 1,
        "schema_name": "native-workflow-interactive-smoke",
        "command": "packet",
        "evidenceProfile": args.evidence_profile,
        "workflow": args.workflow,
        "scriptPath": args.script_path,
        "args": args_payload,
        "expectedStatus": expected,
        "scenarioId": args.scenario_id or None,
        "executionPrerequisites": _build_prerequisites(expected),
        "suggestedPrompt": _build_suggested_prompt(
            args.workflow, args.script_path, args_payload
        ),
        "expectedEvidenceTypes": _build_expected_evidence_types(expected, args.evidence_profile),
        "requiredAgentAttributions": args.required_agent_attribution,
        "manualReviewHints": _build_manual_review_hints(),
        "computerUseBoundary": "manual-wsl-execution-supported",
        "computerUseNote": (
            "Computer Use terminal-driving adapter is deferred until an allowed "
            "non-terminal integration exists. Current supported mode: manual WSL "
            "login-shell execution followed by deterministic JSONL evaluation."
        ),
        "disclaimer": (
            "This packet has NOT been executed. It describes execution prerequisites, "
            "suggested prompts, expected evidence types, and manual review hints. "
            "Use the 'evaluate' subcommand against captured JSONL to produce a "
            "deterministic evaluation result."
        ),
    }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json or not args.out:
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0


# ── evaluate ───────────────────────────────────────────────────


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_jsonl(path: Path) -> List[str]:
    try:
        return path.resolve().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to read {path}: {exc}") from exc


def _try_parse_json(text: str) -> Optional[dict]:
    """Try to parse a line as a JSON object. Returns None on failure."""
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _walk_dicts(value: Any):
    """Yield nested dictionaries from one parsed JSONL record."""

    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_dicts(nested)


def _record_agent_attribution(value: Any, line_number: int, attributions: set, matching_lines: Dict[str, List[int]]) -> None:
    """Record one agent attribution value with stable line evidence."""

    if not isinstance(value, str):
        return
    attribution = value.strip()
    if not attribution:
        return
    attributions.add(attribution)
    matching_lines.setdefault(attribution, []).append(line_number)


def _collect_agent_attributions(record: dict, line_number: int, attributions: set, matching_lines: Dict[str, List[int]]) -> None:
    """Collect Agent attribution fields from one parsed JSONL record."""

    for node in _walk_dicts(record):
        for key in ("attributionAgent", "agentType", "agent_type"):
            _record_agent_attribution(node.get(key), line_number, attributions, matching_lines)


def _collect_agent_attributions_from_text(
    line: str,
    line_number: int,
    attributions: set,
    matching_lines: Dict[str, List[int]],
) -> None:
    """Fallback extraction for textual JSONL fragments."""

    for match in re.finditer(
        r'(?:attributionAgent|agentType|agent_type)["\'\s:=]+([A-Za-z0-9_.:-]+)',
        line,
    ):
        _record_agent_attribution(match.group(1), line_number, attributions, matching_lines)


def _classify_line_structural(record: dict, workflow: str) -> set:
    """Detect evidence keys from a parsed JSON record using structure.

    Returns a set of evidence key names matched structurally.
    Does NOT handle completion (completed_pass/blocked) or environment_disabled,
    which are checked separately to re-use existing logic.
    """
    keys: set = set()
    for node in _walk_dicts(record):
        rt = node.get("type")

        # Real sessions wrap listing records inside attachment objects. Product
        # workflow JS is launched by scriptPath and is not registered as a saved
        # Workflow({name}) entry, so WorkflowProgram plugin skills also count as
        # discovery evidence for workflowprogram-* smoke.
        if rt == "skill_listing":
            skills = node.get("skills") or node.get("names") or []
            content = node.get("content", "")
            if (isinstance(skills, list) and workflow in skills) or (
                isinstance(content, str) and workflow in content
            ):
                keys.add("skill_listing")
            elif workflow.startswith("workflowprogram-") and _has_workflowprogram_skill_listing(
                skills, content
            ):
                keys.add("skill_listing")

        # Real sessions wrap tool_use records inside assistant message.content.
        if node.get("tool") == "Workflow" or (
            rt == "tool_use" and node.get("name") == "Workflow"
        ):
            inp = node.get("input", {})
            script_path = inp.get("scriptPath") if isinstance(inp, dict) else None
            if isinstance(script_path, str) and workflow in script_path:
                keys.add("workflow_invoked")

        # Real sessions store this under the outer user event's toolUseResult.
        if node.get("status") == "async_launched" and (
            rt == "tool_result"
            or "runId" in node
            or "run_id" in node
            or "taskId" in node
            or "transcriptDir" in node
        ):
            keys.add("async_launched")

        if rt in ("subagent_start", "started"):
            keys.add("agent_started")

        if rt == "subagent_output":
            output = node.get("output")
            if isinstance(output, str):
                try:
                    nested = json.loads(output)
                    if isinstance(nested, dict) and "status" in nested:
                        keys.add("schema_result")
                except (json.JSONDecodeError, ValueError):
                    pass
            elif isinstance(output, dict) and "status" in output:
                keys.add("schema_result")
        if rt == "result":
            res = node.get("result")
            if isinstance(res, dict) and "status" in res:
                keys.add("schema_result")

    return keys


def _detect_completion_structural(record: dict, workflow: str, status: str) -> bool:
    """Check if a parsed JSON record structurally contains a workflow completion."""
    rt = record.get("type")
    if rt in ("notification", "task-notification", "queue-operation"):
        text_content = record.get("content", "")
        if isinstance(text_content, str):
            text = text_content.replace('\\"', '"')
            normalized = text.replace(" ", "")
            if "<workflow-result>" in text or "<result>" in text:
                has_workflow_str = workflow in text or workflow in normalized
                return has_workflow_str and _status_match_plain(normalized, status)
    return False


def _has_workflowprogram_skill_listing(skills: Any, content: Any) -> bool:
    """Return true when skill_listing exposes WorkflowProgram product skills."""

    skill_names: list[str] = []
    if isinstance(skills, list):
        skill_names.extend(str(item) for item in skills)
    if isinstance(content, str):
        if "workflowprogram-cn:" in content or "workflowprogram-orchestrate" in content:
            return True
    return any(
        name.startswith("workflowprogram-cn:")
        or name.startswith("workflowprogram-")
        or "workflowprogram-orchestrate" in name
        for name in skill_names
    )


def _status_match_plain(normalized_text: str, expected_status: str) -> bool:
    """Check if normalized text contains a matching status value.
    Like _status_match but without requiring workflow name check.
    """
    if expected_status == "PASS":
        return '"status":"PASS"' in normalized_text
    return '"status":"BLOCKED' in normalized_text


def _extract_run_ids(lines: List[str]) -> List[str]:
    seen: set[str] = set()
    for line in lines:
        # Pattern 1: known run_id JSON key markers
        for expr in RUN_ID_EXPRS:
            idx = line.find(expr)
            if idx == -1:
                continue
            rest = line[idx + len(expr):]
            end = len(rest)
            for delim in ('"', "'", ",", " ", "\t", "}", "\n"):
                pos = rest.find(delim)
                if pos != -1 and pos < end:
                    end = pos
            match = re.match(r"wf_[A-Za-z0-9_-]+", rest[:end].strip())
            if match:
                seen.add(match.group(0))
        # Pattern 2: "Run ID: wf_..." or "Run ID: wf_..." text
        for match in re.finditer(r"Run\s*[Ii][Dd]\s*:\s*(wf_[A-Za-z0-9_-]+)", line):
            seen.add(match.group(1))
        # Pattern 3: toolUseResult.runId in parsed JSON
        record = _try_parse_json(line)
        if record:
            _dfs_extract_run_id(record, seen)
    return sorted(seen)


def _dfs_extract_run_id(obj: Any, seen: set) -> None:
    """Depth-first search for run_id / runId / r fields starting with wf_."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("run_id", "runId", "r") and isinstance(value, str):
                match = re.fullmatch(r"wf_[A-Za-z0-9_-]+", value)
                if match:
                    seen.add(match.group(0))
            else:
                _dfs_extract_run_id(value, seen)
    elif isinstance(obj, list):
        for item in obj:
            _dfs_extract_run_id(item, seen)


def _is_structured_output(text: str) -> bool:
    """Check if subagent output contains recognizable structured JSON with a status field.

    First tries to parse the whole line as JSON and look for nested output fields
    (common in subagent_output JSONL records). Falls back to embedded JSON regex.
    """
    if not text or not text.strip():
        return False
    stripped = text.strip()
    # Strategy 1: line is a full JSONL record with an "output" field
    try:
        record = json.loads(stripped)
        if isinstance(record, dict):
            output_value = record.get("output")
            if isinstance(output_value, str):
                try:
                    nested = json.loads(output_value)
                    if isinstance(nested, dict) and "status" in nested:
                        return True
                except (json.JSONDecodeError, ValueError):
                    pass
            # Also check for direct status at top level
            if "status" in record:
                return True
    except (json.JSONDecodeError, ValueError):
        pass
    # Strategy 2: try direct JSON parse (for embedded objects)
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict) and "status" in obj:
            return True
    except (json.JSONDecodeError, ValueError):
        pass
    # Strategy 3: regex for embedded JSON objects with status field
    for match in re.finditer(r'\{[^{}]*"status"\s*:\s*"[^"]*"[^{}]*\}', stripped):
        try:
            obj = json.loads(match.group())
            if isinstance(obj, dict) and "status" in obj:
                return True
        except (json.JSONDecodeError, ValueError):
            pass
    return False


def _has_workflow_result_in_line(line: str, workflow: str, status: str) -> bool:
    """Check if a line contains a workflow completion result.

    For PASS: require exact '"status":"PASS"' match.
    For BLOCKED: match status values starting with BLOCKED (e.g. BLOCKED_PROBE).

    Uses multiple strategies to avoid false positives:
    1. Look for workflow-result tags
    2. Look for completion notifications with workflow name
    """
    text = line.replace('\\"', '"')
    normalized = text.replace(" ", "")

    # Pattern 1: workflow-result notification
    if "workflow-result" in text or "workflowResult" in text:
        if workflow in text:
            if _status_match(normalized, status):
                return True

    # Pattern 2: completion notification with workflow name
    if any(marker in text.lower() for marker in ("completion", "notification", "task_complete")):
        if workflow in text:
            if _status_match(normalized, status):
                return True

    # Pattern 3: Direct result object with workflow name and matching status
    if workflow in normalized and '"workflow":"' in normalized:
        if _status_match(normalized, status):
            return True

    return False


def _status_match(normalized_text: str, expected_status: str) -> bool:
    """Check if a normalized (no-space) JSON text contains the expected status value.

    For PASS: require exact '"status":"PASS"' (with closing quote).
    For BLOCKED: match any status starting with BLOCKED (e.g. BLOCKED_PROBE).
    """
    if expected_status == "PASS":
        return '"status":"PASS"' in normalized_text
    # For BLOCKED: match "status":"BLOCKED" as a prefix match
    return '"status":"BLOCKED' in normalized_text


def classify_evidence(
    jsonl_path: Path,
    workflow: str,
    journal_jsonl_path: Optional[Path] = None,
) -> Dict[str, Any]:
    main_lines = _read_jsonl(jsonl_path)
    extra_lines: List[str] = []
    journal_path_str: Optional[str] = None
    if journal_jsonl_path is not None:
        try:
            extra_lines = _read_jsonl(journal_jsonl_path)
            journal_path_str = str(journal_jsonl_path.resolve())
        except FileNotFoundError:
            pass

    all_lines = main_lines + extra_lines

    evidence: Dict[str, bool] = {key: False for key in EVIDENCE_KEYS}
    matching_lines: Dict[str, List[int]] = {key: [] for key in EVIDENCE_KEYS}
    agent_attributions: set[str] = set()
    agent_attribution_lines: Dict[str, List[int]] = {}

    # ── Structural detection first ──────────────────────────
    for line_number, line in enumerate(main_lines, start=1):
        record = _try_parse_json(line)
        is_user_message = bool(record and record.get("type") == "user")

        if record is not None:
            _collect_agent_attributions(record, line_number, agent_attributions, agent_attribution_lines)

            # Structural evidence keys
            struct_keys = _classify_line_structural(record, workflow)
            for key in struct_keys:
                evidence[key] = True
                matching_lines[key].append(line_number)

            # Structural completion detection
            if _detect_completion_structural(record, workflow, "PASS"):
                evidence["completed_pass"] = True
                matching_lines["completed_pass"].append(line_number)
            if _detect_completion_structural(record, workflow, "BLOCKED"):
                evidence["completed_blocked"] = True
                matching_lines["completed_blocked"].append(line_number)

            # environment_disabled in error field
            error_val = record.get("error", "")
            if isinstance(error_val, str) and DISABLED_MESSAGE in error_val:
                evidence["environment_disabled"] = True
                matching_lines["environment_disabled"].append(line_number)

            # Prevent text-substring false positives from user messages
            if is_user_message:
                continue

        _collect_agent_attributions_from_text(line, line_number, agent_attributions, agent_attribution_lines)

        # ── Fallback substring matching (NOT for user messages) ─
        # skill_listing fallback
        if not evidence["skill_listing"] and workflow in line and "skill_listing" in line:
            evidence["skill_listing"] = True
            matching_lines["skill_listing"].append(line_number)

        # workflow_invoked fallback
        if not evidence["workflow_invoked"] and workflow in line and "Workflow" in line and "scriptPath" in line:
            evidence["workflow_invoked"] = True
            matching_lines["workflow_invoked"].append(line_number)

        # async_launched fallback
        if not evidence["async_launched"] and "async_launched" in line:
            evidence["async_launched"] = True
            matching_lines["async_launched"].append(line_number)

        # agent_started fallback (main lines)
        if not evidence["agent_started"]:
            for marker in SUBAGENT_START_MARKERS:
                if marker in line:
                    evidence["agent_started"] = True
                    matching_lines["agent_started"].append(line_number)
                    break

        # schema_result fallback (main lines)
        if not evidence["schema_result"]:
            for marker in SUBAGENT_OUTPUT_MARKERS:
                if marker in line:
                    if _is_structured_output(line):
                        evidence["schema_result"] = True
                        matching_lines["schema_result"].append(line_number)
                        break

        # completed_pass fallback
        if not evidence["completed_pass"]:
            if _has_workflow_result_in_line(line, workflow, "PASS"):
                evidence["completed_pass"] = True
                matching_lines["completed_pass"].append(line_number)

        # completed_blocked fallback
        if not evidence["completed_blocked"]:
            if _has_workflow_result_in_line(line, workflow, "BLOCKED"):
                evidence["completed_blocked"] = True
                matching_lines["completed_blocked"].append(line_number)

        # environment_disabled fallback
        if not evidence["environment_disabled"] and DISABLED_MESSAGE in line:
            evidence["environment_disabled"] = True
            matching_lines["environment_disabled"].append(line_number)

    # ── Journal (extra) lines ───────────────────────────────
    for line_number, line in enumerate(extra_lines, start=1):
        record = _try_parse_json(line)
        if record is not None:
            _collect_agent_attributions(record, -line_number, agent_attributions, agent_attribution_lines)

        if record is not None:
            # Structural: "started" type → agent_started
            if not evidence["agent_started"] and record.get("type") == "started":
                evidence["agent_started"] = True
                matching_lines["agent_started"].append(-line_number)

            # Structural: "result" type with result.status → schema_result
            if not evidence["schema_result"] and record.get("type") == "result":
                res = record.get("result")
                if isinstance(res, dict) and "status" in res:
                    evidence["schema_result"] = True
                    matching_lines["schema_result"].append(-line_number)

        # Fallback: substring subagent_start markers
        if not evidence["agent_started"]:
            for marker in SUBAGENT_START_MARKERS:
                if marker in line:
                    evidence["agent_started"] = True
                    matching_lines["agent_started"].append(-line_number)
                    break

        # Fallback: substring subagent_output markers
        if not evidence["schema_result"]:
            for marker in SUBAGENT_OUTPUT_MARKERS:
                if marker in line:
                    if _is_structured_output(line):
                        evidence["schema_result"] = True
                        matching_lines["schema_result"].append(-line_number)
                        break

        _collect_agent_attributions_from_text(line, -line_number, agent_attributions, agent_attribution_lines)

    run_ids = _extract_run_ids(all_lines)

    return {
        "evidence": evidence,
        "matching_lines": matching_lines,
        "agent_attributions": sorted(agent_attributions),
        "agent_attribution_lines": agent_attribution_lines,
        "run_ids": sorted(set(run_ids)),
        "journal_jsonl": journal_path_str,
        "main_line_count": len(main_lines),
        "extra_line_count": len(extra_lines),
    }


def _determine_status(
    evidence: Dict[str, bool],
    expected_status: str,
    profile: str = "full",
) -> Dict[str, Any]:
    blocking: List[str] = []

    if evidence["environment_disabled"]:
        return {
            "status": "UNAVAILABLE",
            "return_code": 2,
            "blockingIssues": [
                "Workflow tool is not enabled in this context. "
                "Ensure CLAUDE_CODE_WORKFLOWS=1 or equivalent feature flag is set."
            ],
        }

    # Check expected evidence chain (varies by profile)
    if not evidence["skill_listing"]:
        blocking.append("Missing evidence: skill_listing (workflow not listed in plugin skills)")
    if not evidence["workflow_invoked"]:
        blocking.append("Missing evidence: workflow_invoked (Workflow({scriptPath}) call not found)")
    if not evidence["async_launched"]:
        blocking.append("Missing evidence: async_launched (workflow not launched asynchronously)")

    if profile not in {"early-blocker", "completion"}:
        if not evidence["agent_started"]:
            blocking.append("Missing evidence: agent_started (no subagent started in session or journal)")
        if not evidence["schema_result"]:
            blocking.append(
                "Missing evidence: schema_result (no structured JSON output from subagent with status field)"
            )

    if profile == "agent-schema":
        if evidence["completed_pass"] and evidence["completed_blocked"]:
            blocking.append("Unexpected evidence: both completed_pass and completed_blocked are present")
        if blocking:
            return {
                "status": "INCONCLUSIVE",
                "return_code": 1,
                "blockingIssues": blocking,
            }
        return {
            "status": "PASS",
            "return_code": 0,
            "blockingIssues": [],
        }

    if expected_status == "PASS":
        if not evidence["completed_pass"]:
            blocking.append("Missing evidence: completed_pass (no workflow completion with PASS status)")
        if evidence["completed_blocked"]:
            blocking.append("Unexpected evidence: completed_blocked present when expected-status is PASS")
    else:
        if not evidence["completed_blocked"]:
            blocking.append("Missing evidence: completed_blocked (no workflow completion with BLOCKED status)")
        if evidence["completed_pass"]:
            blocking.append("Unexpected evidence: completed_pass present when expected-status is BLOCKED")

    if blocking:
        return {
            "status": "INCONCLUSIVE",
            "return_code": 1,
            "blockingIssues": blocking,
        }

    return {
        "status": "PASS",
        "return_code": 0,
        "blockingIssues": [],
    }


def run_evaluate(args: argparse.Namespace) -> int:
    # Validate evidence-profile + expected-status compatibility
    if args.evidence_profile == "early-blocker" and args.expected_status != "BLOCKED":
        payload = {
            "schema_version": 1,
            "schema_name": "native-workflow-interactive-smoke",
            "status": "INCONCLUSIVE",
            "return_code": 1,
            "error": "evidence-profile 'early-blocker' is only valid with expected-status BLOCKED",
            "blockingIssues": [
                "evidence-profile 'early-blocker' is only valid with expected-status BLOCKED"
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    jsonl_path = Path(args.jsonl)
    try:
        jsonl_path.resolve().read_text(encoding="utf-8")
    except FileNotFoundError:
        payload = {
            "schema_version": 1,
            "schema_name": "native-workflow-interactive-smoke",
            "status": "INCONCLUSIVE",
            "return_code": 1,
            "error": f"JSONL file not found: {args.jsonl}",
            "evidenceProfile": args.evidence_profile,
            "blockingIssues": [f"JSONL file not found: {args.jsonl}"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "schema_name": "native-workflow-interactive-smoke",
            "status": "INCONCLUSIVE",
            "return_code": 1,
            "error": str(exc),
            "evidenceProfile": args.evidence_profile,
            "blockingIssues": [f"Failed to read JSONL: {exc}"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    journal_path: Optional[Path] = None
    if args.journal_jsonl:
        journal_path = Path(args.journal_jsonl)
        if not journal_path.exists():
            payload = {
                "schema_version": 1,
                "schema_name": "native-workflow-interactive-smoke",
                "status": "INCONCLUSIVE",
                "return_code": 1,
                "error": f"Journal JSONL not found: {args.journal_jsonl}",
                "evidenceProfile": args.evidence_profile,
                "blockingIssues": [
                    f"Specified --journal-jsonl does not exist: {args.journal_jsonl}"
                ],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1

    expected = args.expected_status.upper()

    try:
        result = classify_evidence(jsonl_path, args.workflow, journal_path)
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "schema_name": "native-workflow-interactive-smoke",
            "status": "INCONCLUSIVE",
            "return_code": 1,
            "error": str(exc),
            "evidenceProfile": args.evidence_profile,
            "blockingIssues": [f"Evidence classification failed: {exc}"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    status_result = _determine_status(result["evidence"], expected, args.evidence_profile)
    required_agent_attributions = args.required_agent_attribution or []
    missing_agent_attributions = [
        attribution
        for attribution in required_agent_attributions
        if attribution not in result["agent_attributions"]
    ]
    if missing_agent_attributions and status_result["status"] != "UNAVAILABLE":
        status_result = {
            "status": "INCONCLUSIVE",
            "return_code": 1,
            "blockingIssues": [
                *status_result["blockingIssues"],
                *[
                    f"Missing required agent attribution: {attribution}"
                    for attribution in missing_agent_attributions
                ],
            ],
        }

    payload = {
        "schema_version": 1,
        "schema_name": "native-workflow-interactive-smoke",
        "status": status_result["status"],
        "return_code": status_result["return_code"],
        "evidenceProfile": args.evidence_profile,
        "scenario": args.scenario_id or None,
        "workflow": args.workflow,
        "jsonl": str(jsonl_path.resolve()),
        "journalJsonl": result["journal_jsonl"],
        "runIds": result["run_ids"],
        "evidence": result["evidence"],
        "matching_lines": result["matching_lines"],
        "agentAttributions": result["agent_attributions"],
        "agentAttributionLines": result["agent_attribution_lines"],
        "requiredAgentAttributions": required_agent_attributions,
        "missingAgentAttributions": missing_agent_attributions,
        "blockingIssues": status_result["blockingIssues"],
        "lineCounts": {
            "main": result["main_line_count"],
            "journal": result["extra_line_count"],
        },
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return status_result["return_code"]


# ── main ───────────────────────────────────────────────────────


def main() -> int:
    args = _parse_args()
    if args.command == "packet":
        return run_packet(args)
    if args.command == "evaluate":
        return run_evaluate(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
