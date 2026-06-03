# Ch0: Overview — What Problem Is WorkflowProgram Actually Solving?

> WorkflowProgram is not trying to help you write more prompt files. It is trying to turn workflows into deliverable, verifiable, and iterable products.

## Scenario

Many teams start their Claude Code workflows the same way:

- write one `SKILL.md`
- add a few `agents/*.md`
- manually edit `settings.json`

That is enough to get a first version running. It is not enough to keep it stable. The hard problems appear immediately:

- which files in the target project may be changed
- what this run actually changed, and where the evidence is
- whether failure came from design or implementation
- how to avoid the same mistake on the next run

WorkflowProgram exists to address these problems directly.

## The Eight Gaps It Tries To Close

| Gap | What Happens Without It | How WorkflowProgram Responds |
|------|--------------------------|------------------------------|
| No single truth source | Docs, prompts, and implementation drift apart | Converge on one machine-readable source of truth |
| Unstable orchestration order | The model skips, repeats, or reorders steps | Move key sequencing into deterministic programs |
| Unclear write boundaries | The target project is easy to pollute directly | Write to an isolated candidate area before managed apply |
| Weak evidence retention | Failures cannot be replayed or validated automatically | Persist structured evidence for every run |
| Design and execution are mixed together | You cannot tell whether design or execution failed | Split design, execution, judgment, and evidence capture |
| Validation is only an exit code | "Finished" gets confused with "correct" | Separate runtime constraints, test constraints, and verdicts |
| Lessons do not flow back | The next run starts from zero again | Separate per-run lessons from long-lived rules |
| Intent routing is unstable | Similar requests land on different flows | Detect intent and route first |

WorkflowProgram is not primarily about generating files. It is about turning these recurring workflow failure modes into design objects.

## What It Delivers

It does not deliver business code. It delivers workflow assets inside the target project:

- `TARGET_ROOT/.claude/skills/*`
- `TARGET_ROOT/.claude/agents/*`
- `TARGET_ROOT/.claude/rules/*`
- `TARGET_ROOT/.claude/settings.json`

It also delivers governance around those assets:

- a candidate -> managed-apply write chain
- `RUN_ROOT` evidence
- a workflow-level validation verdict
- lessons and constraint candidates

## The Main Flow In One Sentence

```text
User request -> specification -> candidate assets -> managed apply -> validation -> lessons
```

In the current implementation, the main carriers are:

- `workflowprogram-orchestrate`
- `workflowprogram-develop`
- `workflow-entry.py`
- `workflow-runner.py`
- `workflowprogram-validate`
- `validate-lessons-delta.py`

## The Four Intuitions To Keep

1. A workflow is a product, not a prompt collection
2. Design, execution, validation, and iteration are different jobs
3. Writes into the target project must be controlled
4. Every run must leave evidence behind

## Next Chapter

Continue to [Ch1: Product Thinking](./01_product_thinking.md).
