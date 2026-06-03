#!/usr/bin/env python3
"""Determine fact-driven legacy runtime retirement eligibility.

Produces a structured JSON assessment with:
  - requiredAssets / missingRequiredAssets
  - dispositions (retain / replace / narrow / remove)
  - blockingIssues (stable rule ids with evidence refs)
  - removalPlan (grouped by disposition)

The assessor is READ-ONLY.  It never deletes or modifies any asset.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SCHEMA_NAME = "native-legacy-retirement-assessment"

REQUIRED_ASSESSMENT_ASSETS: list[str] = [
    ".claude/scripts/assess-native-legacy-retirement.py",
    "tests/unit/test_native_legacy_retirement.py",
    "docs/native-workflow-control-plane-migration-plan.md",
]

LEGACY_PATHS: list[dict[str, Any]] = [
    {
        "id": "workflow-entry-py",
        "paths": [".claude/scripts/workflow-entry.py"],
        "default_disposition": "remove",
        "reason": "Replaced by Workflow tool runtime and product workflow JS",
        "removeWhen": [
            "All five product JS have PASS smoke evidence",
            "No legacy target depends on workflow-entry.py",
        ],
    },
    {
        "id": "workflow-runner-py",
        "paths": [".claude/scripts/workflow-runner.py"],
        "default_disposition": "remove",
        "reason": "Stage orchestration replaced by Native JS control flow",
        "removeWhen": [
            "Develop / Audit / Iterate / Validate / Publish all use Native JS",
            "No caller references workflow-runner.py",
        ],
    },
    {
        "id": "workflow-s5-judge-py",
        "paths": [".claude/scripts/workflow-s5-judge.py"],
        "default_disposition": "narrow",
        "reason": "S5 judge logic may be retained as optional deterministic check",
        "removeWhen": [
            "S5 domain checks ported to L1/L2/L3 validation in product JS",
            "No legacy reference to s5 workflow model remains",
        ],
    },
    {
        "id": "generate-target-runtime-py",
        "paths": [".claude/scripts/generate-target-runtime.py"],
        "default_disposition": "remove",
        "reason": "Target runtime generation is replaced by Workflow JS delivery",
        "removeWhen": [
            "No target depends on generated runtime template",
            "Native product workflows control target asset generation",
        ],
    },
    {
        "id": "workflow-spec-yaml-default",
        "paths": [".claude/skills/workflow-spec-support/yaml-spec-template.md"],
        "default_disposition": "narrow",
        "reason": "workflow-spec.yaml default generation removed; keep template for opt-in IR scenarios",
        "removeWhen": [
            "No opt-in IR scenarios require the YAML template",
            "All design-to-generation pipelines use direct JS authoring",
        ],
    },
    {
        "id": "target-runtime-dir",
        "paths": [".workflowprogram/runtime/"],
        "default_disposition": "remove",
        "reason": "Legacy target runtime directory not created for new Native workflows",
        "removeWhen": [
            "No existing target uses .workflowprogram/runtime/",
            "Migration plan covers all legacy targets",
        ],
    },
    {
        "id": "route-native-control-plane-py",
        "paths": [".claude/scripts/route-native-control-plane.py"],
        "default_disposition": "narrow",
        "reason": "Keep as deterministic router; remove legacy-compatible routing after all targets migrate",
        "removeWhen": [
            "All legacy targets migrated to Native mode",
            "route-native-control-plane.py no longer routes to legacy entries",
        ],
    },
    {
        "id": "native-authoring-js",
        "paths": [".claude/workflows/workflowprogram-native-authoring.js"],
        "default_disposition": "replace",
        "reason": "Transitional M7 renderer bridge; functionality merges into workflowprogram-develop.js",
        "removeWhen": [
            "workflowprogram-develop.js covers all native-authoring stages",
            "No caller references workflowprogram-native-authoring.js",
        ],
    },
    {
        "id": "generate-native-workflow-py",
        "paths": [".claude/scripts/generate-native-workflow.py"],
        "default_disposition": "narrow",
        "reason": "Keep as deterministic renderer; remove JSON authoring spec as default semantic source",
        "removeWhen": [
            "Design docs directly drive JS generation without JSON spec intermediate",
            "No caller depends on JSON authoring spec format",
        ],
    },
    {
        "id": "validate-native-authoring-readiness-py",
        "paths": [".claude/scripts/validate-native-authoring-readiness.py"],
        "default_disposition": "narrow",
        "reason": "Keep as deterministic readiness check; JS Clarify/Confirm stages may call it",
        "removeWhen": [
            "Clarify/Confirm in workflowprogram-develop.js fully covers readiness checks",
            "No foreground path calls validate-native-authoring-readiness.py directly",
        ],
    },
    {
        "id": "deterministic-validators",
        "paths": [
            ".claude/scripts/validate-native-workflow-js.py",
            ".claude/scripts/validate-lessons-delta.py",
            ".claude/scripts/validate-publish-qualification.py",
        ],
        "default_disposition": "retain",
        "reason": "Lightweight static validators remain as deterministic L2/L3 fact checks",
        "removeWhen": [
            "A replacement preserves deterministic L2/L3 validation coverage",
        ],
    },
    {
        "id": "managed-assets-py",
        "paths": [".claude/scripts/managed-assets.py"],
        "default_disposition": "retain",
        "reason": "Controlled apply with candidate hash, drift detection, and idempotency protection",
        "removeWhen": [
            "A replacement preserves controlled apply, drift detection, and idempotency guarantees",
        ],
    },
    {
        "id": "evidence-builders",
        "paths": [
            ".claude/scripts/build-native-develop-evidence.py",
            ".claude/scripts/build-native-iterate-evidence.py",
            ".claude/scripts/build-native-publish-evidence.py",
            ".claude/scripts/build-native-workflow-manifest.py",
        ],
        "default_disposition": "narrow",
        "reason": "Keep as narrow host-side adapters; compute hash and normalize evidence only",
        "removeWhen": [
            "Evidence normalization is fully handled inside product workflow JS",
            "No host-side evidence adapter is called",
        ],
    },
    {
        "id": "interactive-smoke-harness",
        "paths": [".claude/scripts/build-native-interactive-smoke.py"],
        "default_disposition": "retain",
        "reason": "M11 v1 packet + evaluate harness; Computer Use terminal-driving deferred",
        "removeWhen": [
            "A replacement preserves interactive smoke packet generation and deterministic JSONL evaluation",
        ],
    },
]


# Blocking issue rule definitions (stable ids, content-driven detection)
BLOCKING_RULES: list[dict[str, Any]] = [
    {
        "id": "required-assessment-assets-missing",
        "description": (
            "One or more required assessment source assets are absent. "
            "The assessor itself, its tests, and the migration plan document must exist."
        ),
        "detection": "file-exists",
    },
    {
        "id": "transitional-renderer-bridge-active",
        "description": (
            "The transitional M7 renderer bridge (workflowprogram-native-authoring.js, "
            "validate-native-authoring-readiness.py, or --readiness) is still referenced "
            "as the primary path by active skills/commands. "
            "Blocker closes when no active skill/command references these bridge assets "
            "as the primary path (generate-native-workflow.py and --generation-handoff "
            "are not blocker references)."
        ),
        "detection": "content-scan",
    },
    {
        "id": "full-product-interactive-smoke-not-declared-complete",
        "description": (
            "Interactive smoke evidence for all five product workflows (develop, validate, "
            "audit, iterate, publish) has not been declared complete. "
            "Blocker closes when evidence JSON at .workflowprogram/evidence/"
            "native-product-interactive-smoke.json explicitly declares full coverage."
        ),
        "detection": "evidence-json",
    },
    {
        "id": "legacy-compatibility-routing-active",
        "description": (
            "route-native-control-plane.py still contains legacy-compatibility routing markers "
            "or routes existing legacy targets to the legacy entry. "
            "Blocker closes when the script no longer references legacy markers/routes."
        ),
        "detection": "content-scan",
    },
    {
        "id": "rollback-deprecation-anchor-missing",
        "description": (
            "No explicit rollback version tag or deprecation anchor evidence exists. "
            "Blocker closes when .workflowprogram/evidence/legacy-retirement-anchor.json "
            "contains a non-empty known-good ref and explicit deprecation notice."
        ),
        "detection": "evidence-json",
    },
]


def _utc_now() -> str:
    """ISO-8601 UTC timestamp without microsecond noise."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_text_safe(path: Path) -> str | None:
    """Read file as UTF-8 text; return None if absent or not decodable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _file_exists(path: Path) -> bool:
    """Check whether a file exists and is a regular file."""
    return path.is_file()


def _check_required_assets(repo_root: Path) -> dict[str, Any]:
    """Verify every required assessment asset exists.

    Returns a dict with:
      requiredAssets: full list of expected relative paths
      missingRequiredAssets: subset that does not exist on disk
    """
    present: list[str] = []
    missing: list[str] = []
    for rel in REQUIRED_ASSESSMENT_ASSETS:
        if _file_exists(repo_root / rel):
            present.append(rel)
        else:
            missing.append(rel)
    return {
        "requiredAssets": sorted(REQUIRED_ASSESSMENT_ASSETS),
        "presentRequiredAssets": sorted(present),
        "missingRequiredAssets": sorted(missing),
    }


def _check_legacy_paths(repo_root: Path) -> list[dict[str, Any]]:
    """Inventory each known legacy path and compute a disposition.

    Each entry records whether the path exists, the pre-assigned default
    disposition, and the removal preconditions.  Paths that don't exist
    are inventoried with exists=false rather than silently omitted.
    """
    dispositions: list[dict[str, Any]] = []
    for entry in LEGACY_PATHS:
        path_stati: dict[str, bool] = {}
        for rel in entry["paths"]:
            path_stati[rel] = (repo_root / rel).exists()
        dispositions.append(
            {
                "id": entry["id"],
                "paths": list(entry["paths"]),
                "disposition": entry["default_disposition"],
                "reason": entry["reason"],
                "removeWhen": list(entry["removeWhen"]),
                "exists": path_stati,
            }
        )
    return dispositions


def _detect_blocking_issues(repo_root: Path, evidence_root: Path | None) -> list[dict[str, Any]]:
    """Evaluate each blocking rule against the current repo state.

    Returns a list of active blocker dicts.  A rule that does not block
    is omitted from the list.
    """
    ev_root: Path = (evidence_root or repo_root).resolve()
    active: list[dict[str, Any]] = []

    # Rule 1: required-assessment-assets-missing
    asset_check = _check_required_assets(repo_root)
    if asset_check["missingRequiredAssets"]:
        active.append(
            {
                "id": "required-assessment-assets-missing",
                "active": True,
                "evidence": {
                    "missingAssets": list(asset_check["missingRequiredAssets"]),
                    "source": "file-system scan of repo root",
                },
            }
        )

    # Rule 2: transitional-renderer-bridge-active
    # Only inventory presence (for documentation), but scan active skills/commands
    # for compatibility references that indicate the bridge is still the primary path.
    bridge_files = [
        ".claude/workflows/workflowprogram-native-authoring.js",
        ".claude/scripts/generate-native-workflow.py",
        ".claude/scripts/validate-native-authoring-readiness.py",
    ]
    bridge_refs: list[str] = []
    for rel in bridge_files:
        if _file_exists(repo_root / rel):
            bridge_refs.append(rel)

    # Scan skills and commands for active compatibility references.
    # Blocker references are: workflowprogram-native-authoring.js,
    # validate-native-authoring-readiness.py, or --readiness.
    # generate-native-workflow.py and --generation-handoff are NOT
    # blocker references (narrow deterministic renderer).
    scan_dirs = [
        repo_root / ".claude" / "skills",
        repo_root / ".claude" / "commands",
    ]
    blocker_ref_matches: list[str] = []
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for md_file in sorted(scan_dir.rglob("*.md")):
            text = _read_text_safe(md_file)
            if text is None:
                continue
            for bridge_name in (
                "workflowprogram-native-authoring.js",
                "validate-native-authoring-readiness.py",
                "--readiness",
            ):
                if bridge_name in text:
                    relative = md_file.relative_to(repo_root).as_posix()
                    entry = f"{relative} references {bridge_name}"
                    if entry not in blocker_ref_matches:
                        blocker_ref_matches.append(entry)

    bridge_evidence: dict[str, Any] = {
        "filesPresent": sorted(bridge_refs),
        "filesAbsent": sorted(set(bridge_files) - set(bridge_refs)),
        "activeCompatibilityReferences": sorted(blocker_ref_matches),
    }
    # Blocker is active iff active compatibility references exist in
    # active skills/commands. Inventory presence of bridge files alone
    # does NOT block -- only active primary-path references block.
    if blocker_ref_matches:
        active.append(
            {
                "id": "transitional-renderer-bridge-active",
                "active": True,
                "evidence": bridge_evidence,
            }
        )

    # Rule 3: full-product-interactive-smoke-not-declared-complete
    smoke_evidence_path = ev_root / ".workflowprogram" / "evidence" / "native-product-interactive-smoke.json"
    smoke_complete = False
    smoke_detail: dict[str, Any] = {"evidencePath": str(smoke_evidence_path)}
    if _file_exists(smoke_evidence_path):
        raw = _read_text_safe(smoke_evidence_path)
        if raw:
            try:
                smoke_data = json.loads(raw)
            except json.JSONDecodeError as exc:
                smoke_detail["parseError"] = str(exc)
            else:
                smoke_detail["declared"] = smoke_data
                if not isinstance(smoke_data, dict):
                    smoke_detail["invalidShape"] = "Expected a JSON object"
                else:
                    # Every coverage flag must explicitly be true.
                    required_keys = {
                        "develop", "validate", "audit", "iterate", "publish",
                        "discovery", "scriptPath", "agent", "schema", "pass", "blocked_path",
                    }
                    incomplete_keys = {
                        key for key in required_keys if smoke_data.get(key) is not True
                    }
                    if not incomplete_keys and smoke_data.get("declaredComplete") is True:
                        smoke_complete = True
                    else:
                        smoke_detail["incompleteCoverage"] = sorted(incomplete_keys)
    else:
        smoke_detail["evidenceFileMissing"] = True

    if not smoke_complete:
        active.append(
            {
                "id": "full-product-interactive-smoke-not-declared-complete",
                "active": True,
                "evidence": smoke_detail,
            }
        )

    # Rule 4: legacy-compatibility-routing-active
    router_path = repo_root / ".claude" / "scripts" / "route-native-control-plane.py"
    router_text = _read_text_safe(router_path)
    routing_evidence: dict[str, Any] = {"scriptPath": str(router_path)}
    routing_active = False
    if router_text is None:
        routing_evidence["status"] = "ROUTER_NOT_FOUND"
    else:
        routing_evidence["status"] = "ROUTER_PRESENT"
        # Check for legacy compatibility markers
        legacy_markers = [
            "existing-legacy-target",
            "LEGACY_MARKERS",
            "requested_mode",
            "legacy",
        ]
        found_markers: list[str] = []
        for marker in legacy_markers:
            if marker in router_text:
                found_markers.append(marker)
        routing_evidence["compatibilityMarkersFound"] = sorted(found_markers)
        # Check if the router routes to legacy entry
        if "workflowprogram-develop" in router_text and "legacy" in router_text:
            routing_evidence["legacyRoutingDetected"] = True
            routing_active = True
        else:
            routing_evidence["legacyRoutingDetected"] = False

    if routing_active:
        active.append(
            {
                "id": "legacy-compatibility-routing-active",
                "active": True,
                "evidence": routing_evidence,
            }
        )

    # Rule 5: rollback-deprecation-anchor-missing
    anchor_path = ev_root / ".workflowprogram" / "evidence" / "legacy-retirement-anchor.json"
    anchor_detail: dict[str, Any] = {"evidencePath": str(anchor_path)}
    anchor_complete = False
    if _file_exists(anchor_path):
        raw = _read_text_safe(anchor_path)
        if raw:
            try:
                anchor_data = json.loads(raw)
            except json.JSONDecodeError as exc:
                anchor_detail["parseError"] = str(exc)
            else:
                anchor_detail["declared"] = anchor_data
                if not isinstance(anchor_data, dict):
                    anchor_detail["invalidShape"] = "Expected a JSON object"
                else:
                    known_good_ref = anchor_data.get("knownGoodRef")
                    deprecation_notice = anchor_data.get("deprecationNotice")
                    missing_fields: list[str] = []
                    if not isinstance(known_good_ref, str) or not known_good_ref.strip():
                        missing_fields.append("knownGoodRef")
                    if not isinstance(deprecation_notice, str) or not deprecation_notice.strip():
                        missing_fields.append("deprecationNotice")
                    if missing_fields:
                        anchor_detail["missingFields"] = missing_fields
                    else:
                        anchor_complete = True
    else:
        anchor_detail["evidenceFileMissing"] = True

    if not anchor_complete:
        active.append(
            {
                "id": "rollback-deprecation-anchor-missing",
                "active": True,
                "evidence": anchor_detail,
            }
        )

    return active


def _build_removal_plan(dispositions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group dispositions by their enum value."""
    plan: dict[str, list[dict[str, Any]]] = {
        "retain": [],
        "replace": [],
        "narrow": [],
        "remove": [],
    }
    for entry in dispositions:
        disc = entry["disposition"]
        if disc in plan:
            plan[disc].append(
                {
                    "id": entry["id"],
                    "paths": list(entry["paths"]),
                    "reason": entry["reason"],
                }
            )
    # Sort each group for stable output
    for key in plan:
        plan[key].sort(key=lambda x: x["id"])
    return plan


def assess(
    repo_root: Path,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    """Run the full retirement assessment and return a structured report."""
    root = repo_root.resolve()

    # Required assets inventory
    asset_check = _check_required_assets(root)

    # Legacy path dispositions
    dispositions = _check_legacy_paths(root)

    # Blocking issues
    blocking_issues = _detect_blocking_issues(root, evidence_root)

    # Removal plan
    removal_plan = _build_removal_plan(dispositions)

    overall_status = "BLOCKED_RETIREMENT" if blocking_issues else "READY_FOR_RETIREMENT"

    return {
        "schema_version": SCHEMA_VERSION,
        "schema_name": SCHEMA_NAME,
        "status": overall_status,
        "target_root": str(root),
        "evidence_root": str((evidence_root or root).resolve()),
        "assessed_at": _utc_now(),
        "requiredAssets": asset_check["requiredAssets"],
        "presentRequiredAssets": asset_check["presentRequiredAssets"],
        "missingRequiredAssets": asset_check["missingRequiredAssets"],
        "dispositions": dispositions,
        "blockingRules": BLOCKING_RULES,
        "blockingIssues": blocking_issues,
        "removalPlan": removal_plan,
        "summary": (
            "Legacy runtime retirement is currently {}. {} blocking issue(s) must be "
            "resolved before retirement can proceed. "
            "The assessor has NOT deleted or modified any file."
        ).format(
            "BLOCKED" if blocking_issues else "READY",
            len(blocking_issues),
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assess WorkflowProgram legacy runtime retirement eligibility"
    )
    parser.add_argument(
        "--repo-root",
        default="",
        help="Repository root to assess (default: current working directory)",
    )
    parser.add_argument(
        "--evidence-root",
        default="",
        help="Optional evidence root for closure evidence JSON files (default: repo-root)",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Write JSON report to this path",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report to stdout",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root.strip() else Path.cwd().resolve()
    evidence_root = Path(args.evidence_root).resolve() if args.evidence_root.strip() else None
    payload = assess(repo_root, evidence_root)

    if args.out.strip():
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status={payload['status']}")
        for issue in payload.get("blockingIssues", []):
            print(f"  blocker: {issue['id']} (active={issue['active']})")
        for disp in payload.get("dispositions", []):
            print(f"  {disp['id']}: {disp['disposition']}")
        print(f"  summary: {payload['summary']}")

    return 0 if payload["status"] == "READY_FOR_RETIREMENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
