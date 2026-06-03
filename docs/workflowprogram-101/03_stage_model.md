# Ch3: 阶段模型 — 为什么是 S0 到 S6

> 阶段越多不一定越好，但职责不拆开，后面一定会混。

## 3.1 当前阶段模型

`WorkflowProgram` 用 `S0..S6` 来统一描述 workflow 生命周期：

- `S0` 路由
- `S1` 需求澄清
- `S2` 领域研究
- `S3` 结构设计
- `S4` 资产生成与受控写入
- `S5` 验证
- `S6` 闭环

这不是为了好看，而是为了让每一段都能被验证、回退和复盘。

还有一个容易混淆的点：

- `S0` 是所有入口都会先经过的统一路由层。
- 具体某种意图从 `S1-S6` 中至少要走哪些阶段，则由 `workflow-spec.yaml.intent_flows` 声明。

当前默认模板中：

- `develop`：必需 `S1-S6`
- `audit`：必需 `S5-S6`
- `validate`：必需 `S5`，可选 `S6`
- `iterate`：必需 `S6`，可选 `S5`

## 3.2 当前实现为什么这样拆

这一套设计最关键的价值，在于把 3 件经常被混在一起的事情拆开：

- `S4` 负责“把资产生成并受控写入”
- `S5` 负责“判断这次 workflow 是否通过”
- `S6` 负责“提炼 lessons 和约束候选”

所以：

- 生成成功不等于验证通过
- 验证失败不等于这次运行没价值
- 有 lessons 不等于规则已经更新
- 若 workflow 依赖外部能力或显式 team，`S4/S5` 还会多出 discovery / probe / remediation / team evidence 这类附加证据

## 3.3 HighLevel 和 LowLevel 分工

当前两份真源文档的职责是：

- [workflowprogram-stage-highlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-highlevel-design.md)
  - 讲职责边界、验收矩阵、主流程
- [workflowprogram-stage-lowlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-lowlevel-design.md)
  - 讲输入、输出、执行过程、承载文件

你可以把它理解成：

- HighLevel 定义“应该是什么”
- LowLevel 定义“现在具体怎么落”

## 3.4 怎样用它来读当前实现

看源码时，可以这样定位问题：

| 你想知道什么 | 应该先看哪段 |
|---------------|-------------|
| 用户请求被路由成什么 | `S0` |
| 规格草案是否清晰 | `S1` |
| 上下文研究够不够 | `S2` |
| 机器可读设计是否定案 | `S3` |
| 文件是怎么落盘的 | `S4` |
| 最终是否通过验证 | `S5` |
| 这次运行积累了什么经验 | `S6` |

## 3.5 提炼模板

一个好阶段模型至少满足：

1. 每段职责不重叠
2. 每段有最小证据
3. 失败时知道回退到哪

这就是 `S0..S6` 在 WorkflowProgram 里的价值。

## 下一章

继续看 [Ch4: 编排主链](./04_entry_and_runner.md)。
