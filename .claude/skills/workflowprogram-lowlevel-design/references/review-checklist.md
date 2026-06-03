# WorkflowProgram Low-Level Design Review Checklist

Apply after the general `$lowlevel-design` checklist.

## Domain Contracts

- Are authoring and target-runtime files separated?
- Is `.claude/workflows/*.js` the explicit Native-mode runtime truth?
- Does every authoring Stage declare entry, actions, outputs, gate, failure, owned files, and evidence?
- Are workflow-specific Agents inline by default?
- Are reusable skills, Agents, scripts, and metadata conditional?
- Does each old runtime capability have retain / replace / narrow / remove and verification decisions?

## Native JS Contracts

- Is the pure-literal `meta` shape explicit?
- Are phase alignment, Agent schema, gate-consumed fields, parallel writes, and stable return envelope specified?
- Are L1, L2, and L3 validation separated?
- Are static validation and smoke both retained?
- Are JSONL evidence paths recorded for runtime claims?

## Migration Boundary

- Is the LLD steady-state only?
- Are rollout, compatibility bridges, flags, rollback, and removal order moved to a migration implementation plan?
