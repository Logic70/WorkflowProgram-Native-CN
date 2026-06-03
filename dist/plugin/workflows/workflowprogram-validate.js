export const meta = {
  name: 'workflowprogram-validate',
  description: 'Plugin-packaged Native Workflow JS entry for WorkflowProgram validate migration.',
  phases: [
    { title: 'Discover', detail: 'Validate required inputs before requesting host-side inventory evidence.' },
    { title: 'Static Validate', detail: 'Request or consume deterministic static validation evidence.' },
    { title: 'External Verify', detail: 'Request or consume external toolchain verification evidence.' },
    { title: 'Report', detail: 'Return the final validated result with delivery instructions.' },
  ],
}

const workflowName = 'workflowprogram-validate'
const launchMode = 'plugin-script-path'
const asArray = value => Array.isArray(value) ? value : []
const nonEmpty = value => typeof value === 'string' && value.trim().length > 0
const nonEmptyArray = value => asArray(value).length > 0 && asArray(value).every(nonEmpty)
const respond = (status, extra = {}) => {
  return {
    status: status,
    workflow: workflowName,
    launchMode,
    runId: args?.runId || '',
    blockingIssues: [],
    ...extra,
  }
}

phase('Discover')

const runId = args?.runId || ''
const targetRoot = args?.targetRoot || ''
const workflowScriptPath = args?.workflowScriptPath || ''
const candidateHash = args?.candidateHash || ''

if (!nonEmpty(runId) || !nonEmpty(targetRoot) || !nonEmpty(workflowScriptPath) || !nonEmpty(candidateHash)) {
  return respond('BLOCKED_INPUT', {
    blockingIssues: ['runId, targetRoot, workflowScriptPath, and candidateHash are required'],
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

phase('Static Validate')

const staticEvidence = args?.staticEvidence
if (!staticEvidence) {
  return respond('READY_FOR_VALIDATION', {
    nextAction: 'RUN_DETERMINISTIC_VALIDATION',
  })
}

if (staticEvidence.status !== 'PASS' || !nonEmptyArray(staticEvidence.evidence) || staticEvidence.candidateHash !== candidateHash) {
  return respond('BLOCKED_VALIDATION', {
    blockingIssues: ['Static validation must PASS with matching candidateHash and non-empty evidence.'],
    staticEvidence,
    nextAction: 'RUN_DETERMINISTIC_VALIDATION',
  })
}

phase('External Verify')

const externalEvidence = args?.externalEvidence
if (!externalEvidence) {
  return respond('READY_FOR_EXTERNAL_VERIFY', {
    staticEvidence,
    nextAction: 'RUN_EXTERNAL_VERIFY',
  })
}

if (externalEvidence.status !== 'PASS' || !nonEmptyArray(externalEvidence.evidence) || externalEvidence.candidateHash !== candidateHash) {
  return respond('BLOCKED_VALIDATION', {
    blockingIssues: ['External verification must PASS with matching candidateHash and non-empty evidence.'],
    externalEvidence,
    nextAction: 'RUN_EXTERNAL_VERIFY',
  })
}

phase('Report')

return respond('PASS', {
  candidateHash,
  evidence: [
    ...asArray(staticEvidence.evidence),
    ...asArray(externalEvidence.evidence),
  ],
  nextAction: 'DELIVER',
})
