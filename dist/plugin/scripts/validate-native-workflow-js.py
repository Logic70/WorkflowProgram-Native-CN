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
import sys
from pathlib import Path
from typing import Any


META_PREFIX = re.compile(r"\Aexport\s+const\s+meta\s*=\s*\{")
NAME_PATTERN = re.compile(r"(?:\bname\b|['\"]name['\"])\s*:\s*(['\"])(?P<value>[^'\"]+)\1")
DESCRIPTION_PATTERN = re.compile(r"(?:\bdescription\b|['\"]description['\"])\s*:\s*(['\"])(?P<value>[^'\"]+)\1")
TITLE_PATTERN = re.compile(r"(?:\btitle\b|['\"]title['\"])\s*:\s*(['\"])(?P<value>[^'\"]+)\1")
PHASE_CALL_PATTERN = re.compile(r"\bphase\s*\(\s*(['\"])(?P<value>[^'\"]+)\1\s*\)")
RETURN_STATUS_PATTERN = re.compile(r"\breturn\s*\{[\s\S]{0,1000}?\bstatus\s*:", re.MULTILINE)
STRING_LITERAL_PATTERN = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""", re.DOTALL)
AGENT_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*await\s+(?:agent|workflowprogramAgent)\s*\(",
    re.MULTILINE,
)
AGENT_CALL_PATTERN = re.compile(r"\b(?:agent|workflowprogramAgent)\s*\(")
PATH_HINT_PATTERN = re.compile(r"(?:[A-Za-z0-9_.-]+/)+")
WRITE_HINT_PATTERN = re.compile(r"\b(?:write|edit|create|update|modify|save|overwrite)\b", re.IGNORECASE)

FORBIDDEN_APIS = {
    "fs": re.compile(r"(?:\bfrom\s+['\"]fs['\"]|\brequire\s*\(\s*['\"]fs['\"]|\bfs\.)"),
    "require()": re.compile(r"\brequire\s*\("),
    "process": re.compile(r"\bprocess\b"),
    "Date.now()": re.compile(r"\bDate\.now\s*\("),
    "Math.random()": re.compile(r"\bMath\.random\s*\("),
    "new Date()": re.compile(r"\bnew\s+Date\s*\(\s*\)"),
}
META_LITERAL_KEYS = {"name", "description", "phases", "title", "detail"}


def error(rule: str, message: str) -> dict[str, str]:
    """Return one stable structured validation error."""

    return {"rule": rule, "message": message}


def strip_string_literals(text: str) -> str:
    """Remove quoted string contents before checking executable syntax."""

    return STRING_LITERAL_PATTERN.sub("", text)


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

    executable_text = strip_string_literals(text)
    for name, pattern in FORBIDDEN_APIS.items():
        if pattern.search(executable_text):
            errors.append(error("FORBIDDEN_API", f"Native Workflow JS must not use `{name}`."))


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
    declared_phases = phase_titles(TITLE_PATTERN, meta_literal or "")
    actual_phases = phase_titles(PHASE_CALL_PATTERN, text)
    if meta_literal is not None and declared_phases != actual_phases:
        errors.append(
            error(
                "PHASE_ALIGNMENT",
                f"Declared phases {declared_phases} do not match executed phases {actual_phases}.",
            )
        )

    validate_forbidden_apis(text, errors)
    validate_gate_schemas(text, errors)
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
