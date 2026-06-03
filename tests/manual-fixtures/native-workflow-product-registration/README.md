# Native Product Workflow Plugin Script-Path Smoke

This fixture verifies the M8 deployment contract for the five WorkflowProgram product-level Native Workflow JS skeletons.

M8 does not implement business control flow. Every product workflow is packaged inside the plugin and must return `NOT_IMPLEMENTED`, its future migration milestone, the `plugin-script-path` launch mode, and a legacy delegation hint.

> Historical snapshot: this fixture records the M8 registration state. M9 later upgraded develop, M10A upgraded validate and audit, M10B upgraded iterate, and M10C upgraded publish. No product `NOT_IMPLEMENTED` skeleton remains.

## Preconditions

- build the plugin with `python tools/build_plugin.py`;
- install or refresh the built plugin in an interactive Claude Code CLI session with Native Workflow enabled;
- resolve the installed plugin root to an absolute path before invoking `Workflow`.

## Positive Script-Path Launch Check

Ask Claude Code to invoke one plugin-packaged skeleton directly:

```text
ultrawork 不要调用 Skill，不要生成新工作流。直接调用 Workflow 工具：
Workflow({
  scriptPath: "/mnt/d/Code/WorkflowProgram-CN/dist/plugin/workflows/workflowprogram-develop.js",
  args: {}
})
返回原始工具结果。
```

Expected Workflow tool call:

```text
Workflow({
  scriptPath: "/mnt/d/Code/WorkflowProgram-CN/dist/plugin/workflows/workflowprogram-develop.js",
  args: {}
})
```

Expected result:

```json
{
  "status": "NOT_IMPLEMENTED",
  "workflow": "workflowprogram-develop",
  "capability": "develop",
  "launchMode": "plugin-script-path",
  "migrationMilestone": "M9",
  "blockingIssues": [
    "Native develop control flow is packaged but not implemented until M9."
  ],
  "legacyDelegation": {
    "supported": true,
    "entrySkill": "workflowprogram-develop"
  }
}
```

## Negative Name Lookup Check

Plugin-packaged `workflows/*.js` are not assumed to become saved workflows automatically. Verify the deployment boundary explicitly:

```text
ultrawork 不要调用 Skill，不要使用 scriptPath。直接调用 Workflow 工具：
Workflow({
  name: "workflowprogram-develop",
  args: {}
})
返回原始工具结果。
```

Expected result in the verified Claude Code CLI version:

```text
Workflow "workflowprogram-develop" not found.
```

Saved project or user workflows can still use `Workflow({ name, args })` when they are discoverable by the runtime. That is a separate capability from plugin product workflow distribution.

## Observed Result On 2026-06-02

Session ID: `6bc6f041-26dc-406c-bddc-a473a55a3891`

Evidence:

- JSONL line 10 invokes `Workflow({ scriptPath, args })`;
- JSONL line 12 reports background launch with run ID `wf_06936dea-e65`;
- JSONL line 18 returns the structured `NOT_IMPLEMENTED` envelope;
- JSONL line 27 invokes `Workflow({ name, args })`;
- JSONL line 28 reports that `workflowprogram-develop` was not found and lists only built-in saved workflows.

The observed CLI run predates the explicit `launchMode` field added after this boundary was verified. The run proves plugin `scriptPath` launch support. Static tests and the rebuilt plugin payload enforce the updated `plugin-script-path` envelope.

Windows-accessible JSONL path:

```text
\\wsl.localhost\Ubuntu-22.04\home\zhde\.claude\projects\-mnt-d-Code-workflowprogram-native-trial\6bc6f041-26dc-406c-bddc-a473a55a3891.jsonl
```

## M8 Conclusion

The supported product deployment contract is:

```text
WorkflowProgram Skill
  -> resolve absolute plugin root
  -> Workflow({ scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-*.js", args })
  -> Native Workflow JS control plane
```

Repeat full interactive smoke checks for audit, validate, iterate, and publish under M11.
