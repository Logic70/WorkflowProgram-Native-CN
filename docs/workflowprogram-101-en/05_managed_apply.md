# Ch5: Managed Apply — Why You Should Not Overwrite The Target Project Directly

> Being able to write a file does not mean you should write it directly.

## What Goes Wrong With Direct Writes

If the workflow writes directly into the target project, three risks show up quickly:

1. user-maintained files get overwritten
2. there is no clear ownership model for tool-managed files
3. when conflicts happen, intermediate evidence is lost

That is why WorkflowProgram separates "generate the result" from "apply it to the project".

## The More Stable Pattern

This write chain should have at least three steps:

1. write the result into an isolated candidate area
2. generate a change plan that classifies create/update/conflict
3. apply the plan in a managed way

## Why This Matters

This gives you:

- early conflict detection
- a stable managed-file inventory
- preserved candidate and conflict copies
- a clean separation between generation and writing

That separation is critical for later validation and audit.

## The Current Mapping

The key outputs are:

- `RUN_ROOT/outputs/candidate/.claude/`
- `RUN_ROOT/outputs/managed-change-plan.json`
- `RUN_ROOT/outputs/managed-change-result.json`
- `TARGET_ROOT/.workflowprogram/managed-files.json`

To understand this layer, start with:

1. [managed-assets.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/managed-assets.py)
2. [workflow-entry.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-entry.py)
3. the target-asset update contract in [README.md](/mnt/d/Code/WorkflowProgram-CN/README.md)

## Practical Template

If your workflow modifies a user project, default to this pattern:

1. generate candidates first
2. build a change plan
3. apply changes in a managed way
4. preserve evidence on conflict instead of silently overwriting files

That is a hard engineering boundary between a toy workflow and a product workflow.

## Next Chapter

Continue to [Ch6: Validation First](./06_validation.md).
