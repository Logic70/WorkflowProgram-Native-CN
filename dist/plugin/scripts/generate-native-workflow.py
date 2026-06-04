#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
Generate the smallest supported Claude Code Native Workflow JS control plane.

The generator stages one `.claude/workflows/<name>.js` candidate under RUN_ROOT,
validates it statically, and optionally delegates safe writes to managed-assets.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from lib.io_utils import write_json


NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AGENT_CALL_PATTERN = re.compile(r"(?<![\w$])agent\s*\(")
AUTHORING_BODY_FORBIDDEN = {
    "AUTHORING_BODY_CONTAINS_META": re.compile(r"\bexport\s+const\s+meta\s*="),
    "AUTHORING_BODY_CONTAINS_IMPORT": re.compile(r"^\s*import\s+", re.MULTILINE),
    "AUTHORING_BODY_CONTAINS_MODULE_EXPORTS": re.compile(r"\bmodule\.exports\b"),
    "AUTHORING_BODY_CONTAINS_REQUIRE": re.compile(r"\brequire\s*\("),
}
SUPPORTING_ASSET_RULES = {
    "skill": (".claude/skills/", "/SKILL.md"),
    "agent": (".claude/agents/", ".md"),
    "script": (".claude/scripts/", None),
    "compatibility-command": (".claude/commands/", ".md"),
    "authoring-metadata": (".workflowprogram/design/", None),
    "workflow-spec-ir": (".workflowprogram/design/", "workflow-spec.yaml"),
}


def load_validator_module():
    """Load the sibling validator without requiring an import-safe filename."""

    path = Path(__file__).resolve().with_name("validate-native-workflow-js.py")
    spec = importlib.util.spec_from_file_location("workflowprogram_native_workflow_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Native Workflow validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HANDOFF_SCHEMA_VERSION = 1
HANDOFF_SCHEMA_NAME = "native-workflow-generation-handoff-validation"


def strip_js_string_literals(text: str) -> str:
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
            out.append(strip_js_string_literals(expression))
            index = end + 1 if end < len(text) else end
            continue
        index += 1
    return index


def validate_authoring_body(body: str) -> None:
    """Reject full JS modules and unsupported module boundaries in authoring body."""

    executable_text = strip_js_string_literals(body)
    for rule, pattern in AUTHORING_BODY_FORBIDDEN.items():
        if pattern.search(executable_text):
            raise ValueError(f"{rule}: `body` must contain only the executable body after the generated meta header.")


def validate_handoff(path: Path, target_root: Path, run_root: Path) -> dict[str, Any]:
    """Validate a READY_FOR_GENERATION handoff packet from develop JS.

    Returns a structured ``{schema_version, schema_name, status, packet,
    target_root, run_root, run_id, errors}`` report with *status* = ``PASS``
    only when every field passes its rule.

    No candidate files may be created when *status* is not ``PASS``.
    """
    errors: list[dict[str, str]] = []

    # --- Load -----------------------------------------------------------------
    try:
        raw = path.read_text(encoding="utf-8")
        packet = json.loads(raw)
    except Exception as exc:
        errors.append({"rule": "HANDOFF_NOT_VALID_JSON", "message": f"Handoff packet is not valid JSON: {exc}"})
        return {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "schema_name": HANDOFF_SCHEMA_NAME,
            "status": "FAIL",
            "packet": None,
            "target_root": str(target_root.resolve()),
            "run_root": str(run_root.resolve()),
            "run_id": "",
            "errors": errors,
        }

    if not isinstance(packet, dict):
        errors.append({"rule": "HANDOFF_NOT_OBJECT", "message": "Handoff packet must be a JSON object."})
        return {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "schema_name": HANDOFF_SCHEMA_NAME,
            "status": "FAIL",
            "packet": None,
            "target_root": str(target_root.resolve()),
            "run_root": str(run_root.resolve()),
            "run_id": "",
            "errors": errors,
        }

    run_id = ""

    # --- status ---------------------------------------------------------------
    status_val = str(packet.get("status", "")).strip()
    if status_val != "READY_FOR_GENERATION":
        errors.append({"rule": "HANDOFF_STATUS_INVALID", "message": f"status must be READY_FOR_GENERATION, got: {status_val or '<empty>'}"})

    # --- workflow -------------------------------------------------------------
    workflow_val = str(packet.get("workflow", "")).strip()
    if workflow_val != "workflowprogram-develop":
        errors.append({"rule": "HANDOFF_WORKFLOW_INVALID", "message": f"workflow must be 'workflowprogram-develop', got: {workflow_val or '<empty>'}"})

    # --- runId ----------------------------------------------------------------
    run_id_value = packet.get("runId")
    run_id_raw = run_id_value.strip() if isinstance(run_id_value, str) else ""
    if not run_id_raw:
        errors.append({"rule": "HANDOFF_RUN_ID_EMPTY", "message": "runId must be a non-empty string."})
    else:
        run_id = run_id_raw

    # --- targetRoot / runRoot -------------------------------------------------
    packet_target_root = str(packet.get("targetRoot", "")).strip()
    packet_run_root = str(packet.get("runRoot", "")).strip()
    try:
        resolved_packet_target = Path(packet_target_root).resolve() if packet_target_root else None
        resolved_packet_run = Path(packet_run_root).resolve() if packet_run_root else None
    except Exception:
        resolved_packet_target = None
        resolved_packet_run = None

    if not packet_target_root or resolved_packet_target != target_root.resolve():
        errors.append({
            "rule": "HANDOFF_TARGET_ROOT_MISMATCH",
            "message": f"Handoff targetRoot ({packet_target_root or '<empty>'}) must match --target-root ({target_root}).",
        })
    if not packet_run_root or resolved_packet_run != run_root.resolve():
        errors.append({
            "rule": "HANDOFF_RUN_ROOT_MISMATCH",
            "message": f"Handoff runRoot ({packet_run_root or '<empty>'}) must match --run-root ({run_root}).",
        })

    # --- generationRequest ----------------------------------------------------
    gen_req = packet.get("generationRequest")
    if not isinstance(gen_req, dict):
        errors.append({"rule": "HANDOFF_GENERATION_REQUEST_MISSING", "message": "generationRequest object is required."})
    else:
        gen_target_root = str(gen_req.get("targetRoot", "")).strip()
        gen_run_root = str(gen_req.get("runRoot", "")).strip()
        gen_rule_value = gen_req.get("rule")
        gen_rule = gen_rule_value.strip() if isinstance(gen_rule_value, str) else ""
        try:
            resolved_gen_target = Path(gen_target_root).resolve() if gen_target_root else None
            resolved_gen_run = Path(gen_run_root).resolve() if gen_run_root else None
        except Exception:
            resolved_gen_target = None
            resolved_gen_run = None
        if not gen_target_root or resolved_gen_target != target_root.resolve():
            errors.append({
                "rule": "HANDOFF_GENERATION_REQUEST_TARGET_ROOT_MISMATCH",
                "message": f"generationRequest.targetRoot ({gen_target_root or '<empty>'}) must match --target-root ({target_root}).",
            })
        if not gen_run_root or resolved_gen_run != run_root.resolve():
            errors.append({
                "rule": "HANDOFF_GENERATION_REQUEST_RUN_ROOT_MISMATCH",
                "message": f"generationRequest.runRoot ({gen_run_root or '<empty>'}) must match --run-root ({run_root}).",
            })
        if not gen_rule:
            errors.append({"rule": "HANDOFF_GENERATION_REQUEST_RULE_EMPTY", "message": "generationRequest.rule must be a non-empty string."})

    # --- authoringSpec --------------------------------------------------------
    authoring_spec = packet.get("authoringSpec")
    if not isinstance(authoring_spec, dict):
        errors.append({"rule": "HANDOFF_AUTHORING_SPEC_MISSING", "message": "authoringSpec object is required."})
    else:
        for field in ("name", "description", "body"):
            if not isinstance(authoring_spec.get(field), str) or not authoring_spec[field].strip():
                errors.append({"rule": f"HANDOFF_AUTHORING_SPEC_{field.upper()}", "message": f"authoringSpec.{field} must be a non-empty string."})
        phases = authoring_spec.get("phases")
        if not isinstance(phases, list) or not phases:
            errors.append({"rule": "HANDOFF_AUTHORING_SPEC_PHASES", "message": "authoringSpec.phases must be a non-empty array."})

    # --- designEvidence -------------------------------------------------------
    design_ev = packet.get("designEvidence")
    if not isinstance(design_ev, dict):
        errors.append({"rule": "HANDOFF_DESIGN_EVIDENCE_MISSING", "message": "designEvidence object is required."})
    else:
        if design_ev.get("status") != "PASS":
            errors.append({"rule": "HANDOFF_DESIGN_EVIDENCE_STATUS", "message": "designEvidence.status must be PASS."})
        if not isinstance(design_ev.get("summary"), str) or not design_ev["summary"].strip():
            errors.append({"rule": "HANDOFF_DESIGN_EVIDENCE_SUMMARY", "message": "designEvidence.summary must be a non-empty string."})
        if not isinstance(design_ev.get("highLevelDesign"), str) or not design_ev["highLevelDesign"].strip():
            errors.append({"rule": "HANDOFF_DESIGN_EVIDENCE_HLD", "message": "designEvidence.highLevelDesign must be a non-empty string."})
        if not isinstance(design_ev.get("lowLevelDesign"), str) or not design_ev["lowLevelDesign"].strip():
            errors.append({"rule": "HANDOFF_DESIGN_EVIDENCE_LLD", "message": "designEvidence.lowLevelDesign must be a non-empty string."})
        traceability = design_ev.get("traceability")
        if not isinstance(traceability, list) or not traceability:
            errors.append({"rule": "HANDOFF_DESIGN_EVIDENCE_TRACEABILITY", "message": "designEvidence.traceability must be a non-empty array."})
        elif not all(isinstance(t, str) and t.strip() for t in traceability):
            errors.append({"rule": "HANDOFF_DESIGN_EVIDENCE_TRACEABILITY_ITEMS", "message": "designEvidence.traceability items must be non-empty strings."})

    # --- reviewEvidence -------------------------------------------------------
    review_ev = packet.get("reviewEvidence")
    if not isinstance(review_ev, dict):
        errors.append({"rule": "HANDOFF_REVIEW_EVIDENCE_MISSING", "message": "reviewEvidence object is required."})
    else:
        if review_ev.get("status") != "PASS":
            errors.append({"rule": "HANDOFF_REVIEW_EVIDENCE_STATUS", "message": "reviewEvidence.status must be PASS."})
        if not isinstance(review_ev.get("summary"), str) or not review_ev["summary"].strip():
            errors.append({"rule": "HANDOFF_REVIEW_EVIDENCE_SUMMARY", "message": "reviewEvidence.summary must be a non-empty string."})
        blocking = review_ev.get("blockingIssues")
        if not isinstance(blocking, list):
            errors.append({"rule": "HANDOFF_REVIEW_EVIDENCE_BLOCKING_NOT_ARRAY", "message": "reviewEvidence.blockingIssues must be an array."})
        elif len(blocking) > 0:
            errors.append({"rule": "HANDOFF_REVIEW_EVIDENCE_BLOCKING_NOT_EMPTY", "message": f"reviewEvidence.blockingIssues must be empty (got {len(blocking)} issues)."})

    status_out = "FAIL" if errors else "PASS"
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "schema_name": HANDOFF_SCHEMA_NAME,
        "status": status_out,
        "packet": str(path.resolve()),
        "target_root": str(target_root.resolve()),
        "run_root": str(run_root.resolve()),
        "run_id": run_id,
        "errors": errors,
    }


def load_readiness_validator_module():
    """Load the sibling foreground readiness validator."""

    path = Path(__file__).resolve().with_name("validate-native-authoring-readiness.py")
    spec = importlib.util.spec_from_file_location("workflowprogram_native_authoring_readiness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Native authoring readiness validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_authoring_spec_payload(payload: Any) -> dict[str, Any]:
    """Validate and normalize one JSON authoring spec payload."""

    if not isinstance(payload, dict):
        raise ValueError("Authoring spec must be a JSON object.")
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    phases = payload.get("phases")
    body = payload.get("body")
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError("`name` must match `[a-z0-9][a-z0-9-]*`.")
    if not description:
        raise ValueError("`description` must be a non-empty string.")
    if not isinstance(phases, list) or not phases:
        raise ValueError("`phases` must be a non-empty array.")
    titles: list[str] = []
    normalized_phases: list[dict[str, str]] = []
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise ValueError(f"`phases[{index}]` must be an object.")
        title = str(phase.get("title", "")).strip()
        detail = str(phase.get("detail", "")).strip()
        if not title:
            raise ValueError(f"`phases[{index}].title` must be a non-empty string.")
        if title in titles:
            raise ValueError(f"Duplicate phase title: {title}")
        titles.append(title)
        normalized = {"title": title}
        if detail:
            normalized["detail"] = detail
        normalized_phases.append(normalized)
    if not isinstance(body, str) or not body.strip():
        raise ValueError("`body` must be a non-empty JavaScript string.")
    validate_authoring_body(body)
    supporting_assets = normalize_supporting_assets(payload.get("supporting_assets", []))
    task_model_policy = normalize_task_model_policy(payload.get("task_model_policy"))
    return {
        "name": name,
        "description": description,
        "phases": normalized_phases,
        "body": body.strip() + "\n",
        "supporting_assets": supporting_assets,
        "task_model_policy": task_model_policy,
    }


def load_authoring_spec(path: Path) -> dict[str, Any]:
    """Load and validate the minimal JSON authoring spec."""

    return normalize_authoring_spec_payload(json.loads(path.read_text(encoding="utf-8")))


def validate_handoff_spec_alignment(spec: dict[str, Any], handoff_path: Path) -> list[dict[str, str]]:
    """Ensure the disk spec is exactly the product JS authoringSpec."""

    errors: list[dict[str, str]] = []
    try:
        packet = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_spec = normalize_authoring_spec_payload(packet.get("authoringSpec"))
    except Exception as exc:
        return [{"rule": "HANDOFF_AUTHORING_SPEC_INVALID", "message": f"authoringSpec is invalid: {exc}"}]
    comparable_keys = ("name", "description", "phases", "body", "supporting_assets", "task_model_policy")
    for key in comparable_keys:
        if spec.get(key) != handoff_spec.get(key):
            errors.append({"rule": "HANDOFF_AUTHORING_SPEC_MISMATCH", "message": f"Disk spec field `{key}` does not match READY_FOR_GENERATION.authoringSpec."})
    return errors


def normalize_supporting_assets(value: Any) -> list[dict[str, str]]:
    """Validate explicit optional assets without widening the default deployment tree."""

    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("`supporting_assets` must be an array when provided.")
    normalized: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, asset in enumerate(value):
        if not isinstance(asset, dict):
            raise ValueError(f"`supporting_assets[{index}]` must be an object.")
        kind = str(asset.get("kind", "")).strip()
        raw_path = str(asset.get("path", "")).strip().replace("\\", "/")
        content = asset.get("content")
        reason = str(asset.get("reason", "")).strip()
        if kind not in SUPPORTING_ASSET_RULES:
            raise ValueError(f"`supporting_assets[{index}].kind` is not supported: {kind}")
        relative = PurePosixPath(raw_path)
        relative_path = relative.as_posix()
        if not raw_path or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"`supporting_assets[{index}].path` must stay inside the target root.")
        prefix, suffix = SUPPORTING_ASSET_RULES[kind]
        if not relative_path.startswith(prefix) or (suffix and not relative_path.endswith(suffix)):
            raise ValueError(f"`supporting_assets[{index}].path` is invalid for kind `{kind}`.")
        if kind == "workflow-spec-ir" and relative_path != ".workflowprogram/design/workflow-spec.yaml":
            raise ValueError("`workflow-spec-ir` must use `.workflowprogram/design/workflow-spec.yaml`.")
        if relative_path in seen_paths:
            raise ValueError(f"Duplicate supporting asset path: {relative_path}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"`supporting_assets[{index}].content` must be a non-empty string.")
        if not reason:
            raise ValueError(f"`supporting_assets[{index}].reason` must explain why the optional asset is needed.")
        seen_paths.add(relative_path)
        normalized.append(
            {
                "kind": kind,
                "path": relative_path,
                "content": content.rstrip() + "\n",
                "reason": reason,
            }
        )
    return normalized


def normalize_task_model_policy(value: Any) -> dict[str, Any]:
    """Validate optional target workflow task-model metadata."""

    if value is None:
        return {"agent_task_models": {}}
    if not isinstance(value, dict):
        raise ValueError("`task_model_policy` must be an object when provided.")
    raw_agent_task_models = value.get("agent_task_models", {})
    if raw_agent_task_models is None:
        raw_agent_task_models = {}
    if not isinstance(raw_agent_task_models, dict):
        raise ValueError("`task_model_policy.agent_task_models` must be an object when provided.")
    agent_task_models: dict[str, str] = {}
    for label, task_type in raw_agent_task_models.items():
        if not isinstance(label, str) or not label.strip():
            raise ValueError("`task_model_policy.agent_task_models` keys must be non-empty strings.")
        if not isinstance(task_type, str) or not task_type.strip():
            raise ValueError("`task_model_policy.agent_task_models` values must be non-empty strings.")
        agent_task_models[label.strip()] = task_type.strip()
    return {"agent_task_models": agent_task_models}


def render_workflow(spec: dict[str, Any]) -> str:
    """Render a deterministic Native Workflow JS file."""

    meta = {
        "name": spec["name"],
        "description": spec["description"],
        "phases": spec["phases"],
    }
    task_policy = spec.get("task_model_policy") or {}
    agent_task_models = task_policy.get("agent_task_models") or {}
    body = spec["body"]
    if agent_task_models:
        body = AGENT_CALL_PATTERN.sub("workflowprogramAgent(", body)
        helper = (
            f"const taskModels = args?.taskModels || {{}}\n"
            f"const agentTaskTypes = {json.dumps(agent_task_models, ensure_ascii=False, indent=2)}\n"
            "const withTaskModel = (taskType, options) => {\n"
            "  const alias = typeof taskModels[taskType] === 'string' ? taskModels[taskType].trim() : ''\n"
            "  if (!alias || alias === 'inherit') return options\n"
            "  return { ...options, model: alias }\n"
            "}\n"
            "const workflowprogramAgent = async (prompt, options = {}) => {\n"
            "  const taskType = typeof options?.label === 'string' ? agentTaskTypes[options.label] || '' : ''\n"
            "  return agent(prompt, withTaskModel(taskType, options))\n"
            "}\n\n"
        )
    else:
        helper = ""
    return f"export const meta = {json.dumps(meta, ensure_ascii=False, indent=2)}\n\n{helper}{body}"


def generation_report(
    *,
    status: str,
    spec_path: Path,
    target_root: Path,
    run_root: Path,
    candidate_script: Path | None,
    target_script: Path | None,
    validation_report: Path | None,
    readiness_report: Path | None,
    generation_handoff_report: Path | None = None,
    apply_requested: bool,
    managed_result: dict[str, Any] | None = None,
    supporting_assets: list[dict[str, str]] | None = None,
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build one normalized generation report."""

    payload: dict[str, Any] = {
        "schema_version": 1,
        "schema_name": "native-workflow-js-generation",
        "status": status,
        "spec": str(spec_path.resolve()),
        "target_root": str(target_root.resolve()),
        "run_root": str(run_root.resolve()),
        "candidate_script": str(candidate_script.resolve()) if candidate_script else None,
        "target_script": str(target_script.resolve()) if target_script else None,
        "validation_report": str(validation_report.resolve()) if validation_report else None,
        "readiness_report": str(readiness_report.resolve()) if readiness_report else None,
        "generation_handoff_report": str(generation_handoff_report.resolve()) if generation_handoff_report else None,
        "apply_requested": apply_requested,
        "managed_result": managed_result,
        "supporting_assets": [
            {"kind": item["kind"], "path": item["path"], "reason": item["reason"]}
            for item in (supporting_assets or [])
        ],
        "errors": errors or [],
    }
    return payload


def run_managed_apply(target_root: Path, candidate_root: Path, run_root: Path, producer_version: str | None) -> tuple[int, dict[str, Any]]:
    """Delegate target writes to the existing managed-assets implementation."""

    command = [
        sys.executable,
        str(Path(__file__).resolve().with_name("managed-assets.py")),
        "apply-staged",
        "--target-root",
        str(target_root),
        "--source-root",
        str(candidate_root),
        "--run-root",
        str(run_root),
        "--json",
    ]
    if producer_version:
        command.extend(["--producer-version", producer_version])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "managed-assets.py returned invalid JSON") from exc
    return completed.returncode, payload


def build_parser() -> argparse.ArgumentParser:
    """Build the generator CLI."""

    parser = argparse.ArgumentParser(description="Generate one Claude Code Native Workflow JS candidate")
    parser.add_argument("--spec", required=True, help="Path to the JSON Native Workflow authoring spec")
    gate = parser.add_mutually_exclusive_group(required=True)
    gate.add_argument(
        "--generation-handoff",
        default="",
        help="READY_FOR_GENERATION handoff packet from workflowprogram-develop.js (M15 primary path)",
    )
    gate.add_argument(
        "--readiness",
        default="",
        help="Confirmed Native authoring requirement packet (M7 compatibility mode)",
    )
    parser.add_argument("--target-root", required=True, help="Target project root")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT for candidate files and reports")
    parser.add_argument("--apply", action="store_true", help="Apply the candidate through managed-assets.py")
    parser.add_argument("--producer-version", help="Override managed-assets producer version")
    parser.add_argument("--json", action="store_true", help="Print structured JSON")
    return parser


def emit(payload: dict[str, Any], as_json: bool) -> None:
    """Print one result for callers and tests."""

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {payload.get('candidate_script') or payload['spec']}")


def _resolve_gate_path(
    generation_handoff_arg: str,
    readiness_arg: str,
    target_root: Path,
    run_root: Path,
    stages_root: Path,
) -> tuple[str, Path | None, Path | None, Path | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Determine which gate mode to use and validate the input.

    Returns (mode, handoff_path, readiness_path, readiness_report_path, handoff_validation, readiness_result).
    mode is one of 'generation-handoff', 'readiness', or 'none'.
    handoff_validation is the structured validate_handoff() report (PASS or FAIL).
    When readiness validation fails, readiness_result contains the validation report
    and the caller must handle the failure.
    """
    handoff_path = Path(generation_handoff_arg).resolve() if generation_handoff_arg.strip() else None
    readiness_path = Path(readiness_arg).resolve() if readiness_arg.strip() else None

    # --generation-handoff is the M15 primary path
    if handoff_path is not None:
        handoff_validation = validate_handoff(handoff_path, target_root, run_root)
        return ("generation-handoff", handoff_path, None, None, handoff_validation, None)

    # --readiness is the M7 compatibility fallback
    if readiness_path is not None:
        readiness_report_path = stages_root / "native-authoring-readiness.json"
        readiness = load_readiness_validator_module().validate_readiness(readiness_path, target_root)
        write_json(readiness_report_path, readiness)
        return ("readiness", None, readiness_path, readiness_report_path, None, readiness)

    # Mutual exclusion is enforced by argparse, so this branch should not be reachable.
    raise ValueError("Either --generation-handoff or --readiness must be provided.")


def main() -> int:
    """Generate, validate, and optionally apply one Native Workflow JS file."""

    args = build_parser().parse_args()
    spec_path = Path(args.spec).resolve()
    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    stages_root = run_root / "outputs" / "stages"
    generation_path = stages_root / "native-workflow-generation.json"
    handoff_validation_path = stages_root / "native-workflow-generation-handoff.json"
    validation_path = stages_root / "native-workflow-validation.json"
    candidate_root = run_root / "outputs" / "candidate"

    handoff_path: Path | None = None
    readiness_report_path: Path | None = None
    generation_handoff_report_path: Path | None = None

    try:
        gate_mode, handoff_path, _, readiness_report_path, handoff_validation, readiness_result = _resolve_gate_path(
            args.generation_handoff, args.readiness, target_root, run_root, stages_root,
        )

        # Persist handoff validation report regardless of PASS/FAIL
        if handoff_validation is not None:
            generation_handoff_report_path = handoff_validation_path
            write_json(generation_handoff_report_path, handoff_validation)

        # When handoff validation fails, return FAIL before creating candidate files
        if handoff_validation is not None and handoff_validation["status"] != "PASS":
            payload = generation_report(
                status="FAIL",
                spec_path=spec_path,
                target_root=target_root,
                run_root=run_root,
                candidate_script=None,
                target_script=None,
                validation_report=None,
                readiness_report=readiness_report_path,
                generation_handoff_report=generation_handoff_report_path,
                apply_requested=args.apply,
                errors=handoff_validation["errors"],
            )
            write_json(generation_path, payload)
            emit(payload, args.json)
            return 1

        # When readiness validation fails, return FAIL before creating candidate files
        if readiness_result is not None and readiness_result["status"] != "PASS":
            payload = generation_report(
                status="FAIL",
                spec_path=spec_path,
                target_root=target_root,
                run_root=run_root,
                candidate_script=None,
                target_script=None,
                validation_report=None,
                readiness_report=readiness_report_path,
                generation_handoff_report=generation_handoff_report_path,
                apply_requested=args.apply,
                errors=readiness_result["errors"],
            )
            write_json(generation_path, payload)
            emit(payload, args.json)
            return 1

        spec = load_authoring_spec(spec_path)
        if gate_mode == "generation-handoff" and handoff_path is not None:
            alignment_errors = validate_handoff_spec_alignment(spec, handoff_path)
            if alignment_errors:
                payload = generation_report(
                    status="FAIL",
                    spec_path=spec_path,
                    target_root=target_root,
                    run_root=run_root,
                    candidate_script=None,
                    target_script=None,
                    validation_report=None,
                    readiness_report=readiness_report_path,
                    generation_handoff_report=generation_handoff_report_path,
                    apply_requested=args.apply,
                    supporting_assets=spec["supporting_assets"],
                    errors=alignment_errors,
                )
                write_json(generation_path, payload)
                emit(payload, args.json)
                return 1
        candidate_script = candidate_root / ".claude" / "workflows" / f"{spec['name']}.js"
        candidate_script.parent.mkdir(parents=True, exist_ok=True)
        candidate_script.write_text(render_workflow(spec), encoding="utf-8", newline="\n")
        for asset in spec["supporting_assets"]:
            asset_path = candidate_root / Path(asset["path"])
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_text(asset["content"], encoding="utf-8", newline="\n")
        validation = load_validator_module().validate_script(candidate_script)
        write_json(validation_path, validation)
        target_script = target_root / ".claude" / "workflows" / f"{spec['name']}.js"
        if validation["status"] != "PASS":
            payload = generation_report(
                status="FAIL",
                spec_path=spec_path,
                target_root=target_root,
                run_root=run_root,
                candidate_script=candidate_script,
                target_script=target_script,
                validation_report=validation_path,
                readiness_report=readiness_report_path,
                generation_handoff_report=generation_handoff_report_path,
                apply_requested=args.apply,
                supporting_assets=spec["supporting_assets"],
                errors=validation["errors"],
            )
            write_json(generation_path, payload)
            emit(payload, args.json)
            return 1

        managed_result = None
        status = "PASS"
        return_code = 0
        if args.apply:
            return_code, managed_result = run_managed_apply(target_root, candidate_root, run_root, args.producer_version)
            if return_code == 2 or managed_result.get("conflicts"):
                status = "CONFLICT"
                return_code = 2
            elif return_code != 0:
                status = "FAIL"
                return_code = 1

        payload = generation_report(
            status=status,
            spec_path=spec_path,
            target_root=target_root,
            run_root=run_root,
            candidate_script=candidate_script,
            target_script=target_script,
            validation_report=validation_path,
            readiness_report=readiness_report_path,
            generation_handoff_report=generation_handoff_report_path,
            apply_requested=args.apply,
            managed_result=managed_result,
            supporting_assets=spec["supporting_assets"],
        )
        write_json(generation_path, payload)
        emit(payload, args.json)
        return return_code
    except ValueError as exc:
        payload = generation_report(
            status="FAIL",
            spec_path=spec_path,
            target_root=target_root,
            run_root=run_root,
            candidate_script=None,
            target_script=None,
            validation_report=None,
            readiness_report=readiness_report_path,
            generation_handoff_report=generation_handoff_report_path,
            apply_requested=args.apply,
            errors=[{"rule": "SPEC_INVALID", "message": str(exc)}],
        )
        write_json(generation_path, payload)
        emit(payload, args.json)
        return 1
    except Exception as exc:
        payload = generation_report(
            status="FAIL",
            spec_path=spec_path,
            target_root=target_root,
            run_root=run_root,
            candidate_script=None,
            target_script=None,
            validation_report=None,
            readiness_report=readiness_report_path,
            generation_handoff_report=generation_handoff_report_path,
            apply_requested=args.apply,
            errors=[{"rule": "INTERNAL_ERROR", "message": str(exc)}],
        )
        write_json(generation_path, payload)
        emit(payload, args.json)
        return 1


if __name__ == "__main__":
    sys.exit(main())
