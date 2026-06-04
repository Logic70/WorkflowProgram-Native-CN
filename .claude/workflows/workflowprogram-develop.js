export const meta = {
  name: 'workflowprogram-develop',
  description: 'Design or update a target Native Workflow JS control plane through re-entrant evidence handoffs.',
  phases: [
    { title: 'Intake', detail: 'Validate the request, target, run root, and operation.' },
    { title: 'Clarify', detail: 'Require complete logic lenses and close open questions.' },
    { title: 'Confirm', detail: 'Require explicit user confirmation before design.' },
    { title: 'Design', detail: 'Explore the target and produce an implementation-ready design.' },
    { title: 'Review', detail: 'Block generation until an independent design review passes.' },
    { title: 'Author', detail: 'Convert reviewed design into a locked run-scoped authoring spec.' },
    { title: 'Generate', detail: 'Request or consume controlled candidate-generation evidence.' },
    { title: 'Validate', detail: 'Request or consume deterministic validation evidence.' },
    { title: 'Smoke', detail: 'Request or consume interactive smoke evidence.' },
    { title: 'Apply', detail: 'Request or consume controlled apply evidence when approved.' },
    { title: 'Deliver', detail: 'Return the verified candidate or managed-apply result.' },
  ],
}

const workflowName = 'workflowprogram-develop'
const launchMode = 'plugin-script-path'
const runId = args?.runId || ''
const taskModels = args?.taskModels || {}
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
    runId,
    blockingIssues: [],
    ...extra,
  }
}
const blockingIssues = (evidence, fallback) => {
  const issues = asArray(evidence?.blockingIssues).filter(nonEmpty)
  return issues.length > 0 ? issues : [fallback]
}
const hasEvidence = evidence => evidence?.status === 'PASS' && nonEmptyArray(evidence?.evidence)
const hasDesignEvidence = evidence =>
  evidence?.status === 'PASS' &&
  nonEmpty(evidence?.summary) &&
  nonEmpty(evidence?.highLevelDesign) &&
  nonEmpty(evidence?.lowLevelDesign) &&
  nonEmptyArray(evidence?.traceability)
const hasReviewEvidence = evidence =>
  evidence?.status === 'PASS' &&
  nonEmpty(evidence?.summary) &&
  asArray(evidence?.blockingIssues).length === 0
const hasAuthoringSpec = spec =>
  spec &&
  nonEmpty(spec?.name) &&
  nonEmpty(spec?.description) &&
  nonEmpty(spec?.body) &&
  asArray(spec?.phases).length > 0 &&
  asArray(spec?.phases).every(item => nonEmpty(item?.title))
const matchesCandidate = (evidence, candidateHash) =>
  hasEvidence(evidence) && nonEmpty(candidateHash) && evidence?.candidateHash === candidateHash

phase('Intake')

const request = args?.request || ''
const targetRoot = args?.targetRoot || ''
const runRoot = args?.runRoot || ''
const operation = args?.operation || 'create'

if (!nonEmpty(request) || !nonEmpty(targetRoot) || !nonEmpty(runRoot) || !nonEmpty(runId)) {
  return respond('BLOCKED_INPUT', {
    blockingIssues: ['request, targetRoot, runRoot, and runId are required'],
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

if (!['create', 'update', 'migrate'].includes(operation)) {
  return respond('BLOCKED_INPUT', {
    blockingIssues: [`Unsupported operation: ${operation}`],
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

phase('Clarify')

const clarification = args?.clarification || {}
const lenses = clarification.lenses || {}
const requiredLenses = [
  ['purpose', 'Why does this workflow exist and what outcome should it produce?'],
  ['objectModel', 'What objects does the workflow read, transform, classify, or produce?'],
  ['processModel', 'Which phases are required, and in which order?'],
  ['decisionModel', 'Which branches, thresholds, and approvals change execution?'],
  ['evidenceModel', 'Which evidence makes intermediate and final results trustworthy?'],
  ['acceptanceModel', 'Which positive, negative, and ambiguous scenarios prove behavior?'],
  ['boundaryModel', 'Which stop conditions, conflicts, and non-goals apply?'],
]
const missingLensQuestions = requiredLenses
  .filter(([id]) => !nonEmpty(lenses[id]))
  .map(([id, question]) => ({
    id,
    question,
    reason: `The ${id} lens changes the Native Workflow JS design and gates.`,
  }))
const openQuestions = asArray(clarification.openQuestions).map((question, index) => ({
  id: question?.id || `openQuestion-${index + 1}`,
  question: question?.question || String(question),
  reason: question?.reason || 'This open question must be closed before design.',
}))
const questions = [...missingLensQuestions, ...openQuestions]

if (questions.length > 0) {
  return respond('NEEDS_USER_INPUT', {
    questions,
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

phase('Confirm')

const requirementSummary = {
  request,
  targetRoot,
  runRoot,
  operation,
  lenses,
}

if (clarification.confirmedByUser !== true) {
  return respond('READY_FOR_CONFIRMATION', {
    requirementSummary,
    nextAction: 'REINVOKE_WITH_CONFIRMATION',
  })
}

phase('Design')

let designEvidence = args?.designEvidence
if (!designEvidence) {
  const explorations = await parallel(
    ['target-context', 'runtime-boundaries'].map(lens => () =>
      agent(
        `Explore the ${lens} lens for a WorkflowProgram Native develop request.

Requirement:
${JSON.stringify(requirementSummary)}

Read the target project without creating, editing, or deleting files. Identify facts, constraints, and blocking issues. Return structured JSON only.`,
        withTaskModel('repository-exploration', {
          label: `workflowprogram-develop:explore:${lens}`,
          schema: {
            type: 'object',
            properties: {
              status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
              findings: { type: 'array', items: { type: 'string' } },
              constraints: { type: 'array', items: { type: 'string' } },
              blockingIssues: { type: 'array', items: { type: 'string' } },
            },
            required: ['status', 'findings', 'constraints', 'blockingIssues'],
            additionalProperties: false,
          },
        }),
      )
    ),
  )

  const blockedExplorations = explorations.filter(item => item.status !== 'PASS')
  if (blockedExplorations.length > 0) {
    return respond('BLOCKED_DESIGN', {
      blockingIssues: blockedExplorations.flatMap(item => blockingIssues(item, 'Exploration failed.')),
      explorations,
      nextAction: 'FIX_DESIGN_AND_REINVOKE',
    })
  }

  designEvidence = await agent(
    `Create an implementation-ready High-Level and Low-Level design for this WorkflowProgram Native develop request.

Requirement:
${JSON.stringify(requirementSummary)}

Explorations:
${JSON.stringify(explorations)}

The target Native Workflow JS is the runtime truth. Keep workflow-specific Agents inline by default. Separate L1 schema, L2 JavaScript gates, and L3 external facts. Do not write files. Return structured JSON only.`,
    withTaskModel('architecture', {
      label: 'workflowprogram-develop:design',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          summary: { type: 'string' },
          highLevelDesign: { type: 'string' },
          lowLevelDesign: { type: 'string' },
          traceability: { type: 'array', items: { type: 'string' } },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'summary', 'highLevelDesign', 'lowLevelDesign', 'traceability', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
}

if (!hasDesignEvidence(designEvidence)) {
  return respond('BLOCKED_DESIGN', {
    blockingIssues: blockingIssues(designEvidence, 'Design did not pass.'),
    designEvidence,
    nextAction: 'FIX_DESIGN_AND_REINVOKE',
  })
}

phase('Review')

let reviewEvidence = args?.reviewEvidence
if (!reviewEvidence) {
  reviewEvidence = await agent(
    `Review this WorkflowProgram Native develop design from a fresh context.

Requirement:
${JSON.stringify(requirementSummary)}

Design:
${JSON.stringify(designEvidence)}

Check requirement coverage, lifecycle closure, evidence flow, failure modes, ownership boundaries, and testability. Do not write files. Return structured JSON only.`,
    withTaskModel('risk-review', {
      label: 'workflowprogram-develop:review',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          blockingIssues: { type: 'array', items: { type: 'string' } },
          requiredRevisions: { type: 'array', items: { type: 'string' } },
          summary: { type: 'string' },
        },
        required: ['status', 'blockingIssues', 'requiredRevisions', 'summary'],
        additionalProperties: false,
      },
    }),
  )
}

if (!hasReviewEvidence(reviewEvidence)) {
  return respond('BLOCKED_DESIGN_REVIEW', {
    blockingIssues: blockingIssues(reviewEvidence, 'Design review did not pass.'),
    designEvidence,
    reviewEvidence,
    nextAction: 'FIX_DESIGN_AND_REINVOKE',
  })
}

phase('Author')

let authoringSpec = args?.authoringSpec
let authoringEvidence = args?.authoringEvidence
if (!authoringSpec && !authoringEvidence) {
  authoringEvidence = await agent(
    `Create the exact JSON authoring spec for the target Native Workflow JS.

Requirement:
${JSON.stringify(requirementSummary)}

Design:
${JSON.stringify(designEvidence)}

Review:
${JSON.stringify(reviewEvidence)}

Return a strict authoringSpec object for generate-native-workflow.py. The authoringSpec.body is ONLY the executable body that follows the generated meta header. Do not include export const meta, import statements, require(), module.exports, or any complete JavaScript file header in body. Use valid JavaScript syntax for Claude Code Native Workflow: phase(title), await agent(prompt, options), await parallel(thunks), await pipeline(items, stages...), ordinary JS gates, and a stable return envelope with status. Prefer ordinary await/phase sequencing over pipeline when there is no items collection. Separate L1 schema, L2 JS gates, and L3 external facts; external scripts must be represented as explicit Agent/tool responsibilities or supporting assets, not as comments that pretend execution happened. Return structured JSON only and do not write files.`,
    withTaskModel('complex-generation', {
      label: 'workflowprogram-develop:author',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          authoringSpec: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              description: { type: 'string' },
              phases: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    title: { type: 'string' },
                    detail: { type: 'string' },
                  },
                  required: ['title'],
                  additionalProperties: false,
                },
              },
              body: { type: 'string' },
              supporting_assets: { type: 'array', items: { type: 'object' } },
              task_model_policy: { type: 'object' },
            },
            required: ['name', 'description', 'phases', 'body', 'supporting_assets'],
            additionalProperties: false,
          },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'authoringSpec', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
  authoringSpec = authoringEvidence?.authoringSpec
}

if (!hasAuthoringSpec(authoringSpec) || authoringEvidence?.status === 'BLOCKED') {
  return respond('BLOCKED_GENERATION', {
    blockingIssues: blockingIssues(authoringEvidence, 'Authoring spec did not pass.'),
    authoringEvidence,
    nextAction: 'FIX_DESIGN_AND_REINVOKE',
  })
}

phase('Generate')

const generationEvidence = args?.generationEvidence
if (!generationEvidence) {
  return respond('READY_FOR_GENERATION', {
    targetRoot,
    runRoot,
    requirementSummary,
    designEvidence,
    reviewEvidence,
    authoringEvidence,
    authoringSpec,
    generationRequest: {
      targetRoot,
      runRoot,
      operation,
      rule: 'Write READY_FOR_GENERATION.authoringSpec unchanged to RUN_ROOT/native-workflow-authoring.json, then run generate-native-workflow.py under RUN_ROOT only. Do not synthesize or edit JS body in the foreground.',
    },
    nextAction: 'RUN_CONTROLLED_GENERATION',
  })
}

if (!hasEvidence(generationEvidence) || !nonEmpty(generationEvidence.candidateHash) || !nonEmptyArray(generationEvidence.candidateRefs)) {
  return respond('BLOCKED_GENERATION', {
    blockingIssues: blockingIssues(generationEvidence, 'Generation PASS evidence, candidateHash, and candidateRefs are required.'),
    generationEvidence,
    nextAction: 'RUN_CONTROLLED_GENERATION',
  })
}

phase('Validate')

const validationEvidence = args?.validationEvidence
if (!validationEvidence) {
  return respond('READY_FOR_VALIDATION', {
    candidateRefs: generationEvidence.candidateRefs,
    generationEvidence,
    nextAction: 'RUN_DETERMINISTIC_VALIDATION',
  })
}

if (!matchesCandidate(validationEvidence, generationEvidence.candidateHash)) {
  return respond('BLOCKED_VALIDATION', {
    blockingIssues: blockingIssues(validationEvidence, 'Validation PASS evidence must match the generated candidateHash.'),
    validationEvidence,
    nextAction: 'RUN_DETERMINISTIC_VALIDATION',
  })
}

phase('Smoke')

const smokeEvidence = args?.smokeEvidence
if (!smokeEvidence) {
  return respond('READY_FOR_SMOKE', {
    candidateRefs: generationEvidence.candidateRefs,
    validationEvidence,
    nextAction: 'RUN_INTERACTIVE_SMOKE',
  })
}

if (!matchesCandidate(smokeEvidence, generationEvidence.candidateHash)) {
  return respond('BLOCKED_SMOKE', {
    blockingIssues: blockingIssues(smokeEvidence, 'Interactive smoke PASS evidence must match the generated candidateHash.'),
    smokeEvidence,
    nextAction: 'RUN_INTERACTIVE_SMOKE',
  })
}

phase('Apply')

const applyApproved = args?.applyApproved === true
const applyEvidence = args?.applyEvidence

if (applyApproved && !applyEvidence) {
  return respond('READY_FOR_APPLY', {
    candidateRefs: generationEvidence.candidateRefs,
    smokeEvidence,
    nextAction: 'RUN_CONTROLLED_APPLY',
  })
}

if (applyApproved && (!matchesCandidate(applyEvidence, generationEvidence.candidateHash) || !nonEmpty(applyEvidence?.applyManifest))) {
  return respond('BLOCKED_CONFLICT', {
    blockingIssues: blockingIssues(applyEvidence, 'Controlled apply PASS evidence, matching candidateHash, and applyManifest are required.'),
    applyEvidence,
    nextAction: 'RESOLVE_CONFLICT',
  })
}

phase('Deliver')

return respond('PASS', {
  deliveryMode: applyApproved ? 'managed-apply' : 'candidate-only',
  candidateRefs: generationEvidence.candidateRefs,
  evidence: [
    ...asArray(generationEvidence.evidence),
    ...asArray(validationEvidence.evidence),
    ...asArray(smokeEvidence.evidence),
    ...asArray(applyEvidence?.evidence),
  ],
  nextAction: 'DELIVER',
})
