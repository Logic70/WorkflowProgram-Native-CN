<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# Positive Example: Existing Workflow Migration

## Request

```json
{
  "operation": "migrate",
  "request_kind": "redesign_existing",
  "target_state": "existing_managed_workflow",
  "request": "Move the existing /audit workflow to .claude/workflows/audit.js."
}
```

## Existing Assets

```text
.claude/commands/audit.md                 # current user-facing behavior
.claude/agents/audit-parser.md            # reusable role
.claude/skills/audit-report/SKILL.md      # reusable tool instructions
.workflowprogram/design/workflow-spec.yaml # old, partially stale
.workflowprogram/runtime/workflow-runner.py # retired custom runner
.workflowprogram/managed-files.json        # stale manifest
.claude/workflows/audit.js                 # missing target output
```

## Exploration Classification

```json
{
  "status": "PASS",
  "findings": [
    "The current command defines parse -> analyze -> report.",
    "The old workflow-spec.yaml is older than the command."
  ],
  "migrationTasks": [
    "Generate .claude/workflows/audit.js.",
    "Archive .workflowprogram/runtime/ as retired runtime.",
    "Update managed-files.json after controlled apply.",
    "Record workflow-spec.yaml as stale authoring metadata."
  ],
  "trueBlockers": [],
  "userDecisions": [],
  "sourceOfTruth": [
    ".claude/commands/audit.md",
    ".claude/agents/audit-parser.md",
    ".claude/skills/audit-report/SKILL.md"
  ],
  "assetDispositionHints": [
    { "path": ".claude/workflows/audit.js", "action": "generate" },
    { "path": ".workflowprogram/runtime/", "action": "archive" },
    { "path": ".workflowprogram/design/workflow-spec.yaml", "action": "defer" }
  ],
  "blockingIssues": []
}
```

## Authoring Spec Shape

```json
{
  "name": "audit",
  "description": "Native Workflow JS control plane for /audit.",
  "phases": [
    { "title": "Parse" },
    { "title": "Analyze" },
    { "title": "Report" },
    { "title": "Deliver" }
  ],
  "supporting_assets": [
    {
      "kind": "workflow",
      "path": ".claude/workflows/audit.js",
      "content": "phase('Parse')\n...",
      "reason": "Target Native Workflow JS output."
    }
  ],
  "asset_disposition": [
    {
      "path": ".claude/workflows/audit.js",
      "action": "generate",
      "reason": "Missing target file is the expected migration deliverable.",
      "supporting_asset_path": ".claude/workflows/audit.js"
    },
    {
      "path": ".workflowprogram/runtime/",
      "action": "archive",
      "reason": "Retired custom runner after Native Workflow JS migration.",
      "supporting_asset_path": ".workflowprogram/archive/runtime/"
    },
    {
      "path": ".workflowprogram/design/workflow-spec.yaml",
      "action": "defer",
      "reason": "Historical authoring metadata; command is the current truth."
    }
  ]
}
```

## Review Verdict

PASS. Missing target workflow, stale spec, retired runtime, stale manifest, and
lack of an existing Native JS reference are migration tasks. They do not block
Design or Author because current behavioral truth exists.
