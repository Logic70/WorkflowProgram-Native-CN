# Ch8: Apply To Your Project — How To Reuse These Ideas In Your Own Workflow

> Do not start by writing a skill. Start by clarifying the product boundary.

## A More Stable Rollout Order

If you want to design a workflow for your own project, use this order:

1. define the target deliverables
2. define the machine-readable truth source
3. define the control plane
4. define the managed write boundary
5. define where the verdict comes from
6. define how lessons flow back

This is much more stable than "let's just write a few `SKILL.md` files and see".

## A Reusable Design Checklist

You should answer these questions before implementation:

### Delivery

- which files will be written into the target project
- which files are tool-managed
- which files must never be silently overwritten

### Control Plane

- what the machine-readable truth source is
- whether a stage model is needed
- which steps must move into deterministic scripts
- whether the target project also needs its own runtime wrapper

### Validation

- what counts as `PASS`
- what counts as `FAIL`
- which failures are design issues, implementation issues, or environment issues
- who produces the final verdict
- if external capabilities are required, who discovers them, probes them, and generates remediation guidance

### Capability Extensions

- whether the workflow depends on external skills, MCP servers, CLIs, or host-specialized capabilities
- if so, which ones may bootstrap automatically and which ones require explicit approval
- whether you truly need an explicit agent team rather than ordinary subagents

### Feedback Loop

- where lessons are written
- where long-lived rules are written
- which lessons may be extracted automatically and which require approval

## How To Derive Your Workflow From WorkflowProgram

If you do not know where to start, copy the four-layer structure first:

1. `spec`
2. `entry + runner`
3. `validate`
4. `lessons + constraints`

You do not need to copy `S0..S6` exactly on day one, but keeping these four layers is usually the right call.

## A Minimum Viable Version

If you want a lightweight first version, start with:

1. one machine-readable spec
2. one minimal entry wrapper
3. one write flow with clear boundaries
4. one independent verdict artifact
5. one minimal lessons file

That is already more robust than most prompt-only workflows.

## The Final Test

When you look at your own workflow, ask these five questions:

1. Can I clearly name the truth source?
2. Can I clearly name who controls state transitions?
3. Can I clearly name who produces the final verdict?
4. Can I clearly name where evidence is stored?
5. Can I clearly name how failure lessons change the next run?

If all five are clear, the workflow has started to become a product.
