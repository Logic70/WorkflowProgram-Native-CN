export const meta = {
  name: 'valid-minimal',
  description: 'Validate the smallest useful native workflow.',
  phases: [
    { title: 'Probe' },
  ],
}

phase('Probe')

const probe = await agent('Return a structured PASS result.', {
  label: 'probe',
  schema: {
    type: 'object',
    properties: {
      status: { type: 'string', enum: ['PASS'] },
    },
    required: ['status'],
  },
})

if (probe.status !== 'PASS') {
  return { status: 'BLOCKED_PROBE' }
}

return { status: 'PASS' }
