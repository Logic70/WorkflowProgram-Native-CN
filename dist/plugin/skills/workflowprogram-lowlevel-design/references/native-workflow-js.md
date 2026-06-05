<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# Native Workflow JS Detailed Contracts

## Script Shape

Require a pure-literal header:

```javascript
export const meta = {
  name: 'example-workflow',
  description: 'Describe the workflow.',
  phases: [{ title: 'Plan' }, { title: 'Verify' }],
}
```

Use native APIs and ordinary JavaScript:

- `phase(title)`
- `agent(prompt, options)`
- `parallel(thunks)`
- `pipeline(items, stages...)`
- `workflow(nameOrRef, args)`
- conditions, loops, aggregation, and early returns

Align `meta.phases[*].title` with `phase(title)`.

## Agent Contract

Define prompt, label, schema, consumed fields, and failure behavior. Any field read by a JS gate must be declared in the schema.

Keep workflow-specific prompts inline. Extract reusable Agents only for cross-workflow reuse, independent invocation, independent permissions, or separately versioned long prompts.

Named semantic roles are reusable assets, not prompt decorations. If a role such as requirement clarification lead, design reviewer, workflow designer, or authoring spec generator owns durable definitions or is referenced by multiple skills/workflows, define it as a dedicated Agent or shared reference and call it through `agentType`. Do not emulate the role by writing "you are <role>" inside a foreground prompt. JS should pass task-local inputs and enforce gates; the Agent/reference should own the reusable semantics; validators should enforce required fields and handoff completeness.

## Validation Layers

| Layer | Responsibility | Implementation |
|---|---|---|
| L1 Schema | types, required fields, enums, shapes | `agent(..., { schema })` |
| L2 JS Gate | thresholds, quorum, coverage, duplicate IDs, transitions, early return | ordinary JavaScript |
| L3 External Fact | files, builds, tests, Git state, report consistency | Agent invoking CLI or deterministic domain script |

Schema does not prove external truth.

## Static Validator Minimum Rules

| Rule | Failure |
|---|---|
| meta literal | script does not start with pure-literal `export const meta = {...}` |
| required meta | missing `name` or `description` |
| phase alignment | `meta.phases` and `phase()` visibly diverge |
| forbidden API | `fs`, `require()`, `process`, dynamic code execution (`eval()` / `Function()`), `Date.now()`, `Math.random()`, or zero-argument `new Date()` |
| unsupported host tool reference | direct calls or bare references to `Bash`, `Read`, `Write`, or other Claude Code host tools outside `agent()` |
| high-confidence undeclared identifier | a critical runtime identifier such as `runId` is referenced without a visible declaration |
| schema presence | gate-consumed Agent output has no schema |
| parallel write hint | parallel prompts visibly write the same directory |
| return envelope | no stable `status` or equivalent final result |

Do not claim complete semantic validation. The undeclared-identifier check is intentionally conservative and is not a replacement for a JavaScript linter.

## Smoke Contract

Minimum:

- capability probe;
- discovery smoke;
- launch smoke;
- structured Agent smoke;
- schema smoke;
- JS gate smoke.

Add blocked-path, parallel, pipeline, external-fact, resume, or publish smoke for higher-risk workflows.

Record JSONL session evidence when proving Claude Code runtime behavior.

The develop evidence adapter must accept only evaluator PASS reports produced by `build-native-interactive-smoke.py evaluate`. A smoke PASS report must prove Workflow invocation, asynchronous launch, Agent start, structured schema output, a non-empty run ID, and the expected completion status. It must also bind the actual invocation to the exact candidate `scriptPath`, `scriptHash`, `candidateHash`, and a non-empty scenario identifier. A raw JSONL path, arbitrary transcript, or same-name workflow launched from another path is not smoke evidence.

Generation and validation evidence must likewise come from their real report schemas (`native-workflow-js-generation` and `native-workflow-js-validation`) and identify a script inside the current candidate tree. Do not normalize arbitrary `{"status":"PASS"}` objects.

## Controlled Apply Contract

`applyEvidence` is bound to the requested `targetRoot`, and `applyManifest` is a structured object, not a path string. It contains:

- `manifestPath`: the actual target `.workflowprogram/managed-files.json`;
- `reportPath`: the actual `managed-change-result` report;
- `entries`: candidate paths with `create | update | noop` action and candidate SHA-256.

The evidence adapter must require the explicit target root, verify that the managed result binds the same candidate source and target, load the persisted result from `RUN_ROOT/outputs/managed-change-result.json`, require the target `.workflowprogram/managed-files.json`, and verify every target file still matches the candidate hash before returning PASS.

## Asset Disposition Contract

Keep generated content and migration intent separate:

- `supporting_assets` contains only files staged into the candidate tree;
- `asset_disposition` records how existing or target assets are treated.

For `update` and `migrate`, `asset_disposition` is required. Valid actions are `retain`, `generate`, `update`, `archive`, `remove`, `defer`, and `not-applicable`. `generate`, `update`, and `archive` must reference a matching `supporting_asset_path`. `archive` and `remove` remain explicit migration follow-up actions unless the controlled apply implementation proves that it executed them.
