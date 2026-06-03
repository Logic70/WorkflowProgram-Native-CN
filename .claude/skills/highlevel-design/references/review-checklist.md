# General High-Level Design Review Checklist

Run at least three review rounds for substantial designs.

## Round 1: Structure and Scope

- Is an HLD proportionate to the task?
- Are user, logical, and deployment views present?
- Were runtime and data views assessed explicitly?
- Are non-applicable views marked with a reason?
- Are steady-state architecture and migration mechanics separated?
- Are authoritative artifacts and precedence rules explicit?

## Round 2: Behavior and Boundaries

- Does each component have a responsibility, input, output, dependency direction, failure behavior, and validation boundary?
- Are important runtime flows and failure recovery paths explicit?
- Are data ownership, consistency, retention, and sensitivity addressed when relevant?
- Does the deployment view explain runtime units, configuration, release, and rollback?
- Is each quality claim tied to a design mechanism and verification method?

## Round 3: Fresh Closure Review

- Can implementation begin without guessing a major boundary?
- Are unresolved questions isolated and materially blocking?
- Are validation expectations observable and testable?
- Does the latest round reveal any new actionable issue?

Patch every accepted issue before declaring closure. Record deferred items with a reason and owner or trigger condition.
