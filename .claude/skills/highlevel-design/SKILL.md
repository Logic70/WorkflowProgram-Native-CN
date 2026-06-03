---
name: highlevel-design
description: Create, restructure, compare, or review High-Level Design documents for non-trivial software systems and cross-cutting engineering changes. Use for new systems, architecture changes, multi-module features, service boundaries, platform work, deployment changes, or technical migrations that need explicit user, logical, deployment, runtime, and data views. Do not use for narrow fixes or small local edits unless the user explicitly requests an HLD.
version: 1.0.0
---

# High-Level Design

Produce a reviewable High-Level Design (HLD) for a software system or substantial engineering change. Describe the steady-state architecture in the HLD. Keep migration sequencing and implementation task breakdowns in separate supporting documents.

## Load References

Always read [references/architecture-views.md](references/architecture-views.md).

Read [references/review-checklist.md](references/review-checklist.md) before the final review.

## Design Workflow

### 1. Judge Proportionality

Confirm that an HLD is warranted. Use an HLD when the change crosses modules, changes an architectural boundary, introduces runtime or deployment behavior, or needs durable design decisions. For a narrow fix, recommend a smaller design note unless the user explicitly wants an HLD.

### 2. Establish the Decision Frame

Record:

- the design target and current baseline;
- the user-visible or caller-visible outcome;
- in-scope and out-of-scope concerns;
- constraints, facts, assumptions, and unresolved decisions;
- authoritative artifacts after implementation.

Inspect existing code, docs, configuration, and runtime patterns before drafting. Distinguish observed facts from proposals.

### 3. Describe the Architecture Through Views

Use the canonical structure from `references/architecture-views.md`.

Always cover:

- user view;
- logical view;
- deployment view.

Always assess whether runtime and data views apply. Expand them when the system has meaningful request flows, background work, state transitions, persistence, caching, consistency, or data ownership. Otherwise mark them `不适用` with a concise reason.

Do not force workflow stages, intent routing, agent models, or publication flows into designs that do not need them.

### 4. Make Boundaries Verifiable

For each major component, state:

- responsibility;
- inputs and outputs;
- source of truth;
- dependency direction;
- lifecycle or ownership;
- failure behavior;
- validation boundary.

For each important runtime flow, state:

- trigger;
- participating components;
- ordered interactions;
- state changes;
- success result;
- failure and recovery behavior;
- evidence or test strategy.

### 5. Add Quality and Verification Contracts

Describe observable requirements for reliability, security, performance, operability, maintainability, and compatibility when applicable. Connect each important quality claim to a design mechanism and verification method.

Separate:

- structural validation: syntax, schema, required files, and static rules;
- integration validation: component contracts, adapters, and dependency wiring;
- behavioral validation: externally observable results, tests, probes, or user flows.

### 6. Classify Related Artifacts

Classify each related artifact as:

- `authoritative`: executable or normative source of truth;
- `supporting`: explanation, example, fixture, or generated view;
- `historical`: retained for migration context only;
- `deprecated`: scheduled for removal.

State conflicts and precedence explicitly.

### 7. Review to Closure

Use `$design-plan-closure-review` when available. Otherwise apply the same closure discipline:

1. Run a structural review against `references/review-checklist.md`.
2. Patch accepted issues.
3. Run a behavioral and boundary review.
4. Patch accepted issues.
5. Run a fresh final review and stop only when no new actionable issues remain.

Classify findings as `accept`, `reject`, `defer`, or `ask_user`. Do not leave accepted findings unpatched.

## Output Expectations

Deliver:

- the HLD document or patch;
- a short decision summary;
- open questions that materially block implementation;
- review-round results;
- any separate migration-plan recommendation.

Preserve coherent repository conventions. Prefer updating an existing authoritative HLD over creating a parallel document with overlapping authority.
