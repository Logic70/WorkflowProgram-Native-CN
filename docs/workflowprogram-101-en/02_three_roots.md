# Ch2: Three Roots — Why `PLUGIN_ROOT`, `TARGET_ROOT`, And `RUN_ROOT` Must Be Separate

> Once inputs, outputs, and evidence are mixed together, a workflow becomes hard to govern.

## The Three Roots

The current model separates directories into three roles:

- `PLUGIN_ROOT`
  - plugin payload and reference assets
- `TARGET_ROOT`
  - the user project that receives the final workflow assets
- `RUN_ROOT`
  - isolated runtime evidence and intermediate artifacts for one run

This is the basic boundary contract of the whole system.

## Why This Separation Matters

Without it, two failure modes show up quickly:

1. plugin assets and target assets get mixed together, so you cannot tell input from output
2. runtime evidence lands in the delivery directory, which is hard to clean and hard to audit later

That is why WorkflowProgram writes "what happened during this run" into `RUN_ROOT`.

## What The Current Layout Looks Like

The key directory relationship is:

```text
TARGET_ROOT/
├── .claude/                        # final delivery
└── .workflowprogram/
    ├── managed-files.json
    └── runs/<run-id>/              # RUN_ROOT
```

`RUN_ROOT` has a minimum evidence bundle:

- `context.json`
- `state.json`
- `events.jsonl`
- `transcript.md`
- `validation-runtime-report.md`

## What This Means In Practice

If you want to understand a run, start with `RUN_ROOT`, not with the final `.claude/` tree.

Why:

- `.claude/` tells you what survived in the end
- `RUN_ROOT` tells you why it survived

## Practical Template

When you design your own workflow, write down these three answers first:

1. where reference assets are read from
2. where final assets are written
3. where runtime evidence is stored

If these are not explicit, every later boundary rule will drift.

## Next Chapter

Continue to [Ch3: Stage Model](./03_stage_model.md).
