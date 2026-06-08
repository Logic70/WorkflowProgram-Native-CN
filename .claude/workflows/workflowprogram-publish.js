export const meta = {
  name: 'workflowprogram-product-publish',
  description: 'Package a verified target workflow as a marketplace-ready plugin and optionally deliver it.',
  phases: [
    { title: 'Qualify', detail: 'Require or consume deterministic qualification evidence.' },
    { title: 'Package', detail: 'Require or consume deterministic packaging evidence.' },
    { title: 'Verify', detail: 'Require or consume deterministic verification evidence.' },
    { title: 'Local Deliver', detail: 'Require or consume deterministic local delivery evidence.' },
    { title: 'External Apply', detail: 'Require or consume optional deterministic external apply evidence.' },
  ],
}

const workflowName = 'workflowprogram-publish'
const launchMode = 'plugin-script-path'
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
const blockingIssues = (evidence, fallback) => {
  const issues = asArray(evidence?.blockingIssues).filter(nonEmpty)
  return issues.length > 0 ? issues : [fallback]
}
const hasPassEvidence = evidence =>
  evidence?.status === 'PASS' && nonEmptyArray(evidence?.evidence) && isEmptyArray(evidence?.blockingIssues)

const hasPackageHash = (evidence, expectedHash) =>
  hasPassEvidence(evidence) && nonEmpty(evidence?.packageHash) && (!expectedHash || evidence.packageHash === expectedHash)

const hasTargetHash = evidence =>
  hasPassEvidence(evidence) && nonEmpty(evidence?.targetHash)

phase('Qualify')

const runId = args?.runId || ''
const targetRoot = args?.targetRoot || ''
const runRoot = args?.runRoot || ''
const pluginId = args?.pluginId || ''
const repository = args?.repository || ''
const version = args?.version || ''
const repoMode = args?.repoMode || ''
const runtimeMode = args?.runtimeMode || ''

if (!nonEmpty(runId) || !nonEmpty(targetRoot) || !nonEmpty(runRoot) || !nonEmpty(pluginId) || !nonEmpty(repository) || !nonEmpty(version) || !nonEmpty(repoMode) || !nonEmpty(runtimeMode)) {
  return respond('BLOCKED_INPUT', {
    blockingIssues: ['runId, targetRoot, runRoot, pluginId, repository, version, repoMode, and runtimeMode are required'],
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

if (!['current_repo', 'export_repo', 'existing_marketplace'].includes(repoMode)) {
  return respond('BLOCKED_INPUT', {
    blockingIssues: [`Unsupported repoMode: ${repoMode}`],
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

if (!['workflowprogram_dependency', 'vendored_runtime'].includes(runtimeMode)) {
  return respond('BLOCKED_INPUT', {
    blockingIssues: [`Unsupported runtimeMode: ${runtimeMode}`],
    nextAction: 'REINVOKE_WITH_ANSWERS',
  })
}

const qualificationEvidence = args?.qualificationEvidence
if (!qualificationEvidence) {
  return respond('READY_FOR_PUBLISH_QUALIFICATION', {
    nextAction: 'RUN_PUBLISH_QUALIFICATION',
  })
}

if (!hasTargetHash(qualificationEvidence)) {
  return respond('BLOCKED_PUBLISH', {
    blockingIssues: blockingIssues(qualificationEvidence, 'Qualification must PASS with non-empty targetHash and evidence.'),
    qualificationEvidence,
    nextAction: 'RUN_PUBLISH_QUALIFICATION',
  })
}

phase('Package')

const packageEvidence = args?.packageEvidence
if (!packageEvidence) {
  return respond('READY_FOR_PUBLISH_PACKAGE', {
    qualificationEvidence,
    nextAction: 'RUN_PUBLISH_PACKAGE',
  })
}

if (!hasPackageHash(packageEvidence) || !nonEmpty(packageEvidence.targetHash) || packageEvidence.targetHash !== qualificationEvidence.targetHash) {
  return respond('BLOCKED_PUBLISH', {
    blockingIssues: blockingIssues(packageEvidence, 'Package must PASS with non-empty packageHash, matching targetHash, and evidence.'),
    packageEvidence,
    nextAction: 'RUN_PUBLISH_PACKAGE',
  })
}

phase('Verify')

const verificationEvidence = args?.verificationEvidence
if (!verificationEvidence) {
  return respond('READY_FOR_PUBLISH_VERIFICATION', {
    packageEvidence,
    nextAction: 'RUN_PUBLISH_VERIFICATION',
  })
}

if (!hasPackageHash(verificationEvidence, packageEvidence.packageHash)) {
  return respond('BLOCKED_PUBLISH', {
    blockingIssues: blockingIssues(verificationEvidence, 'Verification must PASS with matching packageHash and evidence.'),
    verificationEvidence,
    nextAction: 'RUN_PUBLISH_VERIFICATION',
  })
}

if (repoMode === 'existing_marketplace') {
  const marketplaceEvidence = args?.marketplaceEvidence
  if (!marketplaceEvidence) {
    return respond('READY_FOR_MARKETPLACE_MERGE', {
      verificationEvidence,
      nextAction: 'RUN_MARKETPLACE_MERGE',
    })
  }

  if (!hasPackageHash(marketplaceEvidence, packageEvidence.packageHash)) {
    return respond('BLOCKED_CONFLICT', {
      blockingIssues: blockingIssues(marketplaceEvidence, 'Marketplace merge must PASS with matching packageHash and evidence.'),
      marketplaceEvidence,
      nextAction: 'RUN_MARKETPLACE_MERGE',
    })
  }
}

phase('Local Deliver')

const localDeliveryEvidence = args?.localDeliveryEvidence
if (!localDeliveryEvidence) {
  return respond('READY_FOR_LOCAL_DELIVERY', {
    verificationEvidence,
    nextAction: 'RUN_LOCAL_DELIVERY',
  })
}

if (!hasPackageHash(localDeliveryEvidence, packageEvidence.packageHash)) {
  return respond('BLOCKED_PUBLISH', {
    blockingIssues: blockingIssues(localDeliveryEvidence, 'Local delivery must PASS with matching packageHash and evidence.'),
    localDeliveryEvidence,
    nextAction: 'RUN_LOCAL_DELIVERY',
  })
}

phase('External Apply')

const externalApplyApproved = args?.externalApplyApproved === true

if (!externalApplyApproved) {
  return respond('PASS', {
    deliveryMode: 'local-only',
    evidence: [
      ...asArray(qualificationEvidence.evidence),
      ...asArray(packageEvidence.evidence),
      ...asArray(verificationEvidence.evidence),
      ...asArray(localDeliveryEvidence.evidence),
    ],
    nextAction: 'DELIVER',
  })
}

const externalApplyEvidence = args?.externalApplyEvidence
if (!externalApplyEvidence) {
  return respond('READY_FOR_EXTERNAL_APPLY', {
    localDeliveryEvidence,
    nextAction: 'RUN_EXTERNAL_PUBLISH_APPLY',
  })
}

const extPkgOk = nonEmpty(externalApplyEvidence?.packageHash) && externalApplyEvidence.packageHash === packageEvidence.packageHash

if (!extPkgOk) {
  return respond('BLOCKED_PUBLISH', {
    blockingIssues: blockingIssues(externalApplyEvidence, 'External apply must have matching packageHash.'),
    externalApplyEvidence,
    nextAction: 'RUN_EXTERNAL_PUBLISH_APPLY',
  })
}

if (externalApplyEvidence.status === 'BLOCKED' || externalApplyEvidence.status === 'FAIL') {
  return respond('BLOCKED_CONFLICT', {
    blockingIssues: blockingIssues(externalApplyEvidence, 'External apply is BLOCKED or FAIL.'),
    externalApplyEvidence,
    nextAction: 'RUN_EXTERNAL_PUBLISH_APPLY',
  })
}

if (!hasPassEvidence(externalApplyEvidence)) {
  return respond('BLOCKED_PUBLISH', {
    blockingIssues: blockingIssues(externalApplyEvidence, 'External apply must PASS with evidence.'),
    externalApplyEvidence,
    nextAction: 'RUN_EXTERNAL_PUBLISH_APPLY',
  })
}

return respond('PASS', {
  deliveryMode: 'external-applied',
  evidence: [
    ...asArray(qualificationEvidence.evidence),
    ...asArray(packageEvidence.evidence),
    ...asArray(verificationEvidence.evidence),
    ...asArray(localDeliveryEvidence.evidence),
    ...asArray(externalApplyEvidence.evidence),
  ],
  nextAction: 'DELIVER',
})
