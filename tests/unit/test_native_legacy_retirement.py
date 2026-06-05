from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "assess-native-legacy-retirement.py"
SCHEMA_NAME = "native-legacy-retirement-assessment"


def run_assessor(
    repo_root: Path,
    *,
    evidence_root: Path | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT), "--repo-root", str(repo_root), "--json"]
    if evidence_root is not None:
        cmd.extend(["--evidence-root", str(evidence_root)])
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    assert completed.returncode == 0 or completed.returncode == 1
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        print("STDOUT:", completed.stdout[:500])
        print("STDERR:", completed.stderr[:500])
        raise


# ---------------------------------------------------------------------------
# Overall status
# ---------------------------------------------------------------------------


def test_assessor_returns_blocked_retirement_on_current_repo() -> None:
    """The current repository keeps legacy retirement blocked until product smoke is complete."""
    completed = run_assessor(ROOT)
    payload = load_json(completed)

    assert completed.returncode == 1
    assert payload["status"] == "BLOCKED_RETIREMENT"
    assert payload["schema_version"] == 1
    assert payload["schema_name"] == SCHEMA_NAME
    assert {issue["id"] for issue in payload["blockingIssues"]} == {
        "full-product-interactive-smoke-not-declared-complete",
    }


def test_assessor_readable_summary() -> None:
    """The text output must include status and key sections."""
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "status=BLOCKED_RETIREMENT" in completed.stdout
    assert "full-product-interactive-smoke-not-declared-complete" in completed.stdout
    assert "summary:" in completed.stdout


# ---------------------------------------------------------------------------
# Required assets
# ---------------------------------------------------------------------------


def test_missing_required_asset_is_visible() -> None:
    """When a required assessment asset is absent, it must appear in
    missingRequiredAssets and trigger the corresponding blocker."""
    completed = run_assessor(ROOT)
    payload = load_json(completed)

    # The current repo should have all required assets present
    assert payload["missingRequiredAssets"] == []

def test_missing_asset_triggers_blocker(tmp_path: Path) -> None:
    """A repo missing required assessment assets reports them and
    activates the required-assessment-assets-missing blocker."""
    # Create a minimal repo missing the test file
    scripts_dir = tmp_path / ".claude" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    # Create assessor script stub
    (scripts_dir / "assess-native-legacy-retirement.py").write_text(
        "# stub", encoding="ascii"
    )
    # Create migration plan stub
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "native-workflow-control-plane-migration-plan.md").write_text(
        "# stub", encoding="ascii"
    )
    # No test file -> trigger

    completed = run_assessor(tmp_path)
    payload = load_json(completed)

    assert payload["status"] == "BLOCKED_RETIREMENT"
    missing = payload["missingRequiredAssets"]
    assert any("test_native_legacy_retirement" in a for a in missing)
    blocker_ids = [b["id"] for b in payload["blockingIssues"]]
    assert "required-assessment-assets-missing" in blocker_ids


# ---------------------------------------------------------------------------
# Dispositions
# ---------------------------------------------------------------------------


def test_all_expected_dispositions_present() -> None:
    """Every known legacy path must have a disposition entry."""
    completed = run_assessor(ROOT)
    payload = load_json(completed)

    expected_ids = {
        "workflow-entry-py",
        "workflow-runner-py",
        "workflow-s5-judge-py",
        "generate-target-runtime-py",
        "workflow-spec-yaml-default",
        "target-runtime-dir",
        "route-native-control-plane-py",
        "native-authoring-js",
        "generate-native-workflow-py",
        "validate-native-authoring-readiness-py",
        "deterministic-validators",
        "managed-assets-py",
        "evidence-builders",
        "interactive-smoke-harness",
    }
    observed_ids = {d["id"] for d in payload["dispositions"]}
    assert observed_ids == expected_ids


def test_every_disposition_has_enum_paths_and_remove_when() -> None:
    """Each disposition must carry valid enum, non-empty paths, reason, and removeWhen (may be empty for retain)."""
    valid_enums = {"retain", "replace", "narrow", "remove"}
    for entry in payload_from_current_repo()["dispositions"]:
        assert entry["disposition"] in valid_enums, f"{entry['id']} invalid disposition"
        assert len(entry["paths"]) > 0, f"{entry['id']} has empty paths"
        assert entry["reason"], f"{entry['id']} has empty reason"
        assert isinstance(entry["removeWhen"], list), f"{entry['id']} removeWhen not a list"
        assert isinstance(entry["exists"], dict), f"{entry['id']} exists not a dict"


def test_every_disposition_has_non_empty_remove_when() -> None:
    """Every disposition documents when it can be removed or replaced."""
    for entry in payload_from_current_repo()["dispositions"]:
        assert entry["removeWhen"], f"{entry['id']} should have non-empty removeWhen"


def test_target_runtime_directory_is_inventoried_as_existing(tmp_path: Path) -> None:
    """Directory-shaped legacy assets must not be checked as regular files."""
    (tmp_path / ".workflowprogram" / "runtime").mkdir(parents=True)

    payload = load_json(run_assessor(tmp_path))
    runtime_dir = next(
        entry for entry in payload["dispositions"] if entry["id"] == "target-runtime-dir"
    )
    assert runtime_dir["exists"][".workflowprogram/runtime/"] is True


# ---------------------------------------------------------------------------
# Blocking issues
# ---------------------------------------------------------------------------


def test_current_repo_has_only_product_smoke_blocker() -> None:
    """The current repo must not close retirement before real product smoke evidence."""
    completed = run_assessor(ROOT)
    payload = load_json(completed)

    blocker_ids = {b["id"] for b in payload["blockingIssues"]}
    assert blocker_ids == {"full-product-interactive-smoke-not-declared-complete"}


def test_every_active_blocker_is_declared_by_a_stable_rule() -> None:
    """The report exposes both the stable rule registry and active subset."""
    payload = payload_from_current_repo()
    rule_ids = {rule["id"] for rule in payload["blockingRules"]}
    active_ids = {issue["id"] for issue in payload["blockingIssues"]}

    assert rule_ids == {
        "required-assessment-assets-missing",
        "transitional-renderer-bridge-active",
        "full-product-interactive-smoke-not-declared-complete",
        "legacy-compatibility-routing-active",
        "rollback-deprecation-anchor-missing",
    }
    assert active_ids.issubset(rule_ids)


def test_every_blocker_has_evidence() -> None:
    """Each active blocker must carry an evidence dict."""
    for issue in payload_from_current_repo()["blockingIssues"]:
        assert "evidence" in issue, f"{issue['id']} missing evidence"
        assert isinstance(issue["evidence"], dict), f"{issue['id']} evidence not a dict"


def test_narrow_renderer_reference_alone_does_not_block(tmp_path: Path) -> None:
    """A skill referencing generate-native-workflow.py or --generation-handoff
    (but NOT bridge assets) must NOT activate the transitional-renderer-bridge blocker."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Required assessment assets
    (repo / ".claude" / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "scripts" / "assess-native-legacy-retirement.py").write_text("# stub", encoding="ascii")
    (repo / "tests" / "unit").mkdir(parents=True, exist_ok=True)
    (repo / "tests" / "unit" / "test_native_legacy_retirement.py").write_text("# stub", encoding="ascii")
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "native-workflow-control-plane-migration-plan.md").write_text("# stub", encoding="ascii")

    # Skill only references generate-native-workflow.py and --generation-handoff (not bridge assets)
    (repo / ".claude" / "skills" / "my-skill" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "skills" / "my-skill" / "SKILL.md").write_text(
        "Use --generation-handoff with generate-native-workflow.py\n",
        encoding="ascii",
    )

    completed = run_assessor(repo)
    payload = load_json(completed)
    blocker_ids = {b["id"] for b in payload["blockingIssues"]}
    assert "transitional-renderer-bridge-active" not in blocker_ids, (
        "Narrow renderer reference alone must not activate the bridge blocker"
    )


def test_active_compatibility_reference_blocks(tmp_path: Path) -> None:
    """A skill referencing --readiness or validate-native-authoring-readiness.py
    must activate the transitional-renderer-bridge blocker."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Required assessment assets
    (repo / ".claude" / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "scripts" / "assess-native-legacy-retirement.py").write_text("# stub", encoding="ascii")
    (repo / "tests" / "unit").mkdir(parents=True, exist_ok=True)
    (repo / "tests" / "unit" / "test_native_legacy_retirement.py").write_text("# stub", encoding="ascii")
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "native-workflow-control-plane-migration-plan.md").write_text("# stub", encoding="ascii")

    # Skill references --readiness (a compatibility bridge marker)
    (repo / ".claude" / "skills" / "my-skill" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "skills" / "my-skill" / "SKILL.md").write_text(
        "Use --readiness as the primary path\n",
        encoding="ascii",
    )

    completed = run_assessor(repo)
    payload = load_json(completed)
    blocker_ids = {b["id"] for b in payload["blockingIssues"]}
    assert "transitional-renderer-bridge-active" in blocker_ids, (
        "Active --readiness reference must activate the bridge blocker"
    )


# ---------------------------------------------------------------------------
# Removal plan
# ---------------------------------------------------------------------------


def test_removal_plan_has_grouped_structure() -> None:
    """The removalPlan must be grouped by disposition with stable keys."""
    payload = payload_from_current_repo()
    plan = payload["removalPlan"]
    for key in ("retain", "replace", "narrow", "remove"):
        assert key in plan, f"removalPlan missing group '{key}'"
        assert isinstance(plan[key], list), f"removalPlan.{key} is not a list"


def test_removal_plan_ids_match_dispositions() -> None:
    """Every ID in removalPlan groups must correspond to a disposition entry."""
    payload = payload_from_current_repo()
    all_disp_ids = {d["id"] for d in payload["dispositions"]}
    plan_ids = set()
    for group in payload["removalPlan"].values():
        for entry in group:
            plan_ids.add(entry["id"])
    # Every plan ID must be a known disposition
    unknown = plan_ids - all_disp_ids
    assert not unknown, f"removalPlan references unknown IDs: {unknown}"
    # Every disposition must appear in exactly one group
    missing_from_plan = all_disp_ids - plan_ids
    assert not missing_from_plan, (
        f"Dispositions missing from removalPlan: {missing_from_plan}"
    )


# ---------------------------------------------------------------------------
# Report persistence and read-only guarantee
# ---------------------------------------------------------------------------


def test_report_writes_to_disk(tmp_path: Path) -> None:
    """The --out flag must produce a valid JSON file."""
    out_path = tmp_path / "retirement-assessment.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root", str(ROOT),
            "--out", str(out_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] == "BLOCKED_RETIREMENT"
    assert {issue["id"] for issue in payload["blockingIssues"]} == {
        "full-product-interactive-smoke-not-declared-complete",
    }
    assert payload["schema_name"] == SCHEMA_NAME


def test_assessor_does_not_delete_or_modify_files(tmp_path: Path) -> None:
    """The assessor must never delete or modify any file — it is read-only."""
    (tmp_path / "dummy.txt").write_text("hello", encoding="utf-8")
    original_stat = (tmp_path / "dummy.txt").stat()

    run_assessor(tmp_path)

    assert (tmp_path / "dummy.txt").read_text(encoding="utf-8") == "hello"
    assert (tmp_path / "dummy.txt").stat().st_mtime == original_stat.st_mtime


# ---------------------------------------------------------------------------
# Closure fixture: READY_FOR_RETIREMENT is reachable
# ---------------------------------------------------------------------------


def test_ready_for_retirement_is_reachable_with_closure_evidence(
    tmp_path: Path,
) -> None:
    """Construct a minimal repository tree that makes the assessor return
    READY_FOR_RETIREMENT: required source stubs exist, bridge files have
    no active references, route-legacy behavior is absent, and both evidence JSON files
    explicitly close their gates."""
    repo = tmp_path / "repo"
    ev = tmp_path / "ev"
    repo.mkdir(parents=True, exist_ok=True)
    ev.mkdir(parents=True, exist_ok=True)

    # Required assessment assets (stubs)
    (repo / ".claude" / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "scripts" / "assess-native-legacy-retirement.py").write_text(
        "# stub", encoding="ascii"
    )
    (repo / "tests" / "unit").mkdir(parents=True, exist_ok=True)
    (repo / "tests" / "unit" / "test_native_legacy_retirement.py").write_text(
        "# stub", encoding="ascii"
    )
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "native-workflow-control-plane-migration-plan.md").write_text(
        "# stub", encoding="ascii"
    )

    # Bridge assets may remain inventoried after their primary references close.
    (repo / ".claude" / "workflows").mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "workflows" / "workflowprogram-native-authoring.js").write_text(
        "// retained compatibility asset without active skill references\n",
        encoding="ascii",
    )
    (repo / ".claude" / "scripts" / "generate-native-workflow.py").write_text(
        "# retained narrow renderer\n",
        encoding="ascii",
    )
    (repo / ".claude" / "scripts" / "validate-native-authoring-readiness.py").write_text(
        "# retained narrow readiness validator\n",
        encoding="ascii",
    )

    # Minimal route-native-control-plane.py with no legacy markers.
    (repo / ".claude" / "scripts" / "route-native-control-plane.py").write_text(
        '# Clean router - no legacy refs.\nMODE = "native"\n',
        encoding="ascii",
    )

    # Interactive smoke evidence — explicitly complete
    (ev / ".workflowprogram" / "evidence").mkdir(parents=True, exist_ok=True)
    smoke_complete = {
        "declaredComplete": True,
        "develop": True,
        "validate": True,
        "audit": True,
        "iterate": True,
        "publish": True,
        "discovery": True,
        "scriptPath": True,
        "agent": True,
        "schema": True,
        "pass": True,
        "blocked_path": True,
    }
    (ev / ".workflowprogram" / "evidence" / "native-product-interactive-smoke.json").write_text(
        json.dumps(smoke_complete, indent=2), encoding="utf-8",
    )

    # Rollback anchor evidence — complete
    anchor = {
        "knownGoodRef": "v0.1.18",
        "deprecationNotice": (
            "Legacy runtime v0.x is deprecated. Migrate to Native Workflow JS. "
            "See docs/native-workflow-control-plane-migration-plan.md"
        ),
    }
    (ev / ".workflowprogram" / "evidence" / "legacy-retirement-anchor.json").write_text(
        json.dumps(anchor, indent=2), encoding="utf-8",
    )

    completed = run_assessor(repo, evidence_root=ev)
    payload = load_json(completed)

    assert payload["status"] == "READY_FOR_RETIREMENT", (
        f"Expected READY_FOR_RETIREMENT, got {payload['status']}. "
        f"Blockers: {[b['id'] for b in payload.get('blockingIssues', [])]}"
    )
    assert completed.returncode == 0
    assert payload["blockingIssues"] == []


def test_false_smoke_coverage_does_not_close_gate(tmp_path: Path) -> None:
    """Smoke coverage must be explicitly true, not merely present."""
    evidence_dir = tmp_path / ".workflowprogram" / "evidence"
    evidence_dir.mkdir(parents=True)
    smoke = {
        "declaredComplete": True,
        "develop": True,
        "validate": True,
        "audit": True,
        "iterate": True,
        "publish": False,
        "discovery": True,
        "scriptPath": True,
        "agent": True,
        "schema": True,
        "pass": True,
        "blocked_path": True,
    }
    (evidence_dir / "native-product-interactive-smoke.json").write_text(
        json.dumps(smoke),
        encoding="utf-8",
    )

    payload = load_json(run_assessor(ROOT, evidence_root=tmp_path))
    blocker = next(
        issue
        for issue in payload["blockingIssues"]
        if issue["id"] == "full-product-interactive-smoke-not-declared-complete"
    )
    assert blocker["evidence"]["incompleteCoverage"] == ["publish"]


def test_invalid_anchor_shape_blocks_without_crashing(tmp_path: Path) -> None:
    """Invalid explicit evidence remains a visible blocker."""
    evidence_dir = tmp_path / ".workflowprogram" / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "legacy-retirement-anchor.json").write_text(
        json.dumps(["not", "an", "object"]),
        encoding="utf-8",
    )

    payload = load_json(run_assessor(ROOT, evidence_root=tmp_path))
    blocker = next(
        issue
        for issue in payload["blockingIssues"]
        if issue["id"] == "rollback-deprecation-anchor-missing"
    )
    assert blocker["evidence"]["invalidShape"] == "Expected a JSON object"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_payload_cache: dict | None = None


def payload_from_current_repo() -> dict:
    """Cache the assessor payload for the current repo (run once per session)."""
    global _payload_cache
    if _payload_cache is None:
        completed = run_assessor(ROOT)
        _payload_cache = load_json(completed)
    return _payload_cache
