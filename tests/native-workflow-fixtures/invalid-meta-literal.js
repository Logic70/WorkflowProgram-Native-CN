const meta = {
  name: 'invalid-meta-literal',
  description: 'This header is not exported.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
return { status: 'PASS' }
