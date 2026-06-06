---
name: workflowprogram-highlevel-design
description: Create, restructure, compare, or review High-Level Design documents for WorkflowProgram itself, WorkflowProgram-generated target workflows, and migrations to Claude Code native Workflow JS. Use when the design needs WorkflowProgram stages, intent routing, agents, skills, control-plane JavaScript, validation layers, target workflow publishing, or compatibility decisions for `.workflowprogram/` and `.claude/` assets.
version: 1.0.0
---

# WorkflowProgram High-Level Design

Design WorkflowProgram and its generated workflow assets as a domain-specific extension of the general HLD method.

## Load References

Read the `$highlevel-design` Skill first and apply its general architecture-view method.

Always read [references/workflowprogram-structure.md](references/workflowprogram-structure.md).

Read [references/native-workflow-js.md](references/native-workflow-js.md) when the design uses Claude Code native Workflow JS, `.claude/workflows/*.js`, agents, skills, or migration away from a custom runtime.

For Native Workflow JS phase boundaries or migration of an existing managed workflow, read the implementation examples in `$workflowprogram-lowlevel-design/references/examples/README.md` and load the matching positive/negative examples before finalizing the HLD.

Read [references/review-checklist.md](references/review-checklist.md) before final review.

## Design Workflow

### 1. Start from General Architecture Views

Cover the user, logical, and deployment views required by `$highlevel-design`. Assess runtime and data views explicitly. Do not replace these views with a Stage list.

### 2. Add the WorkflowProgram Domain Model

Describe:

- product entrypoints and intent routing;
- authoring-time assets and runtime assets;
- ordered stages, gates, handoffs, and failure paths;
- generated target workflow ownership;
- agent and skill responsibilities;
- validation layers;
- installation, publication, and compatibility boundaries.

For each stage, state purpose, entry condition, input, action, output, exit criteria, failure path, and evidence.

### 3. Separate Steady State from Migration

Keep the target control plane and artifact ownership model in the HLD. Put rollout phases, temporary compatibility bridges, implementation tasks, and removal order in a separate migration plan or appendix.

### 4. Make Runtime Decisions Explicit

Do not retain a custom runtime, validator, cache, resume mechanism, or guard by default. For each inherited capability:

1. state the current responsibility;
2. determine whether the target scenario still requires it;
3. determine whether native Workflow JS already covers it;
4. retain, replace, narrow, or remove it with a verification method.

### 5. Review to Closure

Use `$design-plan-closure-review`. Apply both the general `$highlevel-design` review checklist and `references/review-checklist.md`. Patch accepted issues after each round and stop only after a fresh round finds no new actionable issue.

## Output Expectations

Deliver:

- a general-view HLD with WorkflowProgram-specific sections;
- an explicit authoritative-artifact map;
- a Stage acceptance matrix;
- validation and smoke-test contracts;
- a separate migration-plan recommendation when behavior changes;
- review-round results and materially blocking questions.
