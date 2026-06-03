# Claude Code Native Workflow JS Variant

Load this reference only when the target uses native Workflow JS or migrates away from a custom runtime.

## Steady-State Decisions

- Treat `.claude/workflows/*.js` as the authoritative executable control plane when native Workflow JS is selected.
- Treat `.workflowprogram/` as optional authoring metadata, audit input, or historical compatibility state unless the design proves a runtime need.
- Prefer explicit JavaScript ordering, branching, and gating over a second custom runner unless a verified native-runtime gap requires one.
- Apply the agent and skill boundary rules from `workflowprogram-structure.md`.

## Validation Layers

Document three layers separately:

| Layer | Responsibility | Typical Mechanism |
|---|---|---|
| L1 Structural | validate files, syntax, schemas, and required fields | static checks, schema checks |
| L2 Orchestration | validate phase order, branching, gates, handoffs, and retries | JavaScript control-plane logic |
| L3 Domain | validate externally observable correctness | tests, CLI probes, domain scripts, review agents |

Retain a smoke test. Native runtime adoption removes duplicated orchestration code; it does not prove that final JavaScript, paths, schemas, permissions, and target behavior work together.

## Scope Questions

Resolve:

- Is interactive Claude Code execution the only supported scenario?
- Must user-authored JS be discoverable by listing, directly callable by path, or both?
- Which artifacts remain runtime dependencies?
- Which checks belong inside JavaScript gates, and which require external tools or agents?
- Are resume or cache behaviors required by the target use case, or only inherited from the previous runtime?
