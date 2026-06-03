---
name: workflowprogram-iterate
description: Generate workflow improvement proposals from lessons and current workflow state
version: 1.0.0
disable-model-invocation: true
---

面向 `TARGET_ROOT` 的工作流迭代主入口。基于累计 lessons、当前 workflow 状态和审计结果执行 Native Lessons Loop。

普通用户请求应优先从 `/workflowprogram-cn:workflowprogram-orchestrate <需求>` 进入；本 skill 是 orchestrate 选择 `iterate` intent 后的 leaf 入口，也可用于高级显式调试。

## Native Default Entry

解析插件绝对路径后调用：

```text
Workflow({
  scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-iterate.js",
  args: { ... }
})
```

JS 拥有 Readback、Collect Findings、Build Lessons Delta、Validate Delta、Append Lessons、Propose Constraints、Review、Apply Approved Constraints 和 Deliver 顺序。前台模型只负责转述确认请求、执行以下窄化 adapter，并将 evidence 重新传回同一 JS：

```text
<PLUGIN_ROOT>/scripts/build-native-iterate-evidence.py readback ...
<PLUGIN_ROOT>/scripts/build-native-iterate-evidence.py validate-delta ...
<PLUGIN_ROOT>/scripts/build-native-iterate-evidence.py append-lessons ...
<PLUGIN_ROOT>/scripts/build-native-iterate-evidence.py apply-constraints ...
```

`validate-delta` 必须调用既有 `validate-lessons-delta.py`。lessons 追加使用 `runId + baselineHash + deltaHash` 保证幂等；长期约束写入使用 `runId + baselineHash + proposalHash` 保证幂等。长期约束提升必须经过独立审视和用户显式批准。

## When To Use

- 从 `lessons.md` 提炼可执行改进项
- 为当前 workflow 生成审批优先的迭代草案
- 将批准后的重复经验提升为长期约束

## Core Rules

- 默认输出提案，不自动写入长期 `constraints.md`。
- 无新增经验是合法 PASS，不应制造空写入。
- lessons append 只能通过受控 adapter 执行。
- constraints apply 只能在用户显式批准后通过受控 adapter 执行。
- 冲突或 drift 必须停止并重新 readback。

## Legacy Compatibility

`/iterate-workflow` 仍作为已有目标的兼容入口保留。它不是新建目标的默认控制面，不得与 Native JS 并行维护第二套执行顺序。
