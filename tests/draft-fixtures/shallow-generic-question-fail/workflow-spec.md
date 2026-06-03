# Workflow Spec Draft

## Workflow Identity
- 工作流名称: generic-question-workflow
- 触发命令: /develop generic question workflow
- 简要描述: 用于证明复杂需求不能只靠泛问题进入设计。

## User Intent
- 用户诉求: 创建一个复杂分析工作流。
- 最终目的: 让团队能够稳定分析仓库并输出报告。
- 成功标准: 工作流能输出报告、证据和验证摘要。

## Clarification Summary
- 澄清轮次: 3
- 已确认事项: 目标项目、输出报告和验证摘要都属于范围。
- 已消解歧义: 运行证据必须保留，失败不得 clean PASS。

## Requirement Logic Interview
- 复杂度: L
- Purpose Lens: 目标是输出可验证的分析报告。
- Object Lens: 输入对象为代码仓库和用户请求；输出对象为分析报告和验证证据。
- Process Lens: intake -> analyze -> report -> validate。
- Decision Lens: 分析失败时停止，验证失败时不得 clean PASS。
- Evidence Lens: 必须保留报告、日志和 S5 summary。
- Acceptance Lens: 给定明确仓库时生成报告并通过验证。
- Boundary Lens: 不修改应用代码；不静默覆盖用户资产。
- 关键追问: 还有哪些边界场景？
- 候选节点: intake；analyze；report；validate。
- 负向/停止场景: 验证失败时停止；输入仓库不可读时停止。

## Trigger Model
- 调用方式: 手动命令触发
- 触发细节: 用户通过 /develop 在仓库根目录发起复杂分析工作流设计。

## Inputs
- 必需输入: 用户需求文本；目标项目路径
- 可选输入: 审批策略
- 所需外部上下文: 当前仓库上下文

## Outputs
- 主交付物: 分析报告
- 次级产物: 验证报告
- 输出格式: Markdown；JSON；YAML

## Quality Gates
- 阻塞条件: 阻塞问题未清零；验证失败
- 必需验证: validate-workflow.py 通过；runtime smoke 通过
- 完成定义: 报告和验证证据全部生成

## Open Questions
- 阻塞未决问题: 无
- 可延后问题: 是否需要额外 reviewer。
- 问题处理策略: 延后问题在 S3 设计阶段评估，不阻塞进入 S2/S3。

## Assumptions and Boundaries
- 当前假设: 目标项目可访问。
- 外部依赖: Claude Code runtime
- 关键边界场景: 目标项目不存在时停止；验证失败时停止；审批未通过时停止。
- 明确不做: 不修改应用代码。

## Target Workflow Graph Readback
- WorkflowProgram 自身是否仍按 `S0..S6` 开发主链执行: 是。
- 目标工作流是否需要非 `S1..S6` 的业务节点: 需要。
- 目标 workflow_graph 节点: intake；analyze；report；validate。
- 目标 workflow_graph 入口与转移: /develop -> intake -> analyze -> report -> validate -> done。
- 每个 graph 节点的输入、输出、gate、owner: intake 输入用户请求；analyze 输出分析中间结果；report 输出报告；validate 输出验证摘要。
- 每个 graph 节点的执行模型（skill / agent / script / team / loop）: intake 使用 skill；analyze 使用 agent；report 使用 skill；validate 使用 script。
- 哪些 node 需要独立 agent，原因是什么: analyze 需要独立 agent，因为需要跨文件推理。
- 哪些 node 不需要独立 agent，原因是什么: intake/report/validate 可由当前 skill 或脚本完成。
- 复杂 node-design 输出路径: outputs/stages/node-designs/analyze.md。
- 需要 `loop_policy` 的 graph 节点: 无。
- 每个 loop 节点的 `max_iterations`、反馈命令、停止条件、证据输出: 无。
- 目标输出是否已映射到 `registry` 或 `test_contract.artifacts`: 是，报告和验证摘要都映射到 deliverables。

## File Plan
- 需要创建的文件: .workflowprogram/design/workflow-spec.yaml；.workflowprogram/runtime/workflow-entry.py；.claude/commands/analyze.md。
- 需要修改的文件: .claude/settings.json。

## Readback Confirmation
- 回读摘要: 系统将创建一个复杂分析工作流，但当前追问仍然过于宽泛。
- 用户确认状态: 已确认
- 最近修正: 无
