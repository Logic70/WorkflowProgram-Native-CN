export const meta = {
  name: 'invalid-agent-skills-option',
  description: 'Agent options must not use unsupported skills lists.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const probe = await agent('Return PASS.', {
  label: 'probe',
  skills: ['browser-use'],
  schema: {
    type: 'object',
    properties: {
      status: { type: 'string' },
    },
    required: ['status'],
  },
})
return { status: probe.status }
