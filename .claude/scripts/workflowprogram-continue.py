#!/usr/bin/env python3
"""Deterministic continuation script for WorkflowProgram Native READY_FOR_GENERATION.

Consumes a saved workflowprogram-develop.js READY_FOR_GENERATION result,
unwraps ``{result}`` envelopes, writes the handoff input and authoring spec
files, invokes ``generate-native-workflow.py --generation-handoff`` without
``--apply``, builds generation evidence via ``build-native-develop-evidence.py
generation``, and emits a structured continuation report.

This script is the ONLY foreground path allowed by the guard for the
READY_FOR_GENERATION state. The foreground must not handwrite the handoff,
authoring spec, or JS body.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON file into a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a dict as JSON, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def unwrap_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a ``{result: {...}}`` envelope when the inner object has
    ``status`` and ``workflow`` keys (the workflow JS respond() shape).

    If the payload already looks like a direct workflow result, return it
    unchanged.
    """
    inner = payload.get("result")
    if not isinstance(inner, dict):
        return payload
    # Only unwrap when the inner object carries the workflow result shape.
    if "status" in inner and "workflow" in inner:
        return inner
    return payload


def resolve_sibling_script(name: str) -> Path:
    """Return the absolute path to a sibling script in the same directory."""
    return Path(__file__).resolve().with_name(name)


def run_script(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a Python script with extra args and ``--json`` appended."""
    return subprocess.run(
        [sys.executable, str(script), *args, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def emit_report(report: dict[str, Any], out_path: Path | None, as_json: bool) -> None:
    """Persist and/or print one continuation report."""
    if out_path is not None:
        write_json(out_path, report)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("status") == "PASS":
        print(f"PASS: {out_path or report.get('stage')}")
    else:
        print("FAIL: " + "; ".join(str(item) for item in report.get("blockingIssues", [])), file=sys.stderr)


def project_template_phase_metadata(authoring_spec: dict[str, Any]) -> dict[str, Any]:
    """Project template phases from phase_contracts before persistence."""

    template = str(authoring_spec.get("template", "")).strip()
    phase_contracts = authoring_spec.get("phase_contracts")
    if not template or not isinstance(phase_contracts, list) or not phase_contracts:
        return authoring_spec

    derived_phases: list[dict[str, str]] = []
    for index, contract in enumerate(phase_contracts):
        if not isinstance(contract, dict):
            raise ValueError(f"phase_contracts[{index}] must be an object.")
        title = str(contract.get("phase", "")).strip()
        if not title:
            raise ValueError(f"phase_contracts[{index}].phase must be a non-empty string.")
        phase: dict[str, str] = {"title": title}
        detail = str(contract.get("detail", "")).strip()
        if detail:
            phase["detail"] = detail
        derived_phases.append(phase)

    explicit_phases = authoring_spec.get("phases")
    if explicit_phases is not None and not isinstance(explicit_phases, list):
        raise ValueError("Template authoring spec phases must be an array when provided.")
    if isinstance(explicit_phases, list) and explicit_phases:
        explicit_titles = [
            str(phase.get("title", "")).strip()
            for phase in explicit_phases
            if isinstance(phase, dict) and str(phase.get("title", "")).strip()
        ]
        derived_titles = [phase["title"] for phase in derived_phases]
        if explicit_titles != derived_titles:
            raise ValueError(
                "Template authoring spec phases must match phase_contracts[].phase values."
            )

    return {**authoring_spec, "phases": derived_phases}


def handoff_envelope_from_result(result: dict[str, Any], target_root: Path, run_root: Path) -> dict[str, Any]:
    """Build the generator handoff from product-owned fields only.

    Newer product JS returns a complete ``generationHandoff`` object. Older
    results carry the same fields at top level. In both cases this helper
    copies product-owned values and only normalizes target/run paths to the CLI
    roots used by the deterministic generator.
    """
    source = result.get("generationHandoff") if isinstance(result.get("generationHandoff"), dict) else result
    generation_request = source.get("generationRequest")
    if not isinstance(generation_request, dict):
        generation_request = result.get("generationRequest")
    if not isinstance(generation_request, dict):
        raise ValueError("generationRequest is missing or not a JSON object.")
    authoring_spec = source.get("authoringSpec", result.get("authoringSpec"))
    if isinstance(authoring_spec, dict):
        authoring_spec = project_template_phase_metadata(authoring_spec)
    normalized_generation_request = dict(generation_request)
    normalized_generation_request["targetRoot"] = str(target_root)
    normalized_generation_request["runRoot"] = str(run_root)
    handoff: dict[str, Any] = {
        "status": source.get("status", result.get("status")),
        "workflow": source.get("workflow", result.get("workflow")),
        "launchMode": source.get("launchMode", result.get("launchMode")),
        "runId": source.get("runId", result.get("runId")),
        "targetRoot": str(target_root),
        "runRoot": str(run_root),
        "requirementSummary": source.get("requirementSummary", result.get("requirementSummary")),
        "designEvidence": source.get("designEvidence", result.get("designEvidence")),
        "reviewEvidence": source.get("reviewEvidence", result.get("reviewEvidence")),
        "authoringSpec": authoring_spec,
        "generationRequest": normalized_generation_request,
    }
    return {key: value for key, value in handoff.items() if value is not None}


def build_continuation_report(
    result: dict[str, Any],
    target_root: Path,
    run_root: Path,
    handoff_input_path: Path,
    authoring_path: Path,
    generation_report_path: Path,
    generation_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Produce a structured continuation report with handoff and evidence paths."""
    return {
        "status": "PASS",
        "schemaName": "workflowprogram-continuation-report",
        "schemaVersion": 1,
        "workflow": result.get("workflow", "workflowprogram-develop"),
        "runId": result.get("runId", ""),
        "targetRoot": str(target_root),
        "runRoot": str(run_root),
        "stage": "READY_FOR_GENERATION",
        "handoffInputPath": str(handoff_input_path),
        "authoringPath": str(authoring_path),
        "generationReportPath": str(generation_report_path),
        "generationEvidence": generation_evidence,
        "nextAction": "REINVOKE_PRODUCT_JS_WITH_GENERATION_EVIDENCE",
        "continuationCommand": (
            "Workflow({ scriptPath: '<PLUGIN_ROOT>/workflows/workflowprogram-develop.js',"
            " args: { ...prevArgs, generationEvidence: <evidence> } })"
        ),
    }


def _validate_authoring_spec_canonical(authoring_spec: dict[str, Any]) -> None:
    """Phase 3: Validate canonical projection rules on the authoring spec.

    This is a safety net - the develop.js should have already projected the
    canonical spec, but this catches any drift before persistence.
    """
    name = str(authoring_spec.get("name", "")).strip()
    if not name:
        return
    primary_workflow_path = f".claude/workflows/{name}.js"

    asset_disposition = authoring_spec.get("asset_disposition", [])
    supporting_assets = authoring_spec.get("supporting_assets", [])

    # Primary workflow path must not be in supporting_assets
    for asset in supporting_assets:
        asset_path = str(asset.get("path", "")).strip()
        if asset_path == primary_workflow_path:
            raise ValueError(
                f"Canonical violation: primary workflow path in supporting_assets: {asset_path}"
            )

    # Primary workflow disposition must not carry supporting_asset_path
    for item in asset_disposition:
        path = str(item.get("path", "")).strip()
        sap = str(item.get("supporting_asset_path", "")).strip()
        if path == primary_workflow_path and sap:
            raise ValueError(
                f"Canonical violation: primary workflow disposition with supporting_asset_path: {path}"
            )


def build_error_report(
    target_root: Path,
    run_root: Path,
    errors: list[str],
) -> dict[str, Any]:
    """Produce a FAIL report with blocking issues."""
    return {
        "status": "FAIL",
        "schemaName": "workflowprogram-continuation-report",
        "schemaVersion": 1,
        "stage": "READY_FOR_GENERATION",
        "targetRoot": str(target_root),
        "runRoot": str(run_root),
        "blockingIssues": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WorkflowProgram Native deterministic continuation for READY_FOR_GENERATION"
    )
    parser.add_argument(
        "--workflow-result",
        required=True,
        help="Path to the saved READY_FOR_GENERATION JS result JSON",
    )
    parser.add_argument(
        "--target-root",
        required=True,
        help="TARGET_ROOT absolute path",
    )
    parser.add_argument(
        "--run-root",
        required=True,
        help="RUN_ROOT absolute path",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON report",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional continuation report path; defaults to RUN_ROOT/outputs/stages/workflowprogram-continuation-generation.json",
    )
    args = parser.parse_args()

    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    continuation_report_path = (
        Path(args.out).resolve()
        if args.out.strip()
        else run_root / "outputs" / "stages" / "workflowprogram-continuation-generation.json"
    )
    errors: list[str] = []

    try:
        # ── 1. Load and unwrap the workflow result ──────────────────────────
        raw = load_json(Path(args.workflow_result))
        result = unwrap_result(raw)

        if not isinstance(result, dict):
            raise ValueError("Workflow result must be a JSON object after unwrapping.")

        status = str(result.get("status", "")).strip()
        if status != "READY_FOR_GENERATION":
            raise ValueError(
                f"Expected status READY_FOR_GENERATION, got: {status or '<empty>'}"
            )

        workflow = str(result.get("workflow", "")).strip()
        if workflow != "workflowprogram-develop":
            raise ValueError(
                f"Expected workflow 'workflowprogram-develop', got: {workflow or '<empty>'}"
            )

        run_id = str(result.get("runId", "")).strip()
        if not run_id:
            raise ValueError("runId must be a non-empty string.")

        # ── 2. Extract authoringSpec and generationRequest ─────────────────
        authoring_spec = result.get("authoringSpec")
        if not isinstance(authoring_spec, dict):
            raise ValueError("authoringSpec is missing or not a JSON object.")
        authoring_spec = project_template_phase_metadata(authoring_spec)
        result = {**result, "authoringSpec": authoring_spec}
        if isinstance(result.get("generationHandoff"), dict):
            generation_handoff = dict(result["generationHandoff"])
            handoff_authoring_spec = generation_handoff.get("authoringSpec")
            generation_handoff["authoringSpec"] = project_template_phase_metadata(
                handoff_authoring_spec if isinstance(handoff_authoring_spec, dict) else authoring_spec
            )
            result["generationHandoff"] = generation_handoff

        # Phase 3: Validate canonical projection consistency
        # The generator will also revalidate, but continue.py validates early.
        _validate_authoring_spec_canonical(authoring_spec)

        # ── 3. Write handoff input JSON ────────────────────────────────────
        handoff_input_path = (
            run_root / "outputs" / "stages" / "native-workflow-generation-handoff-input.json"
        )
        handoff_envelope = handoff_envelope_from_result(result, target_root, run_root)
        write_json(handoff_input_path, handoff_envelope)

        # ── 4. Write authoring spec JSON ───────────────────────────────────
        authoring_path = run_root / "native-workflow-authoring.json"
        write_json(authoring_path, authoring_spec)

        # ── 5. Run generator (no --apply) ──────────────────────────────────
        generator_script = resolve_sibling_script("generate-native-workflow.py")
        gen_result = run_script(
            generator_script,
            [
                "--spec",
                str(authoring_path),
                "--generation-handoff",
                str(handoff_input_path),
                "--target-root",
                str(target_root),
                "--run-root",
                str(run_root),
            ],
        )

        if gen_result.returncode != 0:
            gen_stderr = gen_result.stderr.strip() if gen_result.stderr else ""
            gen_stdout = gen_result.stdout.strip() if gen_result.stdout else ""
            gen_output = gen_stderr or gen_stdout or "generator returned non-zero exit code"
            # Try to extract structured errors from the generator output.
            try:
                gen_payload = json.loads(gen_stdout or gen_stderr)
                gen_errors = gen_payload.get("errors", [])
                if gen_errors:
                    gen_output = "; ".join(
                        str(e.get("message", e)) if isinstance(e, dict) else str(e)
                        for e in gen_errors
                    )
            except (json.JSONDecodeError, AttributeError):
                pass
            errors.append(f"Generator failed: {gen_output}")
            report = build_error_report(target_root, run_root, errors)
            emit_report(report, continuation_report_path, args.json)
            return 1

        # ── 6. Build generation evidence ───────────────────────────────────
        evidence_script = resolve_sibling_script("build-native-develop-evidence.py")
        gen_report_path = run_root / "outputs" / "stages" / "native-workflow-generation.json"
        ev_result = run_script(
            evidence_script,
            [
                "generation",
                "--candidate-root",
                str(run_root / "outputs" / "candidate"),
                "--report",
                str(gen_report_path),
            ],
        )

        if ev_result.returncode != 0:
            ev_output = ev_result.stderr.strip() or ev_result.stdout.strip() or "unknown error"
            errors.append(f"Evidence builder failed: {ev_output}")
            report = build_error_report(target_root, run_root, errors)
            emit_report(report, continuation_report_path, args.json)
            return 1

        generation_evidence = json.loads(ev_result.stdout)

        if generation_evidence.get("status") != "PASS":
            issues = "; ".join(generation_evidence.get("blockingIssues", []))
            errors.append(f"Generation evidence did not pass: {issues or 'unknown reason'}")
            report = build_error_report(target_root, run_root, errors)
            emit_report(report, continuation_report_path, args.json)
            return 1

        # ── 7. Emit structured continuation report ─────────────────────────
        report = build_continuation_report(
            result=result,
            target_root=target_root,
            run_root=run_root,
            handoff_input_path=handoff_input_path,
            authoring_path=authoring_path,
            generation_report_path=gen_report_path,
            generation_evidence=generation_evidence,
        )
        report["continuationReportPath"] = str(continuation_report_path)

        emit_report(report, continuation_report_path, args.json)

        return 0

    except Exception as exc:
        errors.append(str(exc))
        report = build_error_report(target_root, run_root, errors)
        emit_report(report, continuation_report_path, args.json)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
