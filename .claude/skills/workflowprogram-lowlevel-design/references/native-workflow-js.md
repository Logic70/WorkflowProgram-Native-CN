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

## Phase Boundary Contract

Use `phase(title)` for semantic execution boundaries, not progress labels. A process is a Phase candidate when it has an independent purpose and at least one of these properties:

- a clear input/output handoff;
- an exit gate that can continue, block, re-enter, ask the user, or trigger side effects;
- distinct failure recovery or `nextAction`;
- a side-effect boundary such as write, apply, publish, or commit;
- different executor, permission, model, or tool needs;
- distinct evidence required for trust.

If completing this process changes whether the workflow continues, blocks, re-enters, asks the user, or performs side effects, it is a Phase candidate.

Do not create a Phase for a single prompt paragraph, helper function, data transform, several parallel Agents under one objective and one gate, progress-only split, or logic with no independent gate, evidence, or recovery path. Keep parallel exploration under the same readiness gate in one Phase unless the outputs are independently consumed or failures recover differently.

See implementation examples:

- `references/examples/phase-boundary-positive.md`
- `references/examples/phase-boundary-negative.md`

## Existing Workflow Migration Contract

Use this contract for `operation=migrate`, `request_kind=redesign_existing`, or `target_state=existing_managed_workflow`. Do not introduce a separate product term for this mode.

Exploration must classify results into current facts, migration tasks, true blockers, user decisions, source-of-truth inputs, and asset-disposition hints. Expected migration work is not a design blocker.

Treat these as migration tasks unless no behavioral source of truth exists or write boundaries are unclear:

- missing target `.claude/workflows/<name>.js`;
- stale `workflow-spec.yaml` or older design metadata;
- retired `.workflowprogram/runtime/`;
- stale `managed-files.json`;
- duplicate legacy assets;
- no existing Native Workflow JS reference.

True blockers are limited to conditions that prevent a trustworthy design, such as unreadable target roots, no usable source of truth, unresolved user decisions that change topology, unclear write boundaries, or missing required assets with no replacement.

Source-of-truth priority is:

1. explicit user decisions from the current request or re-entry;
2. current command or entrypoint behavior;
3. current Agents and Skills;
4. current design metadata;
5. retired runtime behavior;
6. historical candidates as reference only.

See implementation examples:

- `references/examples/migrate-existing-workflow-positive.md`
- `references/examples/migrate-existing-workflow-negative.md`

## Agent Contract

Define prompt, label, schema, consumed fields, and failure behavior. Any field read by a JS gate must be declared in the schema.

Keep workflow-specific prompts inline. Extract reusable Agents only for cross-workflow reuse, independent invocation, independent permissions, or separately versioned long prompts.

Named semantic roles are reusable assets, not prompt decorations. If a role such as requirement clarification lead, design reviewer, workflow designer, or authoring spec generator owns durable definitions or is referenced by multiple skills/workflows, define it as a dedicated Agent or shared reference and call it through `agentType`. Do not emulate the role by writing "you are <role>" inside a foreground prompt. JS should pass task-local inputs and enforce gates; the Agent/reference should own the reusable semantics; validators should enforce required fields and handoff completeness.

Requirement clarification Agents must receive settled platform decisions as explicit context. They should ask only target-specific questions that can change workflow phases, gates, evidence, acceptance, or boundaries. Do not ask the user to re-decide WorkflowProgram platform policy such as "Native Workflow JS is the runtime truth", "workflow-local prompts are inline by default", "registered Agents are used only for reusable roles", or "target writes go through candidate plus managed apply".

## Validation Layers

| Layer | Responsibility | Implementation |
|---|---|---|
| L1 Schema | types, required fields, enums, shapes | `agent(..., { schema })` |
| L2 JS Gate | thresholds, quorum, coverage, duplicate IDs, transitions, early return | ordinary JavaScript |
| L3 External Fact | files, builds, tests, Git state, report consistency | Agent invoking CLI or deterministic domain script |

Schema does not prove external truth.

If a review schema contains both `blockingIssues` and `requiredRevisions`, the JS gate must treat either non-empty list as blocking. `status: PASS` is insufficient when required revisions remain open.

## Static Validator Minimum Rules

| Rule | Failure |
|---|---|
| meta literal | script does not start with pure-literal `export const meta = {...}` |
| required meta | missing `name` or `description` |
| phase alignment | `meta.phases` and `phase()` visibly diverge |
| forbidden API | `fs`, `require()`, `process`, dynamic code execution (`eval()` / `Function()`), `Date.now()`, `Math.random()`, or zero-argument `new Date()` |
| unsupported host tool reference | direct calls or bare references to `Bash`, `Read`, `Write`, or other Claude Code host tools outside `agent()` |
| unsupported Agent option | top-level `agent()` option keys outside the supported Native Workflow JS contract (`label`, `phase`, `schema`, `model`, `isolation`, `agentType`), such as `skills` |
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

## Foreground Guard Contract

Product JS controls phase ordering, but the foreground assistant still performs re-entry, controlled scripts, and user communication. A target workflow design should specify how foreground bypass is prevented:

- after every product JS result, persist a run state such as `TARGET_ROOT/.workflowprogram/session-state.json`;
- `NEEDS_USER_INPUT`, `READY_FOR_CONFIRMATION`, and `BLOCKED_*` states are read-only from the foreground perspective;
- `READY_FOR_GENERATION`, `READY_FOR_VALIDATION`, `READY_FOR_SMOKE`, and `READY_FOR_APPLY` permit only the named controlled script for that state;
- direct foreground edits to managed target paths such as `.claude/**`, `.workflowprogram/design/**`, and `.workflowprogram/runtime/**` are forbidden;
- commits require a final `PASS` with `deliveryMode=managed-apply` and an `applyManifest` with entries.

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
