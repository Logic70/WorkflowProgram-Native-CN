<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# Negative Example: Noisy Phase Boundaries

## Request

Analyze a target and generate a candidate Native Workflow JS file.

## Incorrect Workflow JS Pattern

```javascript
phase('Read Prompt')
const requestText = args.request

phase('Think')
const normalized = requestText.trim()

phase('Call Agent A')
const targetFacts = await agent('Inspect target files.', {
  label: 'bad:target',
  schema: factsSchema,
})

phase('Call Agent B')
const runtimeFacts = await agent('Inspect runtime files.', {
  label: 'bad:runtime',
  schema: factsSchema,
})

phase('Format JSON')
const designInput = { targetFacts, runtimeFacts }
```

## Problems

- `Read Prompt`, `Think`, and `Format JSON` are helper/data-transform steps.
- `Call Agent A` and `Call Agent B` are same-objective exploration agents.
- There is no independent exit gate between the two agents.
- There is no distinct failure recovery or side-effect boundary.

## Correct Rewrite

```javascript
phase('Analyze')
const [targetFacts, runtimeFacts] = await parallel([
  () => agent('Inspect target files.', { label: 'good:target', schema: factsSchema }),
  () => agent('Inspect runtime files.', { label: 'good:runtime', schema: factsSchema }),
])

const designInput = { targetFacts, runtimeFacts }
```

## Review Verdict

BLOCKED. The incorrect version creates progress labels instead of semantic
execution boundaries.
