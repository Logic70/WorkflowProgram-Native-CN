# Target Node Design Template

Use this template for any target workflow node that is complex, loop-enabled, security-critical, reverse-engineering-specific, tool-heavy, or explicitly marked with `node_design_required: true`.

The file path should be declared in `workflow-spec.yaml`:

```yaml
design_refs:
  node_designs:
    <node_id>: outputs/stages/target-node-designs/<node_id>.md
```

## 1. Node Metadata / 节点元信息

- Node ID: `<node_id>`
- Workflow spec path: `workflow_graph.nodes[id=<node_id>]`
- Owner: `<owner from workflow_graph.nodes[*].owner>`
- Template: `<template from workflow_graph.nodes[*].template>`
- Gate: `<gate from workflow_graph.nodes[*].gate or none>`
- Complexity: `<simple | moderate | complex>`
- Design intensity: `<basic | standard | detailed>`

## 2. Purpose And Boundary / 设计目的与职责边界

- Purpose:
- In scope:
- Out of scope:
- Upstream assumptions:

## 3. Input Contract / 输入契约

| Input ref | Required | Producer | Validation rule |
| --- | --- | --- | --- |
| `<input_ref>` | yes | `<producer>` | `<how to validate>` |

## 4. Output Contract And Consumers / 输出契约与消费者

| Output ref | Required | Consumer | Pass criteria |
| --- | --- | --- | --- |
| `<output_ref>` | yes | `<consumer>` | `<how the consumer uses it>` |

## 5. Context Read/Write Rules / 上下文读写规则

- Reads:
- Writes:
- Must not mutate:
- Persistence rule:
- Managed runtime output boundary: output refs are written under the active run root / `WORKFLOWPROGRAM_OUTPUT_ROOT`; final publish paths, latest markers, and manifests are owned only by `target-runtime-finalizer.py`.

## 6. Internal Execution Plan / 内部执行编排

1. Prepare inputs.
2. Execute the node-specific work.
3. Verify outputs.
4. Record runtime evidence.

Loop policy:

- Loop allowed: `<true | false>`
- If enabled, evidence must include loop-plan, iteration summaries, and final verdict.

## 7. Agent / Skill / Script / Tool Calls / 调用关系

| Capability | Name | Purpose | Input | Output |
| --- | --- | --- | --- | --- |
| agent | `<agent>` | `<purpose>` | `<input>` | `<output>` |
| skill | `<skill>` | `<purpose>` | `<input>` | `<output>` |
| script | `<script>` | `<purpose>` | `<input>` | `<output>` |
| tool | `<cli or MCP>` | `<purpose>` | `<input>` | `<output>` |

## 8. Data Field Contract / 数据字段契约

| Field | Type | Required | Source | Meaning |
| --- | --- | --- | --- | --- |
| `<field>` | `<type>` | yes | `<source>` | `<meaning>` |

## 9. Exit Gate / 准出目标

- Gate decision:
- Required evidence:
- Human approval rule:
- Auto-approval rule:

## 10. Failure, Retry, And Degrade Strategy / 失败、重试与降级策略

- `FAIL` when:
- `WARN` when:
- `ENVIRONMENT-SKIP` when:
- Retry limit:
- Degrade strategy:

## 11. Verification And Tests / 验证与测试要求

- Unit or fixture test:
- Runtime verifier:
- Acceptance test refs:
- Evidence paths:

## 12. Observability And Debug Artifacts / 观测与调试产物

- Logs:
- Reports:
- State artifacts:
- Debug reproduction:

## 13. Safety And Execution Constraints / 安全与执行约束

- Path boundary:
- Approval boundary:
- Host capability boundary:
- Secret handling:
- Destructive action policy:

## 14. Open Tasks And Extension Points / 遗留任务与扩展点

- Open tasks: none
- Extension points:
- Deferred decisions:
