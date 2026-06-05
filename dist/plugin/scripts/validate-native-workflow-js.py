#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
Lightweight static validation for Claude Code Native Workflow JS files.

This validator intentionally checks only rules that can be established
conservatively without executing JavaScript. Domain semantics remain the
responsibility of interactive smoke tests and optional deterministic scripts.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


META_PREFIX = re.compile(r"\Aexport\s+const\s+meta\s*=\s*\{")
META_EXPORT_PATTERN = re.compile(r"\bexport\s+const\s+meta\s*=")
NAME_PATTERN = re.compile(r"(?:\bname\b|['\"]name['\"])\s*:\s*(['\"])(?P<value>[^'\"]+)\1")
DESCRIPTION_PATTERN = re.compile(r"(?:\bdescription\b|['\"]description['\"])\s*:\s*(['\"])(?P<value>[^'\"]+)\1")
TITLE_PATTERN = re.compile(r"(?:\btitle\b|['\"]title['\"])\s*:\s*(['\"])(?P<value>[^'\"]+)\1")
PHASE_CALL_PATTERN = re.compile(r"\bphase\s*\(\s*(['\"])(?P<value>[^'\"]+)\1\s*\)")
RETURN_STATUS_PATTERN = re.compile(r"\breturn\s*\{[\s\S]{0,1000}?\bstatus\s*:", re.MULTILINE)
AGENT_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*await\s+(?:agent|workflowprogramAgent)\s*\(",
    re.MULTILINE,
)
AGENT_CALL_PATTERN = re.compile(r"\b(?:agent|workflowprogramAgent)\s*\(")
SUPPORTED_AGENT_OPTION_KEYS = {"label", "phase", "schema", "model", "isolation", "agentType"}
PATH_HINT_PATTERN = re.compile(r"(?:[A-Za-z0-9_.-]+/)+")
WRITE_HINT_PATTERN = re.compile(r"\b(?:write|edit|create|update|modify|save|overwrite)\b", re.IGNORECASE)

FORBIDDEN_APIS = {
    "fs": re.compile(r"(?:\bfrom\s+['\"]fs['\"]|\brequire\s*\(\s*['\"]fs['\"]|\bfs\.)"),
    "require()": re.compile(r"\brequire\s*\("),
    "process": re.compile(r"\bprocess\b"),
    "eval()": re.compile(r"\beval\b"),
    "Function()": re.compile(r"\bFunction\b"),
    "Date.now()": re.compile(r"\bDate\.now\s*\("),
    "Math.random()": re.compile(r"\bMath\.random\s*\("),
    "new Date()": re.compile(r"\bnew\s+Date\s*\(\s*\)"),
}
META_LITERAL_KEYS = {"name", "description", "phases", "title", "detail"}

# Claude Code native tool names that authors sometimes mistakenly call as
# Workflow JS globals.  These are NOT part of the Native Workflow JS runtime
# and any direct reference in executable code is an error.
UNDECLARED_NATIVE_TOOL_NAMES = [
    "Bash",
    "Read",
    "Write",
    "Edit",
    "Grep",
    "Glob",
    "PowerShell",
    "WebSearch",
    "WebFetch",
    "ToolSearch",
    "NotebookEdit",
    "AskUserQuestion",
    "Skill",
    "Task",
    "SendMessage",
    "Agent",
    "EnterPlanMode",
    "ExitPlanMode",
    "EnterWorktree",
    "ExitWorktree",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskOutput",
    "TaskStop",
    "TaskUpdate",
    "CronCreate",
    "CronDelete",
    "CronList",
    "ScheduleWakeup",
    "Workflow",
    "Monitor",
    "TeamCreate",
    "TeamDelete",
    "PushNotification",
]
# Build per-name patterns that match direct identifier references. Property
# access and object keys are filtered later, while calls and bare references
# remain errors unless the identifier is visibly declared locally.
UNDECLARED_NATIVE_TOOL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(rf"\b{re.escape(name)}\b"))
    for name in UNDECLARED_NATIVE_TOOL_NAMES
]

# High-confidence runtime identifiers whose accidental omission has caused
# real launch failures. This is intentionally not a complete JavaScript linter.
CRITICAL_RUNTIME_IDENTIFIERS = {"runId"}
IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z_$][\w$]*\b")
DECLARATION_PATTERN = re.compile(r"\b(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)")
DESTRUCTURED_DECLARATION_PATTERN = re.compile(r"\b(?:const|let|var)\s*\{([^}]*)\}")
FUNCTION_PARAMS_PATTERN = re.compile(r"\bfunction\s*[A-Za-z_$]*\s*\(([^)]*)\)")
PAREN_ARROW_PARAMS_PATTERN = re.compile(r"\(([^)]*)\)\s*=>")
SINGLE_ARROW_PARAM_PATTERN = re.compile(r"\b([A-Za-z_$][\w$]*)\s*=>")


def error(rule: str, message: str) -> dict[str, str]:
    """Return one stable structured validation error."""

    return {"rule": rule, "message": message}


def strip_string_literals(text: str) -> str:
    """Remove string literal text while preserving template expressions."""

    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in {"'", '"'}:
            index = skip_quoted_literal(text, index, char)
            continue
        if char == "`":
            index = strip_template_literal(text, index, out)
            continue
        out.append(char)
        index += 1
    return "".join(out)


def skip_quoted_literal(text: str, index: int, quote: str) -> int:
    """Return the index after a single or double quoted literal."""

    index += 1
    escaped = False
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return index + 1
        index += 1
    return index


def find_template_expression_end(text: str, index: int) -> int:
    """Return the closing brace index for a template `${...}` expression."""

    depth = 1
    quote: str | None = None
    escaped = False
    while index < len(text):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return len(text)


def strip_template_literal(text: str, index: int, out: list[str]) -> int:
    """Skip template text but keep stripped `${...}` expression code."""

    index += 1
    escaped = False
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char == "`":
            return index + 1
        if char == "$" and index + 1 < len(text) and text[index + 1] == "{":
            end = find_template_expression_end(text, index + 2)
            expression = text[index + 2:end]
            out.append(strip_string_literals(expression))
            index = end + 1 if end < len(text) else end
            continue
        index += 1
    return index


def strip_comments(text: str) -> str:
    """Remove simple JavaScript comments for shape checks."""

    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    text = re.sub(r"//.*", "", text)
    return text


def is_pure_meta_literal(literal: str) -> bool:
    """Accept only object/array punctuation and known keys outside strings."""

    residual = strip_string_literals(literal)
    for key in META_LITERAL_KEYS:
        residual = re.sub(rf"\b{re.escape(key)}\b", "", residual)
    return re.fullmatch(r"[\s{}\[\],:]*", residual) is not None


def extract_balanced(text: str, open_index: int, opener: str, closer: str) -> tuple[str, int]:
    """Extract a balanced JavaScript region while ignoring brackets inside strings."""

    if open_index >= len(text) or text[open_index] != opener:
        raise ValueError(f"Expected '{opener}' at index {open_index}")
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[open_index : index + 1], index + 1
    raise ValueError(f"Unclosed '{opener}' region")


def extract_meta(text: str, errors: list[dict[str, str]]) -> tuple[str | None, dict[str, Any]]:
    """Parse the pure-literal meta prefix with conservative regular expressions."""

    match = META_PREFIX.match(text)
    if not match:
        errors.append(error("META_LITERAL_REQUIRED", "Script must start with pure-literal `export const meta = { ... }`."))
        return None, {}
    open_index = text.find("{", match.start())
    try:
        literal, _ = extract_balanced(text, open_index, "{", "}")
    except ValueError as exc:
        errors.append(error("META_LITERAL_INVALID", str(exc)))
        return None, {}
    if not is_pure_meta_literal(literal):
        errors.append(error("META_LITERAL_INVALID", "Meta must contain only literal objects, arrays, strings, and known keys."))

    name_match = NAME_PATTERN.search(literal)
    description_match = DESCRIPTION_PATTERN.search(literal)
    if not name_match:
        errors.append(error("META_NAME_REQUIRED", "Meta literal must define a non-empty `name`."))
    if not description_match:
        errors.append(error("META_DESCRIPTION_REQUIRED", "Meta literal must define a non-empty `description`."))
    return literal, {
        "name": name_match.group("value") if name_match else None,
        "description": description_match.group("value") if description_match else None,
        "phases": TITLE_PATTERN.findall(literal),
    }


def phase_titles(pattern: re.Pattern[str], text: str) -> list[str]:
    """Return regex named capture values in source order."""

    return [match.group("value") for match in pattern.finditer(text)]


def validate_forbidden_apis(text: str, errors: list[dict[str, str]]) -> None:
    """Reject unsupported or nondeterministic APIs."""

    executable_text = strip_comments(strip_string_literals(text))
    for name, pattern in FORBIDDEN_APIS.items():
        if pattern.search(executable_text):
            errors.append(error("FORBIDDEN_API", f"Native Workflow JS must not use `{name}`."))


def validate_meta_export_count(text: str, errors: list[dict[str, str]]) -> None:
    """Require exactly one top-level meta export generated at the file start."""

    count = len(META_EXPORT_PATTERN.findall(strip_string_literals(text)))
    if count > 1:
        errors.append(error("DUPLICATE_META_EXPORT", "Native Workflow JS must contain exactly one `export const meta` declaration."))


def workflow_parse_source(text: str) -> str:
    """Wrap a Native Workflow JS body in the same async shape used by test harnesses."""

    source = META_EXPORT_PATTERN.sub("const meta =", text, count=1)
    return (
        "async function __workflowprogram_parse_probe(args, phase, agent, parallel, pipeline, workflow, log) {\n"
        f"{source}\n"
        "}\n"
        "export { __workflowprogram_parse_probe }\n"
    )


def validate_module_parse(text: str, errors: list[dict[str, str]]) -> None:
    """Ask Node to parse the workflow as an async module wrapper without executing it."""

    try:
        completed = subprocess.run(
            ["node", "--input-type=module", "--check"],
            input=workflow_parse_source(text),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        errors.append(error("MODULE_PARSE_UNAVAILABLE", "`node` is required to parse Native Workflow JS modules."))
        return
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "module parse failed").strip().splitlines()
        errors.append(error("MODULE_PARSE_FAILED", " ".join(message[:3])))


def validate_gate_schemas(text: str, errors: list[dict[str, str]]) -> None:
    """Require schema when an Agent result is consumed by an if gate."""

    for match in AGENT_ASSIGNMENT_PATTERN.finditer(text):
        name = match.group("name")
        open_index = text.find("(", match.end() - 1)
        try:
            agent_call, call_end = extract_balanced(text, open_index, "(", ")")
        except ValueError:
            errors.append(error("AGENT_CALL_INVALID", f"Agent call assigned to `{name}` is not balanced."))
            continue
        gated = re.search(rf"\bif\s*\([^)]*\b{re.escape(name)}\s*\.", text[call_end:])
        if gated and not re.search(r"\bschema\s*:", agent_call):
            errors.append(
                error(
                    "SCHEMA_REQUIRED_FOR_GATE",
                    f"Agent result `{name}` is consumed by a JS gate but the Agent call has no schema.",
                )
            )


def first_top_level_argument(call: str) -> str:
    """Return the first argument from a balanced call string like ``(...)``."""

    args = top_level_arguments(call)
    return args[0] if args else ""


def top_level_arguments(call: str) -> list[str]:
    """Split a balanced call string into top-level argument strings."""

    inner = call[1:-1]
    depth = 0
    quote: str | None = None
    escaped = False
    start = 0
    args: list[str] = []
    for index, char in enumerate(inner):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(inner[start:index].strip())
            start = index + 1
    tail = inner[start:].strip()
    if tail:
        args.append(tail)
    return args


def object_top_level_keys(source: str) -> set[str]:
    """Return visible top-level keys from a JavaScript object literal."""

    source = strip_comments(source).strip()
    if not source.startswith("{"):
        return set()
    try:
        literal, _ = extract_balanced(source, 0, "{", "}")
    except ValueError:
        return set()

    keys: set[str] = set()
    index = 1
    while index < len(literal) - 1:
        while index < len(literal) - 1 and literal[index] in " \t\r\n,":
            index += 1
        if index >= len(literal) - 1:
            break
        char = literal[index]
        if char in {"'", '"'}:
            end = skip_quoted_literal(literal, index, char)
            key = literal[index + 1 : end - 1]
            cursor = end
        else:
            match = IDENTIFIER_PATTERN.match(literal, index)
            if not match:
                index += 1
                continue
            key = match.group(0)
            cursor = match.end()
        while cursor < len(literal) - 1 and literal[cursor].isspace():
            cursor += 1
        if cursor < len(literal) - 1 and literal[cursor] == ":":
            keys.add(key)
            cursor += 1
            depth = 0
            quote: str | None = None
            escaped = False
            while cursor < len(literal) - 1:
                current = literal[cursor]
                if quote is not None:
                    if escaped:
                        escaped = False
                    elif current == "\\":
                        escaped = True
                    elif current == quote:
                        quote = None
                    cursor += 1
                    continue
                if current in {"'", '"', "`"}:
                    quote = current
                elif current in "([{":
                    depth += 1
                elif current in ")]}":
                    depth -= 1
                elif current == "," and depth == 0:
                    break
                cursor += 1
        index = cursor + 1
    return keys


def validate_agent_option_shapes(text: str, errors: list[dict[str, str]]) -> None:
    """Reject unsupported top-level Agent option keys such as `skills`."""

    for match in AGENT_CALL_PATTERN.finditer(text):
        open_index = text.find("(", match.start())
        try:
            agent_call, _ = extract_balanced(text, open_index, "(", ")")
        except ValueError:
            errors.append(error("AGENT_CALL_INVALID", "An Agent call is not balanced."))
            continue
        args = top_level_arguments(agent_call)
        if len(args) < 2:
            continue
        keys = object_top_level_keys(args[1])
        unsupported = sorted(keys - SUPPORTED_AGENT_OPTION_KEYS)
        if unsupported:
            errors.append(
                error(
                    "UNSUPPORTED_AGENT_OPTION",
                    "Agent options contain unsupported top-level keys: " + ", ".join(unsupported),
                )
            )


def validate_pipeline_shapes(text: str, errors: list[dict[str, str]]) -> None:
    """Reject the common no-items pipeline shape seen in failed migrations."""

    for match in re.finditer(r"\bpipeline\s*\(", text):
        open_index = text.find("(", match.start())
        try:
            pipeline_call, _ = extract_balanced(text, open_index, "(", ")")
        except ValueError:
            errors.append(error("PIPELINE_CALL_INVALID", "A `pipeline()` call is not balanced."))
            continue
        first_arg = strip_comments(first_top_level_argument(pipeline_call)).strip()
        if not first_arg:
            errors.append(error("PIPELINE_SHAPE_INVALID", "`pipeline()` must start with an items argument."))
            continue
        if "=>" in first_arg or first_arg.startswith(("async ", "async(", "function", "(", "agent(", "workflowprogramAgent(", "parallel(")):
            errors.append(error("PIPELINE_SHAPE_INVALID", "`pipeline()` must start with items, not a stage function or Agent call."))


def declared_identifiers(text: str) -> set[str]:
    """Collect simple declarations for conservative undeclared-name checks."""

    executable_text = strip_comments(strip_string_literals(text))
    declared = {match.group(1) for match in DECLARATION_PATTERN.finditer(executable_text)}

    for match in DESTRUCTURED_DECLARATION_PATTERN.finditer(executable_text):
        for item in match.group(1).split(","):
            candidate = item.strip()
            if not candidate:
                continue
            if ":" in candidate:
                candidate = candidate.split(":", 1)[1].strip()
            candidate = candidate.split("=", 1)[0].strip()
            if IDENTIFIER_PATTERN.fullmatch(candidate):
                declared.add(candidate)

    for pattern in (FUNCTION_PARAMS_PATTERN, PAREN_ARROW_PARAMS_PATTERN):
        for match in pattern.finditer(executable_text):
            for item in match.group(1).split(","):
                candidate = item.strip().split("=", 1)[0].strip()
                if IDENTIFIER_PATTERN.fullmatch(candidate):
                    declared.add(candidate)

    declared.update(match.group(1) for match in SINGLE_ARROW_PARAM_PATTERN.finditer(executable_text))
    return declared


def is_property_access_or_key(text: str, match: re.Match[str]) -> bool:
    """Return true when an identifier is a member access or object key."""

    before = text[: match.start()].rstrip()
    after = text[match.end() :].lstrip()
    return before.endswith(".") or after.startswith(":")


def validate_undeclared_native_api(text: str, errors: list[dict[str, str]]) -> None:
    """Reject Claude Code tool names referenced as Native Workflow JS globals.

    Direct calls and bare references fail because host tools are not injected
    into the workflow runtime. Property access and object keys remain allowed.
    """

    executable_text = strip_comments(strip_string_literals(text))
    declared = declared_identifiers(text)
    for name, pattern in UNDECLARED_NATIVE_TOOL_PATTERNS:
        if name in declared:
            continue
        for match in pattern.finditer(executable_text):
            if is_property_access_or_key(executable_text, match):
                continue
            errors.append(
                error(
                    "UNDECLARED_NATIVE_API",
                    f"`{name}` is a Claude Code host tool, not a Native Workflow JS global. Use agent() to delegate tool work.",
                )
            )
            break


def validate_undeclared_identifiers(text: str, errors: list[dict[str, str]]) -> None:
    """Reject high-confidence undeclared runtime identifiers without pretending to lint all JS."""

    executable_text = strip_comments(strip_string_literals(text))
    declared = declared_identifiers(text)
    for identifier in sorted(CRITICAL_RUNTIME_IDENTIFIERS - declared):
        for match in re.finditer(rf"\b{re.escape(identifier)}\b", executable_text):
            if is_property_access_or_key(executable_text, match):
                continue
            errors.append(
                error(
                    "UNDECLARED_IDENTIFIER",
                    f"`{identifier}` is referenced but not visibly declared. Declare it from `args` or remove the reference.",
                )
            )
            break


def validate_parallel_writes(text: str, errors: list[dict[str, str]]) -> None:
    """Flag obvious same-directory write prompts inside one parallel call."""

    for match in re.finditer(r"\bparallel\s*\(", text):
        open_index = text.find("(", match.start())
        try:
            parallel_call, _ = extract_balanced(text, open_index, "(", ")")
        except ValueError:
            errors.append(error("PARALLEL_CALL_INVALID", "A `parallel()` call is not balanced."))
            continue
        if len(AGENT_CALL_PATTERN.findall(parallel_call)) < 2 or len(WRITE_HINT_PATTERN.findall(parallel_call)) < 2:
            continue
        paths = [item.lower() for item in PATH_HINT_PATTERN.findall(parallel_call)]
        repeated = sorted({path for path in paths if paths.count(path) > 1})
        if repeated:
            errors.append(
                error(
                    "PARALLEL_WRITE_HINT",
                    "Parallel Agent prompts visibly write the same path prefix: " + ", ".join(repeated),
                )
            )


def validate_script(path: Path) -> dict[str, Any]:
    """Validate one Native Workflow JS file and return a structured report."""

    resolved = path.resolve()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not resolved.exists():
        return {
            "schema_version": 1,
            "schema_name": "native-workflow-js-validation",
            "status": "FAIL",
            "script": str(resolved),
            "meta": {},
            "phases": [],
            "errors": [error("SCRIPT_NOT_FOUND", f"Script not found: {resolved}")],
            "warnings": [],
        }

    text = resolved.read_text(encoding="utf-8")
    meta_literal, meta = extract_meta(text, errors)
    validate_meta_export_count(text, errors)
    validate_module_parse(text, errors)
    declared_phases = phase_titles(TITLE_PATTERN, strip_comments(meta_literal or ""))
    actual_phases = phase_titles(PHASE_CALL_PATTERN, strip_comments(text))
    if meta_literal is not None and declared_phases != actual_phases:
        errors.append(
            error(
                "PHASE_ALIGNMENT",
                f"Declared phases {declared_phases} do not match executed phases {actual_phases}.",
            )
        )

    validate_forbidden_apis(text, errors)
    validate_undeclared_native_api(text, errors)
    validate_undeclared_identifiers(text, errors)
    validate_agent_option_shapes(text, errors)
    validate_gate_schemas(text, errors)
    validate_pipeline_shapes(text, errors)
    validate_parallel_writes(text, errors)
    if not RETURN_STATUS_PATTERN.search(text):
        errors.append(error("RETURN_ENVELOPE_REQUIRED", "Workflow must return a stable object containing `status`."))

    return {
        "schema_version": 1,
        "schema_name": "native-workflow-js-validation",
        "status": "FAIL" if errors else "PASS",
        "script": str(resolved),
        "meta": {
            "name": meta.get("name"),
            "description": meta.get("description"),
        },
        "phases": actual_phases,
        "errors": errors,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the validator CLI."""

    parser = argparse.ArgumentParser(description="Validate one Claude Code Native Workflow JS file")
    parser.add_argument("--script", required=True, help="Path to the Native Workflow JS file")
    parser.add_argument("--json", action="store_true", help="Print structured JSON")
    return parser


def main() -> int:
    """Run validation and return a stable process exit code."""

    args = build_parser().parse_args()
    try:
        payload = validate_script(Path(args.script))
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "schema_name": "native-workflow-js-validation",
            "status": "FAIL",
            "script": str(Path(args.script).resolve()),
            "meta": {},
            "phases": [],
            "errors": [error("INTERNAL_ERROR", str(exc))],
            "warnings": [],
        }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {payload['script']}")
        for item in payload["errors"]:
            print(f"  [{item['rule']}] {item['message']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
