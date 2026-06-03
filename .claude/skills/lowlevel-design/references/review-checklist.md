# General Low-Level Design Review Checklist

## Round 1: HLD Alignment

- Does every major HLD component map to concrete implementation artifacts?
- Did the LLD avoid introducing unapproved architecture?
- Are authoritative, supporting, historical, and deprecated artifacts explicit?
- Are directory, module, interface, and dependency boundaries concrete?

## Round 2: Runtime and Failure Behavior

- Are state transitions, invariants, writes, retries, concurrency, idempotency, rollback, and recovery explicit where relevant?
- Are schemas, enums, configuration, and error kinds concrete?
- Are security, observability, and deployment details sufficient for implementation?
- Does each important contract have a verification method?

## Round 3: Fresh Closure Review

- Can implementation begin without guessing a contract?
- Are tests mapped to important decisions and failure paths?
- Are unresolved questions isolated and materially blocking?
- Did this round reveal any new actionable issue?

Patch accepted findings before declaring closure.
