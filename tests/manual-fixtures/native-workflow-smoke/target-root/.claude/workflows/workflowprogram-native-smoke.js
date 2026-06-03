export const meta = {
  name: 'workflowprogram-native-smoke',
  description: 'Verify that Claude Code can execute a user-authored native Workflow JS control plane.',
  phases: [
    {
      title: 'Probe',
      detail: 'Run one read-only structured subagent and gate on its result.',
    },
  ],
}

phase('Probe')

const probe = await agent(
  [
    'Act as a read-only native Workflow smoke probe.',
    'Do not use tools and do not create, edit, or delete files.',
    'Return status PASS, wroteFiles false, and a short message confirming that the structured subagent executed.',
  ].join(' '),
  {
    label: 'native-workflow-smoke-probe',
    schema: {
      type: 'object',
      properties: {
        status: {
          type: 'string',
          enum: ['PASS'],
        },
        wroteFiles: {
          type: 'boolean',
        },
        message: {
          type: 'string',
        },
      },
      required: ['status', 'wroteFiles', 'message'],
      additionalProperties: false,
    },
  },
)

if (probe.status !== 'PASS' || probe.wroteFiles !== false) {
  return {
    status: 'BLOCKED_PROBE',
    blockingIssues: ['The read-only smoke probe did not return the required structured result.'],
    probe,
  }
}

return {
  status: 'PASS',
  workflow: 'workflowprogram-native-smoke',
  blockingIssues: [],
  probe,
}
