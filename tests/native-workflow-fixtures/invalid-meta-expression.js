export const meta = {
  name: 'invalid-meta-expression',
  description: 'Computed phase metadata is not a pure literal.',
  phases: buildPhases(),
}

phase('Probe')

return { status: 'PASS' }
