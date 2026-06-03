# Ch5: 受控写入 — 为什么不能直接覆盖目标项目

> 能写进去不代表应该直接写进去。

## 5.1 直接写目标项目会出什么问题

如果工作流直接写目标项目，最容易出现 3 类风险：

1. 覆盖用户手工维护的文件
2. 不知道哪些文件是工具托管的
3. 发生冲突时无法保留中间态证据

所以更稳的做法，是把“生成结果”和“正式写入目标项目”拆开。

## 5.2 更稳的方案是什么

这条写入链应该至少分成三步：

1. 先把结果写到隔离候选区
2. 再做一次变更计划，明确哪些文件是创建、更新、冲突
3. 最后才执行受控应用

## 5.3 为什么这很重要

这一层带来的好处是：

- 可以提前发现冲突
- 可以知道哪些文件是 managed
- 可以保留候选和冲突副本
- 可以把“写入”从“生成”里解耦

这对后续验证和审计都很关键。

## 5.4 当前实现里的映射

关键产物包括：

- `RUN_ROOT/outputs/candidate/.claude/`
- `RUN_ROOT/outputs/managed-change-plan.json`
- `RUN_ROOT/outputs/managed-change-result.json`
- `TARGET_ROOT/.workflowprogram/managed-files.json`

想理解这层设计，优先看：

1. [managed-assets.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/managed-assets.py)
2. [workflow-entry.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-entry.py)
3. [README.md](/mnt/d/Code/WorkflowProgram-CN/README.md) 里的目标资产更新契约

## 5.5 提炼模板

只要你的 workflow 会改用户项目，就默认采用：

1. 先生成候选
2. 再做变更计划
3. 再执行受控应用
4. 冲突时保留证据，不静默覆盖

这是 workflow 工程化的一个硬分水岭。

## 下一章

继续看 [Ch6: 验证优先](./06_validation.md)。
