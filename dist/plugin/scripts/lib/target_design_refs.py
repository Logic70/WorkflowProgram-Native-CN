# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List


RUN_REF_KEYS = (
    "requirements",
    "question_backlog",
    "requirement_logic_map",
    "context_findings",
    "design_overview",
    "design_detail",
    "implementation_plan",
    "acceptance_tests",
    "traceability_matrix",
)

REQUIRED_RUN_REF_KEYS = (
    "requirements",
    "context_findings",
    "design_overview",
    "design_detail",
    "implementation_plan",
    "acceptance_tests",
    "traceability_matrix",
)

CANONICAL_RUN_DEFAULTS: Dict[str, str] = {
    "requirements": "outputs/stages/target-requirements.yaml",
    "question_backlog": "outputs/stages/target-question-backlog.json",
    "requirement_logic_map": "outputs/stages/target-requirement-logic-map.json",
    "context_findings": "outputs/stages/target-context-findings.yaml",
    "design_overview": "outputs/stages/target-design-overview.md",
    "design_detail": "outputs/stages/target-design-detail.md",
    "implementation_plan": "outputs/stages/target-implementation-plan.md",
    "acceptance_tests": "outputs/stages/target-acceptance-tests.yaml",
    "traceability_matrix": "outputs/stages/target-traceability-matrix.json",
}

LEGACY_RUN_DEFAULTS: Dict[str, str] = {
    "requirements": "outputs/stages/s1-requirements.yaml",
    "question_backlog": "outputs/stages/question-backlog.json",
    "requirement_logic_map": "outputs/stages/requirement-logic-map.json",
    "context_findings": "outputs/stages/s2-context-findings.yaml",
    "design_overview": "outputs/stages/s3-design-highlevel.md",
    "design_detail": "outputs/stages/s3-design-lowlevel.md",
    "implementation_plan": "outputs/stages/s3-implementation-plan.md",
    "acceptance_tests": "outputs/stages/acceptance-tests.yaml",
    "traceability_matrix": "outputs/stages/traceability-matrix.json",
}

PERSISTENT_DEFAULTS: Dict[str, str] = {
    "requirements": ".workflowprogram/design/source/target-requirements.yaml",
    "question_backlog": ".workflowprogram/design/source/target-question-backlog.json",
    "requirement_logic_map": ".workflowprogram/design/source/target-requirement-logic-map.json",
    "context_findings": ".workflowprogram/design/source/target-context-findings.yaml",
    "design_overview": ".workflowprogram/design/source/target-design-overview.md",
    "design_detail": ".workflowprogram/design/source/target-design-detail.md",
    "implementation_plan": ".workflowprogram/design/source/target-implementation-plan.md",
    "acceptance_tests": ".workflowprogram/design/source/target-acceptance-tests.yaml",
    "traceability_matrix": ".workflowprogram/design/source/target-traceability-matrix.json",
}

LEGACY_FIELD_ALIASES = {
    "design_overview": "design_highlevel",
    "design_detail": "design_lowlevel",
}

LEGACY_ALLOWED_FIELDS = set(LEGACY_FIELD_ALIASES.values())
DESIGN_REF_CONTROL_FIELDS = {"schema_version", "naming", "node_designs", "node_design_policy", "persistent"}
ALLOWED_DESIGN_REF_FIELDS = set(RUN_REF_KEYS) | DESIGN_REF_CONTROL_FIELDS | LEGACY_ALLOWED_FIELDS


@dataclass
class ResolvedTargetDesignRefs:
    schema_version: int | None = None
    naming: str = ""
    compatibility_mode: str = "absent"
    run_refs: Dict[str, str] = field(default_factory=dict)
    persistent_refs: Dict[str, str] = field(default_factory=dict)
    node_designs: Dict[str, str] = field(default_factory=dict)
    persistent_node_designs: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def declared(self) -> bool:
        return bool(self.run_refs or self.node_designs or self.persistent_refs or self.schema_version or self.naming)

    @property
    def canonical(self) -> bool:
        return self.schema_version == 2 or self.naming == "target_design_v1"


def _design_refs_from_spec(spec_or_refs: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(spec_or_refs, dict):
        return {}
    nested = spec_or_refs.get("design_refs")
    if isinstance(nested, dict):
        return nested
    return spec_or_refs


def _safe_relative(path_text: str) -> bool:
    if not path_text or Path(path_text).is_absolute():
        return False
    parts = Path(path_text).parts
    return bool(parts) and not any(part in {"", ".", ".."} for part in parts)


def is_safe_run_ref(path_text: str) -> bool:
    return _safe_relative(path_text) and path_text.startswith("outputs/stages/")


def is_safe_node_design_ref(path_text: str) -> bool:
    return _safe_relative(path_text) and (
        path_text.startswith("outputs/stages/target-node-designs/")
        or path_text.startswith("outputs/stages/node-designs/")
        or path_text.startswith(".workflowprogram/design/node-designs/")
    )


def is_legacy_node_design_ref(path_text: str) -> bool:
    return is_safe_run_ref(path_text) and path_text.startswith("outputs/stages/node-designs/")


def is_safe_persistent_ref(path_text: str) -> bool:
    return _safe_relative(path_text) and path_text.startswith(".workflowprogram/design/source/")


def is_safe_persistent_node_design_ref(path_text: str) -> bool:
    return _safe_relative(path_text) and (
        path_text.startswith(".workflowprogram/design/source/target-node-designs/")
        or path_text.startswith(".workflowprogram/design/node-designs/")
    )


def canonical_default_run_refs() -> Dict[str, str]:
    return dict(CANONICAL_RUN_DEFAULTS)


def legacy_default_run_refs() -> Dict[str, str]:
    return dict(LEGACY_RUN_DEFAULTS)


def canonical_persistent_refs() -> Dict[str, str]:
    return dict(PERSISTENT_DEFAULTS)


def resolve_target_design_refs(
    spec_or_refs: Dict[str, Any],
    *,
    fill_missing_with_defaults: bool = False,
) -> ResolvedTargetDesignRefs:
    refs = _design_refs_from_spec(spec_or_refs)
    resolved = ResolvedTargetDesignRefs()
    if not refs:
        if fill_missing_with_defaults:
            resolved.compatibility_mode = "canonical-defaults"
            resolved.run_refs.update(CANONICAL_RUN_DEFAULTS)
            resolved.persistent_refs.update(PERSISTENT_DEFAULTS)
        return resolved

    schema_version = refs.get("schema_version")
    if isinstance(schema_version, int):
        resolved.schema_version = schema_version
    elif schema_version is not None:
        resolved.errors.append("design_refs.schema_version must be an integer")
    resolved.naming = str(refs.get("naming", "")).strip()

    used_legacy = False
    for key in RUN_REF_KEYS:
        value = refs.get(key)
        if value is None and key in LEGACY_FIELD_ALIASES:
            legacy_key = LEGACY_FIELD_ALIASES[key]
            value = refs.get(legacy_key)
            if value is not None:
                used_legacy = True
                resolved.warnings.append(f"design_refs.{legacy_key} is legacy; use design_refs.{key}")
        if value is None and fill_missing_with_defaults:
            value = CANONICAL_RUN_DEFAULTS[key] if resolved.canonical else LEGACY_RUN_DEFAULTS[key]
        if value is None:
            continue
        text = str(value).strip()
        resolved.run_refs[key] = text
        if not is_safe_run_ref(text):
            resolved.errors.append(f"design_refs.{key} must stay under outputs/stages/: {text}")

    persistent = refs.get("persistent", {})
    if isinstance(persistent, dict):
        for key in RUN_REF_KEYS:
            value = persistent.get(key)
            if value is None and fill_missing_with_defaults and resolved.canonical:
                value = PERSISTENT_DEFAULTS[key]
            if value is None:
                continue
            text = str(value).strip()
            resolved.persistent_refs[key] = text
            if not is_safe_persistent_ref(text):
                resolved.errors.append(f"design_refs.persistent.{key} must stay under .workflowprogram/design/source/: {text}")
        raw_persistent_nodes = persistent.get("node_designs")
        if isinstance(raw_persistent_nodes, dict):
            for node_id, value in raw_persistent_nodes.items():
                node = str(node_id).strip()
                text = str(value).strip()
                if not node:
                    resolved.errors.append("design_refs.persistent.node_designs contains an empty node id")
                    continue
                resolved.persistent_node_designs[node] = text
                if not is_safe_persistent_node_design_ref(text):
                    resolved.errors.append(
                        f"design_refs.persistent.node_designs.{node} must stay under .workflowprogram/design/source/target-node-designs/ or .workflowprogram/design/node-designs/: {text}"
                    )
        elif raw_persistent_nodes is not None:
            resolved.errors.append("design_refs.persistent.node_designs must be a mapping")
    elif persistent is not None:
        resolved.errors.append("design_refs.persistent must be a mapping")

    raw_node_designs = refs.get("node_designs")
    if isinstance(raw_node_designs, dict):
        for node_id, value in raw_node_designs.items():
            node = str(node_id).strip()
            text = str(value).strip()
            if not node:
                resolved.errors.append("design_refs.node_designs contains an empty node id")
                continue
            resolved.node_designs[node] = text
            if not is_safe_node_design_ref(text):
                resolved.errors.append(
                    f"design_refs.node_designs.{node} must stay under outputs/stages/target-node-designs/, outputs/stages/node-designs/, or .workflowprogram/design/node-designs/: {text}"
                )
            elif is_legacy_node_design_ref(text):
                used_legacy = True
                resolved.warnings.append(
                    f"design_refs.node_designs.{node} uses legacy outputs/stages/node-designs/; use outputs/stages/target-node-designs/"
                )
    elif raw_node_designs is not None:
        resolved.errors.append("design_refs.node_designs must be a mapping")

    if resolved.canonical:
        resolved.compatibility_mode = "canonical"
    elif used_legacy or any(value in LEGACY_RUN_DEFAULTS.values() for value in resolved.run_refs.values()):
        resolved.compatibility_mode = "legacy"
    else:
        resolved.compatibility_mode = "declared"
    return resolved


def resolve_existing_run_refs(run_root: Path, spec_or_refs: Dict[str, Any] | None = None) -> Dict[str, str]:
    resolved = resolve_target_design_refs(spec_or_refs or {})
    refs: Dict[str, str] = {}
    for key in RUN_REF_KEYS:
        candidates = []
        if key in resolved.run_refs:
            candidates.append(resolved.run_refs[key])
        candidates.append(CANONICAL_RUN_DEFAULTS[key])
        candidates.append(LEGACY_RUN_DEFAULTS[key])
        for rel_path in candidates:
            if rel_path and (run_root / rel_path).exists():
                refs[key] = rel_path
                break
    return refs


def iter_existing_node_design_refs(run_root: Path, spec_or_refs: Dict[str, Any] | None = None) -> Dict[str, str]:
    resolved = resolve_target_design_refs(spec_or_refs or {})
    refs = dict(resolved.node_designs)
    for root in (run_root / "outputs" / "stages" / "target-node-designs", run_root / "outputs" / "stages" / "node-designs"):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            rel_path = path.relative_to(run_root).as_posix()
            refs.setdefault(path.stem, rel_path)
    return refs


def artifact_kind_for_path(path_text: str) -> str | None:
    cleaned = path_text.strip().rstrip("/")
    if cleaned.endswith("outputs/stages/target-requirements.yaml") or cleaned.endswith("outputs/stages/s1-requirements.yaml"):
        return "requirement_index"
    if cleaned.endswith("outputs/stages/target-question-backlog.json") or cleaned.endswith("outputs/stages/question-backlog.json"):
        return "question_backlog"
    if cleaned.endswith("outputs/stages/target-requirement-logic-map.json") or cleaned.endswith("outputs/stages/requirement-logic-map.json"):
        return "requirement_logic_map"
    if cleaned.endswith("outputs/stages/target-context-findings.yaml") or cleaned.endswith("outputs/stages/s2-context-findings.yaml"):
        return "context_findings"
    if (
        cleaned.endswith("outputs/stages/target-design-overview.md")
        or cleaned.endswith("outputs/stages/target-design-detail.md")
        or cleaned.endswith("outputs/stages/s3-design-highlevel.md")
        or cleaned.endswith("outputs/stages/s3-design-lowlevel.md")
    ):
        return "design_source"
    if (
        "/outputs/stages/target-node-designs/" in cleaned
        or "/outputs/stages/node-designs/" in cleaned
        or "/.workflowprogram/design/node-designs/" in cleaned
        or cleaned.startswith("outputs/stages/target-node-designs/")
        or cleaned.startswith("outputs/stages/node-designs/")
        or cleaned.startswith(".workflowprogram/design/node-designs/")
    ):
        return "node_design"
    if cleaned.endswith("outputs/stages/target-implementation-plan.md") or cleaned.endswith("outputs/stages/s3-implementation-plan.md"):
        return "implementation_plan"
    if cleaned.endswith("outputs/stages/target-acceptance-tests.yaml") or cleaned.endswith("outputs/stages/acceptance-tests.yaml"):
        return "acceptance_tests"
    if cleaned.endswith("outputs/stages/target-traceability-matrix.json") or cleaned.endswith("outputs/stages/traceability-matrix.json"):
        return "traceability_matrix"
    return None


def semantic_design_source_paths(refs: Iterable[str]) -> List[str]:
    values: List[str] = []
    for ref in refs:
        kind = artifact_kind_for_path(ref)
        if kind in {"design_source", "implementation_plan", "acceptance_tests", "traceability_matrix", "node_design"}:
            values.append(ref)
    return values
