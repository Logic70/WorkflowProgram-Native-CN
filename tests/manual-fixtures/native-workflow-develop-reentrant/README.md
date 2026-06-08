# Native Develop Re-entrant Foreground Args Smoke

This fixture verifies the first real M9 product-control-plane branch: the packaged `workflowprogram-develop.js` must execute through the Claude Code `Workflow` tool and reject an incomplete invocation with a structured foreground re-entry instruction.

## Preconditions

- start Claude Code from a shell that exports `CLAUDE_CODE_WORKFLOWS=1`;
- preserve the shell feature-flag environment when automating an interactive session;
- build the plugin with `python tools/build_plugin.py`;
- invoke the plugin workflow by absolute `scriptPath`.

The verified WSL environment also exports `DISABLE_GROWTHBOOK=1`. A PTY launcher that bypassed the login shell did not receive the same Workflow tool surface. A login shell worked both with and without `--plugin-dir /mnt/d/Code/WorkflowProgram-CN/dist/plugin`.

## Prompt

```text
ultrawork Directly call the Workflow tool with scriptPath "/mnt/d/Code/WorkflowProgram-CN/dist/plugin/workflows/workflowprogram-develop.js" and args {}. Do not invoke a Skill and do not explain. Return the raw tool result.
```

## Expected Result

```json
{
  "status": "NEEDS_FOREGROUND_ARGS",
  "workflow": "workflowprogram-develop",
  "launchMode": "plugin-script-path",
  "runId": "",
  "missingArgs": [
    "request",
    "targetRoot",
    "runRoot",
    "runId"
  ],
  "nextAction": "DERIVE_ARGS_AND_REINVOKE"
}
```

## Observed Result On 2026-06-02

Session ID: `76a1d027-5658-43ec-8758-6e864130dc92`

Run ID: `wf_6985755b-66f`

Evidence:

- JSONL line 12 invokes `Workflow({ scriptPath, args: {} })`;
- JSONL line 14 reports background launch and Run ID `wf_6985755b-66f`;
- JSONL line 21 reports the historical structured `BLOCKED_INPUT` result;
- the returned result is not the old M8 `NOT_IMPLEMENTED` envelope.

Windows-accessible JSONL path:

```text
\\wsl.localhost\Ubuntu-22.04\home\zhde\.claude\projects\-mnt-d-Code-workflowprogram-native-m9-trial\76a1d027-5658-43ec-8758-6e864130dc92.jsonl
```

## Scope

This is an early foreground-args smoke for M9. The M11 Computer Use harness still needs to cover the complete interactive lifecycle: Skill discovery, clarification, confirmation, agent execution, schema validation, generation, validation, smoke evidence, controlled apply, and final delivery.
