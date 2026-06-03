# Workflow Spec Draft

## Workflow Identity
- 工作流名称: repo-workflow-design
- 触发命令: /develop repo workflow
- 简要描述: 为当前仓库生成和验证工作流资产。

## User Intent
- 用户诉求: 为当前仓库设计一个可审计的 Claude Code workflow。
- 最终目的: 让团队能够稳定生成、验证并迭代工作流资产。
- 成功标准: develop 完成后生成的工作流可以通过 validate 与 smoke；生成链必须留下可回放的运行证据。

## Clarification Summary
- 澄清轮次: 3
- 已确认事项: 目标项目路径由当前目录提供；设计包和 runtime 包都属于交付范围。
- 已消解歧义: 不处理 Windows 兼容性；validate 失败必须留下证据链。

## Requirement Logic Interview
- 复杂度: M
- Purpose Lens: 让团队能够稳定生成、验证并迭代 workflow 资产；成功信号是 develop、validate 与 smoke 证据一致。
- Object Lens: 输入对象为用户请求、目标项目路径和现有 .claude 资产；中间对象为 REQ 索引、设计源、managed plan；输出对象为 .claude 资产和 .workflowprogram 设计/runtime 包。
- Process Lens: clarify requirement -> collect context -> design workflow graph -> generate managed assets -> validate runtime evidence。
- Decision Lens: 资产冲突、审批未通过、环境缺失或验证失败时不得继续 clean PASS，必须停止或回到对应阶段。
- Evidence Lens: 必须保留 clarification package、logic map、managed result、state.json、events.jsonl、S5 summary 和 smoke 记录。
- Acceptance Lens: develop 生成资产后 validate/smoke 通过；冲突或验证失败时输出可追溯失败证据。
- Boundary Lens: 不处理 Windows；不得静默覆盖非托管资产；不得跳过审批和 S5。
- 关键追问: 哪些目标输出必须进入 registry 或 test_contract 以便 S5 验证；哪些失败证据足以阻止 clean PASS。
- 候选节点: intake；design_assets；managed_apply；runtime_validate。
- 负向/停止场景: 审批未通过时停止；目标资产冲突时停止；validate 失败时返回设计或生成阶段。

## Trigger Model
- 调用方式: 手动命令触发
- 触发细节: 用户通过 /develop 在仓库根目录发起工作流设计。

## Inputs
- 必需输入: 用户需求文本；目标项目路径
- 可选输入: 审批策略
- 所需外部上下文: 当前仓库的 .claude 资产现状

## Outputs
- 主交付物: .claude 工作流资产；.workflowprogram/design/ 设计包
- 次级产物: .workflowprogram/runtime/ runtime 包；验证报告
- 输出格式: Markdown；YAML；JSON

## Quality Gates
- 阻塞条件: 阻塞问题未清零；审批未通过
- 必需验证: validate-workflow.py 通过；runtime_smoke_matrix.py 通过
- 完成定义: 设计包、runtime 包和验证报告全部生成

## Open Questions
- 阻塞未决问题: 无
- 可延后问题: 是否需要额外的审计 reviewer 角色。
- 问题处理策略: 延后问题在 S3 设计阶段评估，不阻塞进入 S2/S3。

## Assumptions and Boundaries
- 当前假设: 目标项目允许生成 .workflowprogram 资产。
- 外部依赖: Claude Code runtime
- 关键边界场景: 目标项目已存在 .claude 资产时必须增量修改；设计未通过审批时不得进入 S4；validate 失败时必须给出可追溯证据。
- 明确不做: 本轮不处理 Windows 兼容性。

## Target Workflow Graph Readback
- WorkflowProgram 自身是否仍按 `S0..S6` 开发主链执行: 是，WorkflowProgram 自身仍按 S1-S6 develop 主链执行。
- 目标工作流是否需要非 `S1..S6` 的业务节点: 需要，目标工作流使用 intake、design、validate、iterate 业务节点。
- 目标 workflow_graph 节点: intake；design_assets；managed_apply；runtime_validate。
- 目标 workflow_graph 入口与转移: /develop -> intake -> design_assets -> managed_apply -> runtime_validate -> done。
- 每个 graph 节点的输入、输出、gate、owner: intake 输出需求摘要；design_assets 输出 workflow-spec.yaml；managed_apply 输出 managed-change-result.json；runtime_validate 输出 s5-validation-summary.json。
- 目标输出是否已映射到 `registry` 或 `test_contract.artifacts`: 是，命令、skill、runtime 与设计包均映射到 registry 或 deliverables。

## File Plan
- 需要创建的文件: .workflowprogram/design/workflow-spec.yaml；.workflowprogram/runtime/workflow-entry.py；.claude/commands/example.md。
- 需要修改的文件: .claude/settings.json；.workflowprogram/managed-files.json。

## Readback Confirmation
- 回读摘要: 系统将为当前项目生成一个可验证的 workflow，范围包括设计包、runtime 包和验证链，不包含 Windows 兼容性扩展。
- 用户确认状态: 已确认
- 最近修正: 无
