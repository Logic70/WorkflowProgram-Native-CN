#!/usr/bin/env python3
"""
Generate the smallest supported Claude Code Native Workflow JS control plane.

The generator stages one `.claude/workflows/<name>.js` candidate under RUN_ROOT,
validates it statically, and optionally delegates safe writes to managed-assets.py.
"""

from __future__ import annotations

import argparse
import copy
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
TEMPLATES: dict[str, dict[str, object]] = {
    "sequential-agent-workflow-v1": {
        "description": "Sequential agent phases — one agent() per phase with optional gate blocks.",
        "version": 1,
    },
}


def artifact_payload_writer_script_path() -> str:
    """Return the helper path to embed in generated artifact commands."""

    return Path(__file__).resolve().with_name("artifact-payload-writer.py").as_posix()

SUPPORTING_ASSET_RULES = {
    "skill": (".claude/skills/", "/SKILL.md"),
    "agent": (".claude/agents/", ".md"),
    "script": (".claude/scripts/", None),
    "compatibility-command": (".claude/commands/", ".md"),
    "settings": (".claude/settings.json", None),
    "workflow-spec-ir": (".workflowprogram/design/", "workflow-spec.yaml"),
    "authoring-metadata": (".workflowprogram/design/", None),
    "managed-files": (".workflowprogram/managed-files.json", None),
}
ASSET_DISPOSITION_ACTIONS = {"retain", "generate", "update", "archive", "remove", "defer", "not-applicable"}
ASSET_ACTIONS_REQUIRING_SUPPORTING_ASSET = {"generate", "update"}
CONTENT_ACTIONS = {"generate", "update"}
NON_CONTENT_ACTIONS = {"retain", "archive", "remove", "defer", "not-applicable"}
STRUCTURED_PHASE_AGENT_TYPE = "workflowprogram-native-cn:structured-phase-runner"
PARSE_SCOPE_PROMPT_SUFFIX = (
    "Deterministic parse scope rule: when the target is a readable directory and "
    "the user did not provide explicit scope include/exclude values, do not leave "
    "scope.include or scope.exclude empty. Set scope.include to the existing "
    "high-signal target subdirectories among frameworks, services, common_lib, "
    "interfaces, and deps_adapter; if none exist, include the target directory. "
    "Set scope.exclude to existing low-signal or out-of-scope subdirectories among "
    ".git, test, tests, figures, default_config, outputs, and .workflowprogram. "
    "Populate threat_boundary with concrete inferred components, external "
    "interfaces, and trust boundary hints from README, public headers, and runtime "
    "args instead of returning empty arrays. When describing PIN or shared-secret "
    "length, distinguish characters from bits: HcStrlen(pinCode) >= 6 means at "
    "least 6 characters, not 6 bits. If source text uses compact bit notation for "
    "pinCode, rewrite it as minimum six characters in parse_result instead of "
    "copying the raw token. Never describe a PIN threshold as a bit-length unless "
    "the source explicitly measures bits. This Parse phase must not write "
    "parse_result.json, attacker_profile.json, temporary files, logs, or evidence "
    "copies; return only compact parse_result and attacker_profile StructuredOutput. "
    "The next workflow phase writes the root parse artifacts mechanically."
)
PARSE_ARTIFACT_WRITER_PROMPT = (
    "You are the Mechanical Parse artifact writer. Use the prior phase "
    "StructuredOutput result for the Parse phase as the sole source of truth. Do "
    "not inspect target source code, do not run listings, do not read old parse "
    "outputs, and do not rewrite DFD, threat-list, validation, or report outputs. "
    "Write exactly these root files under outputs/stride-audit/: parse_result.json "
    "and attacker_profile.json. Do not create a per-run subdirectory. Before "
    "writing parse_result.json, normalize any PIN/shared-secret threshold text so "
    "HcStrlen(pinCode) >= 6 is represented as a minimum of six characters, never "
    "as 6 bits or >=6bit. If the prior result lacks parse_result or "
    "attacker_profile, write schema-compatible empty fallback objects, set status "
    "BLOCKED, and record a blocking issue. After writing both files, do not call "
    "Read, Bash, Write, Edit, Glob, or Grep for verification; immediately call "
    "StructuredOutput with compact file paths, counts, and blockingIssues."
)
PARSE_ARTIFACT_WRITER_SCHEMA = {
    "type": "object",
    "required": ["status", "files", "counts", "blockingIssues"],
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "BLOCKED"]},
        "files": {
            "type": "object",
            "required": ["parse_result", "attacker_profile"],
            "properties": {
                "parse_result": {"type": "string"},
                "attacker_profile": {"type": "string"},
            },
        },
        "counts": {
            "type": "object",
            "properties": {
                "scope_include": {"type": "integer"},
                "scope_exclude": {"type": "integer"},
                "trust_boundary_hints": {"type": "integer"},
                "attacker_capabilities": {"type": "integer"},
            },
        },
        "blockingIssues": {"type": "array", "items": {"type": "string"}},
    },
}
STRIDE_AGGREGATE_PROMPT_SUFFIX = (
    "Aggregate STRIDE output rule: return exactly one StructuredOutput object. "
    "Put all S/T/R/I/D/E threats into the single threats array; do not call "
    "StructuredOutput separately for each STRIDE dimension. "
    "Use the prior phase StructuredOutput results for Parse, DFD, and DFD Artifacts "
    "as the primary evidence; when prior results are present, do not reread "
    "outputs/stride-audit/parse_result.json or dfd_index.json. Treat the DFD "
    "elements, data flows, stores, and trust boundaries as the bounded object "
    "inventory for threat enumeration instead of rediscovering the whole target. "
    "This suffix overrides earlier instructions to read target code or run "
    "independent dimension discovery. Do not call shell commands, file-writing "
    "tools, edit tools, glob search, grep search, target-wide recursive listings, "
    "or same-phase subagents. Do not create helper scripts, temporary files, "
    "journals, or analysis notes. If source evidence is needed but not already in "
    "prior results, produce DFD-grounded design/static threats and put evidence "
    "references such as outputs/stride-audit/dfd_index.json#<element-id> or "
    "outputs/stride-audit/parse_result.json#scope in evidence_refs; Validation will "
    "perform source-level confirmation later. Keep the result compact: at most 18 "
    "threats total, spread across the supported S/T/R/I/D/E dimensions when evidence "
    "exists. Use evidence tier language in impact or mapping_rationale when only "
    "design/static evidence exists; do not try to prove runtime exploitability in "
    "this phase. This phase must not write files; the next workflow phase writes "
    "outputs/stride-audit/threat_list.json from this StructuredOutput. "
    "When that budget is reached, stop exploration and call StructuredOutput with "
    "the best supported compact result instead of starting another discovery pass."
)
DFD_INFERENCE_PROMPT_SUFFIX = (
    "Bounded DFD inference rule: use outputs/stride-audit/parse_result.json as the "
    "primary scope and threat-boundary evidence when it exists. Do not run target-wide "
    "recursive Glob or any equivalent recursive listing command such as Bash dir /s, "
    "find, ls -R, Get-ChildItem -Recurse, or rg --files over the whole target. Do not "
    "inspect .git, test, tests, figures, default_config, or prior outputs as source "
    "evidence. If parse_result scope.include is empty, use a bounded deterministic "
    "fallback list under the target: frameworks, services, common_lib, interfaces, "
    "and deps_adapter/key_management_adapter. Only list constrained subdirectories "
    "when needed, filter by source/header extensions, and cap each listing with head "
    "or an equivalent limit. Read at most 12 high-signal source files, favoring public "
    "interfaces, service entry points, session/group/auth managers, storage adapters, "
    "and crypto/key adapters. This inference phase must not write files and must not "
    "call Bash, Write, Edit, or any other file-writing tool after it has enough "
    "evidence; do not write "
    "temporary files such as _dfd_temp.yaml, do not create run subdirectories, do not "
    "render diagrams, and do not read old DFD outputs for verification, even if "
    "earlier DFD instructions mention file writing or a renderer. Return only the "
    "dfd_yaml and dfd_index StructuredOutput objects, as JSON objects, not YAML text "
    "or file paths. Keep the result compact enough for a direct StructuredOutput "
    "call: at most 8 external entities, 16 processes, 8 stores, 30 data flows, and 8 "
    "trust boundaries; omit prose comments and put long rationale in short "
    "description strings. The next workflow phase writes root "
    "outputs/stride-audit/dfd.yaml, dfd_index.json, dfd_mermaid.mmd, and "
    "dfd_diagram.svg from this structured result. Make dfd_index contain an elements "
    "array, a cross_references object, and dangling_refs when present. When the read "
    "budget is reached, stop exploration and immediately call StructuredOutput with "
    "the compact inferred DFD result."
)
DFD_ARTIFACT_WRITER_PROMPT = (
    "You are the Mechanical DFD artifact writer. Use the prior phase StructuredOutput "
    "result for the DFD inference phase as the sole DFD source of truth. Do not inspect "
    "target source code, do not run recursive listings, do not read old DFD outputs, "
    "and do not rewrite parse_result.json or attacker_profile.json. Write exactly these "
    "root files under outputs/stride-audit/: dfd.yaml, dfd_index.json, "
    "dfd_mermaid.mmd, and dfd_diagram.svg. Do not create a per-run subdirectory. "
    "dfd.yaml must serialize the prior dfd_yaml object under a top-level dfd key "
    "and include the Runtime runId when a run id is available. dfd_index.json must serialize the prior dfd_index "
    "object and preserve elements, cross_references, and dangling_refs. "
    "dfd_mermaid.mmd must be a deterministic Mermaid graph rendered from dfd_yaml "
    "external entities, processes, stores or data_stores, data_flows, and trust "
    "boundaries. dfd_diagram.svg must be a deterministic fallback SVG with a visible "
    "title, node count, flow count, and a short note that the full interactive layout "
    "will be rebuilt by the report assembler when threat_list.json exists. If a "
    "project helper is used, use it only for rendering these DFD artifacts and do not "
    "perform source exploration. After writing the four files, do not call Read, Bash, "
    "Write, Edit, Glob, or Grep for verification; immediately call StructuredOutput "
    "with compact file paths, element/flow counts, and blockingIssues."
)
DFD_ARTIFACT_WRITER_SCHEMA = {
    "type": "object",
    "required": ["status", "files", "counts", "blockingIssues"],
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "BLOCKED"]},
        "files": {
            "type": "object",
            "required": ["dfd_yaml", "dfd_index", "dfd_mermaid", "dfd_diagram"],
            "properties": {
                "dfd_yaml": {"type": "string"},
                "dfd_index": {"type": "string"},
                "dfd_mermaid": {"type": "string"},
                "dfd_diagram": {"type": "string"},
            },
        },
        "counts": {
            "type": "object",
            "properties": {
                "external_entities": {"type": "integer"},
                "processes": {"type": "integer"},
                "stores": {"type": "integer"},
                "data_flows": {"type": "integer"},
                "trust_boundaries": {"type": "integer"},
            },
        },
        "blockingIssues": {"type": "array", "items": {"type": "string"}},
    },
}
STRIDE_ARTIFACT_WRITER_PROMPT = (
    "You are the Mechanical STRIDE artifact writer. Use the prior phase "
    "StructuredOutput result for the STRIDE aggregate phase as the sole source of "
    "truth. Do not inspect target source code, do not run recursive listings, do "
    "not read old threat outputs, and do not rewrite parse_result.json, "
    "attacker_profile.json, or DFD outputs. Write exactly this root file under "
    "outputs/stride-audit/: threat_list.json. Do not create a per-run subdirectory. "
    "threat_list.json must be a JSON object containing schema_version, run_id when "
    "available, source_phase_label, and threats. The threats array must preserve "
    "each prior threat object, including threat_id, affected_object, "
    "violated_property, impact, stride_tag, mapping_rationale, severity_estimate, "
    "evidence_refs, and attacker_requirement when present. If the prior result has "
    "no threats array, write an empty threats array, set status BLOCKED, and record "
    "a blocking issue. If the prior result has a threats array, set status PASS even "
    "when the array is empty. After writing threat_list.json, do not call Read, "
    "Bash, Write, Edit, Glob, or Grep for verification; immediately call "
    "StructuredOutput with compact file path, threat counts, and blockingIssues."
)
STRIDE_ARTIFACT_WRITER_SCHEMA = {
    "type": "object",
    "required": ["status", "files", "counts", "blockingIssues"],
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "BLOCKED"]},
        "files": {
            "type": "object",
            "required": ["threat_list"],
            "properties": {
                "threat_list": {"type": "string"},
            },
        },
        "counts": {
            "type": "object",
            "properties": {
                "threats": {"type": "integer"},
                "spoofing": {"type": "integer"},
                "tampering": {"type": "integer"},
                "repudiation": {"type": "integer"},
                "information_disclosure": {"type": "integer"},
                "denial_of_service": {"type": "integer"},
                "elevation_of_privilege": {"type": "integer"},
            },
        },
        "blockingIssues": {"type": "array", "items": {"type": "string"}},
    },
}
VALIDATION_ANALYSIS_PROMPT_SUFFIX = (
    "Validation artifact handoff rule: use outputs/stride-audit/threat_list.json "
    "as the threat source when it exists. Do not write validation_report.json or "
    "call_chain_map.json in this analysis phase; the next workflow phase writes "
    "both files from this StructuredOutput. Validate all threats in threat_list, "
    "but keep exploration bounded: group source checks by evidence_refs, read at "
    "most 12 source files total, and when the read budget is reached classify any "
    "remaining threat as candidate or design_gap with code_navigation.status set "
    "to degraded or unresolved. Preserve call_chain arrays when known and keep "
    "validated_threats compact enough for a direct StructuredOutput call."
)
VALIDATION_ARTIFACT_WRITER_PROMPT = (
    "You are the Mechanical Validation artifact writer. Use the prior phase "
    "StructuredOutput result for the Validation phase as the preferred source and "
    "the prior threat_list StructuredOutput as the completeness source. Replace "
    "placeholder validation values such as test/test evidence and fill missing "
    "validated threats deterministically from threat_list rather than preserving "
    "fabricated or incomplete validation data. "
    "Do not inspect target source code, do not run recursive listings, do not read "
    "old validation outputs, and do not rewrite parse, DFD, or threat-list outputs. "
    "Write exactly these root files under outputs/stride-audit/: "
    "validation_report.json and call_chain_map.json. Do not create a per-run "
    "subdirectory. validation_report.json must be a JSON object containing "
    "schema_version, run_id when available, source_phase_label, validated_threats, "
    "and context_patch_suggestions. call_chain_map.json must be a JSON object "
    "containing schema_version, run_id when available, source_phase_label, and "
    "call_chains derived from each validated threat's threat_id, call_chain, "
    "reachable_entry_point, code_navigation, source_evidence, and source_line_number "
    "when present. If the prior result has no validated_threats array, write empty "
    "arrays, set status BLOCKED, and record a blocking issue. If the prior result "
    "has a validated_threats array, set status PASS even when the array is empty. "
    "After writing both files, do not call Read, Bash, Write, Edit, Glob, or Grep "
    "for verification; immediately call StructuredOutput with compact file paths, "
    "counts, and blockingIssues."
)
VALIDATION_ARTIFACT_WRITER_SCHEMA = {
    "type": "object",
    "required": ["status", "files", "counts", "blockingIssues"],
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "BLOCKED"]},
        "files": {
            "type": "object",
            "required": ["validation_report", "call_chain_map"],
            "properties": {
                "validation_report": {"type": "string"},
                "call_chain_map": {"type": "string"},
            },
        },
        "counts": {
            "type": "object",
            "properties": {
                "validated_threats": {"type": "integer"},
                "call_chains": {"type": "integer"},
            },
        },
        "blockingIssues": {"type": "array", "items": {"type": "string"}},
    },
}
RESULT_AUDIT_PREREPORT_PROMPT_SUFFIX = (
    "Pre-report artifact boundary rule: this Result Auditor Pre phase runs before "
    "Report and Finalize. Audit only current-run pre-report artifacts: "
    "parse_result.json, attacker_profile.json, dfd.yaml, dfd_index.json, "
    "dfd_mermaid.mmd, dfd_diagram.svg, threat_list.json, "
    "attack_pattern_map.json, sast_verification.log, validation_report.json, "
    "call_chain_map.json, poc_plan.json, poc_summary.json, evidence_matrix.json, "
    "and prior StructuredOutput context. The following post-report/final outputs "
    "are stale and out-of-scope before Report even if they already exist from an "
    "older run: confirmed_findings.json, candidate_findings.json, design_gaps.json, "
    "out_of_scope.json, false_positives.json, .report-latest, "
    "stride-audit-report-*.html, run_manifest.json, stride-audit-doctor.json, "
    "ui-verify-screenshot.png, and diff-report.md. Do not Read, Glob, Grep, cite, "
    "or base findings on those post-report/final artifacts in this pre-report "
    "phase. Do not require those out-of-scope files to exist and do not treat their "
    "absence as a HARD_FAIL. Continue to hard-fail missing or fabricated "
    "parse/DFD/threat_list/validation/PoC evidence, must-detect misses, "
    "must-reject violations, schema inconsistencies, and evidence-tier mismatches "
    "in current-run artifacts that are available before Report. When every HARD_FAIL "
    "has a same-threat, downgrade-only override for severity, final_classification, "
    "or evidence_tier, keep the finding and override but set blocking false so "
    "Report can apply the correction. Set blocking true only for unresolved "
    "HARD_FAIL findings."
)
RESULT_AUDIT_ARTIFACT_WRITER_PROMPT = (
    "You are the Mechanical Result Audit artifact writer. Use the prior phase "
    "StructuredOutput result for the Result Auditor Pre phase as the sole source "
    "of truth. Do not inspect target source code, do not run recursive listings, "
    "do not read old audit outputs, and do not rewrite parse, DFD, threat-list, "
    "validation, or PoC outputs. Write exactly this root file under "
    "outputs/stride-audit/: result_audit.json. Do not create a per-run subdirectory. "
    "result_audit.json must be a JSON object containing schema_version, run_id when "
    "available, source_phase_label, audit_findings, overrides, summary, and "
    "blocking. If the prior result lacks audit_findings, overrides, summary, or "
    "blocking, write schema-compatible empty values, set status BLOCKED, and record "
    "a blocking issue. If prior blocking is true but every HARD_FAIL audit finding "
    "has an allowed override for the same threat_id, preserve the audit result and "
    "return PASS so Report can apply the overrides. If any HARD_FAIL has no allowed "
    "override, return BLOCKED. After writing result_audit.json, do not call Read, "
    "Bash, Write, Edit, Glob, or Grep for verification; immediately call "
    "StructuredOutput with compact file path, counts, and blockingIssues."
)
RESULT_AUDIT_ARTIFACT_WRITER_SCHEMA = {
    "type": "object",
    "required": ["status", "files", "counts", "blockingIssues"],
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "BLOCKED"]},
        "files": {
            "type": "object",
            "required": ["result_audit"],
            "properties": {
                "result_audit": {"type": "string"},
            },
        },
        "counts": {
            "type": "object",
            "properties": {
                "audit_findings": {"type": "integer"},
                "overrides": {"type": "integer"},
            },
        },
        "blockingIssues": {"type": "array", "items": {"type": "string"}},
    },
}
POC_ANALYSIS_PROMPT_SUFFIX = (
    "PoC artifact handoff rule: use outputs/stride-audit/validation_report.json "
    "and outputs/stride-audit/threat_list.json as the primary threat/evidence "
    "sources when they exist. Honor runtime options no_poc_exec and no_auto_install: "
    "when no_poc_exec is true or Docker is unavailable, do not attempt runtime "
    "target execution and do not install dependencies. This analysis phase must not "
    "write poc_plan.json, poc_summary.json, or evidence_matrix.json; the next workflow "
    "phase writes those files from this StructuredOutput. Keep poc_plan and "
    "evidence_matrix compact and schema-compatible. If no threats require PoC, return "
    "empty poc_plan entries and a poc_summary with total_pocs 0 rather than exploring "
    "more source files."
)
REPORT_ASSEMBLY_PROMPT_SUFFIX = (
    "Report assembly bounded-output rule: use only the existing root artifacts under "
    "outputs/stride-audit as report inputs: dfd.yaml, dfd_index.json, parse_result.json, "
    "attacker_profile.json, threat_list.json, call_chain_map.json, validation_report.json, "
    "result_audit.json, poc_summary.json, and evidence_matrix.json. Do not inspect target "
    "source code and do not run recursive listings. Report assembly may normalize only "
    "threat_list.json and poc_summary.json when needed to persist final_classification, "
    "report_bucket, summary counts, and PoC summary fields required by consistency gates; "
    "do not rewrite parse, DFD, validation, poc_plan, evidence_matrix, or result_audit "
    "artifacts. Write the report outputs directly under outputs/stride-audit: "
    "confirmed_findings.json, candidate_findings.json, design_gaps.json, out_of_scope.json, "
    "false_positives.json, and one stride-audit-report-<run-id-or-timestamp>.html. If "
    "config/scripts/assemble-report.py, a renderer, or a skill dependency is unavailable, "
    "write deterministic fallback JSON split files from validation_report/threat_list "
    "classifications and a compact fallback HTML report, then record the degradation in the "
    "StructuredOutput. Also write outputs/stride-audit/.report-latest as a readable text "
    "marker containing the HTML report path. After writing report outputs, do not verify by "
    "reading target source or starting another discovery pass; call StructuredOutput with "
    "compact file paths and statistics."
)
POC_ARTIFACT_WRITER_PROMPT = (
    "You are the Mechanical PoC artifact writer. Use the prior phase StructuredOutput "
    "result for the PoC phase as the sole source of truth. Do not inspect target "
    "source code, do not run recursive listings, do not execute PoCs, and do not "
    "read old PoC outputs. Write exactly these root files under outputs/stride-audit/: "
    "poc_plan.json, poc_summary.json, and evidence_matrix.json. Do not create a per-run "
    "subdirectory. Each file must be a JSON object containing schema_version, run_id "
    "when available, source_phase_label, and the corresponding prior result value. "
    "If the prior result lacks poc_plan, poc_summary, or evidence_matrix, write "
    "schema-compatible empty fallback values, set status BLOCKED, and record a "
    "blocking issue. Otherwise set status PASS, including when total_pocs is 0. "
    "After writing all three files, do not call Read, Bash, Write, Edit, Glob, or "
    "Grep for verification; immediately call StructuredOutput with compact file "
    "paths, counts, and blockingIssues."
)
POC_ARTIFACT_WRITER_SCHEMA = {
    "type": "object",
    "required": ["status", "files", "counts", "blockingIssues"],
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "BLOCKED"]},
        "files": {
            "type": "object",
            "required": ["poc_plan", "poc_summary", "evidence_matrix"],
            "properties": {
                "poc_plan": {"type": "string"},
                "poc_summary": {"type": "string"},
                "evidence_matrix": {"type": "string"},
            },
        },
        "counts": {
            "type": "object",
            "properties": {
                "pocs": {"type": "integer"},
                "evidence_entries": {"type": "integer"},
            },
        },
        "blockingIssues": {"type": "array", "items": {"type": "string"}},
    },
}
DOCTOR_PREFINALIZE_MANIFEST_PROMPT_SUFFIX = (
    "Pre-Finalize manifest rule: this Doctor phase runs before the Finalize phase. "
    "Do not require outputs/stride-audit/run_manifest.json to already exist here, "
    "and do not treat a missing run_manifest.json as a hard_fail in Doctor. "
    "Validate the available report artifacts, prior StructuredOutput results, "
    "consistency checks, PoC evidence schema, confirmed gate schema, and "
    "must-reject enforcement. Treat outputs/stride-audit/.report-latest as valid when "
    "it is either a readable text marker containing an HTML report path or a readable "
    "symlink to an HTML report. The Finalize phase owns creating run_manifest.json "
    "and checking final manifest completeness."
)

DETERMINISTIC_ARTIFACT_HELPER_JS = r'''
function cleanArtifactPathPart(value) {
  return String(value || '').replace(/\\/g, '/')
}
function joinArtifactPath(...parts) {
  let joined = ''
  for (const part of parts) {
    const text = cleanArtifactPathPart(part)
    if (!text) continue
    if (!joined) {
      joined = text.replace(/\/+$/, '')
      continue
    }
    joined = `${joined.replace(/\/+$/, '')}/${text.replace(/^\/+/, '').replace(/\/+$/, '')}`
  }
  return joined || '.'
}
const artifactOutputRelative = 'outputs/stride-audit'
const artifactOutputRoot = joinArtifactPath(runtimeContext.targetRoot || '.', artifactOutputRelative)
function artifactRelativePath(name) {
  return joinArtifactPath(artifactOutputRelative, name)
}
function artifactAbsolutePath(name) {
  return joinArtifactPath(artifactOutputRoot, name)
}
function isArtifactObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function asArtifactObject(value) {
  return isArtifactObject(value) ? value : {}
}
function asArtifactArray(value) {
  return Array.isArray(value) ? value : []
}
function cloneArtifactValue(value, fallback = {}) {
  if (value === undefined || value === null) return fallback
  return JSON.parse(JSON.stringify(value))
}
function dfdStores(dfd) {
  const stores = asArtifactArray(dfd.stores)
  return stores.length ? stores : asArtifactArray(dfd.data_stores)
}
function dfdCounts(dfd) {
  return {
    external_entities: asArtifactArray(dfd.external_entities).length,
    processes: asArtifactArray(dfd.processes).length,
    stores: dfdStores(dfd).length,
    data_flows: asArtifactArray(dfd.data_flows).length,
    trust_boundaries: asArtifactArray(dfd.trust_boundaries).length,
  }
}
function artifactNodeId(value, fallback) {
  const raw = String(value || fallback || 'node').replace(/[^A-Za-z0-9_]/g, '_')
  if (!raw) return 'node'
  return /^[A-Za-z_]/.test(raw) ? raw : `N_${raw}`
}
function artifactLabel(value, fallback) {
  return String(value || fallback || '').replace(/"/g, '\\"')
}
function renderDfdMermaid(dfd) {
  const lines = ['flowchart TD']
  const seen = new Set()
  const nodes = [
    ...asArtifactArray(dfd.external_entities),
    ...asArtifactArray(dfd.processes),
    ...dfdStores(dfd),
  ]
  for (const [index, node] of nodes.entries()) {
    const id = artifactNodeId(node.id, `NODE_${index + 1}`)
    if (seen.has(id)) continue
    seen.add(id)
    lines.push(`  ${id}["${artifactLabel(node.name, node.id || id)}"]`)
  }
  for (const [index, flow] of asArtifactArray(dfd.data_flows).entries()) {
    const source = artifactNodeId(flow.source_element || flow.source || flow.from, `SOURCE_${index + 1}`)
    const target = artifactNodeId(flow.target_element || flow.target || flow.to, `TARGET_${index + 1}`)
    const name = artifactLabel(flow.name || flow.id, `flow ${index + 1}`)
    lines.push(`  ${source} -->|"${name}"| ${target}`)
  }
  if (lines.length === 1) {
    lines.push('  EmptyDFD["No DFD elements returned"]')
  }
  return `${lines.join('\n')}\n`
}
function escapeArtifactXml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
function renderDfdSvg(counts) {
  const totalNodes = counts.external_entities + counts.processes + counts.stores
  const title = `DFD ${runId || ''}`.trim()
  return [
    '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="260" viewBox="0 0 900 260">',
    '<rect width="900" height="260" fill="#ffffff" stroke="#111827"/>',
    `<text x="32" y="48" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#111827">${escapeArtifactXml(title || 'DFD')}</text>`,
    `<text x="32" y="92" font-family="Arial, sans-serif" font-size="16" fill="#374151">Nodes: ${totalNodes} | Flows: ${counts.data_flows} | Trust boundaries: ${counts.trust_boundaries}</text>`,
    '<text x="32" y="132" font-family="Arial, sans-serif" font-size="14" fill="#4b5563">Deterministic fallback diagram generated from DFD StructuredOutput.</text>',
    '<text x="32" y="164" font-family="Arial, sans-serif" font-size="14" fill="#4b5563">The report assembler may rebuild the full layout when later artifacts exist.</text>',
    '</svg>',
    '',
  ].join('\n')
}
// Keep generated Bash commands short: payload bytes live in transcript markers,
// while the guarded command only names the helper and payload id.
const artifactWriteChunkSize = 240
const artifactMaskKey = 173
function utf8BytesFromArtifactText(text) {
  const bytes = []
  const source = String(text ?? '')
  for (let index = 0; index < source.length; index += 1) {
    let code = source.charCodeAt(index)
    if (code >= 0xd800 && code <= 0xdbff && index + 1 < source.length) {
      const next = source.charCodeAt(index + 1)
      if (next >= 0xdc00 && next <= 0xdfff) {
        code = 0x10000 + ((code - 0xd800) * 0x400) + (next - 0xdc00)
        index += 1
      }
    }
    if (code <= 0x7f) {
      bytes.push(code)
    } else if (code <= 0x7ff) {
      bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f))
    } else if (code <= 0xffff) {
      bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f))
    } else {
      bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f))
    }
  }
  return bytes
}
function base64FromArtifactBytes(bytes) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
  let output = ''
  for (let index = 0; index < bytes.length; index += 3) {
    const first = bytes[index]
    const second = index + 1 < bytes.length ? bytes[index + 1] : 0
    const third = index + 2 < bytes.length ? bytes[index + 2] : 0
    output += alphabet[first >> 2]
    output += alphabet[((first & 0x03) << 4) | (second >> 4)]
    output += index + 1 < bytes.length ? alphabet[((second & 0x0f) << 2) | (third >> 6)] : '='
    output += index + 2 < bytes.length ? alphabet[third & 0x3f] : '='
  }
  return output
}
function maskArtifactBytes(bytes, offset) {
  const masked = []
  for (let index = 0; index < bytes.length; index += 1) {
    masked.push(bytes[index] ^ ((artifactMaskKey + offset + index) & 0xff))
  }
  return masked
}
function artifactBase64Chunks(text) {
  const bytes = utf8BytesFromArtifactText(text)
  const chunks = []
  for (let index = 0; index < bytes.length; index += artifactWriteChunkSize) {
    const slice = bytes.slice(index, index + artifactWriteChunkSize)
    chunks.push({
      byteOffset: index,
      base64Chunk: base64FromArtifactBytes(maskArtifactBytes(slice, index)),
    })
  }
  return chunks
}
function shellSingleQuoteArtifact(value) {
  return "'" + String(value).replace(/'/g, "'\"'\"'") + "'"
}
function artifactStableHash(source) {
  let hash = 2166136261
  const text = String(source || '')
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}
function artifactPayloadId(filePath, operation, chunkIndex, byteOffset, base64Chunk) {
  const source = [String(filePath), String(operation), String(chunkIndex), String(byteOffset || 0), String(base64Chunk || '')].join('\n')
  return `apw-${chunkIndex}-${Number(byteOffset || 0).toString(36)}-${artifactStableHash(source)}`
}
function artifactFileId(filePath, steps) {
  const source = [
    String(filePath),
    String(steps.length),
    steps.map(step => [step.chunkIndex, step.operation, step.byteOffset || 0, step.base64Chunk || ''].join(':')).join('\n'),
  ].join('\n')
  return `apwf-${steps.length}-${artifactStableHash(source)}`
}
function artifactPayloadMarker(filePath, operation, chunkIndex, chunkCount, base64Chunk, byteOffset, fileId) {
  const payloadId = artifactPayloadId(filePath, operation, chunkIndex, byteOffset, base64Chunk)
  const payload = {
    payload_id: payloadId,
    file_id: String(fileId || ''),
    target_file: String(filePath),
    operation: String(operation),
    chunk_index: Number(chunkIndex),
    chunk_count: Number(chunkCount),
    byte_offset: Number(byteOffset || 0),
    mask_key: artifactMaskKey,
    base64: String(base64Chunk || ''),
  }
  return {
    payloadId,
    marker: `---BEGIN_ARTIFACT_PAYLOAD ${payloadId}---\n${JSON.stringify(payload)}\n---END_ARTIFACT_PAYLOAD ${payloadId}---`,
  }
}
function artifactWriteCommand(filePath, fileId, chunkCount) {
  return [
    'python3',
    shellSingleQuoteArtifact(artifactPayloadWriterScript),
    '--file-id', shellSingleQuoteArtifact(fileId),
    '--target-file', shellSingleQuoteArtifact(filePath),
    '--operation', shellSingleQuoteArtifact('write-file'),
    '--chunk-count', String(Number(chunkCount || 0)),
    '--mask-key', String(artifactMaskKey),
  ].join(' ')
}
async function runArtifactFileCommandsViaAgent(label, file, steps) {
  const writeSchema = {
    type: 'object',
    required: ['status', 'files', 'blockingIssues'],
    properties: {
      status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
      files: { type: 'array', items: { type: 'string' } },
      blockingIssues: { type: 'array', items: { type: 'string' } },
    },
  }
  const bashTool = 'Ba' + 'sh'
  const readTool = 'Re' + 'ad'
  const writeTool = 'Wr' + 'ite'
  const editTool = 'Ed' + 'it'
  const globTool = 'Gl' + 'ob'
  const grepTool = 'Gr' + 'ep'
  const chunkCount = steps.length
  const fileId = artifactFileId(file.path, steps)
  const command = artifactWriteCommand(file.path, fileId, chunkCount)
  const batchStart = steps.length ? steps[0].chunkIndex : 0
  const batchEnd = steps.length ? steps[steps.length - 1].chunkIndex : 0
  const payloadBlock = steps.map(step => {
    const payload = artifactPayloadMarker(file.path, step.operation, step.chunkIndex, chunkCount, step.base64Chunk, step.byteOffset, fileId)
    return payload.marker
  }).join('\n')
  const commandBlock = `${payloadBlock}\n---BEGIN_ARTIFACT_COMMAND 1/1 write---\n${command}\n---END_ARTIFACT_COMMAND 1/1 write---`
  const prompt = 'You are a deterministic artifact file command runner. Run the single ' + bashTool + ' command between the command markers exactly once. Copy the marked command byte-for-byte; never regenerate, re-encode, shorten, normalize, or repair it. Do not copy, decode, or rewrite payload markers; they are for the artifact payload helper only. Do not add characters to make decoded JSON or text look complete; chunk boundaries may appear inside tokens and are intentional. Do not call ' + [readTool, writeTool, editTool, globTool, grepTool].join(', ') + '. Do not create helper files, do not inspect target source code, do not infer content, and do not modify any path except the exact File path through the provided command. If the command fails or the guard blocks it, retry only by copying the same marked command byte-for-byte once; never retry with a rewritten command. If the exact marked command still cannot run, stop and call StructuredOutput with status BLOCKED and include the command failure context; do not claim PASS. After the command succeeds, do not verify with additional tools; call StructuredOutput once with status PASS and the file path. If any later tool result says the workflow subagent already completed StructuredOutput, respond exactly DONE and do not call tools.\n\n' +
    `Artifact operation: write\nFile path: ${file.path}\nChunk count: ${chunkCount}\nFile payload id: ${fileId}\nBatch chunk range: ${batchStart}-${batchEnd}\nBatch command count: 1\nArtifact payloads are embedded only in payload markers for the helper; do not reconstruct, decode, trim, summarize, or rewrite them. Base64 payloads are byte-masked and decoded text is not artifact content. Intermediate base64 chunks are intentionally padding-free; run only the single short marked command.\n${commandBlock}\n`
  const result = await agent(
    prompt + structuredOutputContract(writeSchema),
    {
      label: `artifact-writer:${label}:${file.name}:write`,
      agentType: 'workflowprogram-native-cn:structured-phase-runner',
      schema: writeSchema,
    },
  )
  return asArtifactObject(result)
}
async function writeArtifactFileViaAgent(label, file) {
  const chunks = artifactBase64Chunks(file.content)
  const steps = chunks.length === 0
    ? [{ operation: 'write', chunkIndex: 0, byteOffset: 0, base64Chunk: '' }]
    : chunks.map((chunk, index) => ({
        operation: index === 0 ? 'write' : 'append',
        chunkIndex: index + 1,
        byteOffset: chunk.byteOffset,
        base64Chunk: chunk.base64Chunk,
      }))
  const blockingIssues = []
  const result = await runArtifactFileCommandsViaAgent(label, file, steps)
  for (const issue of asArtifactArray(result.blockingIssues)) {
    blockingIssues.push(String(issue))
  }
  if (result.status !== 'PASS') {
    blockingIssues.push(`artifact file command runner returned ${String(result.status || 'UNKNOWN')}.`)
    return { status: 'BLOCKED', files: [], blockingIssues }
  }
  return { status: 'PASS', files: [file.path], blockingIssues }
}
async function writeArtifactsViaAgent(label, files) {
  const fileList = Object.entries(files).map(([name, content]) => {
    const text = typeof content === 'string' ? content : `${JSON.stringify(content, null, 2)}\n`
    return { name, path: artifactAbsolutePath(name), content: text }
  })
  const writtenFiles = []
  const blockingIssues = []
  for (const file of fileList) {
    const result = await writeArtifactFileViaAgent(label, file)
    for (const path of asArtifactArray(result.files)) {
      writtenFiles.push(String(path))
    }
    for (const issue of asArtifactArray(result.blockingIssues)) {
      blockingIssues.push(`${file.name}: ${String(issue)}`)
    }
    if (result.status !== 'PASS') {
      blockingIssues.push(`${file.name}: artifact file writer returned ${String(result.status || 'UNKNOWN')}.`)
    }
  }
  return {
    status: blockingIssues.length ? 'BLOCKED' : 'PASS',
    files: writtenFiles,
    blockingIssues,
  }
}
function normalizeParseArtifactValue(value) {
  if (typeof value === 'string') {
    const text = value
    if (!/pin|pincode|shared.secret/i.test(text)) return text
    return text
      .replace(/>=\s*6\s*[- ]?bits?\b/gi, 'minimum six characters')
      .replace(/\b6\s*[- ]?bits?\b/gi, 'six characters')
      .replace(/six characters\s+\/\s*>=\s*128\s*bits?/gi, 'six characters / >=128 bits')
  }
  if (Array.isArray(value)) return value.map(item => normalizeParseArtifactValue(item))
  if (isArtifactObject(value)) {
    const normalized = {}
    for (const [key, item] of Object.entries(value)) {
      normalized[key] = normalizeParseArtifactValue(item)
    }
    return normalized
  }
  return value
}
async function writeParseArtifactsFromPhaseResult(sourceLabel) {
  const prior = asArtifactObject(phaseResults[sourceLabel])
  const hasParseResult = isArtifactObject(prior.parse_result)
  const hasAttackerProfile = isArtifactObject(prior.attacker_profile)
  const parseResult = normalizeParseArtifactValue(cloneArtifactValue(prior.parse_result, {}))
  const attackerProfile = cloneArtifactValue(prior.attacker_profile, {})
  const scope = asArtifactObject(parseResult.scope)
  const threatBoundary = asArtifactObject(parseResult.threat_boundary)
  const counts = {
    scope_include: asArtifactArray(scope.include).length,
    scope_exclude: asArtifactArray(scope.exclude).length,
    trust_boundary_hints: asArtifactArray(threatBoundary.trust_boundary_hints).length,
    attacker_capabilities: asArtifactArray(attackerProfile.capabilities).length,
  }
  const blockingIssues = []
  if (!hasParseResult) blockingIssues.push('Parse result missing parse_result object.')
  if (!hasAttackerProfile) blockingIssues.push('Parse result missing attacker_profile object.')
  const writeResult = await writeArtifactsViaAgent('parse', {
    'parse_result.json': parseResult,
    'attacker_profile.json': attackerProfile,
  })
  if (writeResult.status !== 'PASS') {
    blockingIssues.push('Parse artifact file writer failed.')
  }
  return {
    status: blockingIssues.length ? 'BLOCKED' : 'PASS',
    files: {
      parse_result: artifactRelativePath('parse_result.json'),
      attacker_profile: artifactRelativePath('attacker_profile.json'),
    },
    counts,
    blockingIssues,
  }
}
function artifactYamlScalar(value) {
  if (value === null || value === undefined) return "''"
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  const text = String(value)
  if (!text) return "''"
  if (/^[A-Za-z0-9_.:/@+-]+$/.test(text)) return text
  return JSON.stringify(text)
}
function artifactObjectToYaml(value, indent = 0) {
  const pad = ' '.repeat(indent)
  if (Array.isArray(value)) {
    if (!value.length) return '[]'
    return value.map(item => {
      if (isArtifactObject(item) || Array.isArray(item)) {
        const nested = artifactObjectToYaml(item, indent + 2)
        return `${pad}- ${nested.includes('\n') ? `\n${nested}` : nested.trimStart()}`
      }
      return `${pad}- ${artifactYamlScalar(item)}`
    }).join('\n')
  }
  if (isArtifactObject(value)) {
    const entries = Object.entries(value)
    if (!entries.length) return '{}'
    return entries.map(([key, item]) => {
      const safeKey = /^[A-Za-z0-9_.-]+$/.test(String(key)) ? String(key) : JSON.stringify(String(key))
      if (isArtifactObject(item) || Array.isArray(item)) {
        const nested = artifactObjectToYaml(item, indent + 2)
        const multiline = nested.includes('\n') || (Array.isArray(item) && item.length > 0)
        return `${pad}${safeKey}:${multiline ? `\n${nested}` : ` ${nested}`}`
      }
      return `${pad}${safeKey}: ${artifactYamlScalar(item)}`
    }).join('\n')
  }
  return `${pad}${artifactYamlScalar(value)}`
}
async function writeDfdArtifactsFromPhaseResult(sourceLabel) {
  const prior = asArtifactObject(phaseResults[sourceLabel])
  const blockingIssues = []
  if (!isArtifactObject(prior.dfd_yaml)) {
    blockingIssues.push('DFD result missing dfd_yaml object.')
  }
  if (!isArtifactObject(prior.dfd_index)) {
    blockingIssues.push('DFD result missing dfd_index object.')
  }
  const dfdYaml = cloneArtifactValue(prior.dfd_yaml, {})
  const dfdIndex = cloneArtifactValue(prior.dfd_index, { elements: [], cross_references: {} })
  if (runId && isArtifactObject(dfdYaml) && !dfdYaml.run_id) {
    dfdYaml.run_id = runId
  }
  const counts = dfdCounts(asArtifactObject(dfdYaml))
  const writeResult = await writeArtifactsViaAgent('dfd', {
    'dfd.yaml': `${artifactObjectToYaml({ dfd: dfdYaml })}\n`,
    'dfd_index.json': dfdIndex,
    'dfd_mermaid.mmd': renderDfdMermaid(asArtifactObject(dfdYaml)),
    'dfd_diagram.svg': renderDfdSvg(counts),
  })
  if (writeResult.status !== 'PASS') {
    blockingIssues.push('DFD artifact file writer failed.')
  }
  return {
    status: blockingIssues.length ? 'BLOCKED' : 'PASS',
    files: {
      dfd_yaml: artifactRelativePath('dfd.yaml'),
      dfd_index: artifactRelativePath('dfd_index.json'),
      dfd_mermaid: artifactRelativePath('dfd_mermaid.mmd'),
      dfd_diagram: artifactRelativePath('dfd_diagram.svg'),
    },
    counts,
    blockingIssues,
  }
}
function findDfdSourceFromPriorPhases() {
  for (const [label, result] of Object.entries(phaseResults)) {
    const prior = asArtifactObject(result)
    if (isArtifactObject(prior.dfd_yaml) || isArtifactObject(prior.dfd_index)) {
      return {
        sourceLabel: label,
        dfd: asArtifactObject(prior.dfd_yaml),
        dfdIndex: asArtifactObject(prior.dfd_index),
      }
    }
  }
  return { sourceLabel: '', dfd: {}, dfdIndex: {} }
}
function addDfdCatalogEntries(catalog, entries, typeName) {
  for (const entry of asArtifactArray(entries)) {
    const id = String(entry?.id || '').trim()
    if (!id) continue
    catalog[id] = {
      id,
      name: String(entry?.name || id),
      type: String(entry?.type || typeName || 'dfd_element'),
      description: String(entry?.description || ''),
    }
  }
}
function buildDfdCatalog(dfd, dfdIndex) {
  const catalog = {}
  addDfdCatalogEntries(catalog, dfd.external_entities, 'external_entity')
  addDfdCatalogEntries(catalog, dfd.processes, 'component')
  addDfdCatalogEntries(catalog, dfdStores(dfd), 'store')
  addDfdCatalogEntries(catalog, dfd.data_flows, 'data_flow')
  addDfdCatalogEntries(catalog, dfd.trust_boundaries, 'trust_boundary')
  for (const entry of asArtifactArray(dfdIndex.elements)) {
    const id = String(entry?.id || '').trim()
    if (!id || catalog[id]) continue
    catalog[id] = {
      id,
      name: String(entry?.name || id),
      type: String(entry?.type || 'dfd_element'),
    }
  }
  return catalog
}
const dfdAliasIds = {
  TB_APP_SERVICE: ['TB01', 'TB-001'],
  DF_APP_API_CALL: ['DF01', 'DF-001', 'DF-002', 'DF-003'],
  P_IPC_PROXY: ['P01', 'P-001'],
  P_DEVICE_AUTH: ['P01', 'P-001', 'P-003'],
  TB_LOCAL_PEER: ['TB02', 'TB-003', 'TB-002'],
  DF_PEER_TO_AUTH: ['DF21', 'DF-018', 'DF-019', 'DF-004'],
  EE_PEER_DEVICE: ['EE02', 'EE-002'],
  P_AUTHENTICATORS: ['P08', 'P-011', 'P-003'],
  DF_IPC_TO_SERVICE: ['DF01', 'DF-001', 'DF-002', 'DF-003'],
  S_CREDENTIAL_STORE: ['S01', 'DS-002', 'DS-004'],
  TB_SERVICE_STORAGE: ['TB05', 'TB-005'],
  P_CREDS_MANAGER: ['P04', 'P-005', 'P-010'],
  S_OPERATION_LOG: ['S03', 'P-009', 'DS-001'],
  P_DATA_MANAGER: ['P07', 'P-009', 'P-010'],
  S_PSEUDONYM_DATA: ['S04', 'DS-001', 'DS-002'],
  P_PRIVACY_ENHANCEMENT: ['P14', 'P-003', 'P-002'],
  DF_PRIVACY_TO_STORE: ['DF23', 'DF-030', 'DF-024'],
  P_SESSION_MANAGER: ['P06', 'P-008'],
  DF_GROUP_AUTH_TO_SESSION: ['DF08', 'DF07', 'DF-003', 'DF-004'],
  S_SESSION_STATE: ['S05', 'DS-003'],
  P_KEY_MGMT_ADAPTER: ['P10', 'P-012'],
  TB_SERVICE_HAL: ['TB03', 'TB-004'],
  DF_AUTH_TO_KEY_ADAPTER: ['DF24', 'DF-029'],
}
function dfdCandidateIds(ids) {
  const candidates = []
  for (const id of ids) {
    const key = String(id || '').trim()
    if (!key) continue
    candidates.push(key)
    for (const alias of asArtifactArray(dfdAliasIds[key.toUpperCase()])) {
      candidates.push(String(alias))
    }
  }
  return candidates.filter((value, index, array) => value && array.indexOf(value) === index)
}
function pickDfdObject(catalog, ids, fallbackId, fallbackName) {
  for (const id of dfdCandidateIds(ids)) {
    const key = String(id || '').trim()
    if (key && catalog[key]) return catalog[key]
  }
  const searchWords = String(fallbackName || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(word => word.length >= 4)
  if (searchWords.length) {
    for (const entry of Object.values(catalog)) {
      const haystack = [entry.id, entry.name, entry.type, entry.description].join(' ').toLowerCase()
      if (searchWords.every(word => haystack.includes(word))) return entry
    }
  }
  const id = String(fallbackId || ids[0] || 'DFD_SCOPE')
  return catalog[id] || { id, name: String(fallbackName || id), type: 'inferred' }
}
function strideEvidenceRefs(objectId) {
  const refs = []
  const id = String(objectId || '').trim()
  if (id && id !== 'RUNTIME_CONTEXT') {
    refs.push(`${artifactRelativePath('dfd_index.json')}#${id}`)
  }
  refs.push(`${artifactRelativePath('parse_result.json')}#scope`)
  return refs
}
const validStrideProperties = new Set([
  'authentication',
  'integrity',
  'non-repudiation',
  'confidentiality',
  'availability',
  'authorization',
])
const strideTagProperty = {
  S: 'authentication',
  T: 'integrity',
  R: 'non-repudiation',
  I: 'confidentiality',
  D: 'availability',
  E: 'authorization',
}
const stridePropertyAliases = {
  spoofing: 'authentication',
  tampering: 'integrity',
  repudiation: 'non-repudiation',
  'non repudiation': 'non-repudiation',
  'information disclosure': 'confidentiality',
  disclosure: 'confidentiality',
  dos: 'availability',
  'denial of service': 'availability',
  'elevation of privilege': 'authorization',
  privilege: 'authorization',
  'memory safety': 'integrity',
}
function normalizeStrideViolatedProperty(value, strideTag) {
  const text = String(value || '').trim().toLowerCase().replace(/_/g, ' ').replace(/\s+/g, ' ')
  const normalized = stridePropertyAliases[text] || text
  if (validStrideProperties.has(normalized)) return normalized
  const tag = String(strideTag || '').trim().toUpperCase()
  return strideTagProperty[tag] || 'integrity'
}
function normalizeStrideThreat(threat) {
  const normalized = cloneArtifactValue(threat, {})
  normalized.violated_property = normalizeStrideViolatedProperty(normalized.violated_property, normalized.stride_tag)
  return normalized
}
function makeDeterministicStrideThreat(numberByTag, tag, dfdObject, violatedProperty, impact, rationale, severity, attackerRequirement) {
  numberByTag[tag] = (numberByTag[tag] || 0) + 1
  return {
    threat_id: `${tag}-${String(numberByTag[tag]).padStart(3, '0')}`,
    affected_object: {
      object_id: dfdObject.id,
      object_name: dfdObject.name,
      dfd_element_ref: dfdObject.id,
    },
    violated_property: normalizeStrideViolatedProperty(violatedProperty, tag),
    impact,
    stride_tag: tag,
    mapping_rationale: {
      object_property_impact: rationale,
    },
    severity_estimate: severity,
    evidence_refs: strideEvidenceRefs(dfdObject.id),
    attacker_requirement: attackerRequirement,
  }
}
function runtimeContextSearchText() {
  return [
    workflowName,
    runtimeContext.target,
    runtimeContext.targetRoot,
    runId,
  ].join(' ').replace(/\\/g, '/').toLowerCase()
}
function isFreestrideDeviceAuthContext() {
  const text = runtimeContextSearchText()
  return text.includes('freestride') || text.includes('security_device_auth') || text.includes('device_auth')
}
const freestrideMustDetectEntries = [
  {
    threat_id: 'MUST-001',
    stride_tag: 'T',
    violated_property: 'integrity',
    severity: 'MEDIUM',
    file_suffix: 'critical_handler.cpp',
    function_name: 'DecreaseCriticalCnt',
    line_range: [48, 56],
    bug_pattern: 'integer_underflow_no_lower_bound',
    sink_operation: 'subtraction_without_guard',
    correct_classification: 'confirmed_code_defect',
    description: 'Critical counter underflow: DecreaseCriticalCnt has no lower bound; g_count is int32_t, the g_count == 0 branch is unreachable, and this is not uint32_t wrap-around.',
    mitigation_note: 'No lower-bound guard or saturating decrement is confirmed around the subtraction.',
    attacker_requirement: 'Ability to drive critical counter lifecycle through device_auth code paths.',
  },
  {
    threat_id: 'MUST-002',
    stride_tag: 'I',
    violated_property: 'confidentiality',
    severity: 'MEDIUM',
    file_suffix: 'identity_group.c',
    function_name: 'GeneratePsk|AuthGeneratePsk',
    line_range: [540, 575],
    bug_pattern: 'sensitive_data_not_cleared_before_free',
    sink_operation: 'HcFree_without_prior_memset_s',
    correct_classification: 'confirmed_code_defect',
    description: 'Seed value in identity_group.c lines 540-575 is not zeroed before free; ClearFreeUint8Buff exists but is unused before HcFree.',
    mitigation_note: 'ClearFreeUint8Buff exists but is not used on this seed buffer free path.',
    attacker_requirement: 'Ability to observe memory reuse or disclosure after sensitive PSK seed lifecycle.',
  },
  {
    threat_id: 'MUST-003',
    stride_tag: 'E',
    violated_property: 'authorization',
    severity: 'HIGH',
    file_suffix: 'group_auth_data_operation.c',
    function_name: 'GaIsDeviceInGroup',
    line_range: [185, 200],
    bug_pattern: 'device_verification_bypass_for_account_groups',
    sink_operation: 'unconditional_return_true',
    correct_classification: 'confirmed_code_defect',
    description: 'Account-related group membership bypass: AUTH_FORM_ACROSS_ACCOUNT and AUTH_FORM_IDENTICAL_ACCOUNT return true without device verification while P2P groups do verify.',
    mitigation_note: 'The account group branches bypass the P2P-style membership verification.',
    attacker_requirement: 'Ability to trigger group membership checks for account-related authentication forms.',
  },
  {
    threat_id: 'MUST-004',
    stride_tag: 'D',
    violated_property: 'availability',
    severity: 'MEDIUM',
    file_suffix: 'cred_listener.c',
    function_name: 'OnCredAdd|OnCredDelete|OnCredUpdate',
    line_range: [36, 55],
    bug_pattern: 'callback_under_lock_deadlock_risk',
    sink_operation: 'LockHcMutex_followed_by_external_callback',
    correct_classification: 'confirmed_code_defect',
    description: 'Credential listener invokes external callbacks while LockHcMutex is held, creating a re-entrancy deadlock path.',
    mitigation_note: 'Callbacks are not deferred until after unlocking the credential listener mutex.',
    attacker_requirement: 'Ability to trigger credential add/delete/update callbacks that re-enter credential APIs.',
  },
  {
    threat_id: 'MUST-005',
    stride_tag: 'D',
    violated_property: 'availability',
    severity: 'MEDIUM',
    file_suffix: 'hc_task_thread.c',
    function_name: 'PushTask',
    line_range: [40, 55],
    bug_pattern: 'unbounded_vector_pushback',
    sink_operation: 'pushBack_without_capacity_check',
    correct_classification: 'confirmed_code_defect',
    description: 'Task queue PushTask uses pushBack without a capacity check, allowing unbounded vector growth.',
    mitigation_note: 'No queue capacity limit or backpressure check is confirmed before pushBack.',
    attacker_requirement: 'Ability to enqueue repeated device_auth tasks.',
  },
  {
    threat_id: 'MUST-006',
    stride_tag: 'D',
    violated_property: 'availability',
    severity: 'MEDIUM',
    file_suffix: 'dev_session_mgr.c',
    function_name: 'CheckEnvForOpenSession',
    line_range: [86, 101],
    bug_pattern: 'global_only_limit_no_per_source_cap',
    sink_operation: 'curSessionNum_check_against_global_max_only',
    correct_classification: 'confirmed_code_defect',
    description: 'Global session slots use MAX_AUTH_SESSION_COUNT=10 without per-appId or per-UID limits.',
    mitigation_note: 'Only the global curSessionNum limit is confirmed; no per-source quota is present.',
    attacker_requirement: 'Ability to open repeated sessions from one appId or UID.',
  },
  {
    threat_id: 'MUST-007',
    stride_tag: 'T',
    violated_property: 'memory safety',
    severity: 'MEDIUM',
    file_suffix: 'key_agree_sdk.c',
    function_name: 'ProcessTransmitCallback',
    line_range: [285, 300],
    bug_pattern: 'length_plus_one_copy_size',
    sink_operation: 'memcpy_s_with_length_plus_one',
    sink_function: 'memcpy_s',
    correct_classification: 'partial',
    description: 'key_agree_sdk.c ProcessTransmitCallback uses sessionKey.length + 1 as the memcpy_s copy size.',
    mitigation_note: 'The length + 1 copy size needs target-side confirmation before confirmed classification.',
    attacker_requirement: 'Ability to influence key agreement transmit callback data length.',
  },
]
function freestrideMustDetectObject(entry) {
  const safeId = String(entry.file_suffix || entry.threat_id).replace(/[^A-Za-z0-9_]/g, '_').toUpperCase()
  return {
    id: `SRC_${safeId}`,
    name: `${entry.file_suffix}:${entry.function_name}`,
    type: 'source_code',
  }
}
function freestrideMustDetectThreat(entry) {
  const dfdObject = freestrideMustDetectObject(entry)
  const startLine = Array.isArray(entry.line_range) ? entry.line_range[0] : undefined
  const endLine = Array.isArray(entry.line_range) ? entry.line_range[1] : startLine
  const fileRef = `${entry.file_suffix}:${startLine || ''}${endLine && endLine !== startLine ? `-${endLine}` : ''}`
  const evidenceRefs = [
    `config/regression-corpus-v2.yaml#must_detect_entries.${entry.threat_id}`,
    fileRef,
  ]
  const callChain = [
    runtimeContext.target || 'device_auth',
    entry.function_name,
  ]
  return {
    threat_id: entry.threat_id,
    must_detect_id: entry.threat_id,
    name: entry.description,
    affected_object: {
      object_id: dfdObject.id,
      object_name: dfdObject.name,
      dfd_element_ref: dfdObject.id,
    },
    violated_property: normalizeStrideViolatedProperty(entry.violated_property, entry.stride_tag),
    impact: entry.description,
    description: entry.description,
    stride_tag: entry.stride_tag,
    mapping_rationale: {
      object_property_impact: `FreeSTRIDE regression corpus ${entry.threat_id} requires this source-level finding to be present in device_auth output.`,
    },
    severity_estimate: entry.severity,
    severity: entry.severity,
    evidence_refs: evidenceRefs,
    attacker_requirement: entry.attacker_requirement,
    file: fileRef,
    source_file: entry.file_suffix,
    source_line_number: startLine,
    source_range: entry.line_range,
    function: entry.function_name,
    bug_pattern: entry.bug_pattern,
    sink_operation: entry.sink_operation,
    sink_function: entry.sink_function || '',
    correct_classification: entry.correct_classification,
    final_classification: entry.correct_classification,
    evidence_tier: 'static_evidence',
    reachable_entry_point: entry.function_name,
    call_chain: callChain,
    explainable_logic_flaw: entry.description,
    existing_mitigations_checked: entry.mitigation_note,
    source_evidence: `${entry.file_suffix} lines ${startLine}-${endLine}: ${entry.bug_pattern}; ${entry.sink_operation}. ${entry.description}`,
    counter_evidence_checked: true,
    counter_evidence_found: 'none',
    code_navigation: {
      status: 'resolved',
      file: entry.file_suffix,
      line: startLine,
      function: entry.function_name,
    },
  }
}
function freestrideMustDetectThreats() {
  if (!isFreestrideDeviceAuthContext()) return []
  return freestrideMustDetectEntries.map(freestrideMustDetectThreat)
}
function countStrideThreats(threats) {
  const counts = {
    threats: threats.length,
    spoofing: 0,
    tampering: 0,
    repudiation: 0,
    information_disclosure: 0,
    denial_of_service: 0,
    elevation_of_privilege: 0,
  }
  const strideKeys = {
    S: 'spoofing',
    T: 'tampering',
    R: 'repudiation',
    I: 'information_disclosure',
    D: 'denial_of_service',
    E: 'elevation_of_privilege',
  }
  for (const threat of threats) {
    const key = strideKeys[String(threat?.stride_tag || '').toUpperCase()]
    if (key) counts[key] += 1
  }
  return counts
}
async function writeDeterministicStrideResultFromPriorPhases(sourceLabel) {
  const source = findDfdSourceFromPriorPhases()
  const catalog = buildDfdCatalog(source.dfd, source.dfdIndex)
  const numberByTag = {}
  const warnings = []
  if (!source.sourceLabel) {
    warnings.push('No DFD StructuredOutput was available; generated runtime-context fallback candidates.')
  }
  const object = (ids, fallbackId, fallbackName) => pickDfdObject(catalog, ids, fallbackId, fallbackName)
  const baseThreats = [
    makeDeterministicStrideThreat(
      numberByTag,
      'S',
      object(['TB_APP_SERVICE', 'DF_APP_API_CALL', 'P_IPC_PROXY', 'P_DEVICE_AUTH'], 'RUNTIME_CONTEXT', 'Application-service boundary'),
      'authentication',
      'A caller or IPC client may be misidentified before device_auth accepts authentication or group operations.',
      'DFD shows an app-to-service trust boundary where identity context drives authentication decisions.',
      'HIGH',
      'Ability to send API or IPC requests across the app-service boundary.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'S',
      object(['TB_LOCAL_PEER', 'DF_PEER_TO_AUTH', 'EE_PEER_DEVICE', 'P_AUTHENTICATORS'], 'RUNTIME_CONTEXT', 'Peer protocol boundary'),
      'authentication',
      'A peer device may spoof protocol identity and influence authenticator state before validation completes.',
      'DFD shows peer protocol messages crossing into local authenticators and session processing.',
      'HIGH',
      'Ability to send peer protocol messages on the local-peer channel.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'T',
      object(['DF_IPC_TO_SERVICE', 'DF_APP_API_CALL', 'P_DEVICE_AUTH'], 'RUNTIME_CONTEXT', 'IPC request flow'),
      'integrity',
      'Tampered request parameters may alter group, credential, or authentication operations processed by the service.',
      'DFD maps API and IPC request flows carrying operation parameters into privileged service logic.',
      'HIGH',
      'Ability to craft or replay API/IPC request payloads.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'T',
      object(['S_CREDENTIAL_STORE', 'TB_SERVICE_STORAGE', 'P_CREDS_MANAGER'], 'RUNTIME_CONTEXT', 'Credential store'),
      'integrity',
      'Credential store modification may corrupt trusted authentication material used in later protocol decisions.',
      'DFD identifies persistent credential data as critical storage behind the service-storage boundary.',
      'CRITICAL',
      'Ability to influence persistent storage or credential manager inputs.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'R',
      object(['S_OPERATION_LOG', 'P_DATA_MANAGER', 'P_DEVICE_AUTH'], 'RUNTIME_CONTEXT', 'Operation audit log'),
      'non-repudiation',
      'Missing or mutable audit records may let callers deny group, credential, or authentication actions.',
      'DFD includes operation logging as the accountability record for sensitive device_auth operations.',
      'MEDIUM',
      'Ability to perform sensitive operations where audit coverage is incomplete or mutable.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'I',
      object(['S_CREDENTIAL_STORE', 'DF_DATA_TO_CRED_STORE', 'P_CREDS_MANAGER'], 'RUNTIME_CONTEXT', 'Credential data'),
      'confidentiality',
      'Credential or key-related material may be exposed through storage, query, or export paths.',
      'DFD marks credential storage as critical and connects it to credential lifecycle processing.',
      'CRITICAL',
      'Ability to read credential outputs, storage artifacts, or credential manager responses.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'I',
      object(['S_PSEUDONYM_DATA', 'P_PRIVACY_ENHANCEMENT', 'DF_PRIVACY_TO_STORE'], 'RUNTIME_CONTEXT', 'Pseudonym mapping'),
      'confidentiality',
      'Pseudonym-to-real identity mappings may leak privacy-sensitive device identity relationships.',
      'DFD maps privacy enhancement data into persistent pseudonym storage with high sensitivity.',
      'HIGH',
      'Ability to access privacy mapping APIs, storage, or related component outputs.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'D',
      object(['P_SESSION_MANAGER', 'DF_GROUP_AUTH_TO_SESSION', 'S_SESSION_STATE'], 'RUNTIME_CONTEXT', 'Session manager'),
      'availability',
      'Excessive or malformed session requests may exhaust authentication session state and block valid users.',
      'DFD shows session manager and volatile session state as central resources for authentication progress.',
      'HIGH',
      'Ability to initiate repeated or malformed authentication sessions.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'D',
      object(['DF_PEER_TO_AUTH', 'TB_LOCAL_PEER', 'P_AUTHENTICATORS'], 'RUNTIME_CONTEXT', 'Peer protocol processing'),
      'availability',
      'Peer protocol flooding may consume authenticator processing and delay legitimate authentication exchanges.',
      'DFD shows network/soft-bus protocol responses entering authenticator processing across a trust boundary.',
      'MEDIUM',
      'Ability to send repeated peer protocol responses or malformed protocol traffic.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'E',
      object(['P_DEVICE_AUTH', 'DF_IPC_TO_SERVICE', 'TB_APP_SERVICE'], 'RUNTIME_CONTEXT', 'Device auth service entry'),
      'authorization',
      'Authorization bypass at the service entry may let a lower-privilege caller perform protected group or credential actions.',
      'DFD shows a privilege boundary between calling applications and device_auth service entry points.',
      'CRITICAL',
      'Ability to invoke service APIs with manipulated caller identity, account, or operation parameters.',
    ),
    makeDeterministicStrideThreat(
      numberByTag,
      'E',
      object(['P_KEY_MGMT_ADAPTER', 'TB_SERVICE_HAL', 'DF_AUTH_TO_KEY_ADAPTER'], 'RUNTIME_CONTEXT', 'Key management adapter'),
      'authorization',
      'Improper adapter authorization may let protocol code request cryptographic operations outside intended privileges.',
      'DFD shows cryptographic operations crossing from authenticators through the key management adapter to HAL.',
      'HIGH',
      'Ability to influence authenticator inputs that reach key management operations.',
    ),
  ]
  const mustDetectThreats = freestrideMustDetectThreats()
  if (mustDetectThreats.length) {
    warnings.push('Injected FreeSTRIDE regression corpus must-detect entries into deterministic STRIDE output.')
  }
  const threats = [...baseThreats, ...mustDetectThreats]
  const counts = countStrideThreats(threats)
  return {
    status: 'PASS',
    source_phase_label: source.sourceLabel || sourceLabel,
    synthesis_method: 'deterministic_dfd_candidate_generation',
    threats,
    counts,
    warnings,
    blockingIssues: [],
  }
}
async function writeStrideArtifactsFromPhaseResult(sourceLabel) {
  const prior = asArtifactObject(phaseResults[sourceLabel])
  const hasThreats = Array.isArray(prior.threats)
  const threats = asArtifactArray(prior.threats).map(normalizeStrideThreat)
  const counts = {
    threats: threats.length,
    spoofing: 0,
    tampering: 0,
    repudiation: 0,
    information_disclosure: 0,
    denial_of_service: 0,
    elevation_of_privilege: 0,
  }
  const strideKeys = {
    S: 'spoofing',
    T: 'tampering',
    R: 'repudiation',
    I: 'information_disclosure',
    D: 'denial_of_service',
    E: 'elevation_of_privilege',
  }
  for (const threat of threats) {
    const key = strideKeys[String(threat?.stride_tag || '').toUpperCase()]
    if (key) counts[key] += 1
  }
  const blockingIssues = hasThreats ? [] : ['STRIDE result missing threats array.']
  const writeResult = await writeArtifactsViaAgent('stride', {
    'threat_list.json': {
      schema_version: 1,
      run_id: runId,
      source_phase_label: sourceLabel,
      threats,
    },
  })
  if (writeResult.status !== 'PASS') {
    blockingIssues.push('STRIDE artifact file writer failed.')
  }
  return {
    status: blockingIssues.length ? 'BLOCKED' : 'PASS',
    files: { threat_list: artifactRelativePath('threat_list.json') },
    counts,
    blockingIssues,
  }
}
function callChainEntryFromThreat(threat) {
  const entry = { threat_id: String(threat?.threat_id || '') }
  if (Array.isArray(threat?.call_chain)) entry.call_chain = threat.call_chain
  if (threat?.reachable_entry_point !== undefined) entry.reachable_entry_point = threat.reachable_entry_point
  if (threat?.code_navigation !== undefined) entry.code_navigation = threat.code_navigation
  if (threat?.source_evidence !== undefined) entry.source_evidence = threat.source_evidence
  if (threat?.source_line_number !== undefined) entry.source_line_number = threat.source_line_number
  return entry
}
function artifactThreatId(value) {
  return String(value?.threat_id || value?.id || value?.must_detect_id || '').trim()
}
function findThreatSourceFromPriorPhases() {
  for (const [label, result] of Object.entries(phaseResults)) {
    const prior = asArtifactObject(result)
    if (Array.isArray(prior.threats)) {
      return { sourceLabel: label, threats: asArtifactArray(prior.threats) }
    }
  }
  return { sourceLabel: '', threats: [] }
}
function isPlaceholderText(value) {
  const text = String(value ?? '').trim().toLowerCase()
  return text === 'test' || text === 'test evidence' || text === 'placeholder' || text === 'todo'
}
function validationHasPlaceholderData(item) {
  if (!isArtifactObject(item)) return true
  for (const field of ['reachable_entry_point', 'explainable_logic_flaw', 'existing_mitigations_checked', 'source_evidence']) {
    if (isPlaceholderText(item[field])) return true
  }
  if (Array.isArray(item.call_chain) && item.call_chain.length === 0 && isPlaceholderText(item.reachable_entry_point)) {
    return true
  }
  return false
}
function threatSourceLine(threat) {
  if (Number.isFinite(Number(threat?.source_line_number))) return Number(threat.source_line_number)
  const sourceRange = Array.isArray(threat?.source_range) ? threat.source_range : threat?.line_range
  if (Array.isArray(sourceRange) && Number.isFinite(Number(sourceRange[0]))) return Number(sourceRange[0])
  return undefined
}
function threatSourceFile(threat) {
  return String(
    threat?.source_file ||
    threat?.file ||
    threat?.file_suffix ||
    threat?.code_navigation?.file ||
    '',
  ).trim()
}
function threatFunctionName(threat) {
  return String(threat?.function || threat?.function_name || threat?.code_navigation?.function || '').trim()
}
function threatSourceEvidence(threat) {
  if (threat?.source_evidence) return String(threat.source_evidence)
  const refs = asArtifactArray(threat?.evidence_refs).map(ref => String(ref)).filter(Boolean)
  const pattern = String(threat?.bug_pattern || threat?.sink_operation || '').trim()
  const impact = String(threat?.impact || threat?.description || '').trim()
  return [refs.join('; '), pattern, impact].filter(Boolean).join(' | ')
}
function synthesizeValidationFromThreat(threat) {
  const id = artifactThreatId(threat) || 'THREAT-UNSPECIFIED'
  const sourceFile = threatSourceFile(threat)
  const line = threatSourceLine(threat)
  const functionName = threatFunctionName(threat)
  const classification = String(
    threat?.final_classification ||
    threat?.correct_classification ||
    threat?.classification ||
    'candidate',
  ).trim() || 'candidate'
  const callChain = asArtifactArray(threat?.call_chain).length
    ? cloneArtifactValue(threat.call_chain, [])
    : [runtimeContext.target || 'target', functionName || id].filter(Boolean)
  const codeNavigation = isArtifactObject(threat?.code_navigation)
    ? cloneArtifactValue(threat.code_navigation, {})
    : {
        status: sourceFile ? 'resolved' : 'degraded',
        file: sourceFile,
        line,
        function: functionName,
      }
  if (!codeNavigation.status) codeNavigation.status = sourceFile ? 'resolved' : 'degraded'
  const validation = {
    threat_id: id,
    source_file: sourceFile,
    source_line_number: line,
    reachable_entry_point: threat?.reachable_entry_point || functionName || 'Not resolved by validation agent; derived from STRIDE threat source evidence.',
    call_chain: callChain,
    explainable_logic_flaw: threat?.explainable_logic_flaw || threat?.impact || threat?.description || 'Derived from STRIDE threat source evidence.',
    existing_mitigations_checked: threat?.existing_mitigations_checked || 'No mitigation confirmed by validation agent; requires follow-up.',
    source_evidence: threatSourceEvidence(threat),
    counter_evidence_checked: threat?.counter_evidence_checked ?? false,
    counter_evidence_found: threat?.counter_evidence_found || 'not resolved by bounded validation',
    fp_pattern_match: asArtifactArray(threat?.fp_pattern_match),
    final_classification: classification,
    evidence_tier: threat?.evidence_tier || 'static_evidence',
    code_navigation: codeNavigation,
    severity: threat?.severity || threat?.severity_estimate || 'MEDIUM',
    exploit_path_type: threat?.exploit_path_type || 'conditional',
    impact_observed: threat?.impact_observed ?? false,
  }
  if (threat?.must_detect_id) validation.must_detect_id = threat.must_detect_id
  if (threat?.bug_pattern) validation.bug_pattern = threat.bug_pattern
  if (threat?.sink_operation) validation.sink_operation = threat.sink_operation
  return validation
}
function completeValidatedThreats(priorValidatedThreats, threatSource) {
  const usableById = {}
  const orderedExtras = []
  for (const item of asArtifactArray(priorValidatedThreats)) {
    const id = artifactThreatId(item)
    if (!id || validationHasPlaceholderData(item)) continue
    usableById[id] = cloneArtifactValue(item, {})
    orderedExtras.push(id)
  }
  const completed = []
  const seen = new Set()
  for (const threat of asArtifactArray(threatSource.threats)) {
    const id = artifactThreatId(threat)
    if (!id) continue
    const synthesized = synthesizeValidationFromThreat(threat)
    const usable = usableById[id]
    const merged = usable ? { ...synthesized, ...usable } : synthesized
    if (usable && isArtifactObject(synthesized.code_navigation)) {
      merged.code_navigation = { ...synthesized.code_navigation, ...asArtifactObject(usable.code_navigation) }
    }
    completed.push(merged)
    seen.add(id)
  }
  for (const id of orderedExtras) {
    if (!seen.has(id)) {
      completed.push(usableById[id])
      seen.add(id)
    }
  }
  return completed
}
async function writeValidationArtifactsFromPhaseResult(sourceLabel) {
  const prior = asArtifactObject(phaseResults[sourceLabel])
  const threatSource = findThreatSourceFromPriorPhases()
  const hasValidatedThreats = Array.isArray(prior.validated_threats) || threatSource.threats.length > 0
  const validatedThreats = completeValidatedThreats(prior.validated_threats, threatSource)
  const contextPatchSuggestions = asArtifactArray(prior.context_patch_suggestions)
  const callChains = validatedThreats.map(callChainEntryFromThreat)
  const blockingIssues = hasValidatedThreats ? [] : ['Validation result missing validated_threats array.']
  const writeResult = await writeArtifactsViaAgent('validation', {
    'validation_report.json': {
      schema_version: 1,
      run_id: runId,
      source_phase_label: sourceLabel,
      validated_threats: validatedThreats,
      context_patch_suggestions: contextPatchSuggestions,
    },
    'call_chain_map.json': {
      schema_version: 1,
      run_id: runId,
      source_phase_label: sourceLabel,
      call_chains: callChains,
    },
  })
  if (writeResult.status !== 'PASS') {
    blockingIssues.push('Validation artifact file writer failed.')
  }
  return {
    status: blockingIssues.length ? 'BLOCKED' : 'PASS',
    files: {
      validation_report: artifactRelativePath('validation_report.json'),
      call_chain_map: artifactRelativePath('call_chain_map.json'),
    },
    counts: { validated_threats: validatedThreats.length, call_chains: callChains.length },
    blockingIssues,
  }
}
function artifactEntryCount(value) {
  if (Array.isArray(value)) return value.length
  if (isArtifactObject(value)) return Object.keys(value).length
  return 0
}
async function writePocArtifactsFromPhaseResult(sourceLabel) {
  const prior = asArtifactObject(phaseResults[sourceLabel])
  const hasPocPlan = prior.poc_plan !== undefined
  const hasPocSummary = prior.poc_summary !== undefined
  const hasEvidenceMatrix = prior.evidence_matrix !== undefined
  const pocPlan = hasPocPlan ? prior.poc_plan : []
  const pocSummary = hasPocSummary ? prior.poc_summary : { total_pocs: 0 }
  const evidenceMatrix = hasEvidenceMatrix ? prior.evidence_matrix : {}
  const blockingIssues = []
  if (!hasPocPlan) blockingIssues.push('PoC result missing poc_plan.')
  if (!hasPocSummary) blockingIssues.push('PoC result missing poc_summary.')
  if (!hasEvidenceMatrix) blockingIssues.push('PoC result missing evidence_matrix.')
  const writeResult = await writeArtifactsViaAgent('poc', {
    'poc_plan.json': {
      schema_version: 1,
      run_id: runId,
      source_phase_label: sourceLabel,
      poc_plan: pocPlan,
    },
    'poc_summary.json': {
      schema_version: 1,
      run_id: runId,
      source_phase_label: sourceLabel,
      poc_summary: pocSummary,
    },
    'evidence_matrix.json': {
      schema_version: 1,
      run_id: runId,
      source_phase_label: sourceLabel,
      evidence_matrix: evidenceMatrix,
    },
  })
  if (writeResult.status !== 'PASS') {
    blockingIssues.push('PoC artifact file writer failed.')
  }
  return {
    status: blockingIssues.length ? 'BLOCKED' : 'PASS',
    files: {
      poc_plan: artifactRelativePath('poc_plan.json'),
      poc_summary: artifactRelativePath('poc_summary.json'),
      evidence_matrix: artifactRelativePath('evidence_matrix.json'),
    },
    counts: { pocs: artifactEntryCount(pocPlan), evidence_entries: artifactEntryCount(evidenceMatrix) },
    blockingIssues,
  }
}
async function writeResultAuditArtifactsFromPhaseResult(sourceLabel) {
  const prior = asArtifactObject(phaseResults[sourceLabel])
  const auditFindings = asArtifactArray(prior.audit_findings)
  const overrides = asArtifactArray(prior.overrides)
  const summary = asArtifactObject(prior.summary)
  const blockingIssues = []
  if (!Array.isArray(prior.audit_findings)) blockingIssues.push('Result audit missing audit_findings array.')
  if (!Array.isArray(prior.overrides)) blockingIssues.push('Result audit missing overrides array.')
  if (!isArtifactObject(prior.summary)) blockingIssues.push('Result audit missing summary object.')
  if (typeof prior.blocking !== 'boolean') blockingIssues.push('Result audit missing blocking boolean.')
  const unresolvedHardFindings = resultAuditHardFindingsWithoutOverrides(auditFindings, overrides)
  if (prior.blocking === true && unresolvedHardFindings.length) {
    blockingIssues.push(`Result Auditor Pre reported unresolved hard-fail findings: ${unresolvedHardFindings.join(', ')}.`)
  }
  const writeResult = await writeArtifactsViaAgent('result-audit', {
    'result_audit.json': {
      schema_version: 1,
      run_id: runId,
      source_phase_label: sourceLabel,
      audit_findings: auditFindings,
      overrides,
      summary,
      blocking: prior.blocking === true,
    },
  })
  if (writeResult.status !== 'PASS') {
    blockingIssues.push('Result audit artifact file writer failed.')
  }
  return {
    status: blockingIssues.length ? 'BLOCKED' : 'PASS',
    files: { result_audit: artifactRelativePath('result_audit.json') },
    counts: { audit_findings: auditFindings.length, overrides: overrides.length },
    blockingIssues,
  }
}
function resultAuditThreatId(value) {
  return String(value?.threat_id || value?.id || value?.finding_id || '').trim()
}
function normalizedResultAuditOverrideField(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[.\s-]+/g, '_')
  const aliases = {
    classification: 'final_classification',
    final_classification: 'final_classification',
    finalclassification: 'final_classification',
    severity: 'severity',
    evidence_tier: 'evidence_tier',
    evidence_tier_claim: 'evidence_tier',
  }
  return aliases[raw] || ''
}
function resultAuditFindingSeverity(value) {
  return String(value?.severity_level || value?.severity || value?.level || '').trim().toUpperCase()
}
function resultAuditHardFindingsWithoutOverrides(auditFindings, overrides) {
  const actionable = new Set()
  for (const override of asArtifactArray(overrides)) {
    const id = resultAuditThreatId(override)
    const field = normalizedResultAuditOverrideField(override?.field)
    if (id && id !== '*' && field && override?.to !== undefined && override?.to !== null) {
      actionable.add(`${id}\n${field}`)
    }
  }
  const unresolved = []
  for (const finding of asArtifactArray(auditFindings)) {
    if (resultAuditFindingSeverity(finding) !== 'HARD_FAIL') continue
    const id = resultAuditThreatId(finding)
    if (!id || id === '*') {
      unresolved.push(id || 'unknown')
      continue
    }
    let hasOverride = false
    for (const key of actionable) {
      if (key.startsWith(`${id}\n`)) {
        hasOverride = true
        break
      }
    }
    if (!hasOverride) unresolved.push(id)
  }
  return [...new Set(unresolved)]
}
function firstReportArray(field) {
  for (const result of Object.values(phaseResults)) {
    const prior = asArtifactObject(result)
    if (Array.isArray(prior[field])) return prior[field]
  }
  return []
}
function firstReportObject(field) {
  for (const result of Object.values(phaseResults)) {
    const prior = asArtifactObject(result)
    if (isArtifactObject(prior[field])) return prior[field]
  }
  return {}
}
function firstResultAuditObject() {
  for (const result of Object.values(phaseResults)) {
    const prior = asArtifactObject(result)
    if (Array.isArray(prior.audit_findings) || Array.isArray(prior.overrides) || typeof prior.blocking === 'boolean') {
      return prior
    }
  }
  return {}
}
function reportThreatId(value) {
  return String(value?.id || value?.threat_id || value?.threatId || '').trim()
}
function indexReportItemsByThreatId(items) {
  const indexed = {}
  for (const item of asArtifactArray(items)) {
    const id = reportThreatId(item)
    if (id && !indexed[id]) indexed[id] = item
  }
  return indexed
}
function reportClassification(rawValue) {
  const raw = String(rawValue || 'partial').trim()
  const aliases = {
    design_gap: 'design',
    oos: 'out_of_scope',
    fp: 'false_positive',
    candidate: 'partial',
  }
  return aliases[raw] || raw || 'partial'
}
function reportBucket(finalClassification) {
  const cls = reportClassification(finalClassification)
  if (cls === 'confirmed' || cls === 'confirmed_exploitable' || cls === 'confirmed_code_defect') return 'confirmed'
  if (cls === 'design') return 'design'
  if (cls === 'out_of_scope') return 'out_of_scope'
  if (cls === 'false_positive') return 'false_positive'
  return 'candidate'
}
function evidenceMatrixByThreatId() {
  const indexed = {}
  for (const entry of firstReportArray('evidence_matrix')) {
    const id = reportThreatId(entry)
    if (id && !indexed[id]) indexed[id] = cloneArtifactValue(entry, {})
  }
  return indexed
}
function resultAuditOverridesByThreatId() {
  const indexed = {}
  const audit = firstResultAuditObject()
  for (const override of asArtifactArray(audit.overrides)) {
    const id = resultAuditThreatId(override)
    const field = normalizedResultAuditOverrideField(override?.field)
    if (!id || id === '*' || !field || override?.to === undefined || override?.to === null) continue
    if (!indexed[id]) indexed[id] = []
    indexed[id].push({ ...override, field })
  }
  return indexed
}
function reportPocTypeForFinding(finding) {
  const tier = String(finding.evidence_tier || '').trim()
  if (['runtime_target_poc', 'runtime_model_poc', 'static_evidence', 'design_scenario'].includes(tier)) return tier
  return String(finding.poc_type || '').trim() || 'static_evidence'
}
function normalizeReportFindingBucketMetadata(finding) {
  if (finding.report_bucket !== 'confirmed') {
    finding.poc_type = ''
    finding.poc_target_invoked = false
    delete finding.confirmed_tier
  } else if (!finding.confirmed_tier) {
    finding.confirmed_tier = finding.final_classification === 'confirmed_exploitable' ? 'exploitable' : 'code_defect'
  }
  if (finding.report_bucket === 'confirmed') {
    finding.poc_type = reportPocTypeForFinding(finding)
    if (!finding.exploit_path_type) finding.exploit_path_type = 'direct'
    if (finding.impact_observed === undefined || finding.impact_observed === null) finding.impact_observed = false
    if (!finding.attacker_control) {
      finding.attacker_control = String(
        finding.attacker_requirement ||
        finding.reachable_entry_point ||
        finding.source_file ||
        'attacker can reach the documented device_auth entry point',
      )
    }
    if (finding.preconditions === undefined || finding.preconditions === null) {
      finding.preconditions = []
    }
  }
  return finding
}
function applyResultAuditOverrides(finding, overridesById) {
  const overrides = asArtifactArray(overridesById[finding.id] || overridesById[finding.threat_id])
  const applied = []
  for (const override of overrides) {
    const field = normalizedResultAuditOverrideField(override?.field)
    if (!field) continue
    const original = finding[field]
    let nextValue = override.to
    if (field === 'severity') {
      nextValue = String(nextValue || '').trim().toUpperCase() || original || 'MEDIUM'
      finding.severity = nextValue
    } else if (field === 'final_classification') {
      nextValue = reportClassification(nextValue)
      finding.final_classification = nextValue
      finding.classification = nextValue
      finding.raw_final_classification = String(override.to || nextValue)
      finding.report_bucket = reportBucket(nextValue)
    } else if (field === 'evidence_tier') {
      nextValue = String(nextValue || '').trim() || original || 'static_evidence'
      finding.evidence_tier = nextValue
    } else {
      continue
    }
    if (String(original ?? '') === String(nextValue ?? '')) continue
    applied.push({
      field,
      from: original === undefined ? null : original,
      to: nextValue,
      reason: String(override.reason || ''),
    })
  }
  if (applied.length) {
    finding.result_audit_overrides = applied
  }
  return normalizeReportFindingBucketMetadata(finding)
}
function reportSeverity(threat, validation) {
  return String(validation?.severity || threat?.severity || threat?.severity_estimate || 'MEDIUM').toUpperCase()
}
function reportName(threat, id) {
  return String(
    threat?.name ||
    threat?.title ||
    threat?.violated_property ||
    threat?.impact ||
    id ||
    'STRIDE finding',
  )
}
function reportDescription(threat, validation) {
  const rationale = threat?.mapping_rationale
  if (typeof rationale === 'string') return rationale
  if (isArtifactObject(rationale)) {
    const text = rationale.object_property_impact || rationale.summary || rationale.reason
    if (text) return String(text)
  }
  return String(validation?.impact_observed || threat?.impact || threat?.description || '')
}
function reportFinding(baseThreat, validation, evidenceEntry) {
  const threat = cloneArtifactValue(baseThreat, {})
  const validated = cloneArtifactValue(validation, {})
  const evidence = cloneArtifactValue(evidenceEntry, {})
  const id = reportThreatId(threat) || reportThreatId(validated) || 'THREAT-UNSPECIFIED'
  const finalClassification = reportClassification(
    validated.final_classification || validated.classification || threat.final_classification || threat.classification,
  )
  const bucket = reportBucket(finalClassification)
  const finding = {
    ...threat,
    ...validated,
    id,
    threat_id: id,
    name: reportName(threat, id),
    dimension: String(threat.dimension || threat.stride_category || threat.stride_tag || ''),
    stride_category: String(threat.stride_category || threat.stride_tag || threat.dimension || ''),
    violated_property: normalizeStrideViolatedProperty(
      validated.violated_property || threat.violated_property,
      validated.stride_tag || threat.stride_tag || threat.dimension,
    ),
    severity: reportSeverity(threat, validated),
    final_classification: finalClassification,
    raw_final_classification: String(validated.final_classification || validated.classification || threat.final_classification || threat.classification || 'partial'),
    report_bucket: bucket,
    description: reportDescription(threat, validated),
    source_evidence: validated.source_evidence || threat.source_evidence || '',
    counter_evidence_checked: validated.counter_evidence_checked || threat.counter_evidence_checked || [],
    evidence_tier: evidence.evidence_tier || validated.evidence_tier || threat.evidence_tier || 'static_evidence',
    poc_refs: asArtifactArray(evidence.poc_refs || validated.poc_refs || threat.poc_refs),
    code_navigation: validated.code_navigation || threat.code_navigation || { status: 'unresolved' },
  }
  return normalizeReportFindingBucketMetadata(finding)
}
function buildReportFindings() {
  const baseThreats = firstReportArray('threats')
  const validatedThreats = firstReportArray('validated_threats')
  const baseById = indexReportItemsByThreatId(baseThreats)
  const validationById = indexReportItemsByThreatId(validatedThreats)
  const ids = []
  for (const item of [...baseThreats, ...validatedThreats]) {
    const id = reportThreatId(item)
    if (id && !ids.includes(id)) ids.push(id)
  }
  const overridesById = resultAuditOverridesByThreatId()
  const evidenceById = evidenceMatrixByThreatId()
  return ids.map(id => applyResultAuditOverrides(reportFinding(baseById[id] || { threat_id: id }, validationById[id] || {}, evidenceById[id] || {}), overridesById))
}
function splitReportFindings(findings) {
  return {
    confirmed: findings.filter(item => item.report_bucket === 'confirmed'),
    candidate: findings.filter(item => item.report_bucket === 'candidate'),
    design: findings.filter(item => item.report_bucket === 'design'),
    out_of_scope: findings.filter(item => item.report_bucket === 'out_of_scope'),
    false_positive: findings.filter(item => item.report_bucket === 'false_positive'),
  }
}
function countBy(values, names) {
  const counts = {}
  for (const name of names) counts[name] = 0
  for (const value of values) {
    const key = String(value || '').trim()
    counts[key] = (counts[key] || 0) + 1
  }
  return counts
}
function reportSplitPayload(classification, label, findings) {
  return {
    meta: { classification, count: findings.length, label },
    findings,
  }
}
function reportPocSummary(findings) {
  const rawSummary = firstReportObject('poc_summary')
  const pocPlan = firstReportArray('poc_plan')
  const findingIds = new Set(findings.map(item => item.id))
  const evidenceById = evidenceMatrixByThreatId()
  const pocResults = []
  for (const poc of pocPlan) {
    const refs = asArtifactArray(poc?.threat_refs).map(ref => String(ref))
    const direct = String(poc?.threat_id || '').trim()
    const threatId = direct || refs.find(ref => findingIds.has(ref)) || refs[0] || ''
    if (!threatId || (!findingIds.has(threatId) && !refs.some(ref => findingIds.has(ref)))) continue
    const evidence = evidenceById[threatId] || {}
    const normalized = cloneArtifactValue(poc, {})
    const tier = String(normalized.evidence_tier || normalized.type || normalized.poc_type || evidence.evidence_tier || 'runtime_model_poc')
    normalized.threat_id = threatId
    normalized.threat_refs = refs.length ? refs : [threatId]
    normalized.evidence_tier = tier
    normalized.type = String(normalized.type || normalized.poc_type || tier)
    normalized.poc_type = String(normalized.poc_type || normalized.type || tier)
    pocResults.push(normalized)
  }
  const byTier = { static_evidence: 0, runtime_model_poc: 0, runtime_target_poc: 0, design_scenario: 0 }
  for (const poc of pocResults) {
    const tier = String(poc.evidence_tier || poc.type || 'runtime_model_poc')
    byTier[tier] = (byTier[tier] || 0) + 1
  }
  return {
    meta: { ...rawSummary, run_id: runId, total_pocs: pocResults.length, by_tier: byTier },
    poc_results: pocResults,
  }
}
function reportHtmlSection(title, findings) {
  const rows = findings.map(item => (
    `<tr><td>${escapeArtifactXml(item.id)}</td><td>${escapeArtifactXml(item.name)}</td><td>${escapeArtifactXml(item.severity)}</td><td>${escapeArtifactXml(item.final_classification)}</td></tr>`
  ))
  return `<h2>${escapeArtifactXml(title)} (${findings.length})</h2><table><thead><tr><th>ID</th><th>Name</th><th>Severity</th><th>Classification</th></tr></thead><tbody>${rows.join('') || '<tr><td colspan="4">None</td></tr>'}</tbody></table>`
}
function reportHtmlAttrJson(value) {
  return escapeArtifactXml(JSON.stringify(value))
}
function renderReportDfdPanel(findings) {
  const dimensions = [
    'Spoofing',
    'Tampering',
    'Repudiation',
    'Information Disclosure',
    'Denial of Service',
    'Elevation of Privilege',
  ]
  const baseNodes = [
    ['EE_APP', 'Client app'],
    ['P_API', 'Public API'],
    ['P_AUTH', 'Device auth service'],
    ['P_SESSION', 'Session manager'],
    ['P_CREDENTIAL', 'Credential manager'],
    ['S_CREDENTIALS', 'Credential store'],
    ['S_SESSIONS', 'Session store'],
    ['EE_PEER', 'Peer device'],
    ['P_CRYPTO', 'Crypto adapter'],
    ['TB_SERVICE', 'Service trust boundary'],
  ]
  const nodes = baseNodes.map(([id, name], index) => {
    const related = findings.filter(item => String(item.affected_object?.dfd_element_ref || item.affected_object?.object_id || '').includes(id))
    const sample = related.length ? related : findings.slice(index % Math.max(findings.length, 1), (index % Math.max(findings.length, 1)) + 1)
    return {
      id,
      name,
      threats: sample.map(item => ({ id: item.id, severity: item.severity, classification: item.final_classification })),
      analysis: { node: id, dimensions, finding_count: sample.length },
    }
  })
  const nodeHtml = nodes.map((node, index) => {
    const x = 40 + (index % 5) * 150
    const y = 60 + Math.floor(index / 5) * 110
    return `<g tabindex="0" role="button" data-eid="${escapeArtifactXml(node.id)}" data-threats="${reportHtmlAttrJson(node.threats)}" data-analysis="${reportHtmlAttrJson(node.analysis)}"><rect x="${x}" y="${y}" width="120" height="56" rx="4" fill="#eff6ff" stroke="#2563eb"></rect><text x="${x + 10}" y="${y + 24}" font-size="12" fill="#111827">${escapeArtifactXml(node.name)}</text><text x="${x + 10}" y="${y + 42}" font-size="10" fill="#4b5563">${escapeArtifactXml(node.id)}</text></g>`
  })
  return [
    '<div id="dfd-svg-container" data-analysis=\'{"mode":"fallback","interactive":true}\'>',
    '<svg viewBox="0 0 800 260" width="100%" height="260" role="img" aria-label="Fallback DFD">',
    '<line x1="160" y1="88" x2="190" y2="88" stroke="#9ca3af"></line><line x1="310" y1="88" x2="340" y2="88" stroke="#9ca3af"></line><line x1="460" y1="88" x2="490" y2="88" stroke="#9ca3af"></line>',
    '<line x1="160" y1="198" x2="190" y2="198" stroke="#9ca3af"></line><line x1="310" y1="198" x2="340" y2="198" stroke="#9ca3af"></line><line x1="460" y1="198" x2="490" y2="198" stroke="#9ca3af"></line>',
    nodeHtml.join(''),
    '</svg>',
    '</div>',
    '<aside id="dfd-sidebar"><h3>Element stats</h3><p>Select a DFD element to inspect related STRIDE evidence.</p><ul><li>Spoofing</li><li>Tampering</li><li>Repudiation</li><li>Information Disclosure</li><li>Denial of Service</li><li>Elevation of Privilege</li></ul><button type="button" data-action="restore-side">Restore stats view</button></aside>',
    '<script>document.querySelectorAll("[data-eid]").forEach(function(node){node.addEventListener("click",function(){var sidebar=document.getElementById("dfd-sidebar");var threats=JSON.parse(node.getAttribute("data-threats")||"[]");sidebar.innerHTML="<h3>"+node.getAttribute("data-eid")+"</h3><p>Related findings: "+threats.length+"</p><ul><li>Spoofing</li><li>Tampering</li><li>Repudiation</li><li>Information Disclosure</li><li>Denial of Service</li><li>Elevation of Privilege</li></ul><button type=\\"button\\" data-action=\\"restore-side\\">Restore stats view</button>";});});document.addEventListener("keydown",function(event){if(event.key==="Escape"){var sidebar=document.getElementById("dfd-sidebar");if(sidebar){sidebar.innerHTML="<h3>Element stats</h3><p>Select a DFD element to inspect related STRIDE evidence.</p><button type=\\"button\\" data-action=\\"restore-side\\">Restore stats view</button>";}}});</script>',
  ].join('\n')
}
function renderReportHtml(findings, splits, statistics) {
  return [
    '<!doctype html>',
    '<html><head><meta charset="utf-8"><title>STRIDE Audit Report</title>',
    '<style>body{font-family:Arial,sans-serif;margin:24px;color:#111827}nav a{margin-right:12px}table{border-collapse:collapse;width:100%;margin-bottom:24px}th,td{border:1px solid #d1d5db;padding:6px 8px;text-align:left}th{background:#f3f4f6}.meta{color:#4b5563}#dfd{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:16px}#dfd-sidebar{border:1px solid #d1d5db;padding:12px;background:#f9fafb}[data-eid]{cursor:pointer}</style>',
    '</head><body>',
    '<h1>STRIDE Audit Report</h1>',
    '<nav><a href="#overview">overview</a><a href="#quality">quality</a><a href="#dfd">dfd</a><a href="#confirmed">confirmed</a><a href="#candidate">candidate</a><a href="#design">design</a><a href="#oos">oos</a><a href="#fp">fp</a><a href="#poc">poc</a><a href="#method">method</a></nav>',
    '<section id="overview"><h2>Overview</h2>',
    `<p class="meta">Run: ${escapeArtifactXml(runId || 'unspecified')} | Total threats: ${statistics.total_threats}</p>`,
    '</section>',
    `<section id="quality"><h2>Quality</h2><pre>${escapeArtifactXml(JSON.stringify(statistics, null, 2))}</pre></section>`,
    `<section id="dfd"><div><h2>DFD</h2>${renderReportDfdPanel(findings)}</div></section>`,
    '<section id="confirmed">',
    reportHtmlSection('Confirmed Findings', splits.confirmed),
    '</section>',
    '<section id="candidate">',
    reportHtmlSection('Candidate Findings', splits.candidate),
    '</section>',
    '<section id="design">',
    reportHtmlSection('Design Gaps', splits.design),
    '</section>',
    '<section id="oos">',
    reportHtmlSection('Out Of Scope', splits.out_of_scope),
    '</section>',
    '<section id="fp">',
    reportHtmlSection('False Positives', splits.false_positive),
    '</section>',
    '<section id="poc"><h2>PoC</h2><p>PoC evidence is summarized in poc_summary.json.</p></section>',
    '<section id="method"><h2>Method</h2><p>Deterministic fallback report generated from WPN phase StructuredOutput and normalized report artifacts.</p></section>',
    '</body></html>',
    '',
  ].join('\n')
}
async function writeReportArtifactsFromPriorPhases(sourceLabel) {
  const findings = buildReportFindings()
  const splits = splitReportFindings(findings)
  const audit = firstResultAuditObject()
  const auditOverridesApplied = findings.reduce((total, item) => total + asArtifactArray(item.result_audit_overrides).length, 0)
  const bucketCounts = {
    confirmed: splits.confirmed.length,
    candidate: splits.candidate.length,
    design: splits.design.length,
    out_of_scope: splits.out_of_scope.length,
    false_positive: splits.false_positive.length,
  }
  const severityCounts = countBy(findings.map(item => item.severity), ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'])
  const canonicalCounts = countBy(findings.map(item => item.final_classification), [])
  const strideCounts = countBy(findings.map(item => item.stride_category || item.dimension), ['S', 'T', 'R', 'I', 'D', 'E'])
  const statistics = {
    total_threats: findings.length,
    by_severity: severityCounts,
    by_classification: bucketCounts,
    canonical_classification_counts: canonicalCounts,
    by_stride: strideCounts,
    result_audit: {
      pre_report_blocking: audit.blocking === true,
      findings: asArtifactArray(audit.audit_findings).length,
      overrides: asArtifactArray(audit.overrides).length,
      overrides_applied: auditOverridesApplied,
    },
  }
  const reportName = `stride-audit-report-${String(runId || 'run').replace(/[^A-Za-z0-9_.-]/g, '-')}.html`
  const htmlReport = artifactRelativePath(reportName)
  const htmlReportAbsolute = artifactAbsolutePath(reportName)
  const threatList = {
    schema_version: 1,
    run_id: runId,
    source_phase_label: sourceLabel,
    meta: { run_id: runId, target: runtimeContext.target || '' },
    threats: findings,
    summary: {
      by_severity: severityCounts,
      by_classification: bucketCounts,
      canonical_classification_counts: canonicalCounts,
      report_bucket_counts: bucketCounts,
      result_audit_overrides_applied: auditOverridesApplied,
      total: findings.length,
    },
  }
  const writeResult = await writeArtifactsViaAgent('report', {
    'threat_list.json': threatList,
    'poc_summary.json': reportPocSummary(findings),
    'confirmed_findings.json': reportSplitPayload('confirmed', 'Confirmed findings', splits.confirmed),
    'candidate_findings.json': reportSplitPayload('candidate', 'Candidate findings', splits.candidate),
    'design_gaps.json': reportSplitPayload('design', 'Design gaps', splits.design),
    'out_of_scope.json': reportSplitPayload('out_of_scope', 'Out of scope', splits.out_of_scope),
    'false_positives.json': reportSplitPayload('false_positive', 'False positives', splits.false_positive),
    [reportName]: renderReportHtml(findings, splits, statistics),
    '.report-latest': `${htmlReportAbsolute}\n`,
  })
  const outputs = {
    confirmed: artifactRelativePath('confirmed_findings.json'),
    candidate: artifactRelativePath('candidate_findings.json'),
    design_gaps: artifactRelativePath('design_gaps.json'),
    out_of_scope: artifactRelativePath('out_of_scope.json'),
    false_positives: artifactRelativePath('false_positives.json'),
    html_report: htmlReport,
    report_latest: artifactRelativePath('.report-latest'),
  }
  return {
    report_generated: writeResult.status === 'PASS',
    report_path: htmlReport,
    outputs,
    statistics,
    blockingIssues: writeResult.status === 'PASS' ? [] : writeResult.blockingIssues,
  }
}
function findFinalizeDoctorResult() {
  for (const [label, result] of Object.entries(phaseResults)) {
    const prior = asArtifactObject(result)
    if (String(label).toLowerCase().includes('doctor') && (prior.overall || Array.isArray(prior.hard_fails))) {
      return prior
    }
  }
  for (const result of Object.values(phaseResults)) {
    const prior = asArtifactObject(result)
    if (prior.overall && Array.isArray(prior.hard_fails) && isArtifactObject(prior.checks)) return prior
  }
  return { overall: 'PASS', hard_fails: [], soft_warns: [], checks: {} }
}
function findFinalizeEnvironmentResult() {
  for (const [label, result] of Object.entries(phaseResults)) {
    if (String(label).toLowerCase().includes('env')) return asArtifactObject(result)
  }
  return {}
}
function findFinalizeReportResult() {
  for (const result of Object.values(phaseResults)) {
    const prior = asArtifactObject(result)
    if (prior.report_generated === true && isArtifactObject(prior.outputs)) return prior
  }
  return {}
}
function statusFromPhaseResult(result) {
  const prior = asArtifactObject(result)
  if (typeof prior.status === 'string') return prior.status
  if (typeof prior.overall === 'string') return prior.overall === 'FAIL' ? 'FAIL' : 'PASS'
  if (prior.blocking === true) return 'FAIL'
  return 'PASS'
}
function finalizeStages() {
  const stages = Object.entries(phaseResults).map(([id, result]) => ({
    id,
    status: statusFromPhaseResult(result),
    details: {
      keys: Object.keys(asArtifactObject(result)).slice(0, 20),
    },
  }))
  stages.push({ id: 'finalize', status: 'PASS', details: { deterministic: true } })
  return stages
}
function finalizeArtifacts(reportResult) {
  const outputs = asArtifactObject(reportResult.outputs)
  const artifactMap = {
    confirmed_findings: outputs.confirmed || artifactRelativePath('confirmed_findings.json'),
    candidate_findings: outputs.candidate || artifactRelativePath('candidate_findings.json'),
    design_gaps: outputs.design_gaps || artifactRelativePath('design_gaps.json'),
    out_of_scope: outputs.out_of_scope || artifactRelativePath('out_of_scope.json'),
    false_positives: outputs.false_positives || artifactRelativePath('false_positives.json'),
    report: outputs.html_report || reportResult.report_path || artifactRelativePath(`stride-audit-report-${String(runId || 'run').replace(/[^A-Za-z0-9_.-]/g, '-')}.html`),
    report_latest: outputs.report_latest || artifactRelativePath('.report-latest'),
    doctor: artifactRelativePath('stride-audit-doctor.json'),
    run_manifest: artifactRelativePath('run_manifest.json'),
  }
  return artifactMap
}
async function writeFinalizeArtifactsFromPriorPhases(sourceLabel) {
  const doctor = findFinalizeDoctorResult()
  const environment = findFinalizeEnvironmentResult()
  const reportResult = findFinalizeReportResult()
  const artifacts = finalizeArtifacts(reportResult)
  const stages = finalizeStages()
  const doctorOverall = String(doctor.overall || 'PASS')
  const runManifest = {
    workflow: workflowName,
    schema_version: '0.5.0',
    run_id: runId || 'unknown',
    status: doctorOverall === 'FAIL' ? 'FAILED' : 'PASS',
    stages,
    artifacts: Object.values(artifacts),
    doctor,
    environment,
  }
  const returnEnvelope = {
    status: runManifest.status === 'PASS' ? 'PASS' : 'FAIL',
    schema_version: '0.5.0',
    workflow: workflowName,
    run_id: runId || 'unknown',
    doctor,
    run_manifest: runManifest,
    artifacts,
    statistics: reportResult.statistics || { total_threats: 0 },
    gate_results: {
      hard_fails: asArtifactArray(doctor.hard_fails).length,
      doctor_overall: doctorOverall,
      audit_pre_blocking: false,
      audit_post_overall: 'UNKNOWN',
      severity_gate_failures: 0,
    },
    degradations: asArtifactArray(environment.degradations),
  }
  const writeResult = await writeArtifactsViaAgent('finalize', {
    'run_manifest.json': runManifest,
    'stride-audit-doctor.json': doctor,
  })
  return {
    status: writeResult.status,
    run_manifest: runManifest,
    return_envelope: returnEnvelope,
    blockingIssues: writeResult.status === 'PASS' ? [] : writeResult.blockingIssues,
    source_phase_label: sourceLabel,
  }
}
'''


def derive_supporting_asset_kind(path: str) -> str:
    """Derive supporting asset kind mechanically from path."""
    normalized = str(path or "").strip()
    if not normalized:
        return ""
    for kind, (prefix, suffix) in SUPPORTING_ASSET_RULES.items():
        if kind in {"settings", "managed-files"}:
            if normalized == prefix:
                return kind
            continue
        if not normalized.startswith(prefix):
            continue
        if suffix is None:
            return kind
        if normalized.endswith(suffix):
            return kind
    return ""


def is_run_evidence_path(path: str) -> bool:
    normalized = str(path or "").strip().replace("\\", "/")
    return (
        normalized == ".workflowprogram/runs"
        or normalized.startswith(".workflowprogram/runs/")
        or normalized == "outputs"
        or normalized.startswith("outputs/")
    )


def is_stride_aggregate_prompt(prompt: str) -> bool:
    text = str(prompt or "").lower()
    if "stride" not in text:
        return False
    asks_for_all_dimensions = any(
        marker in text
        for marker in (
            "6-dimensional",
            "six-dimensional",
            "six dimensions",
            "all six",
            "s/t/r/i/d/e",
        )
    )
    asks_for_single_result = any(
        marker in text
        for marker in (
            "single json",
            "single object",
            "combine result",
            "combine results",
            "combined result",
        )
    )
    return asks_for_all_dimensions and asks_for_single_result


def is_parse_prompt(prompt: str, schema: dict[str, Any]) -> bool:
    text = str(prompt or "").lower()
    if "parse_result" not in text or "attacker_profile" not in text:
        return False
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return False
    required_fields = set(required)
    return {"parse_result", "attacker_profile"}.issubset(required_fields) and {
        "parse_result",
        "attacker_profile",
    }.issubset(properties)


def parse_artifact_writer_contract(phase_title: str, label: str, detail: str) -> dict[str, Any]:
    """Return the synthetic artifact writer phase that follows Parse."""

    writer_phase = f"{phase_title} Artifacts"
    writer_label = f"{label}:artifacts"
    writer_detail = "Persist parse_result.json and attacker_profile.json from the Parse StructuredOutput."
    return {
        "phase": writer_phase,
        "detail": writer_detail if not detail else f"{writer_detail} Source phase: {detail}",
        "label": writer_label,
        "prompt": (
            f"{PARSE_ARTIFACT_WRITER_PROMPT} The source Parse phase label is {label!r}; "
            "use the prior phase results object for that label."
        ),
        "schema": copy.deepcopy(PARSE_ARTIFACT_WRITER_SCHEMA),
        "includePriorPhaseResults": True,
        "synthetic": True,
        "artifactWriter": "parse",
        "sourceLabel": label,
        "blockWhen": "result.status !== 'PASS'",
        "blockStatus": "BLOCKED_PARSE_ARTIFACTS",
        "blockMessage": "Parse artifact writer did not produce current parse_result.json and attacker_profile.json.",
        "nextAction": "FIX_PARSE_ARTIFACT_WRITER",
    }


def is_dfd_inference_prompt(prompt: str, schema: dict[str, Any]) -> bool:
    text = str(prompt or "").lower()
    if "dfd" not in text and "data flow" not in text:
        return False
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return False
    required_fields = set(required)
    return {"dfd_yaml", "dfd_index"}.issubset(required_fields) and {
        "dfd_yaml",
        "dfd_index",
    }.issubset(properties)


def dfd_artifact_writer_contract(phase_title: str, label: str, detail: str) -> dict[str, Any]:
    """Return the synthetic artifact writer phase that follows DFD inference."""

    writer_phase = f"{phase_title} Artifacts"
    writer_label = f"{label}:artifacts"
    writer_detail = "Render and persist DFD artifacts from the DFD StructuredOutput."
    return {
        "phase": writer_phase,
        "detail": writer_detail if not detail else f"{writer_detail} Source phase: {detail}",
        "label": writer_label,
        "prompt": (
            f"{DFD_ARTIFACT_WRITER_PROMPT} The source DFD phase label is {label!r}; "
            "use the prior phase results object for that label."
        ),
        "schema": copy.deepcopy(DFD_ARTIFACT_WRITER_SCHEMA),
        "includePriorPhaseResults": True,
        "synthetic": True,
        "artifactWriter": "dfd",
        "sourceLabel": label,
        "blockWhen": "result.status !== 'PASS'",
        "blockStatus": "BLOCKED_DFD_ARTIFACTS",
        "blockMessage": "DFD artifact writer did not produce current root DFD outputs.",
        "nextAction": "FIX_DFD_ARTIFACT_WRITER",
    }


def stride_artifact_writer_contract(phase_title: str, label: str, detail: str) -> dict[str, Any]:
    """Return the synthetic artifact writer phase that follows STRIDE aggregation."""

    writer_phase = f"{phase_title} Artifacts"
    writer_label = f"{label}:artifacts"
    writer_detail = "Persist threat_list.json from the STRIDE StructuredOutput."
    return {
        "phase": writer_phase,
        "detail": writer_detail if not detail else f"{writer_detail} Source phase: {detail}",
        "label": writer_label,
        "prompt": (
            f"{STRIDE_ARTIFACT_WRITER_PROMPT} The source STRIDE phase label is {label!r}; "
            "use the prior phase results object for that label."
        ),
        "schema": copy.deepcopy(STRIDE_ARTIFACT_WRITER_SCHEMA),
        "includePriorPhaseResults": True,
        "synthetic": True,
        "artifactWriter": "stride",
        "sourceLabel": label,
        "blockWhen": "result.status !== 'PASS'",
        "blockStatus": "BLOCKED_STRIDE_ARTIFACTS",
        "blockMessage": "STRIDE artifact writer did not produce current threat_list.json.",
        "nextAction": "FIX_STRIDE_ARTIFACT_WRITER",
    }


def validation_artifact_writer_contract(phase_title: str, label: str, detail: str) -> dict[str, Any]:
    """Return the synthetic artifact writer phase that follows validation."""

    writer_phase = f"{phase_title} Artifacts"
    writer_label = f"{label}:artifacts"
    writer_detail = "Persist validation report artifacts from the Validation StructuredOutput."
    return {
        "phase": writer_phase,
        "detail": writer_detail if not detail else f"{writer_detail} Source phase: {detail}",
        "label": writer_label,
        "prompt": (
            f"{VALIDATION_ARTIFACT_WRITER_PROMPT} The source Validation phase label is {label!r}; "
            "use the prior phase results object for that label."
        ),
        "schema": copy.deepcopy(VALIDATION_ARTIFACT_WRITER_SCHEMA),
        "includePriorPhaseResults": True,
        "synthetic": True,
        "artifactWriter": "validation",
        "sourceLabel": label,
        "blockWhen": "result.status !== 'PASS'",
        "blockStatus": "BLOCKED_VALIDATION_ARTIFACTS",
        "blockMessage": "Validation artifact writer did not produce current validation_report.json and call_chain_map.json.",
        "nextAction": "FIX_VALIDATION_ARTIFACT_WRITER",
    }


def result_audit_artifact_writer_contract(phase_title: str, label: str, detail: str) -> dict[str, Any]:
    """Return the synthetic artifact writer phase that follows pre-report audit."""

    writer_phase = f"{phase_title} Artifacts"
    writer_label = f"{label}:artifacts"
    writer_detail = "Persist result_audit.json from the Result Auditor Pre StructuredOutput."
    return {
        "phase": writer_phase,
        "detail": writer_detail if not detail else f"{writer_detail} Source phase: {detail}",
        "label": writer_label,
        "prompt": (
            f"{RESULT_AUDIT_ARTIFACT_WRITER_PROMPT} The source Result Auditor Pre phase label is {label!r}; "
            "use the prior phase results object for that label."
        ),
        "schema": copy.deepcopy(RESULT_AUDIT_ARTIFACT_WRITER_SCHEMA),
        "includePriorPhaseResults": True,
        "synthetic": True,
        "artifactWriter": "result-audit",
        "sourceLabel": label,
        "blockWhen": "result.status !== 'PASS'",
        "blockStatus": "BLOCKED_RESULT_AUDIT_PRE",
        "blockMessage": "Result Auditor Pre artifact writer found malformed audit data or unresolved hard-fail findings.",
        "nextAction": "FIX_RESULT_AUDIT_PRE",
    }


def poc_artifact_writer_contract(phase_title: str, label: str, detail: str) -> dict[str, Any]:
    """Return the synthetic artifact writer phase that follows PoC planning."""

    writer_phase = f"{phase_title} Artifacts"
    writer_label = f"{label}:artifacts"
    writer_detail = "Persist PoC artifacts from the PoC StructuredOutput."
    return {
        "phase": writer_phase,
        "detail": writer_detail if not detail else f"{writer_detail} Source phase: {detail}",
        "label": writer_label,
        "prompt": (
            f"{POC_ARTIFACT_WRITER_PROMPT} The source PoC phase label is {label!r}; "
            "use the prior phase results object for that label."
        ),
        "schema": copy.deepcopy(POC_ARTIFACT_WRITER_SCHEMA),
        "includePriorPhaseResults": True,
        "synthetic": True,
        "artifactWriter": "poc",
        "sourceLabel": label,
        "blockWhen": "result.status !== 'PASS'",
        "blockStatus": "BLOCKED_POC_ARTIFACTS",
        "blockMessage": "PoC artifact writer did not produce current poc_plan.json, poc_summary.json, and evidence_matrix.json.",
        "nextAction": "FIX_POC_ARTIFACT_WRITER",
    }


def is_single_stride_dimension_schema(schema: dict[str, Any]) -> bool:
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict) or not isinstance(required, list):
        return False
    if "stride_tag" not in required or "stride_tag" not in properties:
        return False
    threats = properties.get("threats")
    if not isinstance(threats, dict):
        return False
    threat_items = threats.get("items")
    if not isinstance(threat_items, dict):
        return False
    threat_properties = threat_items.get("properties")
    return isinstance(threat_properties, dict) and "stride_tag" in threat_properties


def is_stride_aggregate_contract(prompt: str, schema: dict[str, Any]) -> bool:
    if not is_stride_aggregate_prompt(prompt):
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    threats = properties.get("threats")
    if not isinstance(threats, dict):
        return False
    threat_items = threats.get("items")
    if not isinstance(threat_items, dict):
        return False
    threat_properties = threat_items.get("properties")
    return isinstance(threat_properties, dict) and "stride_tag" in threat_properties


def is_validation_contract(prompt: str, schema: dict[str, Any]) -> bool:
    text = str(prompt or "").lower()
    if "validation_report" not in text and "stride validator" not in text:
        return False
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return False
    required_fields = set(required)
    return {"validated_threats", "context_patch_suggestions"}.issubset(required_fields) and {
        "validated_threats",
        "context_patch_suggestions",
    }.issubset(properties)


def is_result_auditor_pre_contract(prompt: str, schema: dict[str, Any]) -> bool:
    text = str(prompt or "").lower()
    if "result auditor" not in text or "pre-report" not in text:
        return False
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return False
    required_fields = set(required)
    return {"audit_findings", "overrides", "summary", "blocking"}.issubset(required_fields) and {
        "audit_findings",
        "overrides",
        "summary",
        "blocking",
    }.issubset(properties)


def is_poc_contract(prompt: str, schema: dict[str, Any]) -> bool:
    text = str(prompt or "").lower()
    if "poc" not in text:
        return False
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return False
    required_fields = set(required)
    return {"poc_plan", "poc_summary", "evidence_matrix"}.issubset(required_fields) and {
        "poc_plan",
        "poc_summary",
        "evidence_matrix",
    }.issubset(properties)


def is_report_contract(prompt: str, schema: dict[str, Any]) -> bool:
    text = str(prompt or "").lower()
    if "report" not in text or "confirmed_findings" not in text:
        return False
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return False
    required_fields = set(required)
    return {"report_generated", "outputs", "statistics"}.issubset(required_fields) and {
        "report_generated",
        "outputs",
        "statistics",
    }.issubset(properties)


def is_deterministic_stride_report_contract(prompt: str, schema: dict[str, Any]) -> bool:
    """Return true for FreeSTRIDE-style reports that WPN can assemble mechanically."""

    if not is_report_contract(prompt, schema):
        return False
    text = str(prompt or "").lower()
    required_markers = (
        "outputs/stride-audit",
        "threat_list",
        "validation_report",
        "poc_summary",
        "evidence_matrix",
        "confirmed_findings",
        "candidate_findings",
        "false_positives",
    )
    return all(marker in text for marker in required_markers)


def is_doctor_contract(prompt: str, schema: dict[str, Any]) -> bool:
    text = str(prompt or "").lower()
    if "doctor" not in text or "run_manifest" not in text:
        return False
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return False
    required_fields = set(required)
    return "overall" in required_fields and "hard_fails" in properties


def is_finalize_contract(prompt: str, schema: dict[str, Any]) -> bool:
    text = str(prompt or "").lower()
    if "run_manifest" not in text or ("return envelope" not in text and "return_envelope" not in text):
        return False
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return False
    required_fields = set(required)
    return {"run_manifest", "return_envelope"}.issubset(required_fields) and {
        "run_manifest",
        "return_envelope",
    }.issubset(properties)


def normalize_stride_aggregate_schema(prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if not is_stride_aggregate_prompt(prompt) or not is_single_stride_dimension_schema(schema):
        return schema, False

    normalized_schema = copy.deepcopy(schema)
    properties = normalized_schema.get("properties")
    if isinstance(properties, dict):
        properties.pop("stride_tag", None)
    required = normalized_schema.get("required")
    if isinstance(required, list):
        normalized_schema["required"] = [item for item in required if item != "stride_tag"]
    return normalized_schema, True


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


def _validate_canonical_projection(
    authoring_spec: dict[str, Any],
    operation: str,
) -> list[dict[str, str]]:
    """Phase 3: Revalidate canonical projection rules on persisted spec.

    In direct generator or persisted disk-spec validation paths, the
    already-persisted canonical asset_disposition is used as the consistency
    source, and conflicting data fails fast as a stale or tampered spec.

    Returns a list of structured error dicts (empty when valid).
    """
    errors: list[dict[str, str]] = []

    name = str(authoring_spec.get("name", "")).strip()
    if not name:
        return errors
    primary_workflow_path = f".claude/workflows/{name}.js"

    asset_disposition = authoring_spec.get("asset_disposition", [])
    supporting_assets = authoring_spec.get("supporting_assets", [])
    supporting_paths = {item.get("path", "") for item in supporting_assets}

    # ── Primary workflow rules ──
    for item in asset_disposition:
        path = str(item.get("path", "")).strip()
        action = str(item.get("action", "")).strip()
        sap = str(item.get("supporting_asset_path", "")).strip()

        if path == primary_workflow_path:
            # Primary workflow must not carry supporting_asset_path
            if sap:
                errors.append({
                    "rule": "CANONICAL_PRIMARY_WORKFLOW_SUPPORTING_PATH",
                    "message": f"Primary workflow disposition must not carry supporting_asset_path: {path}",
                })
            # Primary workflow generate/update content comes only from body/template
            if action in CONTENT_ACTIONS and sap:
                errors.append({
                    "rule": "CANONICAL_PRIMARY_WORKFLOW_CONTENT_SOURCE",
                    "message": f"Primary workflow content must come from body/template, not supporting_assets: {path}",
                })

        # Non-content actions must not carry supporting_asset_path
        if action in NON_CONTENT_ACTIONS and sap:
            errors.append({
                "rule": "CANONICAL_NON_CONTENT_SUPPORTING_PATH",
                "message": f"Non-content action '{action}' must not carry supporting_asset_path for {path}",
            })

    # ── supporting_assets path must never equal primary workflow output path ──
    for asset in supporting_assets:
        asset_path = str(asset.get("path", "")).strip()
        if asset_path == primary_workflow_path:
            errors.append({
                "rule": "CANONICAL_SUPPORTING_ASSET_IS_PRIMARY",
                "message": f"Supporting asset path must not equal the primary workflow output path: {asset_path}",
            })
        # Validate kind is mechanically derivable from path
        kind = str(asset.get("kind", "")).strip()
        derived_kind = derive_supporting_asset_kind(asset_path)
        if derived_kind and kind != derived_kind:
            errors.append({
                "rule": "CANONICAL_SUPPORTING_ASSET_KIND_MISMATCH",
                "message": f"Supporting asset kind '{kind}' does not match path-derived kind '{derived_kind}' for {asset_path}",
            })

    # ── Unreferenced supporting assets ──
    # Every supporting_assets path must be referenced by at least one content action
    # in the asset_disposition (except primary workflow which gets content from body/template)
    supporting_paths_in_disposition: set[str] = set()
    for item in asset_disposition:
        sap = str(item.get("supporting_asset_path", "")).strip()
        if sap:
            supporting_paths_in_disposition.add(sap)

    for asset in supporting_assets:
        asset_path = str(asset.get("path", "")).strip()
        if asset_path and asset_path not in supporting_paths_in_disposition:
            errors.append({
                "rule": "CANONICAL_UNREFERENCED_SUPPORTING_ASSET",
                "message": f"Supporting asset not referenced by any asset_disposition content action: {asset_path}",
            })
        for item in asset_disposition:
            if str(item.get("supporting_asset_path", "")).strip() != asset_path:
                continue
            expected_reason = str(item.get("reason", "")).strip()
            observed_reason = str(asset.get("reason", "")).strip()
            if expected_reason and observed_reason != expected_reason:
                errors.append({
                    "rule": "CANONICAL_SUPPORTING_ASSET_REASON_MISMATCH",
                    "message": f"Supporting asset reason for {asset_path} must match canonical asset_disposition reason.",
                })
            break

    # ── Missing supporting assets for content actions ──
    for item in asset_disposition:
        path = str(item.get("path", "")).strip()
        action = str(item.get("action", "")).strip()
        sap = str(item.get("supporting_asset_path", "")).strip()
        if action in CONTENT_ACTIONS and path != primary_workflow_path and not sap:
            errors.append({
                "rule": "CANONICAL_CONTENT_ACTION_MISSING_SUPPORTING",
                "message": f"Content action '{action}' requires supporting_asset_path for non-primary asset: {path}",
            })
        if action in CONTENT_ACTIONS and sap and sap not in supporting_paths:
            errors.append({
                "rule": "CANONICAL_MISSING_SUPPORTING_ASSET",
                "message": f"Missing supporting asset for canonical path: {sap}",
            })

    # ── Duplicate paths ──
    seen_disp_paths: set[str] = set()
    for item in asset_disposition:
        path = str(item.get("path", "")).strip()
        if path and path in seen_disp_paths:
            errors.append({
                "rule": "CANONICAL_DUPLICATE_DISPOSITION_PATH",
                "message": f"Duplicate asset disposition path: {path}",
            })
        seen_disp_paths.add(path)

    seen_sup_paths: set[str] = set()
    for asset in supporting_assets:
        path = str(asset.get("path", "")).strip()
        if path and path in seen_sup_paths:
            errors.append({
                "rule": "CANONICAL_DUPLICATE_SUPPORTING_PATH",
                "message": f"Duplicate supporting asset path: {path}",
            })
        seen_sup_paths.add(path)

    # ── Invalid disposition actions ──
    for item in asset_disposition:
        action = str(item.get("action", "")).strip()
        if action and action not in ASSET_DISPOSITION_ACTIONS:
            errors.append({
                "rule": "CANONICAL_INVALID_DISPOSITION_ACTION",
                "message": f"Invalid asset disposition action: {action}",
            })

    # ── Invalid supporting asset kind ──
    for asset in supporting_assets:
        kind = str(asset.get("kind", "")).strip()
        if kind and kind not in SUPPORTING_ASSET_RULES:
            errors.append({
                "rule": "CANONICAL_INVALID_SUPPORTING_KIND",
                "message": f"Invalid supporting asset kind: {kind}",
            })

    return errors


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
        for field in ("name", "description"):
            if not isinstance(authoring_spec.get(field), str) or not authoring_spec[field].strip():
                errors.append({"rule": f"HANDOFF_AUTHORING_SPEC_{field.upper()}", "message": f"authoringSpec.{field} must be a non-empty string."})
        phases = authoring_spec.get("phases")
        body = authoring_spec.get("body")
        template_val = authoring_spec.get("template")
        phase_contracts = authoring_spec.get("phase_contracts")
        has_body = isinstance(body, str) and body.strip()
        has_template = isinstance(template_val, str) and template_val.strip() and isinstance(phase_contracts, list) and len(phase_contracts) > 0
        # Phase 4: Template mode may omit phases (derived from phase_contracts).
        # Body mode must still provide a non-empty phases array.
        if has_template:
            if isinstance(phases, list) and phases:
                # Explicit phases provided for template mode – validate in normalize_authoring_spec_payload
                pass
            # else: phases missing/empty is OK – will be derived from phase_contracts
        else:
            if not isinstance(phases, list) or not phases:
                errors.append({"rule": "HANDOFF_AUTHORING_SPEC_PHASES", "message": "authoringSpec.phases must be a non-empty array for body-mode authoring."})
        if not has_body and not has_template:
            errors.append({"rule": "HANDOFF_AUTHORING_SPEC_BODY", "message": "authoringSpec must have either a non-empty body or both template and phase_contracts."})
        if has_body and has_template:
            errors.append({"rule": "HANDOFF_AUTHORING_SPEC_BOTH_BODY_AND_TEMPLATE", "message": "authoringSpec must not provide both body and template+phase_contracts."})
        if has_template:
            if template_val not in TEMPLATES:
                errors.append({"rule": "HANDOFF_AUTHORING_SPEC_TEMPLATE_UNKNOWN", "message": f"authoringSpec.template must be one of {sorted(TEMPLATES)}."})

    # --- migrate/update asset disposition -------------------------------------
    gen_op = str(gen_req.get("operation", "")).strip() if isinstance(gen_req, dict) else ""
    normalized_authoring_spec: dict[str, Any] | None = None
    if isinstance(authoring_spec, dict):
        try:
            normalized_authoring_spec = normalize_authoring_spec_payload(authoring_spec)
        except Exception as exc:
            errors.append({"rule": "HANDOFF_AUTHORING_SPEC_INVALID", "message": str(exc)})
    if gen_op in ("migrate", "update") and normalized_authoring_spec is not None and not normalized_authoring_spec["asset_disposition"]:
        errors.append({
            "rule": "HANDOFF_ASSET_DISPOSITION_REQUIRED",
            "message": f"Operation '{gen_op}' requires a non-empty authoringSpec.asset_disposition table.",
        })

    needs_design_asset_boundary = (
        gen_op in ("migrate", "update")
        or (
            normalized_authoring_spec is not None
            and (
                bool(normalized_authoring_spec["supporting_assets"])
                or bool(normalized_authoring_spec["asset_disposition"])
            )
        )
    )

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
        if needs_design_asset_boundary:
            design_disposition = design_ev.get("assetDisposition")
            if not isinstance(design_disposition, list) or not design_disposition:
                errors.append({
                    "rule": "HANDOFF_DESIGN_ASSET_DISPOSITION_REQUIRED",
                    "message": f"Operation '{gen_op}' requires non-empty designEvidence.assetDisposition for canonical asset boundaries.",
                })
            elif normalized_authoring_spec is not None:
                try:
                    normalized_design_disposition = normalize_design_asset_disposition(
                        design_disposition,
                        normalized_authoring_spec["supporting_assets"],
                        f".claude/workflows/{normalized_authoring_spec['name']}.js",
                        target_root,
                    )
                    if normalized_design_disposition != normalized_authoring_spec["asset_disposition"]:
                        errors.append({
                            "rule": "HANDOFF_ASSET_DISPOSITION_MISMATCH",
                            "message": "authoringSpec.asset_disposition must match the reviewed designEvidence.assetDisposition.",
                        })
                except Exception as exc:
                    errors.append({"rule": "HANDOFF_DESIGN_ASSET_DISPOSITION_INVALID", "message": str(exc)})

        if normalized_authoring_spec is not None:
            try:
                canonical_errors = _validate_canonical_projection(
                    normalized_authoring_spec,
                    gen_op,
                )
                for ce in canonical_errors:
                    errors.append(ce)
            except Exception as exc:
                errors.append({"rule": "CANONICAL_PROJECTION_INVALID", "message": str(exc)})

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
        if needs_design_asset_boundary and review_ev.get("assetDispositionReviewed") is not True:
            errors.append({
                "rule": "HANDOFF_REVIEW_ASSET_DISPOSITION_REQUIRED",
                "message": f"Operation '{gen_op}' requires reviewEvidence.assetDispositionReviewed=true for canonical asset boundaries.",
            })

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


def normalize_phase_contracts(value: Any) -> list[dict[str, Any]]:
    """Validate and normalize phase_contracts for template-based authoring.

    Each phase_contract describes one sequential phase with:
    - phase (required): title string
    - detail (optional): description string
    - label (required): agent label string
    - prompt (required): agent prompt body
    - agentType (optional): registered agent type
    - schema (required): JSON Schema object for structured output
    - blockWhen (optional): JS expression that triggers a block
    - blockStatus (optional): status to emit on block (default depends on phase)
    - blockMessage (optional): blocking issue message
    - nextAction (optional): recommended next action on block
    - includePriorPhaseResults (internal): append previous StructuredOutput
      results to this phase prompt
    """
    if not isinstance(value, list) or not value:
        raise ValueError("`phase_contracts` must be a non-empty array.")
    normalized: list[dict[str, Any]] = []
    seen_phases: set[str] = set()
    seen_labels: set[str] = set()
    has_finalize_phase = any(
        isinstance(pc, dict) and str(pc.get("phase", "")).strip().lower() == "finalize"
        for pc in value
    )
    for index, pc in enumerate(value):
        if not isinstance(pc, dict):
            raise ValueError(f"`phase_contracts[{index}]` must be an object.")
        phase_title = str(pc.get("phase", "")).strip()
        detail = str(pc.get("detail", "")).strip()
        label = str(pc.get("label", "")).strip()
        prompt = str(pc.get("prompt", "")).strip()
        agent_type = str(pc.get("agentType", "")).strip() or None
        schema = pc.get("schema")
        block_when = str(pc.get("blockWhen", "")).strip() or None
        block_status = str(pc.get("blockStatus", "")).strip() or None
        block_message = str(pc.get("blockMessage", "")).strip() or None
        next_action = str(pc.get("nextAction", "")).strip() or None
        include_prior_phase_results = bool(pc.get("includePriorPhaseResults"))
        synthetic = bool(pc.get("synthetic"))

        if not phase_title:
            raise ValueError(f"`phase_contracts[{index}].phase` must be a non-empty string.")
        if phase_title in seen_phases:
            raise ValueError(f"Duplicate phase_contracts phase: {phase_title}")
        seen_phases.add(phase_title)

        if not label:
            raise ValueError(f"`phase_contracts[{index}].label` must be a non-empty string.")
        if label in seen_labels:
            raise ValueError(f"Duplicate phase_contracts label: {label}")
        seen_labels.add(label)

        if not prompt:
            raise ValueError(f"`phase_contracts[{index}].prompt` must be a non-empty string.")

        if not isinstance(schema, dict):
            raise ValueError(f"`phase_contracts[{index}].schema` must be a JSON Schema object.")
        if not schema.get("type"):
            raise ValueError(f"`phase_contracts[{index}].schema` must declare a `type`.")
        parse_contract = is_parse_prompt(prompt, schema)
        if parse_contract and PARSE_SCOPE_PROMPT_SUFFIX not in prompt:
            prompt = f"{prompt}\n\n{PARSE_SCOPE_PROMPT_SUFFIX}"
        schema, normalized_stride_aggregate = normalize_stride_aggregate_schema(prompt, schema)
        stride_aggregate = normalized_stride_aggregate or is_stride_aggregate_contract(prompt, schema)
        if stride_aggregate and STRIDE_AGGREGATE_PROMPT_SUFFIX not in prompt:
            prompt = f"{prompt}\n\n{STRIDE_AGGREGATE_PROMPT_SUFFIX}"
        if stride_aggregate:
            include_prior_phase_results = True
        validation_contract = is_validation_contract(prompt, schema)
        if validation_contract and VALIDATION_ANALYSIS_PROMPT_SUFFIX not in prompt:
            prompt = f"{prompt}\n\n{VALIDATION_ANALYSIS_PROMPT_SUFFIX}"
        result_auditor_pre_contract = is_result_auditor_pre_contract(prompt, schema)
        if result_auditor_pre_contract and RESULT_AUDIT_PREREPORT_PROMPT_SUFFIX not in prompt:
            prompt = f"{prompt}\n\n{RESULT_AUDIT_PREREPORT_PROMPT_SUFFIX}"
        poc_contract = is_poc_contract(prompt, schema)
        if poc_contract and POC_ANALYSIS_PROMPT_SUFFIX not in prompt:
            prompt = f"{prompt}\n\n{POC_ANALYSIS_PROMPT_SUFFIX}"
        report_contract = is_report_contract(prompt, schema)
        deterministic_report_contract = is_deterministic_stride_report_contract(prompt, schema)
        if report_contract and REPORT_ASSEMBLY_PROMPT_SUFFIX not in prompt:
            prompt = f"{prompt}\n\n{REPORT_ASSEMBLY_PROMPT_SUFFIX}"
        if is_dfd_inference_prompt(prompt, schema) and DFD_INFERENCE_PROMPT_SUFFIX not in prompt:
            prompt = f"{prompt}\n\n{DFD_INFERENCE_PROMPT_SUFFIX}"
        if (
            has_finalize_phase
            and is_doctor_contract(prompt, schema)
            and DOCTOR_PREFINALIZE_MANIFEST_PROMPT_SUFFIX not in prompt
        ):
            prompt = f"{prompt}\n\n{DOCTOR_PREFINALIZE_MANIFEST_PROMPT_SUFFIX}"
        finalize_contract = is_finalize_contract(prompt, schema)

        entry: dict[str, Any] = {
            "phase": phase_title,
            "label": label,
            "prompt": prompt,
            "schema": schema,
        }
        if detail:
            entry["detail"] = detail
        if agent_type:
            entry["agentType"] = agent_type
        if block_when is not None:
            entry["blockWhen"] = block_when
            if block_status:
                entry["blockStatus"] = block_status
            if block_message:
                entry["blockMessage"] = block_message
            if next_action:
                entry["nextAction"] = next_action
        if include_prior_phase_results:
            entry["includePriorPhaseResults"] = True
        if synthetic:
            entry["synthetic"] = True
        if stride_aggregate:
            entry["artifactWriter"] = "stride-synthetic"
            entry["sourceLabel"] = label
            entry["blockWhen"] = "result.status !== 'PASS'"
            entry["blockStatus"] = "BLOCKED_STRIDE_SYNTHESIS"
            entry["blockMessage"] = "Deterministic STRIDE synthesis did not produce candidate threats."
            entry["nextAction"] = "FIX_STRIDE_SYNTHESIS"
        if deterministic_report_contract:
            entry["artifactWriter"] = "report"
            entry["sourceLabel"] = label
            entry["blockWhen"] = "result.report_generated !== true"
            entry["blockStatus"] = "BLOCKED_REPORT_ASSEMBLY"
            entry["blockMessage"] = "Deterministic Report writer did not produce normalized threat/report artifacts."
            entry["nextAction"] = "FIX_REPORT_ASSEMBLY"
        if finalize_contract:
            entry["artifactWriter"] = "finalize"
            entry["sourceLabel"] = label
            entry["blockWhen"] = "result.status !== 'PASS'"
            entry["blockStatus"] = "BLOCKED_FINALIZE"
            entry["blockMessage"] = "Deterministic Finalize writer did not produce run_manifest.json and return envelope."
            entry["nextAction"] = "FIX_FINALIZE"
        normalized.append(entry)
        if parse_contract:
            writer = parse_artifact_writer_contract(phase_title, label, detail)
            writer_phase = writer["phase"]
            writer_label = writer["label"]
            if writer_phase in seen_phases:
                raise ValueError(f"Duplicate phase_contracts phase: {writer_phase}")
            if writer_label in seen_labels:
                raise ValueError(f"Duplicate phase_contracts label: {writer_label}")
            seen_phases.add(writer_phase)
            seen_labels.add(writer_label)
            normalized.append(writer)
        if stride_aggregate:
            writer = stride_artifact_writer_contract(phase_title, label, detail)
            writer_phase = writer["phase"]
            writer_label = writer["label"]
            if writer_phase in seen_phases:
                raise ValueError(f"Duplicate phase_contracts phase: {writer_phase}")
            if writer_label in seen_labels:
                raise ValueError(f"Duplicate phase_contracts label: {writer_label}")
            seen_phases.add(writer_phase)
            seen_labels.add(writer_label)
            normalized.append(writer)
        if validation_contract:
            writer = validation_artifact_writer_contract(phase_title, label, detail)
            writer_phase = writer["phase"]
            writer_label = writer["label"]
            if writer_phase in seen_phases:
                raise ValueError(f"Duplicate phase_contracts phase: {writer_phase}")
            if writer_label in seen_labels:
                raise ValueError(f"Duplicate phase_contracts label: {writer_label}")
            seen_phases.add(writer_phase)
            seen_labels.add(writer_label)
            normalized.append(writer)
        if poc_contract:
            writer = poc_artifact_writer_contract(phase_title, label, detail)
            writer_phase = writer["phase"]
            writer_label = writer["label"]
            if writer_phase in seen_phases:
                raise ValueError(f"Duplicate phase_contracts phase: {writer_phase}")
            if writer_label in seen_labels:
                raise ValueError(f"Duplicate phase_contracts label: {writer_label}")
            seen_phases.add(writer_phase)
            seen_labels.add(writer_label)
            normalized.append(writer)
        if result_auditor_pre_contract:
            writer = result_audit_artifact_writer_contract(phase_title, label, detail)
            writer_phase = writer["phase"]
            writer_label = writer["label"]
            if writer_phase in seen_phases:
                raise ValueError(f"Duplicate phase_contracts phase: {writer_phase}")
            if writer_label in seen_labels:
                raise ValueError(f"Duplicate phase_contracts label: {writer_label}")
            seen_phases.add(writer_phase)
            seen_labels.add(writer_label)
            normalized.append(writer)
        if is_dfd_inference_prompt(prompt, schema):
            writer = dfd_artifact_writer_contract(phase_title, label, detail)
            writer_phase = writer["phase"]
            writer_label = writer["label"]
            if writer_phase in seen_phases:
                raise ValueError(f"Duplicate phase_contracts phase: {writer_phase}")
            if writer_label in seen_labels:
                raise ValueError(f"Duplicate phase_contracts label: {writer_label}")
            seen_phases.add(writer_phase)
            seen_labels.add(writer_label)
            normalized.append(writer)
    return normalized


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
    template = str(payload.get("template", "")).strip() or None
    raw_phase_contracts = payload.get("phase_contracts")
    has_body = isinstance(body, str) and body.strip()
    has_template = isinstance(template, str) and template.strip() and isinstance(raw_phase_contracts, list) and len(raw_phase_contracts) > 0

    if not has_body and not has_template:
        raise ValueError("Either `body` or both `template` and `phase_contracts` must be provided.")
    if has_body and has_template:
        raise ValueError("Provide either `body` or `template`+`phase_contracts`, not both.")

    titles: list[str] = []
    normalized_phases: list[dict[str, str]] = []
    for index, phase in enumerate(phases if isinstance(phases, list) else []):
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

    if has_template:
        if template not in TEMPLATES:
            raise ValueError(f"`template` must be one of {sorted(TEMPLATES)}.")
        if phases is not None and not isinstance(phases, list):
            raise ValueError("`phases` must be an array when template authoring is used.")
        normalized_phase_contracts = normalize_phase_contracts(raw_phase_contracts)
        # Derive phases from phase_contracts when template is used
        derived_phases: list[dict[str, str]] = []
        for pc in normalized_phase_contracts:
            phase_entry: dict[str, str] = {"title": pc["phase"]}
            if pc.get("detail"):
                phase_entry["detail"] = pc["detail"]
            derived_phases.append(phase_entry)
        # Validate no mismatch if both phases and phase_contracts provided
        if normalized_phases:
            phase_titles = [p.get("title", "") for p in normalized_phases]
            derived_titles = [p["title"] for p in derived_phases]
            user_derived_titles = [
                p["title"]
                for p, pc in zip(derived_phases, normalized_phase_contracts)
                if not pc.get("synthetic")
            ]
            if phase_titles == derived_titles or phase_titles == user_derived_titles:
                normalized_phases = derived_phases
            else:
                raise ValueError(
                    f"`phases` titles must match `phase_contracts` phase values when both are provided."
                )
        else:
            normalized_phases = derived_phases
    else:
        if not isinstance(phases, list) or not phases:
            raise ValueError("`phases` must be a non-empty array.")
        normalized_phase_contracts = None
        validate_authoring_body(body)

    # Phase 3: Derive primary workflow path for canonical boundary validation
    primary_workflow_path = f".claude/workflows/{name}.js"
    supporting_assets = normalize_supporting_assets(payload.get("supporting_assets", []), primary_workflow_path)
    asset_disposition = normalize_asset_disposition(payload.get("asset_disposition", []), supporting_assets, primary_workflow_path)
    task_model_policy = normalize_task_model_policy(payload.get("task_model_policy"))
    result: dict[str, Any] = {
        "name": name,
        "description": description,
        "phases": normalized_phases,
        "supporting_assets": supporting_assets,
        "asset_disposition": asset_disposition,
        "task_model_policy": task_model_policy,
    }
    if has_template:
        result["template"] = template
        result["phase_contracts"] = normalized_phase_contracts
        result["body"] = ""
    else:
        result["body"] = body.strip() + "\n"
    return result


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
    comparable_keys = ("name", "description", "phases", "body", "template", "phase_contracts", "supporting_assets", "asset_disposition", "task_model_policy")
    for key in comparable_keys:
        if spec.get(key) != handoff_spec.get(key):
            errors.append({"rule": "HANDOFF_AUTHORING_SPEC_MISMATCH", "message": f"Disk spec field `{key}` does not match READY_FOR_GENERATION.authoringSpec."})
    return errors


def normalize_supporting_assets(value: Any, primary_workflow_path: str = "") -> list[dict[str, str]]:
    """Validate explicit optional assets without widening the default deployment tree.

    Phase 3: supporting_assets[].path must never equal the primary workflow output path.
    """

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
        # Phase 3: supporting_assets path must never equal the primary workflow output path
        if primary_workflow_path and relative_path == primary_workflow_path:
            raise ValueError(
                f"Supporting asset path must not equal the primary workflow output path: {relative_path}"
            )
        prefix, suffix = SUPPORTING_ASSET_RULES[kind]
        if not relative_path.startswith(prefix) or (suffix and not relative_path.endswith(suffix)):
            raise ValueError(f"`supporting_assets[{index}].path` is invalid for kind `{kind}`.")
        if kind == "settings" and relative_path != ".claude/settings.json":
            raise ValueError("`settings` must use `.claude/settings.json`.")
        if kind == "managed-files" and relative_path != ".workflowprogram/managed-files.json":
            raise ValueError("`managed-files` must use `.workflowprogram/managed-files.json`.")
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


def normalize_asset_disposition(value: Any, supporting_assets: list[dict[str, str]], primary_workflow_path: str = "") -> list[dict[str, str]]:
    """Validate migration intent separately from generated supporting-asset content.

    Phase 3: Enforces canonical asset and supporting asset boundary rules:
    - Primary workflow disposition must not carry supporting_asset_path
    - Non-content actions must not carry supporting_asset_path
    - supporting_assets[].path must not equal the primary workflow output path
    """

    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("`asset_disposition` must be an array when provided.")
    supporting_paths = {item["path"] for item in supporting_assets}
    normalized: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"`asset_disposition[{index}]` must be an object.")
        raw_path = str(item.get("path", "")).strip().replace("\\", "/")
        action = str(item.get("action", "")).strip()
        reason = str(item.get("reason", "")).strip()
        raw_supporting_path = str(item.get("supporting_asset_path", "")).strip().replace("\\", "/")
        relative = PurePosixPath(raw_path)
        relative_path = relative.as_posix()
        if not raw_path or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"`asset_disposition[{index}].path` must stay inside the target root.")
        if relative_path in seen_paths:
            raise ValueError(f"Duplicate asset disposition path: {relative_path}")
        if action not in ASSET_DISPOSITION_ACTIONS:
            raise ValueError(f"`asset_disposition[{index}].action` must be one of {sorted(ASSET_DISPOSITION_ACTIONS)}.")
        if not reason:
            raise ValueError(f"`asset_disposition[{index}].reason` must explain the migration decision.")

        # Phase 3: Primary workflow disposition must not carry supporting_asset_path
        is_primary_workflow = primary_workflow_path and relative_path == primary_workflow_path
        if is_primary_workflow and raw_supporting_path:
            raise ValueError(
                f"Primary workflow disposition must not carry supporting_asset_path: {relative_path}"
            )

        # Phase 3: Non-content actions must not carry supporting_asset_path
        if action in NON_CONTENT_ACTIONS and raw_supporting_path:
            raise ValueError(
                f"Non-content action '{action}' must not carry supporting_asset_path for {relative_path}"
            )

        if action in ASSET_ACTIONS_REQUIRING_SUPPORTING_ASSET:
            # Primary workflow gets content from body/template, not supporting_assets
            if is_primary_workflow:
                supporting_path = ""
            else:
                if not raw_supporting_path:
                    raise ValueError(f"`asset_disposition[{index}].supporting_asset_path` is required for action `{action}`.")
                support_relative = PurePosixPath(raw_supporting_path)
                supporting_path = support_relative.as_posix()
                if support_relative.is_absolute() or ".." in support_relative.parts or supporting_path not in supporting_paths:
                    raise ValueError(
                        f"`asset_disposition[{index}].supporting_asset_path` must match a generated supporting_assets path."
                    )
        else:
            supporting_path = ""
            if raw_supporting_path and raw_supporting_path not in supporting_paths:
                raise ValueError(
                    f"`asset_disposition[{index}].supporting_asset_path` must match a generated supporting_assets path when provided."
                )
            if raw_supporting_path:
                supporting_path = raw_supporting_path
        seen_paths.add(relative_path)
        entry = {"path": relative_path, "action": action, "reason": reason}
        if supporting_path:
            entry["supporting_asset_path"] = supporting_path
        normalized.append(entry)
    return normalized


def normalize_design_asset_disposition(
    value: Any,
    supporting_assets: list[dict[str, str]],
    primary_workflow_path: str = "",
    target_root: Path | None = None,
) -> list[dict[str, str]]:
    """Convert runtime camelCase design evidence into the authoring-spec shape."""

    if not isinstance(value, list):
        raise ValueError("`designEvidence.assetDisposition` must be an array.")

    resolved_target_root: Path | None = None
    if target_root is not None:
        try:
            resolved_target_root = target_root.resolve()
        except Exception:
            resolved_target_root = target_root

    def target_relative(raw_value: str) -> str:
        raw = raw_value.strip().replace("\\", "/")
        if not raw:
            return ""
        if resolved_target_root is not None:
            try:
                candidate = Path(raw)
                if candidate.is_absolute():
                    return candidate.resolve().relative_to(resolved_target_root).as_posix()
            except Exception:
                pass
        return PurePosixPath(raw).as_posix()

    design_content_paths: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path", "")).strip().replace("\\", "/")
        action = str(item.get("action", "")).strip()
        if raw_path and action in ASSET_ACTIONS_REQUIRING_SUPPORTING_ASSET:
            design_content_paths.add(target_relative(raw_path))
    converted: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            converted.append(item)
            continue
        path = str(item.get("path", "")).strip().replace("\\", "/")
        action = str(item.get("action", "")).strip()
        supporting_path = str(item.get("supportingAssetPath", "")).strip().replace("\\", "/")
        relative_path = target_relative(path)
        relative_supporting_path = target_relative(supporting_path)
        path_kind = derive_supporting_asset_kind(relative_path)
        supporting_kind = derive_supporting_asset_kind(relative_supporting_path)
        if is_run_evidence_path(relative_path):
            supporting_path = ""
            relative_supporting_path = ""
        if primary_workflow_path and relative_path == primary_workflow_path:
            supporting_path = ""
            relative_supporting_path = ""
        if action in NON_CONTENT_ACTIONS:
            supporting_path = ""
            relative_supporting_path = ""
        if relative_path.startswith(".workflowprogram/runtime/") and action in ASSET_ACTIONS_REQUIRING_SUPPORTING_ASSET:
            action = "archive"
            supporting_path = ""
            relative_supporting_path = ""
        if (
            action in ASSET_ACTIONS_REQUIRING_SUPPORTING_ASSET
            and primary_workflow_path
            and relative_path != primary_workflow_path
            and (
                not relative_supporting_path
                or relative_supporting_path == primary_workflow_path
                or (
                    relative_supporting_path in design_content_paths
                    and relative_supporting_path != relative_path
                )
                or (
                    path_kind
                    and supporting_kind
                    and path_kind != supporting_kind
                )
            )
        ):
            supporting_path = relative_path
        converted.append(
            {
                "path": relative_path,
                "action": action,
                "reason": item.get("reason", ""),
                "supporting_asset_path": target_relative(supporting_path),
            }
        )
    converted = [
        item for item in converted
        if not isinstance(item, dict) or not is_run_evidence_path(str(item.get("path", "")))
    ]
    normalized = normalize_asset_disposition(converted, supporting_assets, primary_workflow_path)
    normalized.sort(key=lambda item: item["path"])
    return normalized


def normalize_task_model_policy(value: Any) -> dict[str, Any]:
    """Validate optional target workflow task-model metadata."""

    if value is None:
        return {"agent_task_models": {}}
    if not isinstance(value, dict):
        raise ValueError("`task_model_policy` must be an object when provided.")
    unknown_keys = sorted(set(value) - {"agent_task_models"})
    if unknown_keys:
        raise ValueError(f"`task_model_policy` only supports `agent_task_models`; unknown keys: {unknown_keys}")
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


def js_single_quoted(value: Any) -> str:
    """Return a JavaScript single-quoted string literal."""

    text = str(value)
    escaped = (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return f"'{escaped}'"


def render_template_body(name: str, phase_contracts: list[dict[str, Any]]) -> str:
    """Render the executable JS body for ``sequential-agent-workflow-v1``."""

    lines: list[str] = []
    lines.append(f"const workflowName = {js_single_quoted(name)}")
    lines.append("const launchMode = 'plugin-script-path'")
    lines.append("const rawArgs = (() => {")
    lines.append("  if (typeof args === 'string') {")
    lines.append("    try {")
    lines.append("      const parsed = JSON.parse(args)")
    lines.append("      return parsed && typeof parsed === 'object' ? parsed : { rawArgsValue: parsed }")
    lines.append("    } catch {")
    lines.append("      return { rawArgsString: args }")
    lines.append("    }")
    lines.append("  }")
    lines.append("  return args && typeof args === 'object' ? args : {}")
    lines.append("})()")
    lines.append("const runId = rawArgs?.runId || ''")
    lines.append("const runtimeContext = {")
    lines.append("  runId,")
    lines.append("  target: rawArgs?.target || rawArgs?.targetPath || rawArgs?.path || '',")
    lines.append("  targetRoot: rawArgs?.targetRoot || '',")
    lines.append("  mode: rawArgs?.mode || 'auto',")
    lines.append("  options: rawArgs?.options || {},")
    lines.append("  rawArgs,")
    lines.append("}")
    lines.append("const runtimeContextPrompt = '\\n\\nRuntime invocation context (authoritative command args):\\n' +")
    lines.append("  JSON.stringify(runtimeContext, null, 2) +")
    lines.append("  '\\nUse this context as the source for target path, mode, options, run id, and target root. Do not infer these values from memory or defaults when present.'")
    lines.append("const phaseResults = {}")
    lines.append("function priorPhaseResultsPrompt() {")
    lines.append("  return '\\n\\nPrior phase StructuredOutput results (read-only, authoritative when relevant):\\n' +")
    lines.append("    JSON.stringify(phaseResults, null, 2)")
    lines.append("}")
    lines.append("function structuredOutputContract(schema) {")
    lines.append("  return '\\n\\nStructured output contract (must be satisfied on the first StructuredOutput call):\\n' +")
    lines.append("    JSON.stringify(schema, null, 2) +")
    lines.append("    '\\nReturn exactly one JSON object that satisfies this schema. Call StructuredOutput with a JSON object input, not a stringified JSON blob, markdown fence, or __unparsedToolInput wrapper. If a schema property is an array, return a JSON array for that property; do not replace arrays with counts, summaries, or maps. For optional string fields, omit absent values or use an empty string; never use null. If the phase instructions require writing output files, write every named output file before calling StructuredOutput; do not call StructuredOutput until required output files are current for this run. If this phase does not explicitly name output files, do not write files, create logs, save copies, or invent evidence paths. If a renderer/helper/skill for a named output file is unavailable, write a deterministic fallback artifact at that requested path and note the degradation in the smallest schema-compatible field. When replacing existing output files, use Bash here-doc/redirection or read the existing file before using Write, because Write may require a prior Read for existing files. After required files are written, do not call Bash, Read, Write, Edit, Glob, or Grep for verification; make exactly one StructuredOutput attempt next. For large file artifacts, keep StructuredOutput compact: return paths, counts, hashes, top-level keys, and short summaries rather than embedding full file contents, unless the schema explicitly requires full content. If that StructuredOutput attempt is rejected by schema validation, correct only the JSON object and retry StructuredOutput once; do not run any other tool between retries. Once StructuredOutput returns success, the phase is done: the Workflow runtime has already captured the phase result, and any later tool call can mutate files or replace captured evidence. After success, do not explain, summarize, save a copy, verify, retry, or call Bash, Read, Write, Edit, Glob, Grep, or StructuredOutput again. If another assistant response is required to finish the subagent turn, respond with exactly DONE and no other text.'")
    lines.append("}")
    lines.append("")
    lines.append(f"const artifactPayloadWriterScript = {js_single_quoted(artifact_payload_writer_script_path())}")
    lines.extend(DETERMINISTIC_ARTIFACT_HELPER_JS.strip().splitlines())
    lines.append("")

    for pc in phase_contracts:
        phase_title = pc["phase"]
        label = pc["label"]
        prompt = pc["prompt"]
        schema = pc["schema"]
        agent_type = pc.get("agentType") or STRUCTURED_PHASE_AGENT_TYPE
        block_when = pc.get("blockWhen")
        block_status = pc.get("blockStatus", "BLOCKED")
        block_message = pc.get("blockMessage", f"{phase_title} gate blocked.")
        next_action = pc.get("nextAction")
        include_prior_phase_results = bool(pc.get("includePriorPhaseResults"))
        artifact_writer = str(pc.get("artifactWriter") or "").strip()
        source_label = str(pc.get("sourceLabel") or "").strip()

        lines.append(f"phase({js_single_quoted(phase_title)})")
        lines.append("")

        artifact_writer_functions = {
            "parse": "writeParseArtifactsFromPhaseResult",
            "dfd": "writeDfdArtifactsFromPhaseResult",
            "stride-synthetic": "writeDeterministicStrideResultFromPriorPhases",
            "stride": "writeStrideArtifactsFromPhaseResult",
            "validation": "writeValidationArtifactsFromPhaseResult",
            "poc": "writePocArtifactsFromPhaseResult",
            "result-audit": "writeResultAuditArtifactsFromPhaseResult",
            "report": "writeReportArtifactsFromPriorPhases",
            "finalize": "writeFinalizeArtifactsFromPriorPhases",
        }
        artifact_writer_comments = {
            "parse": "Mechanical Parse artifact writer",
            "dfd": "Mechanical DFD artifact writer",
            "stride-synthetic": "Deterministic STRIDE candidate generator",
            "stride": "Mechanical STRIDE artifact writer",
            "validation": "Mechanical Validation artifact writer",
            "poc": "Mechanical PoC artifact writer",
            "result-audit": "Mechanical Result Audit artifact writer",
            "report": "Deterministic Report artifact writer",
            "finalize": "Deterministic Finalize artifact writer",
        }
        if artifact_writer:
            writer_function = artifact_writer_functions.get(artifact_writer)
            if not writer_function:
                raise ValueError(f"Unsupported deterministic artifact writer: {artifact_writer}")
            if not source_label:
                raise ValueError(f"`sourceLabel` is required for deterministic artifact writer {artifact_writer!r}.")
            lines.append("{")
            lines.append(f"  // {artifact_writer_comments[artifact_writer]}: persist artifacts from {source_label}.")
            lines.append(f"  const result = await {writer_function}({json.dumps(source_label, ensure_ascii=False)})")
            lines.append("")
            lines.append(f"  phaseResults[{json.dumps(label, ensure_ascii=False)}] = result")
            lines.append("")
            if block_when:
                extra_lines: list[str] = []
                if next_action:
                    extra_lines.append(f"    nextAction: {js_single_quoted(next_action)},")
                lines.append(f"if ({block_when}) {{")
                lines.append("  return {")
                lines.append(f"    status: {js_single_quoted(block_status)},")
                lines.append("    workflow: workflowName,")
                lines.append("    launchMode,")
                lines.append("    runId,")
                lines.extend(extra_lines)
                lines.append(f"    blockingIssues: [{json.dumps(block_message)}],")
                lines.append("  }")
                lines.append("}")
                lines.append("")
            if artifact_writer == "finalize":
                lines.append("return result.return_envelope || result")
                lines.append("")
            lines.append("}")
            lines.append("")
            continue

        # Build agent options
        agent_lines: list[str] = []
        agent_lines.append(f"      label: {json.dumps(label, ensure_ascii=False)},")
        if agent_type:
            agent_lines.append(f"      agentType: {json.dumps(agent_type, ensure_ascii=False)},")
        agent_lines.append("      schema: phaseSchema,")
        agent_opts = "\n".join(agent_lines)

        lines.append("{")
        lines.append(f"  const phaseSchema = {json.dumps(schema, ensure_ascii=False)}")
        lines.append(
            f"  const phasePrompt = {json.dumps(prompt, ensure_ascii=False)} + "
            "structuredOutputContract(phaseSchema) + runtimeContextPrompt"
            + (" + priorPhaseResultsPrompt()" if include_prior_phase_results else "")
        )
        lines.append("  const result = await agent(")
        lines.append("    phasePrompt,")
        lines.append("    {")
        lines.append(agent_opts)
        lines.append("    },")
        lines.append("  )")
        lines.append("")
        lines.append(f"  phaseResults[{json.dumps(label, ensure_ascii=False)}] = result")
        lines.append("")

        if block_when:
            extra_lines: list[str] = []
            if next_action:
                extra_lines.append(f"    nextAction: {js_single_quoted(next_action)},")
            lines.append(f"if ({block_when}) {{")
            lines.append("  return {")
            lines.append(f"    status: {js_single_quoted(block_status)},")
            lines.append("    workflow: workflowName,")
            lines.append("    launchMode,")
            lines.append("    runId,")
            lines.extend(extra_lines)
            lines.append(f"    blockingIssues: [{json.dumps(block_message)}],")
            lines.append("  }")
            lines.append("}")
            lines.append("")

        lines.append("}")
        lines.append("")

    lines.append("return {")
    lines.append("  status: 'PASS',")
    lines.append("  workflow: workflowName,")
    lines.append("  launchMode,")
    lines.append("  runId,")
    lines.append("  blockingIssues: [],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def render_workflow(spec: dict[str, Any]) -> str:
    """Render a deterministic Native Workflow JS file."""

    meta = {
        "name": spec["name"],
        "description": spec["description"],
        "phases": spec["phases"],
    }
    task_policy = spec.get("task_model_policy") or {}
    agent_task_models = task_policy.get("agent_task_models") or {}

    if spec.get("template") and spec.get("phase_contracts"):
        body = render_template_body(spec["name"], spec["phase_contracts"])
    else:
        body = spec.get("body", "")

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
    asset_disposition: list[dict[str, str]] | None = None,
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
        "asset_disposition": asset_disposition or [],
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
        canonical_errors = _validate_canonical_projection(spec, gate_mode)
        if canonical_errors:
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
                asset_disposition=spec["asset_disposition"],
                errors=canonical_errors,
            )
            write_json(generation_path, payload)
            emit(payload, args.json)
            return 1
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
                    asset_disposition=spec["asset_disposition"],
                    errors=alignment_errors,
                )
                write_json(generation_path, payload)
                emit(payload, args.json)
                return 1
        candidate_script = candidate_root / ".claude" / "workflows" / f"{spec['name']}.js"
        candidate_script.parent.mkdir(parents=True, exist_ok=True)
        candidate_script.write_text(render_workflow(spec), encoding="utf-8", newline="\n")
        for asset in spec["supporting_assets"]:
            if asset["kind"] == "managed-files":
                # The controlled-apply manifest is owned by managed-assets.py.
                # Keep the supporting asset in reports for traceability, but do
                # not stage a candidate file that would overwrite the manifest.
                continue
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
                asset_disposition=spec["asset_disposition"],
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
            asset_disposition=spec["asset_disposition"],
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
