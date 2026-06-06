# WorkflowProgram Native Examples

Use these examples when designing or reviewing Native Workflow JS control planes.
They are implementation-level references, not abstract rules.

| Example | Use When | Shows |
|---|---|---|
| [phase-boundary-positive.md](phase-boundary-positive.md) | Deciding `phase(title)` boundaries | Semantic phases with gates, evidence, and recovery |
| [phase-boundary-negative.md](phase-boundary-negative.md) | Reviewing noisy phase plans | Prompt-only and helper-only splits that should not be phases |
| [migrate-existing-workflow-positive.md](migrate-existing-workflow-positive.md) | `operation=migrate`, `request_kind=redesign_existing`, or `target_state=existing_managed_workflow` | Classifying existing gaps as migration tasks and authoring a new workflow |
| [migrate-existing-workflow-negative.md](migrate-existing-workflow-negative.md) | Reviewing blocked migration designs | Incorrectly treating expected migration work as `BLOCKED_DESIGN` |

Do not copy these examples verbatim into a target project. Use their classification,
handoff, and gate patterns.
