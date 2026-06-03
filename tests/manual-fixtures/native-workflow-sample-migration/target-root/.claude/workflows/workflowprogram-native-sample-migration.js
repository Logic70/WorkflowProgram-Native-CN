export const meta = {
  name: 'workflowprogram-native-sample-migration',
  description: 'Exercise Native Workflow JS pipeline, parallel review, structured Agents, and a JS gate.',
  phases: [
    {
      title: 'Intake',
      detail: 'Create deterministic review candidates.',
    },
    {
      title: 'Review',
      detail: 'Use pipeline and parallel structured Agents.',
    },
    {
      title: 'Decide',
      detail: 'Gate the final result in JavaScript.',
    },
  ],
}

phase('Intake')

const candidates = [
  { id: 'sample-a', summary: 'Read-only migration probe A' },
  { id: 'sample-b', summary: 'Read-only migration probe B' },
]

phase('Review')

const reviewed = await pipeline(
  candidates,
  async (candidate) => {
    const votes = await parallel(
      ['correctness', 'boundary'].map(lens => () =>
        agent(
          `Review ${candidate.id} through the ${lens} lens. This is read-only. Do not use tools or write files. Return PASS and a short reason.`,
          {
            label: `sample:${candidate.id}:${lens}`,
            schema: {
              type: 'object',
              properties: {
                status: { type: 'string', enum: ['PASS'] },
                reason: { type: 'string' },
              },
              required: ['status', 'reason'],
              additionalProperties: false,
            },
          },
        )
      ),
    )
    return { candidate, votes }
  },
)

phase('Decide')

const blocked = reviewed.filter(item => item.votes.some(vote => vote.status !== 'PASS'))
if (blocked.length > 0) {
  return {
    status: 'BLOCKED_REVIEW',
    workflow: 'workflowprogram-native-sample-migration',
    blockingIssues: blocked,
  }
}

return {
  status: 'PASS',
  workflow: 'workflowprogram-native-sample-migration',
  blockingIssues: [],
  reviewed,
}
