# Ch4: Orchestration Chain — Why Orchestration Logic Must Live In Programs

> If the sequence only lives in prompt text, it is still advice rather than a program.

## Why Skill Text Is Not Enough

Skill text is good at defining semantic intent. It is not good at guaranteeing:

- fixed script order
- state persistence
- boundary checks
- consistent structured failure results

The more stable pattern is to split orchestration into two layers:

- an entry layer
  - turns the high-level agreement into a fixed sequence of steps
- a control layer
  - advances state, enforces boundaries, and persists evidence

## What Each Layer Answers

The entry layer answers:

- what should happen first, second, and next
- which checks must happen before any write
- when the flow may move into formal execution

The control layer answers:

- how state advances
- which boundaries must never be crossed
- whether the minimum evidence bundle exists
- what structured output must be written when the run fails

## The Current Mapping

In the current implementation:

- [workflow-entry.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-entry.py)
  - entry layer
  - wires the script chain into a fixed sequence
- [workflow-runner.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-runner.py)
  - control layer
  - owns transitions, boundary checks, evidence persistence, and minimum runtime constraints

The entry chain invokes these steps in order:

1. `validate-workflow-spec.py`
2. `generate-workflow-view.py`
3. `generate-workflow-maintenance.py`
4. `generate-target-runtime.py`
5. `managed-assets.py plan/apply-staged`
6. `discover-host-capabilities.py` (when declared)
7. `probe-host-capabilities.py` / `apply-host-bootstrap.py`
8. `generate-environment-remediation.py`
9. `workflow-runner.py run`
10. `validate-run-state.py`

This means the main path no longer depends on "the model remembering what to do next".

Two boundaries matter here:

- the entry layer prepares not only `.claude/` candidates, but also `workflow-view.md`, `workflow-maintenance.md`, and the target-side runtime wrapper bundle
- if the workflow depends on external capabilities, the entry layer completes discovery, probing, bootstrap, and remediation guidance before entering the runner

## Why This Matters

With these two layers, `workflowprogram-develop` is not just a long instruction sheet anymore. It becomes a deterministic product entry chain.

Keep this summary in mind:

- the entry layer sequences the steps
- the control layer governs the run
- the validation layer judges the result

## Practical Template

As soon as your workflow involves:

- stage transitions
- writes into a target project
- runtime evidence
- structured validation

you should consider moving orchestration logic out of prompts and into deterministic programs.

## Next Chapter

Continue to [Ch5: Managed Apply](./05_managed_apply.md).
