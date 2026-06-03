# Ch6: Validation First — Why Generation And Validation Must Be Separate

> The generator is the last component that should act as its own final judge.

## Why Validation Must Be Independent

If generation and validation are owned by the same role, two mistakes become common:

- generation success is mistaken for validation success
- final failure cannot be localized to design, implementation, or environment

That is why WorkflowProgram isolates validation in `S5`.

## The Three Validation Layers

Validation is not a single layer. It is three different checks:

- execution-constraint layer
  - asks whether the run is formally valid
  - for example: boundaries, minimum evidence, valid states and enums
- verdict layer
  - asks whether the run truly passed
  - it checks boundaries, flow, artifacts, and failure mapping rather than only exit status
- dynamic evidence layer
  - asks whether a real run left enough evidence
  - it uses fixed fixtures to fill in end-to-end runtime evidence

## The Current Mapping

The shortest way to remember it:

- the execution-constraint layer decides "may this run proceed like this?"
- the verdict layer decides "does this run count as passing?"
- the dynamic evidence layer decides "did we capture enough runtime evidence?"

In the current implementation:

- `workflow-runner.py`
  - execution-constraint layer
- `workflowprogram-validate`
  - verdict layer
- `runtime_smoke.py`
  - dynamic evidence layer

This boundary is one of the most important design decisions in WorkflowProgram.

If the workflow also declares external capabilities or explicit team orchestration, S5 consumes more than the base verdict:

- capability discovery reports and manual guidance
- host capability probe results
- environment remediation reports and guides
- team fan-out / join evidence

## Which Files Matter Most

The most important outputs from this layer are:

- `RUN_ROOT/validation-runtime-report.md`
- `RUN_ROOT/outputs/stages/s5-validation-summary.json`

The main control-plane evidence is:

- `RUN_ROOT/context.json`
- `RUN_ROOT/state.json`
- `RUN_ROOT/events.jsonl`

Do not mix those two categories together.

When those optional layers are enabled, common additional evidence includes:

- `RUN_ROOT/outputs/stages/host-capability-candidates.json`
- `RUN_ROOT/outputs/stages/host-capability-report.json`
- `RUN_ROOT/outputs/stages/environment-remediation-report.json`
- `RUN_ROOT/outputs/stages/team-plan.json`

## Code Maintenance Gates Are Layered Too

WorkflowProgram maintenance no longer treats every small commit as a full release validation:

- `quality-gate.py commit`
  - fast commit gate for diff checks, core JSON, minimal spec, and template schema
- `quality-gate.py integration`
  - for runtime, runner, finalizer, schema, generator, publish/package, or test harness changes
- `quality-gate.py release`
  - before publishing a plugin version; it must cover build, version consistency, full repository validation, plugin bootstrap, and smoke matrix

The rule is: simplify commit gates, not release gates.

## Practical Template

As soon as a workflow becomes slightly non-trivial, you usually want at least:

1. an execution-constraint layer
2. a verdict layer
3. a dynamic evidence layer

If you compress them into one thing, expansion becomes painful very quickly.

## Next Chapter

Continue to [Ch7: Lessons And Constraints](./07_lessons_and_constraints.md).
