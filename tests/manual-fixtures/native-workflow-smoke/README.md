# Native Workflow Smoke Fixture

This fixture probes the smallest useful migration assumption: Claude Code can execute a user-authored native Workflow JS control plane through `Workflow({ scriptPath })`.

The fixture is intentionally read-only:

- one explicit phase;
- one structured subagent;
- one JS gate;
- no filesystem API;
- no target-project writes.

From WSL, ask Claude Code to invoke:

```text
Workflow({
  scriptPath: "/mnt/d/Code/WorkflowProgram-CN/tests/manual-fixtures/native-workflow-smoke/target-root/.claude/workflows/workflowprogram-native-smoke.js"
})
```

Expected workflow result:

```json
{
  "status": "PASS",
  "workflow": "workflowprogram-native-smoke",
  "blockingIssues": []
}
```

## Observed Result On 2026-06-01

The interactive smoke workflow passed when Claude Code was launched manually from the fixture target root with `CLAUDE_CODE_WORKFLOWS=1`.

Observed workflow result:

```json
{
  "status": "PASS",
  "workflow": "workflowprogram-native-smoke",
  "blockingIssues": [],
  "probe": {
    "status": "PASS",
    "wroteFiles": false
  }
}
```

Observed execution metadata:

- Session ID: `eb6802d3-b6f6-4e0a-b728-13f4f8f2cb0d`
- Run ID: `wf_c719aa99-826`
- Agent count: `1`
- Total tokens: `13034`
- Duration: `7065ms`

JSONL evidence:

- `\\wsl.localhost\Ubuntu-22.04\home\zhde\.claude\projects\-mnt-d-Code-WorkflowProgram-CN-tests-manual-fixtures-native-workflow-smoke-target-root\eb6802d3-b6f6-4e0a-b728-13f4f8f2cb0d.jsonl`
  - line 5: user prompt with the `ultrawork` keyword and target JS path;
  - line 7: initial `skill_listing` includes `workflowprogram-native-smoke`;
  - line 8: `ultrawork_request` attachment;
  - line 16: assistant invokes `Workflow({ scriptPath })`;
  - line 17: Workflow runtime returns `async_launched` and Run ID `wf_c719aa99-826`;
  - line 28: completion notification returns the structured `PASS` result.
- `\\wsl.localhost\Ubuntu-22.04\home\zhde\.claude\projects\-mnt-d-Code-WorkflowProgram-CN-tests-manual-fixtures-native-workflow-smoke-target-root\eb6802d3-b6f6-4e0a-b728-13f4f8f2cb0d\subagents\workflows\wf_c719aa99-826\journal.jsonl`
  - line 1: structured probe agent started;
  - line 2: structured probe agent returned `status: PASS` and `wroteFiles: false`.

## Context-Specific Failure Observed During Automation

Earlier non-interactive and separately launched contexts returned:

```text
Workflow exists but is not enabled in this context.
```

The local Claude Code binary contains both `CLAUDE_CODE_WORKFLOWS` and the dynamic feature flag `tengu_workflows_enabled`. Therefore, every supported execution mode still needs an explicit capability probe. The passing interactive result proves that user-authored JS control planes are executable; it does not prove that every Claude Code entrypoint enables the Workflow tool.

Classify the recorded JSONL again with:

```bash
python .claude/scripts/probe-native-workflow-capability.py \
  --jsonl '\\wsl.localhost\Ubuntu-22.04\home\zhde\.claude\projects\-mnt-d-Code-WorkflowProgram-CN-tests-manual-fixtures-native-workflow-smoke-target-root\eb6802d3-b6f6-4e0a-b728-13f4f8f2cb0d.jsonl' \
  --workflow workflowprogram-native-smoke \
  --json
```

The probe reports listing evidence at line 7, launch evidence at line 17, and structured completion evidence at lines 26 and 28.
