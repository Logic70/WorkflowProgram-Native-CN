#!/usr/bin/env python3
"""Guard foreground tool use after a WorkflowProgram Native handoff.

The Native Workflow JS control plane returns re-entrant states such as
NEEDS_USER_INPUT, READY_FOR_GENERATION, BLOCKED_GENERATION, READY_FOR_APPLY, or
PASS. The foreground assistant must honor that state instead of editing target
workflow assets directly. This script provides two deterministic pieces:

* record: persist the latest handoff state under TARGET_ROOT/.workflowprogram.
* check: run as a Claude Code PreToolUse hook and block unsafe foreground writes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


STATE_RELATIVE_PATH = Path(".workflowprogram") / "session-state.json"
SCHEMA_NAME = "workflowprogram-foreground-guard-state"
SCHEMA_VERSION = 1
MAX_UNBOUND_STATE_AGE_SECONDS = 30 * 60

MANAGED_PREFIXES = (
    ".claude/",
    ".workflowprogram/design/",
    ".workflowprogram/runtime/",
    ".workflowprogram/runs/",
    ".workflowprogram/managed-files.json",
)

DIRECT_FILE_WRITE_TOOLS = {
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
}

AGENT_TOOLS = {
    "Agent",
    "Task",
}

WPN_INTENT_PATTERNS = (
    r"\bWPN\b",
    r"\bWorkflowProgram\b",
    r"WorkflowProgram\s+Native",
    r"workflowprogram-native",
    r"Native\s+Workflow\s+JS",
    r"native\s+workflow",
    r"产品\s*Workflow",
)

WRITE_COMMAND_PATTERNS = (
    r"\bgit\s+add\b",
    r"\bgit\s+commit\b",
    r"\bgit\s+rm\b",
    r"\brm\s+",
    r"\bmv\s+",
    r"\bcp\s+",
    r"\bdel\s+",
    r"\berase\s+",
    r"\bmove-item\b",
    r"\bcopy-item\b",
    r"\bremove-item\b",
    r"\bset-content\b",
    r"\badd-content\b",
    r"\bnew-item\b",
    r"\bout-file\b",
    r"\btouch\b",
    r"\bmkdir\b",
    r"\btee\b",
    r">",
)

EMBEDDED_WRITE_PATTERNS = (
    r"\bopen\s*\([^)]*,\s*['\"][^'\"]*[wax+][^'\"]*['\"]",
    r"\.write_text\s*\(",
    r"\.write_bytes\s*\(",
    r"\bwrite_text\s*\(",
    r"\bwrite_bytes\s*\(",
    r"\bwriteFile(?:Sync)?\s*\(",
    r"\bappendFile(?:Sync)?\s*\(",
    r"\bcreateWriteStream\s*\(",
    r"\bSet-Content\b",
    r"\bAdd-Content\b",
    r"\bOut-File\b",
    r"\bNew-Item\b",
)

CONTROLLED_COMMANDS_BY_STATUS = {
    "READY_FOR_GENERATION": (
        "workflowprogram-continue.py",
    ),
    "READY_FOR_VALIDATION": (
        "validate-native-workflow-js.py",
        "build-native-develop-evidence.py",
    ),
    "READY_FOR_SMOKE": (
        "build-native-interactive-smoke.py",
        "build-native-develop-evidence.py",
    ),
    "READY_FOR_APPLY": (
        "managed-assets.py",
        "build-native-develop-evidence.py",
    ),
}

SIDE_EFFECT_COMMAND_TOKENS = (
    "generate-native-workflow.py",
    "build-native-develop-evidence.py",
    "workflowprogram-continue.py",
    "validate-native-workflow-js.py",
    "build-native-interactive-smoke.py",
    "managed-assets.py",
)


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def path_identity(value: str | os.PathLike[str] | None) -> str:
    if not value:
        return ""
    raw = str(value).strip().replace("\\", "/").rstrip("/")
    match = re.match(r"^/mnt/([A-Za-z])/(.*)$", raw)
    if match:
        return f"{match.group(1).lower()}:/{match.group(2)}"
    if re.match(r"^[A-Za-z]:/", raw):
        return raw[0].lower() + raw[1:]
    return raw


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
    except OSError:
        return path_identity(child) == path_identity(parent) or path_identity(child).startswith(path_identity(parent) + "/")


def normalize_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
        return relative.as_posix()
    except ValueError:
        child_id = path_identity(path)
        root_id = path_identity(root)
        if child_id.startswith(root_id + "/"):
            return child_id[len(root_id) + 1 :]
        return child_id


def workflow_status_to_write_mode(status: str) -> str:
    if status in {"NEEDS_USER_INPUT", "READY_FOR_CONFIRMATION"} or status.startswith("BLOCKED_"):
        return "read-only"
    if status == "READY_FOR_GENERATION":
        return "controlled-generation"
    if status == "READY_FOR_VALIDATION":
        return "deterministic-validation"
    if status == "READY_FOR_SMOKE":
        return "interactive-smoke"
    if status == "READY_FOR_APPLY":
        return "controlled-apply"
    if status == "PASS":
        return "deliver"
    return "read-only"


def extract_apply_manifest(result: dict[str, Any]) -> dict[str, Any] | None:
    direct = result.get("applyManifest")
    if isinstance(direct, dict):
        return direct
    evidence = result.get("applyEvidence")
    if isinstance(evidence, dict) and isinstance(evidence.get("applyManifest"), dict):
        return evidence["applyManifest"]
    return None


def build_state(
    target_root: Path,
    run_root: Path,
    result: dict[str, Any],
    *,
    recorded_transcript_path: Path | None = None,
    recorded_session_id: str = "",
) -> dict[str, Any]:
    status = str(result.get("status") or "UNKNOWN")
    candidate_refs = result.get("candidateRefs") if isinstance(result.get("candidateRefs"), list) else []
    apply_manifest = extract_apply_manifest(result)
    return {
        "schemaName": SCHEMA_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": now_utc_iso(),
        "transcriptPath": str(recorded_transcript_path.resolve()) if recorded_transcript_path else "",
        "sessionId": recorded_session_id,
        "targetRoot": str(target_root.resolve()),
        "runRoot": str(run_root.resolve()),
        "workflow": result.get("workflow") or "workflowprogram-develop",
        "runId": result.get("runId") or "",
        "workflowStatus": status,
        "nextAction": result.get("nextAction") or "",
        "writeMode": workflow_status_to_write_mode(status),
        "deliveryMode": result.get("deliveryMode") or "",
        "candidateRefs": candidate_refs,
        "candidateHash": result.get("candidateHash")
        or (result.get("generationEvidence") or {}).get("candidateHash")
        or (result.get("smokeEvidence") or {}).get("candidateHash")
        or "",
        "applyApproved": result.get("applyApproved") is True or bool(apply_manifest),
        "applyManifest": apply_manifest,
    }


def state_path_for_target(target_root: Path) -> Path:
    return target_root / STATE_RELATIVE_PATH


def find_state_from_path(start: Path) -> tuple[Path, dict[str, Any]] | None:
    cursor = start if start.is_dir() else start.parent
    for parent in [cursor, *cursor.parents]:
        candidate = parent / STATE_RELATIVE_PATH
        if candidate.is_file():
            try:
                return candidate, load_json_file(candidate)
            except (OSError, json.JSONDecodeError):
                return None
    return None


def parse_utc_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def state_is_recent(state: dict[str, Any]) -> bool:
    updated = parse_utc_iso(state.get("updatedAt"))
    if updated is None:
        return False
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    return 0 <= age <= MAX_UNBOUND_STATE_AGE_SECONDS


def state_applies_to_payload(payload: dict[str, Any], state: dict[str, Any]) -> bool:
    if not has_wpn_intent(payload):
        return True
    payload_session_id = str(payload.get("sessionId") or "").strip()
    state_session_id = str(state.get("sessionId") or "").strip()
    if payload_session_id and state_session_id:
        return payload_session_id == state_session_id

    payload_transcript = transcript_path(payload)
    state_transcript = str(state.get("transcriptPath") or "").strip()
    if payload_transcript and state_transcript:
        return path_identity(payload_transcript) == path_identity(state_transcript)

    # Legacy states have no transcript/session binding. Treat only recent states
    # as active so old interrupted runs do not hijack a fresh WPN request.
    return state_is_recent(state)


def current_state_from_found(payload: dict[str, Any], found: tuple[Path, dict[str, Any]] | None) -> dict[str, Any] | None:
    if not found:
        return None
    state = found[1]
    return state if state_applies_to_payload(payload, state) else None


def hook_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def tool_name(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "toolName", "tool", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("tool_input", "toolInput", "input", "parameters"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def transcript_path(payload: dict[str, Any]) -> Path | None:
    for key in ("transcript_path", "transcriptPath", "transcript"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value)
    return None


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def latest_user_prompt_from_transcript(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item.get("lastPrompt"), str):
            return item["lastPrompt"]
        message = item.get("message")
        if isinstance(message, dict) and message.get("role") == "user":
            text = content_text(message.get("content"))
            if text.strip():
                return text
    return ""


def wpn_intent_text(payload: dict[str, Any]) -> str:
    candidates = [
        str(payload.get("prompt") or ""),
        str(payload.get("lastPrompt") or ""),
        content_text(payload.get("message")),
    ]
    path = transcript_path(payload)
    if path:
        candidates.append(latest_user_prompt_from_transcript(path))
    return "\n".join(item for item in candidates if item)


def has_wpn_intent(payload: dict[str, Any]) -> bool:
    text = wpn_intent_text(payload)
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in WPN_INTENT_PATTERNS)


def input_paths(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from input_paths(item)
    elif isinstance(value, dict):
        for key in ("file_path", "path", "paths"):
            if key in value:
                yield from input_paths(value[key])


def is_managed_target_path(path: Path, state: dict[str, Any]) -> bool:
    target_root = Path(str(state.get("targetRoot") or ""))
    run_root = Path(str(state.get("runRoot") or ""))
    if run_root and is_relative_to(path, run_root):
        return False
    if not target_root or not is_relative_to(path, target_root):
        return False
    relative = normalize_relative(path, target_root)
    return any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in MANAGED_PREFIXES)


def command_writes(command: str) -> bool:
    lowered = command.lower()
    return any(re.search(pattern, lowered) for pattern in WRITE_COMMAND_PATTERNS)


def command_embedded_writer(command: str) -> bool:
    return any(re.search(pattern, command, re.IGNORECASE) for pattern in EMBEDDED_WRITE_PATTERNS)


def command_path_literals(command: str) -> Iterable[str]:
    """Return command string literals/tokens that may be filesystem paths.

    This intentionally stays conservative: it only extracts substrings that
    mention WorkflowProgram-managed prefixes, so normal shell arguments and
    natural-language prompt text do not become path candidates.
    """
    normalized = command.replace("\\", "/")
    quoted = re.findall(r"""['"]([^'"]*(?:\.claude|\.workflowprogram)[^'"]*)['"]""", normalized)
    for item in quoted:
        yield item
    for item in re.findall(r"""(?<![\w.-])((?:[A-Za-z]:)?[^\s'"`<>|;&]*(?:\.claude|\.workflowprogram)[^\s'"`<>|;&]*)""", normalized):
        yield item.rstrip("),]")


def command_writes_managed_target(command: str, cwd: Path, state: dict[str, Any]) -> bool:
    if not command_embedded_writer(command):
        return False
    target_root = Path(str(state.get("targetRoot") or ""))
    for raw_path in command_path_literals(command):
        path = Path(raw_path)
        if not path.is_absolute():
            if raw_path.startswith((".claude/", ".workflowprogram/")):
                path = target_root / raw_path
            else:
                path = cwd / raw_path
        if is_managed_target_path(path, state):
            return True
    return False


def command_has_known_side_effect(command: str) -> bool:
    return any(token in command for token in SIDE_EFFECT_COMMAND_TOKENS)


def command_is_commit(command: str) -> bool:
    return re.search(r"\bgit\s+commit\b", command.lower()) is not None


def command_is_guard(command: str) -> bool:
    return "workflowprogram-foreground-guard.py" in command


def command_is_controlled_for_status(command: str, status: str) -> bool:
    allowed = CONTROLLED_COMMANDS_BY_STATUS.get(status, ())
    if not any(token in command for token in allowed):
        return False
    if status == "READY_FOR_APPLY":
        return "apply-staged" in command or " apply" in command
    if status == "READY_FOR_GENERATION":
        required = ("workflowprogram-continue.py", "--workflow-result", "--target-root", "--run-root")
        return all(token in command for token in required)
    if status == "READY_FOR_VALIDATION":
        return "validate-native-workflow-js.py" in command or " validation" in command
    if status == "READY_FOR_SMOKE":
        return "build-native-interactive-smoke.py" in command or " smoke" in command
    return False


def commit_allowed(state: dict[str, Any]) -> bool:
    manifest = state.get("applyManifest")
    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    return (
        state.get("workflowStatus") == "PASS"
        and state.get("deliveryMode") == "managed-apply"
        and isinstance(entries, list)
        and len(entries) > 0
    )


def block(reason: str, state: dict[str, Any] | None = None) -> int:
    payload = {
        "status": "BLOCKED",
        "reason": reason,
        "guard": "workflowprogram-foreground-guard",
    }
    if state:
        payload["workflowStatus"] = state.get("workflowStatus")
        payload["nextAction"] = state.get("nextAction")
        payload["writeMode"] = state.get("writeMode")
    print(json.dumps(payload, ensure_ascii=False))
    print(f"WorkflowProgram foreground guard blocked tool use: {reason}", file=sys.stderr)
    return 2


def allow(reason: str = "allowed") -> int:
    if os.environ.get("WORKFLOWPROGRAM_GUARD_TRACE", "").lower() in {"1", "true", "yes"}:
        print(json.dumps({"status": "PASS", "reason": reason, "guard": "workflowprogram-foreground-guard"}))
    return 0


def check_file_tool(payload: dict[str, Any], state: dict[str, Any] | None) -> int:
    if not state:
        if has_wpn_intent(payload):
            return block(
                "WPN / WorkflowProgram Native requests must launch the product Workflow before any foreground file edit.",
            )
        return allow("no-state")
    for raw_path in input_paths(tool_input(payload)):
        path = Path(raw_path)
        if is_managed_target_path(path, state):
            return block(
                "Foreground file tools must not edit managed target workflow assets; use candidate generation and managed apply.",
                state,
            )
    return allow("file-tool")


def check_bash_tool(payload: dict[str, Any]) -> int:
    data = tool_input(payload)
    command = str(data.get("command") or "")
    cwd = Path(str(payload.get("cwd") or data.get("cwd") or os.getcwd()))
    if command_is_guard(command):
        return allow("guard-command")
    found = find_state_from_path(cwd)
    state = current_state_from_found(payload, found)
    if not state:
        if has_wpn_intent(payload) and (
            command_writes(command)
            or command_has_known_side_effect(command)
            or command_embedded_writer(command)
        ):
            return block(
                "WPN / WorkflowProgram Native requests must launch the product Workflow before any foreground shell write or side-effect script.",
            )
        return allow("no-state")
    if command_is_commit(command):
        if commit_allowed(state):
            return allow("managed-apply-commit")
        return block("Git commit is allowed only after PASS with managed-apply evidence and apply manifest.", state)
    status = str(state.get("workflowStatus") or "")
    if (
        command_writes(command)
        or command_has_known_side_effect(command)
        or command_writes_managed_target(command, cwd, state)
    ) and not command_is_controlled_for_status(command, status):
        return block(
            "Foreground shell writes are blocked for the current WorkflowProgram state; follow nextAction instead.",
            state,
        )
    return allow("bash-tool")


def check_agent_tool(payload: dict[str, Any]) -> int:
    if not has_wpn_intent(payload):
        return allow("agent-non-wpn")
    return block(
        "WPN / WorkflowProgram Native requests must launch the product Workflow before any foreground Agent exploration.",
    )


def unwrap_result_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a ``{result: {...}}`` envelope when the inner object carries
    ``status`` and ``workflow`` keys (the workflow JS respond() shape).

    The Workflow tool may return results wrapped in a ``result`` key. This
    function peels that envelope so the guard records the actual workflow
    state, not the outer wrapper.
    """
    inner = payload.get("result")
    if isinstance(inner, dict) and "status" in inner and "workflow" in inner:
        return inner
    return payload


def command_record(args: argparse.Namespace) -> int:
    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    if args.workflow_result_json:
        result = json.loads(args.workflow_result_json)
    elif args.workflow_result == "-":
        result = json.loads(sys.stdin.read())
    else:
        result = load_json_file(Path(args.workflow_result))
    if not isinstance(result, dict):
        raise ValueError("Workflow result must be a JSON object.")
    result = unwrap_result_envelope(result)
    if not isinstance(result, dict):
        raise ValueError("Workflow result after unwrapping must be a JSON object.")
    recorded_transcript = Path(args.transcript_path).resolve() if args.transcript_path else None
    state = build_state(
        target_root,
        run_root,
        result,
        recorded_transcript_path=recorded_transcript,
        recorded_session_id=args.session_id,
    )
    write_json(state_path_for_target(target_root), state)
    if args.json:
        print(json.dumps({"status": "PASS", "statePath": str(state_path_for_target(target_root)), "state": state}, ensure_ascii=False, indent=2))
    return 0


def command_check(_: argparse.Namespace) -> int:
    payload = hook_payload()
    name = tool_name(payload)
    if name in AGENT_TOOLS:
        return check_agent_tool(payload)
    if name in DIRECT_FILE_WRITE_TOOLS:
        paths = list(input_paths(tool_input(payload)))
        state = None
        for raw_path in paths:
            found = find_state_from_path(Path(raw_path))
            if found:
                state = current_state_from_found(payload, found)
                break
        if not state:
            found = find_state_from_path(Path(str(payload.get("cwd") or os.getcwd())))
            state = current_state_from_found(payload, found)
        return check_file_tool(payload, state)
    if name in {"Bash", "PowerShell", "shell_command", "Shell"}:
        return check_bash_tool(payload)
    return allow("non-write-tool")


def command_assert_commit(args: argparse.Namespace) -> int:
    state_file = state_path_for_target(Path(args.target_root).resolve())
    if not state_file.is_file():
        return block(f"WorkflowProgram foreground state not found: {state_file}")
    state = load_json_file(state_file)
    if not commit_allowed(state):
        return block("Commit gate requires PASS deliveryMode=managed-apply with applyManifest entries.", state)
    if args.json:
        print(json.dumps({"status": "PASS", "statePath": str(state_file)}, ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WorkflowProgram foreground guard")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record a WorkflowProgram Native workflow result")
    record.add_argument("--target-root", required=True)
    record.add_argument("--run-root", required=True)
    record.add_argument("--workflow-result", default="-")
    record.add_argument("--workflow-result-json", default="")
    record.add_argument("--transcript-path", default="")
    record.add_argument("--session-id", default="")
    record.add_argument("--json", action="store_true")

    check = sub.add_parser("check", help="Check one Claude Code PreToolUse hook payload from stdin")
    check.add_argument("--json", action="store_true")

    assert_commit = sub.add_parser("assert-commit", help="Require managed apply PASS before commit")
    assert_commit.add_argument("--target-root", required=True)
    assert_commit.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "record":
        return command_record(args)
    if args.command == "check":
        return command_check(args)
    if args.command == "assert-commit":
        return command_assert_commit(args)
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
