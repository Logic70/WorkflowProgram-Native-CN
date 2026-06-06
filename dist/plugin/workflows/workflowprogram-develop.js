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
const phaseBoundaryGuidance = [
  'Phase Boundary Contract:',
  'Use phase(title) for semantic execution boundaries, not progress labels.',
  'A process is a Phase candidate when it has an independent purpose plus a clear input/output handoff, an exit gate, distinct recovery or nextAction, a side-effect boundary, different executor/permission/model/tool needs, or distinct evidence required for trust.',
  'If completing this process changes whether the workflow continues, blocks, re-enters, asks the user, or performs side effects, it is a Phase candidate.',
  'Do not create a Phase for a single prompt paragraph, helper function, data transform, several parallel Agents under one objective and one gate, progress-only split, or logic with no independent gate, evidence, or recovery path.',
].join('\n')
const migrationExplorationGuidance = [
  'Existing workflow migration contract:',
  'Use existing WPN terms: operation=migrate, request_kind=redesign_existing, target_state=existing_managed_workflow, or manual_migration_required=true. Do not introduce a separate product concept.',
  'Classify exploration output into findings, constraints, migrationTasks, trueBlockers, userDecisions, sourceOfTruth, and assetDispositionHints.',
  'Expected migration work is not a design blocker: missing target .claude/workflows/<name>.js, stale workflow-spec.yaml, retired .workflowprogram/runtime/, stale managed-files.json, duplicate legacy assets, and no existing Native JS reference are migrationTasks when a current command, Agent, Skill, design document, runtime file, candidate, or user decision still defines behavior.',
  'Only trueBlockers stop Design: unreadable target roots, no usable behavioral source of truth, unresolved user decisions that change topology, unclear write boundaries, or missing required assets with no replacement.',
  'Source-of-truth priority: explicit user decisions, current command or entrypoint behavior, current Agents and Skills, current design metadata, retired runtime behavior, then historical candidates as reference only.',
].join('\n')
const asArray = value => Array.isArray(value) ? value : []
const nonEmpty = value => typeof value === 'string' && value.trim().length > 0
const nonEmptyArray = value => asArray(value).length > 0 && asArray(value).every(nonEmpty)
const isSha256Ref = value => nonEmpty(value) && value.startsWith('sha256:')
const isAbsolutePathRef = value =>
  nonEmpty(value) &&
  (value.startsWith('/') || value.startsWith('\\\\') || /^[A-Za-z]:[\\/]/.test(value))
const pathIdentity = value => {
  if (!nonEmpty(value)) return ''
  const normalized = value.trim().replace(/\\/g, '/').replace(/\/+$/, '')
  const wsl = normalized.match(/^\/mnt\/([A-Za-z])\/(.*)$/)
  if (wsl) return `${wsl[1].toLowerCase()}:/${wsl[2]}`
  return /^[A-Za-z]:\//.test(normalized) ? normalized[0].toLowerCase() + normalized.slice(1) : normalized
}
const nonEmptyPathArray = value => asArray(value).length > 0 && asArray(value).every(isAbsolutePathRef)
const hasLensContent = value => {
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.length > 0
  return value && typeof value === 'object' && Object.keys(value).length > 0
}
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
const hasEvidence = evidence =>
  evidence?.status === 'PASS' &&
  nonEmptyPathArray(evidence?.evidence) &&
  asArray(evidence?.blockingIssues).length === 0
const dispositionActions = ['retain', 'generate', 'update', 'archive', 'remove', 'defer', 'not-applicable']
const actionsRequiringSupportingAsset = ['generate', 'update', 'archive']
const normalizeDisposition = item => ({
  path: item?.path || '',
  action: item?.action || '',
  reason: item?.reason || '',
  supportingAssetPath: item?.supportingAssetPath || item?.supporting_asset_path || '',
})
const dispositionKey = value =>
  JSON.stringify(asArray(value).map(normalizeDisposition).sort((left, right) => left.path.localeCompare(right.path)))
const validAssetDisposition = (value, supportingAssets) => {
  const supportingPaths = new Set(asArray(supportingAssets).map(item => item?.path).filter(nonEmpty))
  return asArray(value).every(item => {
    const normalized = normalizeDisposition(item)
    if (!nonEmpty(normalized.path) || !dispositionActions.includes(normalized.action) || !nonEmpty(normalized.reason)) return false
    if (actionsRequiringSupportingAsset.includes(normalized.action)) {
      return nonEmpty(normalized.supportingAssetPath) && supportingPaths.has(normalized.supportingAssetPath)
    }
    return !nonEmpty(normalized.supportingAssetPath) || supportingPaths.has(normalized.supportingAssetPath)
  })
}
const requiresAssetDisposition = operation => ['update', 'migrate'].includes(operation)
const decisionText = decision => {
  if (typeof decision === 'string') return decision
  if (!decision || typeof decision !== 'object') return ''
  return decision.question || decision.prompt || decision.text || decision.id || ''
}
const explorationDesignBlockers = (explorations, operation) => {
  if (operation === 'migrate') {
    return explorations.flatMap(item => [
      ...asArray(item?.trueBlockers).filter(nonEmpty),
      ...asArray(item?.userDecisions).map(decisionText).filter(nonEmpty).map(item => `User decision required: ${item}`),
    ])
  }
  return explorations
    .filter(item => item.status !== 'PASS')
    .flatMap(item => blockingIssues(item, 'Exploration failed.'))
}
const hasDesignEvidence = (evidence, operation) =>
  evidence?.status === 'PASS' &&
  nonEmpty(evidence?.summary) &&
  nonEmpty(evidence?.highLevelDesign) &&
  nonEmpty(evidence?.lowLevelDesign) &&
  nonEmptyArray(evidence?.traceability) &&
  (!requiresAssetDisposition(operation) || asArray(evidence?.assetDisposition).length > 0)
const hasReviewEvidence = (evidence, operation) =>
  evidence?.status === 'PASS' &&
  nonEmpty(evidence?.summary) &&
  asArray(evidence?.blockingIssues).length === 0 &&
  asArray(evidence?.requiredRevisions).length === 0 &&
  (!requiresAssetDisposition(operation) || evidence?.assetDispositionReviewed === true)
const reviewBlockingIssues = evidence => {
  const blockers = asArray(evidence?.blockingIssues).filter(nonEmpty)
  const revisions = asArray(evidence?.requiredRevisions).filter(nonEmpty)
  const issues = [...blockers, ...revisions.map(item => `Required revision not closed: ${item}`)]
  return issues.length > 0 ? issues : ['Design review did not pass.']
}
const hasSmokeEvaluatorEvidence = evidence =>
  hasEvidence(evidence) &&
  asArray(evidence?.smokeReports).length > 0 &&
  asArray(evidence?.smokeReports).every(report =>
    isAbsolutePathRef(report?.reportPath) &&
    isSha256Ref(report?.reportHash) &&
    nonEmpty(report?.workflow) &&
    isAbsolutePathRef(report?.scriptPath) &&
    isSha256Ref(report?.scriptHash) &&
    report?.candidateHash === evidence?.candidateHash &&
    nonEmpty(report?.scenarioId) &&
    ['full', 'early-blocker', 'completion', 'agent-schema'].includes(report?.evidenceProfile) &&
    nonEmptyArray(report?.runIds) &&
    report?.evidence?.workflow_invoked === true &&
    report?.evidence?.async_launched === true &&
    report?.evidence?.agent_started === true &&
    report?.evidence?.schema_result === true &&
    (
      (
        report?.expectedStatus === 'PASS' &&
        report?.evidence?.completed_pass === true &&
        report?.evidence?.completed_blocked !== true
      ) ||
      (
        report?.expectedStatus === 'BLOCKED' &&
        report?.evidence?.completed_blocked === true &&
        report?.evidence?.completed_pass !== true
      )
    )
  ) &&
  asArray(evidence?.smokeReports).some(report => report?.expectedStatus === 'PASS')
const hasApplyManifest = (evidence, targetRoot) =>
  pathIdentity(evidence?.targetRoot) === pathIdentity(targetRoot) &&
  evidence?.applyManifest &&
  typeof evidence.applyManifest === 'object' &&
  isAbsolutePathRef(evidence.applyManifest?.manifestPath) &&
  isAbsolutePathRef(evidence.applyManifest?.reportPath) &&
  asArray(evidence.applyManifest?.entries).length > 0 &&
  asArray(evidence.applyManifest?.entries).every(item =>
    nonEmpty(item?.path) &&
    ['create', 'update', 'noop'].includes(item?.action) &&
    isSha256Ref(item?.sha256)
  )
const hasAuthoringSpec = (spec, operation, designEvidence) =>
  spec &&
  nonEmpty(spec?.name) &&
  nonEmpty(spec?.description) &&
  nonEmpty(spec?.body) &&
  asArray(spec?.phases).length > 0 &&
  asArray(spec?.phases).every(item => nonEmpty(item?.title)) &&
  validAssetDisposition(spec?.asset_disposition, spec?.supporting_assets) &&
  (
    !requiresAssetDisposition(operation) ||
    (
      asArray(spec?.asset_disposition).length > 0 &&
      dispositionKey(spec.asset_disposition) === dispositionKey(designEvidence?.assetDisposition)
    )
  )
const matchesCandidate = (evidence, candidateHash) =>
  hasEvidence(evidence) && isSha256Ref(candidateHash) && evidence?.candidateHash === candidateHash
const logicLensDefinitions = [
  {
    id: 'purpose',
    legacyId: 'purpose',
    title: 'Purpose Lens',
    task: 'Convert the request into observable purpose, user value, and success signal.',
    question: 'What decision or action should become easier after this workflow runs?',
  },
  {
    id: 'objectModel',
    legacyId: 'object_model',
    title: 'Object Lens',
    task: 'Identify input, intermediate, and output objects plus source-of-truth rules.',
    question: 'What intermediate object must exist before the workflow can make the next decision?',
  },
  {
    id: 'processModel',
    legacyId: 'process_model',
    title: 'Process Lens',
    task: 'Decompose the work into phase candidates only when purpose, handoff, gate, evidence, recovery, executor, or side-effect boundary changes.',
    question: 'Which process boundaries change whether the workflow continues, blocks, re-enters, asks the user, or performs side effects?',
  },
  {
    id: 'decisionModel',
    legacyId: 'decision_model',
    title: 'Decision Lens',
    task: 'Expose branching choices, decision inputs, fallbacks, confidence, and owners.',
    question: 'How should the workflow choose between plausible strategies or next actions?',
  },
  {
    id: 'evidenceModel',
    legacyId: 'evidence_model',
    title: 'Evidence Lens',
    task: 'Define evidence required to trust outputs, decisions, and intermediate models.',
    question: 'What evidence should a reviewer see before trusting this output?',
  },
  {
    id: 'acceptanceModel',
    legacyId: 'acceptance_model',
    title: 'Acceptance Lens',
    task: 'Turn clarified logic into concrete positive, negative, and ambiguous scenarios.',
    question: 'Give one example input where the workflow should pass and one where it should stop.',
  },
  {
    id: 'boundaryModel',
    legacyId: 'boundary_model',
    title: 'Boundary Lens',
    task: 'Define non-goals, stop conditions, manual confirmations, and degradation rules.',
    question: 'What must the workflow never modify or infer automatically?',
  },
]
const lensValue = lens => lenses?.[lens.id] ?? lenses?.[lens.legacyId]
const fallbackQuestion = lens => ({
  id: lens.id,
  lens: lens.id,
  question: lens.question,
  reason: `${lens.title} changes the Native Workflow JS design and gates.`,
})
const settledPlatformDecisions = [
  'Native Workflow JS is the runtime control plane for WorkflowProgram develop; commands and skills are entry/support assets, not the executable state machine.',
  'Workflow-specific Agent prompts are inline in the target JS by default; only reusable cross-workflow roles use registered agentType or shared references.',
  'agent() options may include label, phase, schema, model, isolation, and agentType; do not use skills: [...] in agent options.',
  'The foreground assistant must not synthesize or edit target workflow JS directly after a workflow handoff; generation, validation, smoke, and apply must use controlled scripts/evidence.',
  'Target writes must go to RUN_ROOT/outputs/candidate first and reach TARGET_ROOT only through managed apply with a manifest.',
  'Old Python runtime assets are not preserved as an active runtime in the Native target; keep, archive, or remove them only through explicit asset disposition.',
]
const isResolvedOpenQuestion = question =>
  question &&
  typeof question === 'object' &&
  (
    question.resolved === true ||
    ['RESOLVED', 'ANSWERED', 'CLOSED'].includes(String(question.status || '').toUpperCase()) ||
    nonEmpty(question.answer) ||
    nonEmpty(question.response) ||
    nonEmpty(question.resolution)
  )
const normalizeOpenQuestion = (question, index) => {
  if (typeof question === 'string') {
    if (!nonEmpty(question)) return null
    return {
      id: `openQuestion-${index + 1}`,
      lens: 'purpose',
      question: question.trim(),
      reason: 'This open question must be closed before design.',
    }
  }
  if (!question || typeof question !== 'object' || isResolvedOpenQuestion(question)) return null
  const id = nonEmpty(question.id) ? question.id : `openQuestion-${index + 1}`
  const text = question.question || question.prompt || question.text
  return {
    id,
    lens: nonEmpty(question.lens) ? question.lens : 'purpose',
    question: nonEmpty(text) ? text : `Clarify unresolved open question ${id}.`,
    reason: nonEmpty(question.reason) ? question.reason : 'This open question must be closed before design.',
  }
}

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
const missingLenses = logicLensDefinitions.filter(lens => !hasLensContent(lensValue(lens)))
const openQuestions = asArray(clarification.openQuestions)
  .map((question, index) => normalizeOpenQuestion(question, index))
  .filter(question => question && nonEmpty(question.question))
let questions = []

if (missingLenses.length > 0 || openQuestions.length > 0) {
  const clarificationResult = await agent(
    `Clarify this WorkflowProgram Native develop request by asking only design-consequential questions.

Requirement:
${JSON.stringify({ request, targetRoot, runRoot, operation })}

Current clarification:
${JSON.stringify(clarification)}

Logic lens definitions:
${JSON.stringify(logicLensDefinitions)}

Phase boundary guidance:
${phaseBoundaryGuidance}

Settled WorkflowProgram platform decisions, not user-choice questions:
${JSON.stringify(settledPlatformDecisions)}

Missing runtime lens ids:
${JSON.stringify(missingLenses.map(lens => lens.id))}

Open questions:
${JSON.stringify(openQuestions)}

Use the registered requirement-clarification-lead semantics. Ask 1-3 questions that can change workflow phase boundaries, decisions, evidence, acceptance, or boundaries. Do not ask the user to re-decide settled platform decisions above. Do not write files. Return structured JSON only.`,
    withTaskModel('clarification', {
      label: 'workflowprogram-develop:clarify',
      agentType: 'workflowprogram-native-cn:requirement-clarification-lead',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'NEEDS_USER_INPUT', 'BLOCKED'] },
          questions: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string' },
                lens: { type: 'string' },
                question: { type: 'string' },
                reason: { type: 'string' },
              },
              required: ['id', 'lens', 'question', 'reason'],
              additionalProperties: false,
            },
          },
          lensCoverage: { type: 'object' },
          openQuestions: { type: 'array', items: { type: 'object' } },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'questions', 'lensCoverage', 'openQuestions', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
  if (clarificationResult.status === 'BLOCKED') {
    return respond('BLOCKED_INPUT', {
      blockingIssues: blockingIssues(clarificationResult, 'Clarification agent blocked.'),
      clarificationResult,
      nextAction: 'REINVOKE_WITH_ANSWERS',
    })
  }
  questions = asArray(clarificationResult.questions).filter(item => nonEmpty(item?.question))
  if (questions.length === 0) {
    questions = [...missingLenses.map(fallbackQuestion), ...openQuestions]
  }
  return respond('NEEDS_USER_INPUT', {
    questions,
    missingLenses: missingLenses.map(lens => lens.id),
    lensCoverage: clarificationResult.lensCoverage,
    clarificationResult,
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
  migrationDecisions: args?.migrationDecisions || args?.explorationDisposition || {},
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

Read the target project without creating, editing, or deleting files. Identify facts, constraints, migration tasks, true blockers, user decisions, source-of-truth inputs, and asset disposition hints. For operation=migrate, follow this guidance:
${migrationExplorationGuidance}

Resolved migration decisions:
${JSON.stringify(requirementSummary.migrationDecisions)}

Return structured JSON only.`,
        withTaskModel('repository-exploration', {
          label: `workflowprogram-develop:explore:${lens}`,
          schema: {
            type: 'object',
            properties: {
              status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
              findings: { type: 'array', items: { type: 'string' } },
              constraints: { type: 'array', items: { type: 'string' } },
              migrationTasks: { type: 'array', items: { type: 'string' } },
              trueBlockers: { type: 'array', items: { type: 'string' } },
              userDecisions: { type: 'array', items: { type: 'string' } },
              sourceOfTruth: { type: 'array', items: { type: 'string' } },
              assetDispositionHints: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    path: { type: 'string' },
                    action: { type: 'string', enum: dispositionActions },
                    reason: { type: 'string' },
                    supportingAssetPath: { type: 'string' },
                  },
                  required: ['path', 'action', 'reason'],
                  additionalProperties: false,
                },
              },
              blockingIssues: { type: 'array', items: { type: 'string' } },
            },
            required: ['status', 'findings', 'constraints', 'migrationTasks', 'trueBlockers', 'userDecisions', 'sourceOfTruth', 'assetDispositionHints', 'blockingIssues'],
            additionalProperties: false,
          },
        }),
      )
    ),
  )

  const explorationBlockers = explorationDesignBlockers(explorations, operation)
  if (explorationBlockers.length > 0) {
    return respond('BLOCKED_DESIGN', {
      blockingIssues: explorationBlockers,
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

Phase boundary guidance:
${phaseBoundaryGuidance}

Migration guidance:
${migrationExplorationGuidance}

The target Native Workflow JS is the runtime truth. Keep workflow-specific Agents inline by default. Separate L1 schema, L2 JavaScript gates, and L3 external facts. Define phases using the Phase Boundary Contract above; do not split prompt-only work or same-gate parallel exploration into noisy phases. For update or migrate operations, turn migrationTasks and assetDispositionHints into an explicit assetDisposition table for existing and target assets. Each item must include path, action, reason, and supportingAssetPath when action is generate, update, or archive. Valid actions: retain, generate, update, archive, remove, defer, not-applicable. Do not block merely because the target workflow JS is missing before Generate, old design metadata is stale, old runtime assets require archive, managed-files is stale, duplicate legacy assets exist, or no Native JS reference exists. Do not write files. Return structured JSON only.`,
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
          assetDisposition: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                path: { type: 'string' },
                action: { type: 'string', enum: dispositionActions },
                reason: { type: 'string' },
                supportingAssetPath: { type: 'string' },
              },
              required: ['path', 'action', 'reason'],
              additionalProperties: false,
            },
          },
          blockingIssues: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'summary', 'highLevelDesign', 'lowLevelDesign', 'traceability', 'assetDisposition', 'blockingIssues'],
        additionalProperties: false,
      },
    }),
  )
}

if (!hasDesignEvidence(designEvidence, operation)) {
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

Check requirement coverage, lifecycle closure, evidence flow, failure modes, ownership boundaries, testability, and the assetDisposition table. For update or migrate operations, set assetDispositionReviewed=true only when every retained, generated, updated, archived, removed, deferred, or not-applicable asset has a justified disposition and required supporting assets are explicit. Do not block a design because a target workflow JS file does not exist before Generate, because retired runtime assets still need archive, or because managed-files needs an apply-time update; verify that the design classifies those items as migration tasks with asset disposition. Do not write files. Return structured JSON only.`,
    withTaskModel('risk-review', {
      label: 'workflowprogram-develop:review',
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
          blockingIssues: { type: 'array', items: { type: 'string' } },
          requiredRevisions: { type: 'array', items: { type: 'string' } },
          summary: { type: 'string' },
          assetDispositionReviewed: { type: 'boolean' },
        },
        required: ['status', 'blockingIssues', 'requiredRevisions', 'summary', 'assetDispositionReviewed'],
        additionalProperties: false,
      },
    }),
  )
}

if (!hasReviewEvidence(reviewEvidence, operation)) {
  return respond('BLOCKED_DESIGN_REVIEW', {
    blockingIssues: reviewBlockingIssues(reviewEvidence),
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

Phase boundary guidance:
${phaseBoundaryGuidance}

Return a strict authoringSpec object for generate-native-workflow.py. The authoringSpec.body is ONLY the executable body that follows the generated meta header. Do not include export const meta, import statements, require(), module.exports, or any complete JavaScript file header in body. Use valid JavaScript syntax for Claude Code Native Workflow: phase(title), await agent(prompt, options), await parallel(thunks), await pipeline(items, stages...), ordinary JS gates, and a stable return envelope with status. Prefer ordinary await/phase sequencing over pipeline when there is no items collection. Set authoringSpec.phases from the Phase Boundary Contract above, not from prompt paragraphs or same-gate parallel Agents. Do not call Claude Code host tools such as Bash, Read, Write, Edit, or Workflow as JavaScript globals. Do not put skills: [...] in agent options; if a stage needs a reusable skill or CLI tool, state the tool/skill responsibility inside the Agent prompt and require schema fields proving completion. Separate L1 schema, L2 JS gates, and L3 external facts; external scripts must be represented as explicit Agent/tool responsibilities or supporting assets, not as comments that pretend execution happened.

Optional task_model_policy: When the target workflow needs model routing per Agent, set task_model_policy.agent_task_models to a map of agent-label → task-type (e.g. "architecture", "risk-review", "complex-generation"). Omit or leave empty when every agent uses the default model.

Supporting assets and disposition are separate contracts. supporting_assets contains only files that must be generated into the candidate tree, with kind, path, content, and reason. asset_disposition records how existing or target assets are treated, with path, action, reason, and supporting_asset_path when action is generate, update, or archive. Valid actions: retain, generate, update, archive, remove, defer, not-applicable. For update or migrate operations, asset_disposition must match the reviewed design assetDisposition exactly. archive and remove are migration follow-up actions; do not claim managed apply completed them. Return structured JSON only and do not write files.`,
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
              supporting_assets: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    kind: { type: 'string' },
                    path: { type: 'string' },
                    content: { type: 'string' },
                    reason: { type: 'string' },
                  },
                  required: ['kind', 'path', 'content', 'reason'],
                  additionalProperties: false,
                },
              },
              asset_disposition: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    path: { type: 'string' },
                    action: { type: 'string', enum: dispositionActions },
                    reason: { type: 'string' },
                    supporting_asset_path: { type: 'string' },
                  },
                  required: ['path', 'action', 'reason'],
                  additionalProperties: false,
                },
              },
              task_model_policy: {
                type: 'object',
                properties: {
                  agent_task_models: { type: 'object' },
                },
                additionalProperties: false,
              },
            },
            required: ['name', 'description', 'phases', 'body', 'supporting_assets', 'asset_disposition'],
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

if (!hasAuthoringSpec(authoringSpec, operation, designEvidence) || authoringEvidence?.status === 'BLOCKED') {
  return respond('BLOCKED_GENERATION', {
    blockingIssues: blockingIssues(authoringEvidence, 'Authoring spec did not pass.'),
    authoringEvidence,
    nextAction: 'FIX_DESIGN_AND_REINVOKE',
  })
}

phase('Generate')

const generationEvidence = args?.generationEvidence
if (!generationEvidence) {
  const generationHandoff = {
    status: 'READY_FOR_GENERATION',
    workflow: workflowName,
    launchMode,
    runId,
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
      rule: 'The foreground MUST run workflowprogram-continue.py to process this handoff. Do not handwrite handoff input, authoringSpec JSON, or JS body in the foreground. The continuation script unwraps the result envelope, writes the deterministic handoff files, invokes the generator without --apply, and builds generation evidence.',
    },
    handoffSpec: {
      inputFile: 'outputs/stages/native-workflow-generation-handoff-input.json',
      authoringFile: 'native-workflow-authoring.json',
      generationReport: 'outputs/stages/native-workflow-generation.json',
    },
  }
  const continuation = {
    nextAction: 'RUN_CONTROLLED_GENERATION',
    script: 'workflowprogram-continue.py',
    command: 'workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflowprogram-continue.py --workflow-result <RUN_ROOT>/outputs/stages/latest-workflow-result.json --target-root <TARGET_ROOT> --run-root <RUN_ROOT> --json',
    rule: 'The foreground MUST invoke this deterministic script after saving the exact Workflow result; do not write handoff or authoring files manually.',
  }
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
      rule: 'Run workflowprogram-continue.py to stage the candidate deterministically. Do not handwrite handoff, authoringSpec, or JS body in the foreground.',
    },
    generationHandoff,
    continuation,
    nextAction: 'RUN_CONTROLLED_GENERATION',
    continuationCommand: {
      script: 'workflowprogram-continue.py',
      description: 'Deterministic continuation script for READY_FOR_GENERATION - unwraps {result} envelope, writes handoff input and authoring files, invokes generator without --apply, and builds generation evidence.',
      rule: 'The foreground MUST invoke this deterministic script; the guard only allows workflowprogram-continue.py for READY_FOR_GENERATION shell writes.',
    },
  })
}

if (
  !hasEvidence(generationEvidence) ||
  !isSha256Ref(generationEvidence.candidateHash) ||
  !nonEmptyPathArray(generationEvidence.candidateRefs) ||
  !isAbsolutePathRef(generationEvidence.workflowScriptPath)
) {
  return respond('BLOCKED_GENERATION', {
    blockingIssues: blockingIssues(generationEvidence, 'Generation PASS evidence, candidateHash, candidateRefs, and workflowScriptPath are required.'),
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

if (
  !matchesCandidate(validationEvidence, generationEvidence.candidateHash) ||
  !isAbsolutePathRef(validationEvidence?.workflowScriptPath) ||
  pathIdentity(validationEvidence.workflowScriptPath) !== pathIdentity(generationEvidence.workflowScriptPath)
) {
  return respond('BLOCKED_VALIDATION', {
    blockingIssues: blockingIssues(validationEvidence, 'Validation PASS evidence must match the generated candidateHash and workflowScriptPath.'),
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

if (!hasSmokeEvaluatorEvidence(smokeEvidence)) {
  return respond('BLOCKED_SMOKE', {
    blockingIssues: ['Interactive smoke evidence must contain structured evaluator reports proving Workflow launch, async run, Agent execution, schema output, and a PASS completion.'],
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

if (applyApproved && (!matchesCandidate(applyEvidence, generationEvidence.candidateHash) || !hasApplyManifest(applyEvidence, targetRoot))) {
  return respond('BLOCKED_CONFLICT', {
    blockingIssues: blockingIssues(applyEvidence, 'Controlled apply PASS evidence, matching candidateHash and targetRoot, and a structured managed apply manifest are required.'),
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
