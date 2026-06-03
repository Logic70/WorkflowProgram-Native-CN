#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import yaml


ROOT = Path(__file__).resolve().parents[2]
VALID_SPEC = ROOT / "tests" / "spec-fixtures" / "valid-minimal.yaml"
VALIDATOR = ROOT / ".claude" / "scripts" / "validate-workflow-spec.py"


def load_valid_spec() -> Dict[str, Any]:
    payload = yaml.safe_load(VALID_SPEC.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def run_validator(payload: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        spec_path = Path(tmp) / "workflow-spec.yaml"
        spec_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR), "--spec", str(spec_path), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    result = json.loads(completed.stdout or "{}")
    assert isinstance(result, dict)
    return result


def test_canonical_target_design_refs_pass() -> None:
    result = run_validator(load_valid_spec())
    assert result["status"] == "PASS"
    assert result["errors"] == []


def test_legacy_target_design_aliases_pass_with_warning() -> None:
    payload = load_valid_spec()
    refs = dict(payload["design_refs"])
    refs.pop("schema_version", None)
    refs.pop("naming", None)
    refs["design_highlevel"] = refs.pop("design_overview")
    refs["design_lowlevel"] = refs.pop("design_detail")
    refs.pop("persistent", None)
    payload["design_refs"] = refs

    result = run_validator(payload)
    assert result["status"] == "PASS"
    assert any("legacy" in warning for warning in result["warnings"])


def test_missing_required_canonical_ref_fails() -> None:
    payload = load_valid_spec()
    payload["design_refs"].pop("design_detail")

    result = run_validator(payload)
    assert result["status"] == "FAIL"
    assert any("design_detail" in error for error in result["errors"])


def test_complex_node_exemption_passes() -> None:
    payload = load_valid_spec()
    node = payload["workflow_graph"]["nodes"][-1]
    node["complexity"] = "complex"
    node["node_design_exemption"] = {
        "reason": "Infrastructure-only fixture node; covered by target design detail.",
        "accepted_by": "design_review",
    }

    result = run_validator(payload)
    assert result["status"] == "PASS"


def test_invalid_persistent_path_fails() -> None:
    payload = load_valid_spec()
    payload["design_refs"]["persistent"]["design_detail"] = "../target-design-detail.md"

    result = run_validator(payload)
    assert result["status"] == "FAIL"
    assert any("persistent.design_detail" in error for error in result["errors"])


if __name__ == "__main__":
    test_canonical_target_design_refs_pass()
    test_legacy_target_design_aliases_pass_with_warning()
    test_missing_required_canonical_ref_fails()
    test_complex_node_exemption_passes()
    test_invalid_persistent_path_fails()
