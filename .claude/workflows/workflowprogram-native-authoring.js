export const meta = {
  name: 'workflowprogram-native-authoring',
  description: 'Run read-only Explore, Design, Review, and Handoff phases after foreground requirement clarification.',
  phases: [
    { title: 'Explore', detail: 'Inspect the confirmed scope and target context without writing files.' },
    { title: 'Design', detail: 'Produce independent Native Workflow JS design candidates.' },
    { title: 'Review', detail: 'Review candidates against the confirmed requirement packet.' },
    { title: 'Handoff', detail: 'Return a structured proposal for foreground candidate generation.' },
  ],
}

const requirement = args?.requirement || ''
const targetRoot = args?.targetRoot || ''
const readinessPacket = args?.readinessPacket || ''
const readinessStatus = args?.readinessStatus || ''
const taskModels = args?.taskModels || {}
const withTaskModel = (taskType, options) => {
  const alias = typeof taskModels[taskType] === 'string' ? taskModels[taskType].trim() : ''
  if (!alias || alias === 'inherit') return options
  return { ...options, model: alias }
}

if (!requirement || !targetRoot || !readinessPacket || readinessStatus !== 'PASS') {
  return {
    status: 'BLOCKED_INPUT',
    workflow: 'workflowprogram-native-authoring',
    blockingIssues: ['requirement, targetRoot, readinessPacket, and readinessStatus=PASS are required'],
  }
}

phase('Explore')

const exploration = await agent(
  `You are the read-only exploration phase for WorkflowProgram Native authoring.

Confirmed requirement:
${requirement}

Target root:
${targetRoot}

Readiness packet:
${readinessPacket}

Readiness status:
${readinessStatus}

Read the readiness packet and confirm it records confirmed_by_user=true, complete lenses, and no open questions. Then inspect the target project and identify reusable assets, constraints, risks, and facts that affect a Native Workflow JS design. Do not create, edit, or delete files. Return structured JSON only.`,
  withTaskModel('repository-exploration', {
    label: 'native-authoring:explore',
    schema: {
      type: 'object',
      properties: {
        status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
        findings: { type: 'array', items: { type: 'string' } },
        constraints: { type: 'array', items: { type: 'string' } },
        reusableAssets: { type: 'array', items: { type: 'string' } },
        blockingIssues: { type: 'array', items: { type: 'string' } },
      },
      required: ['status', 'findings', 'constraints', 'reusableAssets', 'blockingIssues'],
      additionalProperties: false,
    },
  }),
)

if (exploration.status !== 'PASS') {
  return {
    status: 'BLOCKED_EXPLORE',
    workflow: 'workflowprogram-native-authoring',
    blockingIssues: exploration.blockingIssues,
  }
}

phase('Design')

const designCandidates = await parallel(
  ['minimal-control-plane', 'risk-first-control-plane'].map(strategy => () =>
    agent(
      `Design one Claude Code Native Workflow JS control plane using the ${strategy} strategy.

Confirmed requirement:
${requirement}

Exploration:
${JSON.stringify(exploration)}

Return a read-only design proposal. Do not write files. Keep workflow-specific Agent prompts inline by default. Explicitly identify phases, schemas, JavaScript gates, optional supporting assets, and smoke scenarios.`,
      withTaskModel('architecture', {
        label: `native-authoring:design:${strategy}`,
        schema: {
          type: 'object',
          properties: {
            status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
            strategy: { type: 'string' },
            workflowName: { type: 'string' },
            description: { type: 'string' },
            phases: { type: 'array', items: { type: 'string' } },
            schemas: { type: 'array', items: { type: 'string' } },
            gates: { type: 'array', items: { type: 'string' } },
            supportingAssets: { type: 'array', items: { type: 'string' } },
            smokeScenarios: { type: 'array', items: { type: 'string' } },
            blockingIssues: { type: 'array', items: { type: 'string' } },
          },
          required: ['status', 'strategy', 'workflowName', 'description', 'phases', 'schemas', 'gates', 'supportingAssets', 'smokeScenarios', 'blockingIssues'],
          additionalProperties: false,
        },
      }),
    )
  ),
)

phase('Review')

const review = await agent(
  `Review these Native Workflow JS design candidates against the confirmed requirement and exploration findings.

Confirmed requirement:
${requirement}

Exploration:
${JSON.stringify(exploration)}

Candidates:
${JSON.stringify(designCandidates)}

Reject any proposal that skips a requirement, lacks a stable return envelope, confuses schema with external-fact validation, allows unsafe parallel writes, or adds optional assets without a reason. Do not write files.`,
  withTaskModel('risk-review', {
    label: 'native-authoring:review',
    schema: {
      type: 'object',
      properties: {
        status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
        selectedStrategy: { type: 'string' },
        blockingIssues: { type: 'array', items: { type: 'string' } },
        requiredRevisions: { type: 'array', items: { type: 'string' } },
        handoffSummary: { type: 'string' },
      },
      required: ['status', 'selectedStrategy', 'blockingIssues', 'requiredRevisions', 'handoffSummary'],
      additionalProperties: false,
    },
  }),
)

if (designCandidates.some(candidate => candidate.status !== 'PASS') || review.status !== 'PASS') {
  return {
    status: 'BLOCKED_REVIEW',
    workflow: 'workflowprogram-native-authoring',
    blockingIssues: review.blockingIssues,
    designCandidates,
    review,
  }
}

phase('Handoff')

return {
  status: 'PASS',
  workflow: 'workflowprogram-native-authoring',
  blockingIssues: [],
  readinessPacket,
  exploration,
  designCandidates,
  review,
}
