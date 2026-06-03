# Native Workflow Authoring Meta-Workflow Smoke

This smoke validates the WorkflowProgram plugin's own read-only Native authoring workflow.

The foreground skill must clarify requirements, read the scope back to the user, receive explicit confirmation, and pass `validate-native-authoring-readiness.py` before launching this workflow.

The checked-in packet targets `/mnt/d/Code/workflowprogram-native-trial`. If you use another target root, update `confirmed-readiness.json` and the invocation together.

Before launching the meta-workflow, run:

```bash
python3 /mnt/d/Code/WorkflowProgram-CN/dist/plugin/scripts/validate-native-authoring-readiness.py \
  --packet /mnt/d/Code/WorkflowProgram-CN/tests/manual-fixtures/native-workflow-authoring/confirmed-readiness.json \
  --target-root /mnt/d/Code/workflowprogram-native-trial \
  --json
```

From an interactive WSL Claude Code session with `CLAUDE_CODE_WORKFLOWS=1`, ask Claude Code to invoke:

```text
Workflow({
  scriptPath: "/mnt/d/Code/WorkflowProgram-CN/dist/plugin/workflows/workflowprogram-native-authoring.js",
  args: {
    requirement: "Create a read-only code review workflow that checks correctness and test gaps with two parallel reviewers and returns a structured verdict.",
    targetRoot: "/mnt/d/Code/workflowprogram-native-trial",
    readinessPacket: "/mnt/d/Code/WorkflowProgram-CN/tests/manual-fixtures/native-workflow-authoring/confirmed-readiness.json",
    readinessStatus: "PASS"
  }
})
```

Expected behavior:

- `/workflows` shows `workflowprogram-native-authoring`;
- phases advance through `Explore`, `Design`, `Review`, and `Handoff`;
- the workflow does not write target files;
- the structured result is `PASS` or an explicit `BLOCKED_*` state.

The automated suite statically validates the JS and verifies dist packaging. Interactive `/workflows` visibility remains a manual smoke because Workflow availability is context-specific.
