export const meta = {
  name: 'invalid-undeclared-identifier',
  description: 'The script references runId without declaring it.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
return { status: 'PASS', workflow: 'probe', runId }
