# WorkflowProgram 101: Designing Workflows As Products

[中文](../workflowprogram-101/index.md) | [English](index.md)

> A maintainable workflow is not just able to generate files. It also needs to explain how it generates, validates, and iterates.

This is the chapter-based English guide for `WorkflowProgram-CN`.

If you want a faster overview first:

- [HTML tutorial](../workflowprogram-101-html/index.en.html)
- [Single-page overview](../workflowprogram-101.en.md)
- [Chinese HTML tutorial](../workflowprogram-101-html/index.html)

If you want to go through the material chapter by chapter in a `Workflow101` style, read in this order:

| Chapter | What You Will Understand | Keywords |
|------|------|------|
| [Ch0 Overview](00_overview.md) | What WorkflowProgram is actually solving | productization, control plane, deliverables |
| [Ch1 Product Thinking](01_product_thinking.md) | Why a workflow is not just a prompt bundle | truth source, control plane, validation, loop |
| [Ch2 Three Roots](02_three_roots.md) | Why `PLUGIN_ROOT / TARGET_ROOT / RUN_ROOT` must be separated | boundaries, evidence, delivery |
| [Ch3 Stage Model](03_stage_model.md) | Why the model is `S0..S6` | responsibilities, evidence, rollback |
| [Ch4 Orchestration Chain](04_entry_and_runner.md) | Why there is an entry wrapper and a runner | deterministic script chain, control plane |
| [Ch5 Managed Apply](05_managed_apply.md) | Why target projects should not be overwritten directly | candidate, managed apply, conflict handling |
| [Ch6 Validation First](06_validation.md) | Why generation and validation must be separated | runner, judge, smoke |
| [Ch7 Lessons And Constraints](07_lessons_and_constraints.md) | How WorkflowProgram learns | lessons, constraints, S6 |
| [Ch8 Apply To Your Project](08_apply_to_your_project.md) | How to reuse these ideas in your own workflow | design checklist, rollout order |

## Recommended Reading Order

1. Start with [Ch0 Overview](00_overview.md)
2. Continue through [Ch1](01_product_thinking.md) to [Ch7](07_lessons_and_constraints.md)
3. End with [Ch8](08_apply_to_your_project.md) and map the ideas to your own target project

## Read With These Questions In Mind

If you have built workflows before, you have probably already hit some of these failure modes:

| Common Problem | Typical Symptom | WorkflowProgram's Response |
|----------|----------|----------------------------|
| Prompts run, but there is no single truth source | Semantics live in skill text, chats, and tribal knowledge | Converge first on a machine-readable truth source |
| Step order depends on model memory | One run designs first, another jumps straight to writing files | Move key sequencing into deterministic programs |
| Target project files are overwritten directly | A broken `.claude/` tree is hard to recover | Write to an isolated candidate area first, then apply changes in a managed way |
| The workflow depends on external capabilities, but no one checks readiness first | Missing skills, MCP servers, or CLIs cause mid-run failure | Discover capabilities first, then probe the host and generate remediation guidance |
| Parallel collaboration stays implicit | Multiple agents work at once, but there is no structured fan-out or join evidence | Use an explicit team contract to declare fan-out, join policy, and evidence |
| Failure cannot be localized | You only know that "it failed" | Separate design, execution, judgment, and evidence capture |
| Runtime evidence is incomplete | You cannot see state, events, or reports afterward | Persist structured evidence for every run |
| Multi-run iteration has no memory | The same mistakes repeat every time | Feed per-run lessons into long-lived rules |
| Natural-language entry is unstable | Similar requests route to different skills | Perform intent detection and routing first |
| Documentation changes do not affect behavior | Markdown changes, but runtime behavior does not | Make the executable truth source explicit |

If you are reading source code along the way, these files are the best anchors:

1. [README.md](/mnt/d/Code/WorkflowProgram-CN/README.md)
2. [README.en.md](/mnt/d/Code/WorkflowProgram-CN/README.en.md)
3. [workflowprogram-stage-highlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-highlevel-design.md)
4. [workflowprogram-stage-lowlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-lowlevel-design.md)
5. [workflow-entry.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-entry.py)
6. [workflow-runner.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-runner.py)
7. [workflow-s5-judge.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-s5-judge.py)

If your workflow also depends on external tools, MCP servers, host skills, or explicit team orchestration, add these files to the reading list:

8. [discover-host-capabilities.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/discover-host-capabilities.py)
9. [probe-host-capabilities.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/probe-host-capabilities.py)
10. [generate-environment-remediation.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/generate-environment-remediation.py)

## The Goal Of This Guide

This guide is not about memorizing terms. It is about building a practical standard for judging:

- what is only a prompt collection
- what is already productized enough to be delivered and maintained
- why WorkflowProgram looks the way it does today
