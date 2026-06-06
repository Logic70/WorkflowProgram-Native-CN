<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# Negative Example: Blocking On Expected Migration Work

## Request

```json
{
  "operation": "migrate",
  "request_kind": "redesign_existing",
  "target_state": "existing_managed_workflow",
  "request": "Move the existing /audit workflow to .claude/workflows/audit.js."
}
```

## Incorrect Exploration Result

```json
{
  "status": "BLOCKED",
  "findings": [
    ".claude/commands/audit.md defines the current workflow.",
    ".workflowprogram/runtime/ contains the old runner."
  ],
  "blockingIssues": [
    ".claude/workflows/audit.js does not exist.",
    "workflow-spec.yaml is stale compared with the command.",
    ".workflowprogram/runtime/ must be archived.",
    "managed-files.json must be updated.",
    "No existing Native Workflow JS reference exists."
  ]
}
```

## Why This Is Wrong

- The missing `.claude/workflows/audit.js` is the target deliverable.
- A stale spec is an asset disposition decision, not a reason to stop.
- Retired runtime files become `archive` tasks.
- `managed-files.json` updates are part of controlled apply.
- First-time migration naturally has no Native JS reference.

## Correct Gate Result

```json
{
  "status": "PASS",
  "migrationTasks": [
    "Generate .claude/workflows/audit.js.",
    "Archive .workflowprogram/runtime/.",
    "Update managed-files.json."
  ],
  "trueBlockers": [],
  "sourceOfTruth": [".claude/commands/audit.md"],
  "blockingIssues": []
}
```

## Review Verdict

BLOCKED. The incorrect result creates an exploration loop and prevents Author
from producing the missing target file.
