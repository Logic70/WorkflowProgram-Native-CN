export const meta = {
  name: 'workflowprogram-audit',
  description: 'Plugin-packaged Native Workflow JS entry for WorkflowProgram audit migration.',
  phases: [
    { title: 'Discover', detail: 'Validate required inputs and asset references.' },
    { title: 'Inspect', detail: 'Request or consume read-only structural inspection evidence.' },
    { title: 'Audit', detail: 'Request or consume structured risk audit evidence.' },
    { title: 'Verify', detail: 'Request or consume deterministic verification evidence.' },
    { title: 'Report', detail: 'Return the final audit result with delivery instructions.' },
  ],
}

const workflowName = 'workflowprogram-audit'
const launchMode = 'plugin-script-path'
const defaultTaskModels = {
  'clarification': 'deepseek-v4-flash[1M]',
  'repository-exploration': 'deepseek-v4-flash[1M]',
  'generation': 'deepseek-v4-flash[1M]',
  'static-review': 'deepseek-v4-flash[1M]',
  'architecture': 'deepseek-v4-pro[1M]',
  'complex-generation': 'deepseek-v4-pro[1M]',
  'risk-review': 'deepseek-v4-pro[1M]',
  'publish-verification': 'deepseek-v4-pro[1M]',
}
const suppliedTaskModels = args?.taskModels || args?.taskModelResolution?.taskModels
const taskModels = suppliedTaskModels && typeof suppliedTaskModels === 'object' ? suppliedTaskModels : defaultTaskModels
const withTaskModel = (taskType, options) => {
  const alias = typeof taskModels[taskType] === 'string' ? taskModels[taskType].trim() : ''
  if (!alias || alias === 'inherit') return options
  return { ...options, model: alias }
}
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

const isValidInspectPass = (evidence) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!Array.isArray(evidence.findings)) return false
  if (evidence.findings.some(f => typeof f !== 'string')) return false
  if (!Array.isArray(evidence.blockingIssues) || evidence.blockingIssues.length !== 0) return false
  return true
}

const isValidAuditPass = (evidence) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (typeof evidence.summary !== 'string' || evidence.summary.trim().length === 0) return false
  if (!Array.isArray(evidence.issues)) return false
  if (evidence.issues.some(issue => {
    return typeof issue.id !== 'string' || issue.id.trim().length === 0
      || typeof issue.severity !== 'string' || !['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].includes(issue.severity)
      || typeof issue.summary !== 'string' || issue.summary.trim().length === 0
  })) return false
  if (!Array.isArray(evidence.blockingIssues) || evidence.blockingIssues.length !== 0) return false
  return true
}

const blockedIssuesWithFallback = (evidence, fallback) => {
  const blockers = asArray(evidence?.blockingIssues).filter(nonEmpty)
  return blockers.length > 0 ? blockers : [fallback]
}

phase('Discover')

const runId = args?.runId || ''
const targetRoot = args?.targetRoot || ''
const workflowScriptPath = args?.workflowScriptPath || ''
const candidateHash = args?.candidateHash || ''
const assetRefs = asArray(args?.assetRefs)

if (!nonEmpty(runId) || !nonEmpty(targetRoot) || !nonEmpty(workflowScriptPath) || !nonEmpty(candidateHash) || !nonEmptyArray(assetRefs)) {
  return respond('BLOCKED_INPUT', {
    blockingIssues: ['runId, targetRoot, workflowScriptPath, candidateHash, and non-empty assetRefs are required'],
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

const discoveryEvidence = args?.discoveryEvidence
if (!discoveryEvidence) {
  return respond('READY_FOR_AUDIT_DISCOVERY', {
    nextAction: 'RUN_AUDIT_DISCOVERY',
  })
}

if (discoveryEvidence.status !== 'PASS' || !nonEmptyArray(discoveryEvidence.evidence) || discoveryEvidence.candidateHash !== candidateHash) {
  return respond('BLOCKED_AUDIT', {
    blockingIssues: ['Discovery must PASS with matching candidateHash and non-empty evidence.'],
    discoveryEvidence,
    nextAction: 'RUN_AUDIT_DISCOVERY',
  })
}

phase('Inspect')

let inspectEvidence = args?.inspectEvidence
if (!inspectEvidence) {
  inspectEvidence = await agent(
    `Inspect the target workflow assets at ${targetRoot} (script: ${workflowScriptPath}).
Read-only. Identify structure, patterns, and blocking issues. Return structured JSON only.`,
    withTaskModel('repository-exploration', {
      label: 'workflowprogram-audit:inspect',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          findings: { type: 'array', items: { type: 'string' } },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'findings', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
}

if (!isValidInspectPass(inspectEvidence)) {
  return respond('BLOCKED_AUDIT', {
    blockingIssues: blockedIssuesWithFallback(inspectEvidence, 'Inspect evidence is missing, malformed, or blocked.'),
    inspectEvidence,
    nextAction: 'FIX_ISSUES_AND_REINVOKE',
  })
}

phase('Audit')

let auditEvidence = args?.auditEvidence
if (!auditEvidence) {
  auditEvidence = await agent(
    `Audit risk for the target workflow assets at ${targetRoot} (script: ${workflowScriptPath}).
Asset refs: ${JSON.stringify(assetRefs)}
Inspect findings: ${JSON.stringify(inspectEvidence.findings)}
Read-only. Evaluate risks by severity. Return structured JSON only.`,
    withTaskModel('risk-review', {
      label: 'workflowprogram-audit:risk-review',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          issues: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string' },
                severity: { type: 'string', enum: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] },
                summary: { type: 'string' },
              },
              required: ['id', 'severity', 'summary'],
              additionalProperties: false,
            },
          },
          blockingIssues: { type: 'array', items: { type: 'string' } },
          summary: { type: 'string' },
        },
        required: ['status', 'issues', 'blockingIssues', 'summary'],
        additionalProperties: false,
      },
    }),
  )
}

if (!isValidAuditPass(auditEvidence)) {
  return respond('BLOCKED_AUDIT', {
    blockingIssues: blockedIssuesWithFallback(auditEvidence, 'Audit evidence is missing, malformed, or blocked.'),
    auditEvidence,
    nextAction: 'FIX_ISSUES_AND_REINVOKE',
  })
}

phase('Verify')

const verifyEvidence = args?.verifyEvidence
if (!verifyEvidence) {
  return respond('READY_FOR_AUDIT_VERIFICATION', {
    inspectEvidence,
    auditEvidence,
    nextAction: 'RUN_AUDIT_VERIFICATION',
  })
}

if (verifyEvidence.status !== 'PASS' || !nonEmptyArray(verifyEvidence.evidence) || verifyEvidence.candidateHash !== candidateHash) {
  return respond('BLOCKED_AUDIT', {
    blockingIssues: ['Verification must PASS with matching candidateHash and non-empty evidence.'],
    verifyEvidence,
    nextAction: 'RUN_AUDIT_VERIFICATION',
  })
}

phase('Report')

return respond('PASS', {
  candidateHash,
  issues: asArray(auditEvidence.issues),
  evidence: [
    ...asArray(discoveryEvidence.evidence),
    ...asArray(verifyEvidence.evidence),
  ],
  nextAction: 'DELIVER',
})
