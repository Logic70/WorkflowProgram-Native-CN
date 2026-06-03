# WorkflowProgram 101：把工作流当成产品来设计

[中文](index.md) | [English](../workflowprogram-101-en/index.md)

> 一套可维护的工作流，不只是能生成文件，还要能说明怎么生成、怎么验证、怎么迭代。

这是 `WorkflowProgram-CN` 的章节版入门教程。

如果你只想快速扫一遍全貌，读单页版：

- [HTML 版教程](../workflowprogram-101-html/index.html)
- [单页版教程](../workflowprogram-101.md)

如果你想按 `Workflow101` 的方式逐章理解，按下面顺序读：

| 章节 | 你会理解什么 | 关键词 |
|------|--------------|--------|
| [Ch0 全景](00_overview.md) | WorkflowProgram 到底在解决什么问题 | 产品化、控制面、交付物 |
| [Ch1 设计哲学](01_product_thinking.md) | 为什么 workflow 不是 prompt 集合 | 真源、控制面、验证、闭环 |
| [Ch2 三层目录模型](02_three_roots.md) | 为什么要区分 `PLUGIN_ROOT/TARGET_ROOT/RUN_ROOT` | 边界、证据、交付 |
| [Ch3 阶段模型](03_stage_model.md) | 为什么是 `S0..S6` | 职责、证据、回退 |
| [Ch4 编排主链](04_entry_and_runner.md) | 为什么要有 `workflow-entry.py` 和 `workflow-runner.py` | 确定性脚本链、程序控制面 |
| [Ch5 受控写入](05_managed_apply.md) | 为什么不能直接覆盖目标项目 | candidate、managed apply、冲突 |
| [Ch6 验证优先](06_validation.md) | 为什么生成链和验证链必须分开 | runner、judge、smoke |
| [Ch7 经验积累](07_lessons_and_constraints.md) | WorkflowProgram 如何学习 | lessons、constraints、S6 |
| [Ch8 迁移到你的项目](08_apply_to_your_project.md) | 如何用这套方法设计自己的 workflow | 设计清单、落地顺序 |

## 怎么读

建议顺序：

1. 先读 [Ch0 全景](00_overview.md)
2. 再读 [Ch1](01_product_thinking.md) 到 [Ch7](07_lessons_and_constraints.md)
3. 最后用 [Ch8](08_apply_to_your_project.md) 对照你自己的目标项目

## 先带着这些问题去读

如果你以前做过工作流编排，通常会先撞到下面这些问题：

| 常见问题 | 典型表现 | WorkflowProgram 的设计思路 |
|----------|----------|----------------------------|
| 提示词能跑，但语义没有统一真源 | 口径散在技能说明、聊天记录和人工约定里 | 先收口到机器可读的设计真源，再派生说明文档 |
| 编排顺序靠模型“记住” | 这轮先做设计，下一轮直接跳去写文件 | 把关键顺序沉到确定性程序里 |
| 目标项目被直接覆盖 | 改坏 `.claude/` 后很难恢复 | 先写隔离候选区，再做受控应用 |
| 工作流依赖外部能力，但运行前没人确认 | 缺 skill、MCP、CLI 时直接在中途失败 | 先做能力发现，再做宿主探测和环境修复指引 |
| 并行协作只停留在口头约定 | 多个 agent 同时工作但没有结构化证据 | 用显式 team 契约声明 fan-out、join 和证据要求 |
| 失败后不知道错在设计还是执行 | 最终只有“失败了”，没有分层证据 | 把设计、执行、判定、补证据拆层 |
| 运行留下的证据不足 | 回头看不到状态、事件和运行报告 | 为每次运行固定留下结构化证据 |
| 多轮迭代没有记忆 | 每次都重复踩同一个坑 | 把单次经验回流到长期规则 |
| 自然语言入口不稳定 | 同一句话有时走开发，有时走验证 | 先做入口识别和意图路由 |
| 修改了文档但真实行为没变 | 改了 Markdown，却没改真实行为 | 明确“执行真源”和“说明文档”谁说了算 |

如果你已经在读源码，这几个文件最值得配合着看：

1. [README.md](/mnt/d/Code/WorkflowProgram-CN/README.md)
2. [workflowprogram-stage-highlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-highlevel-design.md)
3. [workflowprogram-stage-lowlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-lowlevel-design.md)
4. [workflow-entry.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-entry.py)
5. [workflow-runner.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-runner.py)
6. [workflow-s5-judge.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-s5-judge.py)

如果你的 workflow 还依赖外部工具、MCP、宿主技能或显式 team，还应额外关注：

7. [discover-host-capabilities.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/discover-host-capabilities.py)
8. [probe-host-capabilities.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/probe-host-capabilities.py)
9. [generate-environment-remediation.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/generate-environment-remediation.py)

## 这套教程的目标

它不是教你背术语，而是帮你建立一个判断标准：

- 什么样的 workflow 只是 prompt 组合
- 什么样的 workflow 已经具备产品化能力
- WorkflowProgram 当前实现为什么会长成现在这样
