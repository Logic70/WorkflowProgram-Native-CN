export const meta = {
  name: 'invalid-undeclared-api',
  description: 'The script calls Bash() as if it were a Native Workflow JS global.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
const result = Bash('ls -la')
return { status: result ? 'PASS' : 'BLOCKED' }
