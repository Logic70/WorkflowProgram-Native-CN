<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

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

## Evidence And Migration Decisions

- Treat raw JSONL as smoke input, not smoke proof. A deterministic evaluator report must prove launch, asynchronous execution, Agent start, schema result, and the expected terminal state before a workflow can pass. For generated candidates, bind the report to the exact candidate `scriptPath`, script hash, candidate-tree hash, and a non-empty scenario identifier.
- Treat controlled apply evidence as a target-bound structured managed-change result that covers every candidate asset, matches the persisted managed result and target manifest, and proves target file hashes. A path string is not an apply manifest.
- Keep `supporting_assets` and `asset_disposition` separate. Supporting assets describe content to create or update; disposition records retain, update, archive, remove, defer, or not-applicable decisions for migration scope.
- Do not impose fields such as `runId` on every workflow return unless the native runtime contract or a product-specific envelope requires them. Static validation should reject unsupported host-tool calls or bare references, reject dynamic code execution that hides them, and conservatively detect critical undeclared identifiers without inventing a second runtime API.

## Existing Workflow Migration

For `operation=migrate`, `request_kind=redesign_existing`, or `target_state=existing_managed_workflow`, design with existing WPN terms and do not introduce a separate product concept.

Classify discovered gaps as migration tasks unless they prevent a trustworthy design. Missing target workflow JS, stale design metadata, retired runtime assets, stale manifests, duplicate legacy assets, and lack of a Native JS reference are expected migration inputs when a current command, Agent, Skill, or user decision still defines behavior.

Use the implementation examples under `$workflowprogram-lowlevel-design/references/examples/` before finalizing the HLD.

## Scope Questions

Resolve:

- Is interactive Claude Code execution the only supported scenario?
- Must user-authored JS be discoverable by listing, directly callable by path, or both?
- Which artifacts remain runtime dependencies?
- Which checks belong inside JavaScript gates, and which require external tools or agents?
- Are resume or cache behaviors required by the target use case, or only inherited from the previous runtime?
