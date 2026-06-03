# Ch3: Stage Model — Why The Model Is `S0` To `S6`

> More stages are not automatically better, but without stage separation responsibilities will blur.

## The Current Stage Model

WorkflowProgram uses `S0..S6` to describe a workflow lifecycle:

- `S0` route
- `S1` requirement clarification
- `S2` context exploration
- `S3` structural design
- `S4` asset generation and managed apply
- `S5` validation
- `S6` feedback loop

This is not decorative. It exists so each segment can be validated, replayed, and rolled back.

One detail matters here:

- `S0` is the universal route layer that every entry passes first.
- The minimum required path through `S1-S6` is declared by `workflow-spec.yaml.intent_flows`.

In the default template:

- `develop`: required `S1-S6`
- `audit`: required `S5-S6`
- `validate`: required `S5`, optional `S6`
- `iterate`: required `S6`, optional `S5`

## Why It Is Split This Way

The value of the stage model is that it separates three concerns that are often mixed together:

- `S4` is about generating assets and applying them safely
- `S5` is about judging whether the workflow passed
- `S6` is about turning what happened into lessons and constraint candidates

So:

- generation success does not equal validation success
- validation failure does not mean the run produced no value
- having lessons does not mean the rules have already been updated
- when a workflow depends on external capabilities or explicit teams, `S4/S5` also carry discovery, probe, remediation, and team evidence

## HighLevel vs LowLevel

The current active design docs divide responsibilities like this:

- [workflowprogram-stage-highlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-highlevel-design.md)
  - responsibilities, acceptance logic, and main flow
- [workflowprogram-stage-lowlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-lowlevel-design.md)
  - inputs, outputs, execution details, and concrete carriers

In short:

- HighLevel defines what should be true
- LowLevel defines how it is currently implemented

## How To Read The Code Through Stages

| Question | Stage To Start With |
|---------------|-------------|
| What did the user request route into? | `S0` |
| Is the spec draft clear enough? | `S1` |
| Was context exploration deep enough? | `S2` |
| Is the machine-readable design settled? | `S3` |
| How were files applied? | `S4` |
| Did the workflow finally pass? | `S5` |
| What did this run teach us? | `S6` |

## Practical Template

A useful stage model should satisfy three things:

1. responsibilities do not overlap
2. each stage has minimum evidence
3. failures indicate where to roll back

That is the value of `S0..S6` in WorkflowProgram.

## Next Chapter

Continue to [Ch4: Orchestration Chain](./04_entry_and_runner.md).
