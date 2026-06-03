---
name: lowlevel-design
description: Create, restructure, compare, or review Low-Level Design documents for non-trivial software systems and cross-cutting engineering changes. Use after an HLD exists when Codex needs implementation-ready module boundaries, files, interfaces, schemas, state machines, algorithms, failure handling, configuration, observability, tests, and traceability. Do not use for narrow local edits unless the user explicitly requests an LLD.
version: 1.0.0
---

# Low-Level Design

Translate an approved High-Level Design into implementation-ready contracts. Preserve the HLD's boundaries and sources of truth. Do not silently introduce new architecture.

## Load References

Always read [references/lowlevel-structure.md](references/lowlevel-structure.md).

Read [references/review-checklist.md](references/review-checklist.md) before final review.

## Design Workflow

### 1. Confirm Design Inputs

Read the authoritative HLD, relevant source files, schemas, configuration, tests, and existing LLD. Record HLD decisions, unresolved questions, and implementation constraints.

Stop and request a design decision when implementation would require changing an HLD boundary.

### 2. Define the Implementation Surface

Describe:

- files and directories to create, update, retain, or remove;
- modules, classes, functions, commands, jobs, or handlers;
- public and internal interfaces;
- dependency direction and ownership;
- configuration, environment, and deployment details;
- persistence, schemas, state machines, and invariants where applicable.

### 3. Specify Runtime Behavior

For each important flow, define:

- trigger and preconditions;
- ordered steps;
- inputs and outputs;
- state transitions;
- idempotency and concurrency behavior;
- error taxonomy;
- retry, rollback, and recovery behavior;
- logs, metrics, traces, or evidence.

### 4. Make Contracts Testable

Map every important requirement and HLD decision to implementation artifacts and verification:

| Requirement / Decision | Module or File | Interface or Schema | Test or Evidence |
|---|---|---|---|

Separate unit, integration, smoke, migration, rollback, and operational checks when applicable.

### 5. Keep Implementation Planning Separate

The LLD describes how the steady-state implementation works. Put sequencing, rollout phases, temporary bridges, task assignments, and removal order in a separate implementation or migration plan.

### 6. Review to Closure

Use `$design-plan-closure-review` when available. Otherwise:

1. Review HLD alignment and structural completeness.
2. Patch accepted issues.
3. Review runtime, failure, data, and test behavior.
4. Patch accepted issues.
5. Run a fresh final review and stop only when no new actionable issue remains.

Classify findings as `accept`, `reject`, `defer`, or `ask_user`.

## Output Expectations

Deliver:

- the LLD document or patch;
- HLD-to-LLD traceability;
- unresolved implementation decisions;
- a separate implementation-plan recommendation;
- review-round results.
