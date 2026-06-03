export const meta = {
  name: 'workflowprogram-iterate',
  description: 'Plugin-packaged Native Workflow JS entry for WorkflowProgram iterate migration.',
  phases: [
    { title: 'Readback', detail: 'Validate inputs and request or consume deterministic readback evidence.' },
    { title: 'Collect Findings', detail: 'Collect structured findings from a read-only agent or injected evidence.' },
    { title: 'Build Lessons Delta', detail: 'Build a structured lessons delta via an agent or injected evidence.' },
    { title: 'Validate Delta', detail: 'Request or consume deterministic delta validation evidence.' },
    { title: 'Append Lessons', detail: 'Request or consume controlled lessons append evidence.' },
    { title: 'Propose Constraints', detail: 'Propose long-lived constraints via an agent or injected evidence.' },
    { title: 'Review', detail: 'Review constraint candidates via an independent agent or injected evidence.' },
    { title: 'Apply Approved Constraints', detail: 'Request or consume controlled constraints apply evidence.' },
    { title: 'Deliver', detail: 'Return the final iterate result with delivery instructions.' },
  ],
}

const workflowName = 'workflowprogram-iterate'
const launchMode = 'plugin-script-path'
const taskModels = args?.taskModels || {}
const withTaskModel = (taskType, options) => {
  const alias = typeof taskModels[taskType] === 'string' ? taskModels[taskType].trim() : ''
  if (!alias || alias === 'inherit') return options
  return { ...options, model: alias }
}
const asArray = value => Array.isArray(value) ? value : []
const nonEmpty = value => typeof value === 'string' && value.trim().length > 0
const nonEmptyArray = value => asArray(value).length > 0 && asArray(value).every(nonEmpty)
const isEmptyArray = value => Array.isArray(value) && value.length === 0
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

const hasEvidencePass = (evidence) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!nonEmpty(evidence.stateHash)) return false
  if (!nonEmptyArray(evidence.evidence)) return false
  if (!isEmptyArray(evidence.blockingIssues)) return false
  return true
}

const isValidFindingsPass = (evidence, stateHash) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!Array.isArray(evidence.findings)) return false
  if (evidence.findings.some(f => {
    return typeof f.id !== 'string' || f.id.trim().length === 0
      || typeof f.category !== 'string' || f.category.trim().length === 0
      || typeof f.summary !== 'string' || f.summary.trim().length === 0
  })) return false
  if (!nonEmpty(evidence.stateHash) || evidence.stateHash !== stateHash) return false
  if (!isEmptyArray(evidence.blockingIssues)) return false
  return true
}

const isValidDeltaPass = (evidence, stateHash) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!Array.isArray(evidence.delta)) return false
  if (evidence.delta.some(d => {
    return typeof d.type !== 'string' || d.type.trim().length === 0
      || typeof d.summary !== 'string' || d.summary.trim().length === 0
      || typeof d.body !== 'string' || d.body.trim().length === 0
  })) return false
  if (!nonEmpty(evidence.stateHash) || evidence.stateHash !== stateHash) return false
  if (!isEmptyArray(evidence.blockingIssues)) return false
  return true
}

const isValidDeltaValidationPass = (evidence, stateHash) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!nonEmpty(evidence.stateHash) || evidence.stateHash !== stateHash) return false
  if (!nonEmptyArray(evidence.evidence)) return false
  if (!nonEmpty(evidence.deltaHash)) return false
  if (!isEmptyArray(evidence.blockingIssues)) return false
  return true
}

const isValidAppendPass = (evidence, baselineHash, deltaHash) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!nonEmpty(evidence.baselineHash) || evidence.baselineHash !== baselineHash) return false
  if (!nonEmpty(evidence.stateHash)) return false
  if (!nonEmpty(evidence.deltaHash) || evidence.deltaHash !== deltaHash) return false
  if (!nonEmptyArray(evidence.evidence)) return false
  if (!isEmptyArray(evidence.blockingIssues)) return false
  return true
}

const isValidProposalPass = (evidence, stateHash) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!Array.isArray(evidence.constraintCandidates)) return false
  if (evidence.constraintCandidates.some(c => {
    return typeof c.rule !== 'string' || c.rule.trim().length === 0
      || typeof c.reason !== 'string' || c.reason.trim().length === 0
  })) return false
  if (!nonEmpty(evidence.stateHash) || evidence.stateHash !== stateHash) return false
  if (!isEmptyArray(evidence.blockingIssues)) return false
  return true
}

const isValidReviewPass = (evidence, stateHash) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!Array.isArray(evidence.approvedCandidates)) return false
  if (evidence.approvedCandidates.some(c => {
    return typeof c.rule !== 'string' || c.rule.trim().length === 0
      || typeof c.reason !== 'string' || c.reason.trim().length === 0
  })) return false
  if (!nonEmpty(evidence.stateHash) || evidence.stateHash !== stateHash) return false
  if (!isEmptyArray(evidence.blockingIssues)) return false
  return true
}

const isValidApplyPass = (evidence, baselineHash) => {
  if (!evidence || evidence.status !== 'PASS') return false
  if (!nonEmpty(evidence.baselineHash) || evidence.baselineHash !== baselineHash) return false
  if (!nonEmpty(evidence.stateHash)) return false
  if (!nonEmpty(evidence.proposalHash)) return false
  if (!nonEmptyArray(evidence.evidence)) return false
  if (!isEmptyArray(evidence.blockingIssues)) return false
  return true
}

phase('Readback')

const runId = args?.runId || ''
const targetRoot = args?.targetRoot || ''
const runRoot = args?.runRoot || ''

if (!nonEmpty(runId) || !nonEmpty(targetRoot) || !nonEmpty(runRoot)) {
  return respond('BLOCKED_INPUT', {
    blockingIssues: ['runId, targetRoot, and runRoot are required'],
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

const readbackEvidence = args?.readbackEvidence
if (!readbackEvidence) {
  return respond('READY_FOR_ITERATION_READBACK', {
    nextAction: 'RUN_ITERATION_READBACK',
  })
}

if (!hasEvidencePass(readbackEvidence)) {
  return respond('BLOCKED_ITERATION', {
    blockingIssues: ['Readback must PASS with a non-empty stateHash, non-empty evidence refs, and empty blockingIssues.'],
    readbackEvidence,
    nextAction: 'RUN_ITERATION_READBACK',
  })
}

const stateHash = readbackEvidence.stateHash

phase('Collect Findings')

let findingsEvidence = args?.findingsEvidence
if (findingsEvidence) {
  if (!isValidFindingsPass(findingsEvidence, stateHash)) {
    return respond('BLOCKED_ITERATION', {
      blockingIssues: ['Injected findingsEvidence must PASS with structured findings array, empty blockingIssues, and matching stateHash.'],
      findingsEvidence,
      nextAction: 'FIX_FINDINGS_AND_REINVOKE',
    })
  }
} else {
  findingsEvidence = await agent(
    `Collect structured findings for WorkflowProgram iterate against the target project at ${targetRoot}.

Read-only. Identify lessons, failure patterns, and gaps that should become new lessons entries or constraint candidates. Return the exact stateHash supplied: ${stateHash}. Return structured JSON only.`,
    withTaskModel('static-review', {
      label: 'workflowprogram-iterate:collect-findings',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          stateHash: { type: 'string' },
          findings: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string' },
                category: { type: 'string' },
                summary: { type: 'string' },
              },
              required: ['id', 'category', 'summary'],
              additionalProperties: false,
            },
          },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'stateHash', 'findings', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
}

if (!isValidFindingsPass(findingsEvidence, stateHash)) {
  return respond('BLOCKED_ITERATION', {
    blockingIssues: ['Findings collection must PASS with structured findings, empty blockingIssues, and matching stateHash.'],
    findingsEvidence,
    nextAction: 'FIX_FINDINGS_AND_REINVOKE',
  })
}

if (findingsEvidence.findings.length === 0) {
  return respond('PASS', {
    deliveryMode: 'no-new-lessons',
    findingsEvidence,
    readbackEvidence,
    evidence: asArray(readbackEvidence.evidence),
    nextAction: 'DELIVER',
  })
}

phase('Build Lessons Delta')

let lessonsDeltaEvidence = args?.lessonsDeltaEvidence
if (lessonsDeltaEvidence) {
  if (!isValidDeltaPass(lessonsDeltaEvidence, stateHash)) {
    return respond('BLOCKED_ITERATION', {
      blockingIssues: ['Injected lessonsDeltaEvidence must PASS with structured delta array, empty blockingIssues, and matching stateHash.'],
      lessonsDeltaEvidence,
      nextAction: 'FIX_DELTA_AND_REINVOKE',
    })
  }
} else {
  lessonsDeltaEvidence = await agent(
    `Build a lessons delta from structured findings for the target project at ${targetRoot}.

Read-only. Each delta entry must include a type (lesson, constraint-candidate, warning), summary, and body text ready to append to lessons.md. Return the exact stateHash supplied: ${stateHash}. Return structured JSON only.

Findings:
${JSON.stringify(findingsEvidence.findings)}`,
    withTaskModel('generation', {
      label: 'workflowprogram-iterate:build-lessons-delta',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          stateHash: { type: 'string' },
          delta: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                type: { type: 'string' },
                summary: { type: 'string' },
                body: { type: 'string' },
              },
              required: ['type', 'summary', 'body'],
              additionalProperties: false,
            },
          },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'stateHash', 'delta', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
}

if (!isValidDeltaPass(lessonsDeltaEvidence, stateHash)) {
  return respond('BLOCKED_ITERATION', {
    blockingIssues: ['Lessons delta must PASS with structured delta entries, empty blockingIssues, and matching stateHash.'],
    lessonsDeltaEvidence,
    nextAction: 'FIX_DELTA_AND_REINVOKE',
  })
}

phase('Validate Delta')

const deltaValidationEvidence = args?.deltaValidationEvidence
if (!deltaValidationEvidence) {
  return respond('READY_FOR_LESSONS_DELTA_VALIDATION', {
    stateHash,
    lessonsDeltaEvidence,
    nextAction: 'RUN_LESSONS_DELTA_VALIDATION',
  })
}

if (!isValidDeltaValidationPass(deltaValidationEvidence, stateHash)) {
  return respond('BLOCKED_VALIDATION', {
    blockingIssues: ['Delta validation must PASS with matching stateHash, non-empty evidence refs, non-empty deltaHash, and empty blockingIssues.'],
    deltaValidationEvidence,
    nextAction: 'RUN_LESSONS_DELTA_VALIDATION',
  })
}

const deltaHash = deltaValidationEvidence.deltaHash

phase('Append Lessons')

const appendEvidence = args?.appendEvidence
if (!appendEvidence) {
  return respond('READY_FOR_LESSONS_APPEND', {
    stateHash,
    deltaHash,
    nextAction: 'RUN_CONTROLLED_LESSONS_APPEND',
  })
}

if (!isValidAppendPass(appendEvidence, stateHash, deltaHash)) {
  return respond('BLOCKED_CONFLICT', {
    blockingIssues: ['Lessons append must PASS: baselineHash must match initial stateHash, non-empty post-write stateHash, deltaHash must match validation deltaHash, non-empty evidence refs, and empty blockingIssues. Append may fail due to baseline drift.'],
    appendEvidence,
    nextAction: 'RESOLVE_CONFLICT',
  })
}

const postAppendStateHash = appendEvidence.stateHash

phase('Propose Constraints')

let proposalEvidence = args?.proposalEvidence
if (proposalEvidence) {
  if (!isValidProposalPass(proposalEvidence, stateHash)) {
    return respond('BLOCKED_ITERATION', {
      blockingIssues: ['Injected proposalEvidence must PASS with constraintCandidates array (each with non-empty rule and reason), empty blockingIssues, and matching stateHash.'],
      proposalEvidence,
      nextAction: 'FIX_PROPOSAL_AND_REINVOKE',
    })
  }
} else {
  proposalEvidence = await agent(
    `Propose long-lived constraint candidates for the target project at ${targetRoot} based on lessons delta.

Read-only. Each candidate must have a rule (the constraint) and a reason (the motivation). Return the exact stateHash supplied: ${stateHash}. Return structured JSON only. If no constraints are needed, return an empty constraintCandidates array.

Lessons Delta:
${JSON.stringify(lessonsDeltaEvidence.delta)}

Findings:
${JSON.stringify(findingsEvidence.findings)}`,
    withTaskModel('architecture', {
      label: 'workflowprogram-iterate:propose-constraints',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          stateHash: { type: 'string' },
          constraintCandidates: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                rule: { type: 'string' },
                reason: { type: 'string' },
              },
              required: ['rule', 'reason'],
              additionalProperties: false,
            },
          },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'stateHash', 'constraintCandidates', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
}

if (!isValidProposalPass(proposalEvidence, stateHash)) {
  return respond('BLOCKED_ITERATION', {
    blockingIssues: ['Constraint proposal must PASS with constraintCandidates array (each with non-empty rule and reason), empty blockingIssues, and matching stateHash.'],
    proposalEvidence,
    nextAction: 'FIX_PROPOSAL_AND_REINVOKE',
  })
}

if (proposalEvidence.constraintCandidates.length === 0) {
  return respond('PASS', {
    deliveryMode: 'append-only',
    reason: 'no-constraint-candidates',
    findingsEvidence,
    lessonsDeltaEvidence,
    appendEvidence,
    readbackEvidence,
    evidence: [
      ...asArray(readbackEvidence.evidence),
      ...asArray(deltaValidationEvidence.evidence),
      ...asArray(appendEvidence.evidence),
    ],
    nextAction: 'DELIVER',
  })
}

phase('Review')

let reviewEvidence = args?.reviewEvidence
if (reviewEvidence) {
  if (!isValidReviewPass(reviewEvidence, stateHash)) {
    return respond('BLOCKED_ITERATION', {
      blockingIssues: ['Injected reviewEvidence must PASS with approvedCandidates array (each with non-empty rule and reason), empty blockingIssues, and matching stateHash.'],
      reviewEvidence,
      nextAction: 'FIX_REVIEW_AND_REINVOKE',
    })
  }
} else {
  reviewEvidence = await agent(
    `Review constraint candidates for the target project at ${targetRoot} from an independent perspective.

Read-only. Evaluate each candidate and return only approved candidates with their rule and reason. Return the exact stateHash supplied: ${stateHash}. Return structured JSON only.

Constraint Candidates:
${JSON.stringify(proposalEvidence.constraintCandidates.map(c => ({rule: c.rule, reason: c.reason})))}`,
    withTaskModel('risk-review', {
      label: 'workflowprogram-iterate:review-constraints',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          stateHash: { type: 'string' },
          approvedCandidates: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                rule: { type: 'string' },
                reason: { type: 'string' },
              },
              required: ['rule', 'reason'],
              additionalProperties: false,
            },
          },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'stateHash', 'approvedCandidates', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
}

if (!isValidReviewPass(reviewEvidence, stateHash)) {
  return respond('BLOCKED_ITERATION', {
    blockingIssues: ['Constraint review must PASS with approvedCandidates array (each with non-empty rule and reason), empty blockingIssues, and matching stateHash.'],
    reviewEvidence,
    nextAction: 'FIX_REVIEW_AND_REINVOKE',
  })
}

// Zero approvedCandidates: deliver PASS without asking for confirmation
if (reviewEvidence.approvedCandidates.length === 0) {
  return respond('PASS', {
    deliveryMode: 'append-only',
    reason: 'no-approved-constraints',
    findingsEvidence,
    lessonsDeltaEvidence,
    reviewEvidence,
    appendEvidence,
    readbackEvidence,
    evidence: [
      ...asArray(readbackEvidence.evidence),
      ...asArray(deltaValidationEvidence.evidence),
      ...asArray(appendEvidence.evidence),
    ],
    nextAction: 'DELIVER',
  })
}

phase('Apply Approved Constraints')

const constraintsApproved = args?.constraintsApproved
if (constraintsApproved === undefined || constraintsApproved === null) {
  return respond('READY_FOR_CONFIRMATION', {
    stateHash: postAppendStateHash,
    proposals: {
      originalCandidates: proposalEvidence.constraintCandidates,
      approvedCandidates: reviewEvidence.approvedCandidates,
    },
    nextAction: 'REINVOKE_WITH_CONFIRMATION',
  })
}

if (constraintsApproved === false) {
  return respond('PASS', {
    deliveryMode: 'proposal-only',
    findingsEvidence,
    lessonsDeltaEvidence,
    proposalEvidence,
    reviewEvidence,
    appendEvidence,
    readbackEvidence,
    evidence: [
      ...asArray(readbackEvidence.evidence),
      ...asArray(deltaValidationEvidence.evidence),
      ...asArray(appendEvidence.evidence),
    ],
    nextAction: 'DELIVER',
  })
}

const applyConstraintsEvidence = args?.applyConstraintsEvidence
if (!applyConstraintsEvidence) {
  return respond('READY_FOR_CONSTRAINTS_APPLY', {
    stateHash: postAppendStateHash,
    approvedCandidates: reviewEvidence.approvedCandidates,
    nextAction: 'RUN_CONTROLLED_CONSTRAINTS_APPLY',
  })
}

if (!isValidApplyPass(applyConstraintsEvidence, postAppendStateHash)) {
  return respond('BLOCKED_CONFLICT', {
    blockingIssues: ['Constraints apply must PASS: baselineHash must match post-append stateHash, non-empty post-write stateHash, non-empty proposalHash, non-empty evidence refs, and empty blockingIssues. Apply may fail due to baseline drift.'],
    applyConstraintsEvidence,
    nextAction: 'RESOLVE_CONFLICT',
  })
}

phase('Deliver')

return respond('PASS', {
  deliveryMode: 'managed-constraints-apply',
  findingsEvidence,
  lessonsDeltaEvidence,
  proposalEvidence,
  reviewEvidence,
  appendEvidence,
  applyConstraintsEvidence,
  readbackEvidence,
  evidence: [
    ...asArray(readbackEvidence.evidence),
    ...asArray(deltaValidationEvidence.evidence),
    ...asArray(appendEvidence.evidence),
    ...asArray(applyConstraintsEvidence.evidence),
  ],
  nextAction: 'DELIVER',
})
