export const meta = {
  name: 'invalid-parallel-write',
  description: 'Parallel Agents visibly write the same directory.',
  phases: [{ title: 'Generate' }],
}

phase('Generate')
await parallel([
  () => agent('Write files under docs/output/.'),
  () => agent('Edit files in docs/output/.'),
])
return { status: 'PASS' }
