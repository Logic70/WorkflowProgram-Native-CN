# Native Workflow Sample Migration

This sample migrates a small read-only review workflow from the legacy runner model to one Native Workflow JS file.

Covered Native runtime concepts:

- explicit `phase()` ordering;
- `pipeline()` over deterministic candidates;
- nested `parallel()` read-only reviews;
- inline structured `agent()` calls;
- schema validation;
- a JavaScript blocked-path gate;
- a stable return envelope.

Generate a fresh candidate:

```bash
python .claude/scripts/generate-native-workflow.py \
  --spec tests/manual-fixtures/native-workflow-sample-migration/authoring-spec.json \
  --readiness tests/manual-fixtures/native-workflow-sample-migration/confirmed-readiness.json \
  --target-root <target-root> \
  --run-root <run-root> \
  --json
```

From an interactive WSL Claude Code session with Native Workflows enabled, invoke:

```text
Workflow({
  scriptPath: "/mnt/d/Code/WorkflowProgram-CN/tests/manual-fixtures/native-workflow-sample-migration/target-root/.claude/workflows/workflowprogram-native-sample-migration.js"
})
```

Expected result:

```json
{
  "status": "PASS",
  "workflow": "workflowprogram-native-sample-migration",
  "blockingIssues": []
}
```

This repository validates the script statically and regenerates it in unit tests. The interactive execution remains a manual smoke because Native Workflow availability is context-specific.
