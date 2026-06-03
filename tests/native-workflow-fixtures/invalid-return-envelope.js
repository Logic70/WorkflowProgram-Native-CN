export const meta = {
  name: 'invalid-return-envelope',
  description: 'The workflow does not return a stable status.',
  phases: [{ title: 'Probe' }],
}

phase('Probe')
return { result: 'done' }
