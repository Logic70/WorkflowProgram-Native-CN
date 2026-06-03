# Ch6: 验证优先 — 为什么生成链和验证链必须分开

> 生成者最不适合担任自己的最终裁判。

## 6.1 为什么验证必须独立出来

如果“生成”和“验证”是同一个角色负责，通常会有两个问题：

- 生成成功就被误当成验证通过
- 最终失败时无法区分是设计缺陷、实现缺陷还是环境缺陷

所以 `WorkflowProgram` 当前把验证单独放在 `S5`。

## 6.2 先理解三层验证各自解决什么问题

验证不是一层，而是三层：

- 执行约束层
  - 回答“这次运行在形式上是不是合格的”
  - 例如有没有越界写入、有没有留下最小证据、状态和值域是否合法
- 结果判定层
  - 回答“这次运行算不算真正通过”
  - 不只看脚本有没有结束，而是看边界、流程、产物和失败映射是否满足定义
- 动态补证据层
  - 回答“真实运行时有没有留下足够证据”
  - 用固定场景补上端到端运行时的信息

## 6.3 当前实现里的映射

一句话记忆：

- 执行约束层决定“能不能这样跑”
- 结果判定层决定“这样跑算不算通过”
- 动态补证据层决定“真实运行时有没有把证据补齐”

在当前实现里，对应关系是：

- `workflow-runner.py`
  - 执行约束层
- `workflowprogram-validate`
  - 结果判定层
- `runtime_smoke.py`
  - 动态补证据层

这条边界，是 `WorkflowProgram` 当前实现最关键的设计之一。

如果 workflow 还声明了外部能力或显式 team，S5 不只看基础 verdict，还会额外消费：

- 能力发现报告与人工指引
- 宿主能力探测结果
- 环境修复报告与修复指南
- Team fan-out / join 证据

## 6.4 最终看什么文件

这层最重要的输出是：

- `RUN_ROOT/validation-runtime-report.md`
- `RUN_ROOT/outputs/stages/s5-validation-summary.json`

而控制面证据主要是：

- `RUN_ROOT/context.json`
- `RUN_ROOT/state.json`
- `RUN_ROOT/events.jsonl`

这两类文件不要混着理解。

如果启用了扩展能力，常见的附加证据还包括：

- `RUN_ROOT/outputs/stages/host-capability-candidates.json`
- `RUN_ROOT/outputs/stages/host-capability-report.json`
- `RUN_ROOT/outputs/stages/environment-remediation-report.json`
- `RUN_ROOT/outputs/stages/team-plan.json`

## 6.5 代码维护门禁也分层

WorkflowProgram 自身维护不再把每次小提交都升级为完整发布验证：

- `quality-gate.py commit`
  - 快速提交门禁，检查 diff、核心 JSON、最小 spec 和模板 schema。
- `quality-gate.py integration`
  - 改到 runtime、runner、finalizer、schema、生成器、publish/package 或测试 harness 时运行。
- `quality-gate.py release`
  - 发布插件版本前运行，必须覆盖构建、版本一致性、完整仓库校验、插件 bootstrap 和 smoke matrix。

原则是：提交门禁可以精简，发布门禁不能精简。

## 6.6 提炼模板

只要 workflow 稍微复杂一点，最好至少拆出：

1. 执行约束层
2. 判定层
3. 动态证据层

把这三层揉在一起，后面几乎一定会难以扩展。

## 下一章

继续看 [Ch7: 经验积累](./07_lessons_and_constraints.md)。
