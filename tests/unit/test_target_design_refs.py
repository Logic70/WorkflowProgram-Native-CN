#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude" / "scripts"))

from lib.target_design_refs import (  # noqa: E402
    artifact_kind_for_path,
    canonical_default_run_refs,
    iter_existing_node_design_refs,
    resolve_existing_run_refs,
    resolve_target_design_refs,
)


def write_text(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_canonical_refs() -> None:
    refs = resolve_target_design_refs(
        {
            "design_refs": {
                "schema_version": 2,
                "naming": "target_design_v1",
                "requirements": "outputs/stages/target-requirements.yaml",
                "context_findings": "outputs/stages/target-context-findings.yaml",
                "design_overview": "outputs/stages/target-design-overview.md",
                "design_detail": "outputs/stages/target-design-detail.md",
                "implementation_plan": "outputs/stages/target-implementation-plan.md",
                "acceptance_tests": "outputs/stages/target-acceptance-tests.yaml",
                "traceability_matrix": "outputs/stages/target-traceability-matrix.json",
                "persistent": {
                    "design_overview": ".workflowprogram/design/source/target-design-overview.md",
                },
                "node_designs": {
                    "build_dfd": "outputs/stages/target-node-designs/build_dfd.md",
                },
            }
        }
    )
    assert refs.compatibility_mode == "canonical"
    assert not refs.errors
    assert refs.run_refs["design_detail"] == "outputs/stages/target-design-detail.md"
    assert refs.persistent_refs["design_overview"] == ".workflowprogram/design/source/target-design-overview.md"
    assert refs.node_designs["build_dfd"] == "outputs/stages/target-node-designs/build_dfd.md"


def test_persistent_node_design_refs_are_allowed() -> None:
    refs = resolve_target_design_refs(
        {
            "design_refs": {
                "node_designs": {
                    "build_dfd": ".workflowprogram/design/node-designs/build_dfd.md",
                },
                "persistent": {
                    "node_designs": {
                        "review": ".workflowprogram/design/node-designs/review.md",
                    }
                },
            }
        }
    )
    assert not refs.errors
    assert refs.node_designs["build_dfd"] == ".workflowprogram/design/node-designs/build_dfd.md"
    assert refs.persistent_node_designs["review"] == ".workflowprogram/design/node-designs/review.md"


def test_legacy_aliases_warn() -> None:
    refs = resolve_target_design_refs(
        {
            "design_refs": {
                "requirements": "outputs/stages/s1-requirements.yaml",
                "design_highlevel": "outputs/stages/s3-design-highlevel.md",
                "design_lowlevel": "outputs/stages/s3-design-lowlevel.md",
                "node_designs": {"x": "outputs/stages/node-designs/x.md"},
            }
        }
    )
    assert refs.compatibility_mode == "legacy"
    assert not refs.errors
    assert refs.run_refs["design_overview"] == "outputs/stages/s3-design-highlevel.md"
    assert refs.run_refs["design_detail"] == "outputs/stages/s3-design-lowlevel.md"
    assert refs.warnings


def test_unsafe_paths_error() -> None:
    refs = resolve_target_design_refs(
        {
            "design_refs": {
                "schema_version": 2,
                "naming": "target_design_v1",
                "design_detail": "../secret.md",
                "persistent": {"design_detail": "/tmp/secret.md"},
                "node_designs": {"x": "outputs/stages/other/x.md"},
            }
        }
    )
    assert len(refs.errors) == 3


def test_existing_run_refs_prefer_existing_canonical() -> None:
    with tempfile.TemporaryDirectory(prefix="target-design-refs-") as temp_dir:
        run_root = Path(temp_dir)
        write_text(run_root / "outputs" / "stages" / "target-design-overview.md")
        write_text(run_root / "outputs" / "stages" / "s3-design-lowlevel.md")
        refs = resolve_existing_run_refs(run_root, {"design_refs": {}})
        assert refs["design_overview"] == "outputs/stages/target-design-overview.md"
        assert refs["design_detail"] == "outputs/stages/s3-design-lowlevel.md"


def test_existing_node_design_refs_include_canonical_and_legacy() -> None:
    with tempfile.TemporaryDirectory(prefix="target-node-design-refs-") as temp_dir:
        run_root = Path(temp_dir)
        write_text(run_root / "outputs" / "stages" / "target-node-designs" / "canonical.md")
        write_text(run_root / "outputs" / "stages" / "node-designs" / "legacy.md")
        refs = iter_existing_node_design_refs(run_root)
        assert refs["canonical"] == "outputs/stages/target-node-designs/canonical.md"
        assert refs["legacy"] == "outputs/stages/node-designs/legacy.md"


def test_artifact_kind_mapping() -> None:
    expected = canonical_default_run_refs()
    assert artifact_kind_for_path(expected["requirements"]) == "requirement_index"
    assert artifact_kind_for_path(expected["design_overview"]) == "design_source"
    assert artifact_kind_for_path(expected["acceptance_tests"]) == "acceptance_tests"
    assert artifact_kind_for_path("outputs/stages/node-designs/x.md") == "node_design"
    assert artifact_kind_for_path(".workflowprogram/design/node-designs/x.md") == "node_design"


def main() -> int:
    test_canonical_refs()
    test_persistent_node_design_refs_are_allowed()
    test_legacy_aliases_warn()
    test_unsafe_paths_error()
    test_existing_run_refs_prefer_existing_canonical()
    test_existing_node_design_refs_include_canonical_and_legacy()
    test_artifact_kind_mapping()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
