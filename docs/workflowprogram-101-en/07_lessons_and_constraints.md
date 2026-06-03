# Ch7: Lessons And Constraints — Why `S6` Is Not Optional

> A workflow that cannot learn will eventually repeat the same mistakes.

## What `S6` Owns

WorkflowProgram explicitly makes experience accumulation part of `S6`, not an off-flow afterthought.

Its goals are:

- extract lessons
- produce constraint candidates
- give the next-round improvement direction

That means feedback itself is part of the workflow.

## The Two-Level Memory Model

The current design separates memory into two layers:

- `lessons.md`
  - append-only log
  - failures, conflicts, and candidate constraints
- `.claude/rules/constraints.md`
  - long-lived rules
  - stable ALWAYS/NEVER guidance

This is the core of the memory model documented in [CLAUDE.md](/mnt/d/Code/WorkflowProgram-CN/CLAUDE.md).

## What Is Already Hardened In Code

The minimum `S6` loop is already machine-checkable:

- `RUN_ROOT/outputs/stages/s6-lessons-delta.md` must exist
- it must contain the current `run_id`
- it must contain the current `failure_kind`
- it must include either constraint candidates or an explicit "no new constraints"
- `user-progress.md` must include historical key-node results

This is validated by [validate-lessons-delta.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/validate-lessons-delta.py).

## Why WorkflowProgram Is Its Own Best Example

`WorkflowProgram-CN` applies the same loop to itself:

- it maintains its own `lessons.md`
- it maintains its own `constraints.md`
- it uses active design docs and the capability matrix to prevent drift

So it does not only demand a feedback loop from downstream workflows. It runs through the same loop itself.

## Practical Template

A workflow that learns should at least answer:

1. where failure records go
2. which experience stays as log and which becomes a rule
3. what new sessions load by default
4. which lessons flow into the next run

Without this layer, a workflow can execute, but it cannot evolve.

## Next Chapter

Continue to [Ch8: Apply To Your Project](./08_apply_to_your_project.md).
