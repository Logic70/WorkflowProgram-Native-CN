export const meta = {
  name: 'invalid-gate-without-schema',
  description: 'The gate consumes an Agent output without a schema.',
  phases: [{ title: 'Review' }],
}

phase('Review')
const review = await agent('Return a verdict.', { label: 'reviewer' })
if (review.verdict !== 'PASS') {
  return { status: 'BLOCKED_REVIEW' }
}
return { status: 'PASS' }
