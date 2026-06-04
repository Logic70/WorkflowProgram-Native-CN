# WorkflowProgram Logic Lenses

This file is the human-readable source for requirement clarification lenses used by
WorkflowProgram Native develop. The machine-readable counterpart is
`.claude/scripts/lib/clarification_utils.py::LOGIC_LENSES`.

New Native Workflow JS runtime args use the camelCase `runtime_key`. Legacy S1
authoring packets and deterministic scripts may use the snake_case `legacy_key`.
No third key set is allowed.

| runtime_key | legacy_key | title | task | suggested question |
|---|---|---|---|---|
| `purpose` | `purpose` | Purpose Lens | Convert the request from desired artifact into observable purpose and success signal. | What decision or action should become easier after this workflow runs? |
| `objectModel` | `object_model` | Object Lens | Identify input, intermediate, and output objects plus source-of-truth rules. | What intermediate object must exist before the workflow can make the next decision? |
| `processModel` | `process_model` | Process Lens | Decompose the work into meaningful target workflow steps or node candidates. | Before the next major step starts, what must already be known or produced? |
| `decisionModel` | `decision_model` | Decision Lens | Expose branching choices, decision inputs, fallbacks, confidence, and owners. | How should the workflow choose between plausible strategies or next actions? |
| `evidenceModel` | `evidence_model` | Evidence Lens | Define evidence required to trust outputs, decisions, and intermediate models. | What evidence should a reviewer see before trusting this output? |
| `acceptanceModel` | `acceptance_model` | Acceptance Lens | Turn clarified logic into concrete scenarios and expected outputs. | Give one example input where the workflow should pass and one where it should stop. |
| `boundaryModel` | `boundary_model` | Boundary Lens | Define non-goals, stop conditions, manual confirmations, and degradation rules. | What must the workflow never modify or infer automatically? |

## Ownership

- `requirement-clarification-lead` owns user-facing clarification behavior.
- `workflowprogram-develop.js` owns ordering, re-entry, and gates.
- `clarification_utils.py` owns deterministic legacy S1 parsing and machine-readable lens metadata.
- Validators must reject unmapped lens keys and catch drift between this file and machine-readable definitions.

## Design-Consequence Standard

A clarification question is valid only when a different answer can change at least
one of these design surfaces:

- workflow phases or graph nodes;
- branching, approval, threshold, or fallback rules;
- required evidence and validation gates;
- acceptance scenarios or expected outputs;
- write boundaries, stop conditions, manual confirmation, or non-goals.
