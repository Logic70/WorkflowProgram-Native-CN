export const meta = {
  name: 'invalid-forbidden-api',
  description: 'The script uses a nondeterministic API.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const value = Math.random()
return { status: value ? 'PASS' : 'BLOCKED' }
