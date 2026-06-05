# Native Workflow Product Smoke Evidence

This fixture tracks the remaining legacy-retirement blocker:
`full-product-interactive-smoke-not-declared-complete`.

Do not close the blocker by hand-editing coverage flags. The supported flow is:

1. Execute packet prompts in a real interactive Claude Code session with Native Workflow enabled.
2. Evaluate each captured JSONL with `.claude/scripts/build-native-interactive-smoke.py evaluate`, passing the exact product workflow `--script-path` and a non-empty `--scenario-id`.
3. Aggregate evaluator reports with `.claude/scripts/build-native-product-smoke-evidence.py`.
4. Write the aggregate to `.workflowprogram/evidence/native-product-interactive-smoke.json` only when the aggregate returns `PASS` and `declaredComplete=true`.

## Packets

The `packets/` directory contains early-blocker packets for the five product workflows:

- `develop-blocked.packet.json`
- `validate-blocked.packet.json`
- `audit-blocked.packet.json`
- `iterate-blocked.packet.json`
- `publish-blocked.packet.json`

These packets cover blocked-path launch evidence. They do not cover the required PASS, agent, or schema evidence by themselves.

Product smoke is coverage-based across real evaluator reports:

- `early-blocker` proves plugin discovery, `Workflow({ scriptPath })` launch, async execution, and a `BLOCKED_*` completion.
- `completion` proves plugin discovery, `Workflow({ scriptPath })` launch, async execution, and a workflow-level `PASS` or `BLOCKED_*` completion without requiring subagent evidence in that same run.
- `agent-schema` proves plugin discovery, `Workflow({ scriptPath })` launch, async execution, subagent start, and schema-shaped subagent output without requiring workflow completion in that same run.

The aggregator rejects reports that lack `return_code=0`, empty blockers, an absolute `scriptPath`, a non-empty scenario, run IDs, async launch evidence, or profile-specific completion/Agent evidence.

## Aggregation

Example after collecting real evaluator reports:

```powershell
python .claude/scripts/build-native-product-smoke-evidence.py `
  --evaluation .workflowprogram/evidence/product-smoke/develop-blocked.evaluate.json `
  --evaluation .workflowprogram/evidence/product-smoke/validate-blocked.evaluate.json `
  --evaluation .workflowprogram/evidence/product-smoke/audit-blocked.evaluate.json `
  --evaluation .workflowprogram/evidence/product-smoke/iterate-blocked.evaluate.json `
  --evaluation .workflowprogram/evidence/product-smoke/publish-blocked.evaluate.json `
  --evaluation .workflowprogram/evidence/product-smoke/validate-pass.evaluate.json `
  --evaluation .workflowprogram/evidence/product-smoke/develop-agent-schema.evaluate.json `
  --out .workflowprogram/evidence/native-product-interactive-smoke.json `
  --json
```

The aggregate script returns non-zero and keeps `declaredComplete=false` until all required coverage flags are true.
