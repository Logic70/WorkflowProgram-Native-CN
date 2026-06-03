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
| forbidden API | `fs`, `require()`, `process`, `Date.now()`, `Math.random()`, or zero-argument `new Date()` |
| schema presence | gate-consumed Agent output has no schema |
| parallel write hint | parallel prompts visibly write the same directory |
| return envelope | no stable `status` or equivalent final result |

Do not claim complete semantic validation.

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
