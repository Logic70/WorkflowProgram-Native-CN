<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# Positive Example: Phase Boundaries

## Request

Build a Native Workflow JS control plane that analyzes a target, reviews the
analysis, generates a candidate, and returns a controlled generation handoff.

## Correct Phase Plan

| Phase | Why It Is A Phase |
|---|---|
| Analyze | Produces the analysis object consumed by later gates |
| Review | Has an independent blocking gate and required revisions |
| Author | Converts reviewed design into an authoring spec |
| Generate | Triggers a controlled side-effect handoff |

## Workflow JS Pattern

```javascript
phase('Analyze')
const analyses = await parallel([
  () => agent('Inspect target context. Return facts and constraints.', {
    label: 'example:target-context',
    schema: analysisSchema,
  }),
  () => agent('Inspect runtime boundaries. Return facts and constraints.', {
    label: 'example:runtime-boundaries',
    schema: analysisSchema,
  }),
])

phase('Review')
const review = await agent(`Review analyses:\n${JSON.stringify(analyses)}`, {
  label: 'example:review',
  schema: reviewSchema,
})
if (review.status !== 'PASS' || review.requiredRevisions.length > 0) {
  return {
    status: 'BLOCKED_REVIEW',
    blockingIssues: review.requiredRevisions,
    nextAction: 'FIX_DESIGN_AND_REINVOKE',
  }
}

phase('Author')
const authoringSpec = await agent('Create the locked authoring spec.', {
  label: 'example:author',
  schema: authoringSpecSchema,
})

phase('Generate')
return {
  status: 'READY_FOR_GENERATION',
  authoringSpec,
  nextAction: 'RUN_CONTROLLED_GENERATION',
}
```

## Review Verdict

PASS. Each phase changes continuation, evidence, recovery, or side-effect state.
The two parallel analysis agents remain inside one phase because they share one
objective and one downstream gate.
