---
name: workflowprogram-lowlevel-design
description: Create, restructure, compare, or review Low-Level Design documents for WorkflowProgram itself, WorkflowProgram-generated target workflows, and migrations to Claude Code native Workflow JS. Use when implementation-ready detail is needed for WorkflowProgram stages, control-plane JavaScript, agents, skills, schemas, gates, static validation, managed updates, smoke fixtures, JSONL evidence, publishing, or old-runtime migration.
version: 1.0.0
---

# WorkflowProgram Low-Level Design

Design implementation-ready WorkflowProgram contracts as a domain-specific extension of the general LLD method.

## Load References

Read `$lowlevel-design` first and apply its general detailed-design method.

Always read [references/workflowprogram-lowlevel-structure.md](references/workflowprogram-lowlevel-structure.md).

Read [references/native-workflow-js.md](references/native-workflow-js.md) when designing Native Workflow JS, `.claude/workflows/*.js`, static validation, managed updates, or migration away from the Python runtime.

Read [references/review-checklist.md](references/review-checklist.md) before final review.

## Design Workflow

### 1. Start from the WorkflowProgram HLD

Read the authoritative or target WorkflowProgram HLD and classify each referenced artifact. Keep old-runtime facts separate from Native Workflow JS target decisions.

### 2. Define Concrete Contracts

Specify:

- target directories and files;
- Native Workflow JS module shape and pure-literal `meta`;
- phases, Agent prompts, schemas, JS gates, `parallel()`, and `pipeline()`;
- semantic ownership for reusable prompts and roles: dedicated Agent files or shared references own reusable clarification/review/generation semantics; JS owns ordering and gates; deterministic scripts own enforcement;
- authoring stages, inputs, outputs, failure states, and evidence;
- static validator rules and fixtures;
- controlled-update drift detection;
- optional skill, reusable Agent, domain script, metadata, and publishing conditions;
- smoke tests and JSONL evidence.

When a prompt role is reused across product workflows, appears in skill text as a named role, or contains durable definitions such as requirement-clarification lenses, specify it as a reusable Agent or shared reference. Do not rely on ad hoc prompts like "you are <role>" from the foreground model or inline JS to stand in for a registered Agent. Keep workflow-local one-off prompts inline.

### 3. Decide Each Inherited Capability

For every old Python runtime capability, record:

| Capability | Current Responsibility | Retain / Replace / Narrow / Remove | Native Mechanism | Verification |
|---|---|---|---|---|

Do not preserve old runtime machinery by default.

### 4. Preserve Validation Layers

Keep:

- L1 schema validation;
- L2 JavaScript orchestration gates;
- L3 external-fact validation via CLI or deterministic domain scripts;
- static validation before launch;
- interactive smoke after static validation.

### 5. Separate LLD from Migration Plan

Keep steady-state implementation contracts in the LLD. Put implementation order, temporary compatibility bridges, feature flags, rollout, and old-asset removal into a separate migration plan.

### 6. Review to Closure

Use `$design-plan-closure-review`. Apply the general `$lowlevel-design` checklist and [references/review-checklist.md](references/review-checklist.md). Patch accepted findings after each round.

## Output Expectations

Deliver:

- a WorkflowProgram-specific LLD;
- HLD-to-LLD traceability;
- file, schema, state, validator, and fixture contracts;
- inherited-capability decisions;
- a separate migration implementation plan;
- review-round results.
