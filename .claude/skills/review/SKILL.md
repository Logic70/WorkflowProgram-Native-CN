---
name: review
description: 对当前变更执行并行多代理代码审查
version: 1.0.0
disable-model-invocation: true
---

对当前变更执行一次并行化代码审查，分别覆盖安全、性能、风格和逻辑四个维度。

## Step 1: 获取 diff

运行 `git diff $ARGUMENTS` 获取审查范围。
如果 `$ARGUMENTS` 为空，则默认使用未暂存变更。
如果 diff 为空，则停止并报告 `No changes to review.`。

## Step 2: Fan-out

在单条消息中并行启动 4 个 Task：

- 安全审查
- 性能审查
- 风格审查
- 逻辑审查

要求：

- 子代理提示词必须完整内联
- 将完整 diff 附在提示词后
- 输出必须是 JSON Lines 或明确的“无问题”说明

## Step 3: Fan-in

收集所有代理输出后：

- 提取 JSON Lines
- 按严重度排序：`critical -> warning -> info`
- 合并重复项

## Step 4: 输出报告

输出结构化审查报告，包括：

- 各维度发现数量
- critical 问题
- warning 问题
- info 建议
- 最终结论：`PASS / NEEDS_WORK / CRITICAL_ISSUES`
