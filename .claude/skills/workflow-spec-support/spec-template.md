# Workflow Specification

> **Note**: 本模板用于自然语言设计文档。
> 对于机器可读的编排配置，请使用 `yaml-spec-template.md`。
> 两者关系：`spec-template.md` → target design source → `workflow-spec.yaml` target runtime map → 生成 `workflow-view.md` / `workflow-maintenance.md` derived target views。
> `workflow-spec.yaml` 是机器语义真源与运行态地图；完整目标工作流设计推理应保留在 `target-design-overview.md` / `target-design-detail.md` / 条件性 `target-node-designs/**` 中。
> 复杂、loop、工具重、逆向、安全或多下游节点的 node-design 必须参考 `target-node-design-template.md`，并能通过 `validate-target-node-design.py`。
> 新生成目标工作流默认使用 `target_runtime_policy.mode=managed_runtime`：用户命令只作为 wrapper 启动 `.workflowprogram/runtime/workflow-entry.py`，目标业务节点由 `target-workflow-runner.py` 按 `workflow_graph.nodes` 执行并记录 provenance。
> 目标 runtime 不假设 `claude -p` 可用；执行节点必须通过 `target_executor_policy` 选择 `fixture_host` / `command_adapter` 自动 provider，或通过 `current_agent` / `manual` provider 提交结构化 executor evidence，再由 finalizer 决定能否 PASS。
> 若目标 workflow 会生成最终报告或可复用输出，默认启用 `target_publish_policy.enabled=true`：节点只能先写 run-scoped outputs，`target-runtime-finalizer.py` 统一校验 state/node/provenance/report 后原子发布，禁止业务节点直接声明 final PASS/COMPLETE；`validate-target-publish-state.py` 会拒绝手写 `COMPLETE` manifest、旧 latest marker 或 target-state/report/provenance 不一致的最终目录。`required_reports` 和 `workflow_graph` 节点输入/输出都不得引用 finalizer 自己生成的 manifest/latest marker。
> 节点 owner prompt（agent/skill）必须把 `workflow_graph.nodes[*].output_refs` 描述为 active run root / `WORKFLOWPROGRAM_OUTPUT_ROOT` 下的相对路径；不要把这些路径描述成最终发布目录，也不要让任何 owner prompt 读取或写入 finalizer-owned manifest/latest marker。

## Workflow Identity

- 工作流名称：
- 触发命令：
- 简要描述：

## User Intent

- 用户诉求：
- 最终目的：
- 成功标准：

## Requirement Lineage

- 原始请求 source_ref：
- `REQ-*` 需求条目：
- 每条需求的优先级：
- 每条需求的验收口径：
- 每条需求的边界或明确不做：

## Clarification Summary

- 澄清轮次：
- 已确认事项：
- 已消解歧义：

## Requirement Logic Interview

- 复杂度：S / M / L / XL
- Purpose Lens：问题、目的、主要使用者、成功信号、非目标
- Object Lens：输入对象、中间对象、输出对象、关键字段、source of truth、未知信息处理
- Process Lens：候选步骤 / node、每步输入输出、前置条件、完成信号、人工触点
- Decision Lens：关键分支、决策输入、规则或启发式、fallback、置信度、owner
- Evidence Lens：必须保留的证据、证据链接、PASS 最小证据、不可接受证据
- Acceptance Lens：happy path、负向场景、歧义场景、期望输出、验收 owner
- Boundary Lens：明确不做、停止条件、人工确认、可延后规则、安全约束、降级策略
- 关键追问：记录 1-3 个会改变 node / decision / evidence / acceptance / boundary 的窄问题
- 候选节点：复杂请求中目标 workflow_graph.nodes[*] 的候选节点
- 负向/停止场景：复杂请求中必须失败、停止或要求用户确认的场景

## Open Questions

- 阻塞未决问题：
- 可延后问题：
- 问题处理策略：

## Assumptions and Boundaries

- 当前假设：
- 外部依赖：
- 关键边界场景：
- 明确不做：

## Readback Confirmation

- 回读摘要：
- 用户确认状态：
- 最近修正：

## Problem Statement

- 需要自动化的流程是什么？
- 为什么现在需要这个工作流？

## Users and Stakeholders

- 主要使用者：
- 次要相关方：

## Trigger Model

- 调用方式：手动命令 / Hook / 混合
- 触发细节：

## Inputs

- 必需输入：
- 可选输入：
- 所需外部上下文：

## Outputs

- 主交付物：
- 次级产物：
- 输出格式：

## Quality Gates

- 阻塞条件：
- 必需验证：
- 完成定义：

## Roles and Expert Dimensions

- 角色 1：
- 角色 2：
- 角色 3：
- 需要补充的专业能力（skill / MCP / CLI）：
- 是否需要 capability discovery / host bootstrap 指引：
- 若使用领域能力画像（如 reverse engineering），默认能力包中哪些能力需要保留、移除或替换：
- 若领域画像提供默认 agent team，哪些角色/阶段分工需要保留、裁剪或关闭：
- 若存在 `project_local` bootstrap，需要生成哪些可复用配置 / wrapper / bootstrap 资产：
- 若存在 `host_global` bootstrap，WorkflowProgram 只生成 plan 与人工处理指引；哪些步骤必须由用户或外部安装流程完成：

## Design Source Plan

- 是否需要 `target-design-overview.md`：
- 是否需要 `target-design-detail.md`：
- 是否存在复杂节点需要 `target-node-designs/<node-id>.md`：
- 复杂节点升级理由：
- 每个复杂节点的 node-design 是否覆盖 Node Metadata、Purpose/Boundary、Input、Output、Context、Execution、Calls、Data Fields、Exit Gate、Failure、Verification、Observability、Safety、Open Tasks：
- 每个 node-design 是否和 `workflow_graph.nodes[*]` 的 owner、template、gate、input_refs、output_refs、loop_policy 一致：
- `workflow-spec.yaml.design_refs` 应引用哪些 target design source：
- 是否需要持久化 `.workflowprogram/design/source/**`：

## Pattern Selection Notes

- Sequential 需求：
- Fan-out 机会：
- Explore 需求：
- Event-Driven 需求：
- Test-Driven 循环：
- Specialized Agent 需求：
- RalphLoop 适用性：
- 是否需要某个目标节点持续迭代直到 verifier/test 通过：
- 循环目标来源（用户目标 / 模型分解子目标）：
- 若是模型子目标，父目标引用：
- 是否需要 TDD test-first 证据：

## Target Workflow Graph Readback

- WorkflowProgram 自身是否仍按 `S0..S6` 开发主链执行：
- 目标工作流是否需要非 `S1..S6` 的业务节点：
- 目标 workflow_graph 节点：
- 目标 workflow_graph 入口与转移：
- 每个 graph 节点的输入、输出、gate、owner：
- 每个 graph 节点的执行模型（skill / agent / script / team / loop）：
- 目标 runtime policy：`managed_runtime` / 例外理由
- 目标 executor policy：默认 provider、允许 provider、manual/current-agent evidence 路径、不可用 provider 的 FAIL 行为
- 若使用 `current_agent` / `manual` provider，每个 node 的 executor evidence 必须记录哪些输入、输出、operator、时间戳和 output sha256：
- 目标 publish policy：是否启用 run-scoped outputs + finalizer + atomic publish；最终输出目录、latest marker、manifest 路径
- command 是否 wrapper-only 调用 `.workflowprogram/runtime/workflow-entry.py`：
- 运行态 immutable paths（通常为 `.claude/**`、`.workflowprogram/design/**`、`.workflowprogram/runtime/**`、`config/scripts/**`）：
- 哪些 node 需要独立 agent，原因是什么：
- 哪些 node 不需要独立 agent，原因是什么：
- 复杂 node-design 输出路径：
- 复杂 node-design 验证方式：`validate-target-node-design.py --spec <RUN_ROOT>/workflow-spec.yaml --node-design <path> --node-id <node-id>`
- 需要 `loop_policy` 的 graph 节点：
- 每个 loop 节点的 `max_iterations`、反馈命令、停止条件、证据输出：
- 目标输出是否已映射到 `registry` 或 `test_contract.artifacts`：

## Extraction Decision

- 留在当前仓库还是抽取：
- 理由：

## File Plan

- 需要创建的文件：
- 需要修改的文件：

## Risks

- 已知风险：
- 假设条件：

## Acceptance Criteria

- [ ] 验收项 1
- [ ] 验收项 2
- [ ] 验收项 3

## Traceability Expectations

- `REQ-* -> workflow_graph.nodes[*]` 映射：
- `REQ-* -> generated assets` 映射：
- `REQ-* -> target-acceptance-tests.yaml` 映射：
- `REQ-* -> expected S5 evidence` 映射：
- 无法自动验证的需求及豁免理由：
