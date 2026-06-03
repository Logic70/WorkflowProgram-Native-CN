# Ch1: Product Thinking — A Workflow Is Not A Prompt, It Is A Product

> Being able to run once is not the same as being maintainable. WorkflowProgram is designed for repeated, stable use.

## Why Prompt-Only Workflows Break Down

If a workflow only has prompts and manual conventions, it usually lacks:

- a machine-readable truth source
- stable step ordering
- clear layer ownership when failures happen
- a repeatable way to preserve lessons

That might be acceptable for one person and one run. It becomes unstable as soon as the workflow needs to be shared, delivered, and evolved.

## WorkflowProgram's Answer

The current implementation uses four layers:

1. Truth source: `workflow-spec.yaml`
2. Control plane: `workflow-entry.py` + `workflow-runner.py`
3. Validation layer: `workflowprogram-validate`
4. Feedback loop: `S6 lessons & constraints`

These are not four documents. They are four responsibilities.

## The Most Important Design Decisions

The active design docs make these decisions explicit:

- `workflow-spec.yaml` is the control-plane truth source
- the runner owns control-plane execution, not the final S5 verdict
- `workflowprogram-validate` owns the workflow-level verdict
- S6 owns lessons and constraint candidates

So WorkflowProgram explicitly rejects the pattern where one giant prompt tries to design, execute, validate, and summarize at the same time.

## A Simple Productization Test

When you design your own workflow, ask these four questions:

1. What is the machine-readable truth source?
2. Who owns the control plane?
3. Who produces the final verdict?
4. Where do failed runs deposit lessons?

If any answer is missing, the workflow is not productized yet.

## Practical Template

Do not judge a workflow only by whether it generates files. Judge it by whether it has:

- a clear truth source
- a programmatic control plane
- an independent validation layer
- a real feedback loop

## Next Chapter

Continue to [Ch2: Three Roots](./02_three_roots.md).
