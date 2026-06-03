# Workflow Spec Draft

## Workflow Identity
- 工作流名称: stride-security-test-workflow
- 触发命令: /develop stride security workflow
- 简要描述: 为代码仓库创建 STRIDE 安全测试工作流。

## User Intent
- 用户诉求: 创建一个能阅读代码、建立 DFD、执行 STRIDE 威胁分析并选择测试方法的安全测试工作流。
- 最终目的: 让安全测试不只输出泛泛风险清单，而是能追溯到代码证据、DFD 节点和测试方法。
- 成功标准: 每个威胁都能关联 DFD 元素、代码证据、STRIDE 类别、测试方法和验收结果。

## Clarification Summary
- 澄清轮次: 4
- 已确认事项: 需要代码阅读、DFD 建模、STRIDE 分类、测试方法选择和证据报告。
- 已消解歧义: DFD 不完整时标记 unknown 并阻塞高风险结论；测试方法必须可追溯到威胁和证据。

## Requirement Logic Interview
- 复杂度: XL
- Purpose Lens: 目标是从代码事实推导可测试的 STRIDE 风险，帮助安全 reviewer 决定下一步测试行动。
- Object Lens: 输入对象为代码仓库、架构文档和用户指定范围；中间对象为组件清单、数据流、信任边界、DFD、威胁候选、测试方法矩阵；输出对象为 STRIDE 报告、测试计划和证据索引。
- Process Lens: intake scope -> collect code evidence -> build DFD -> validate unknowns -> classify STRIDE threats -> choose test methods -> generate report -> verify evidence coverage。
- Decision Lens: DFD unknown 是否阻塞；威胁是否高风险；选择静态检查、动态测试、模糊测试或人工审查；证据不足时降级为 hypothesis 而非 confirmed finding。
- Evidence Lens: 每个 DFD 节点需要代码路径或文档引用；每个威胁需要 DFD 元素、STRIDE 类别、攻击路径、证据片段和选定测试方法；缺证据的结论必须标记 unknown 或 hypothesis。
- Acceptance Lens: 给定含认证和外部输入的服务仓库，应输出 DFD、至少一个 Spoofing/Tampering/Information Disclosure 候选及对应测试方法；给定无法读取代码时必须停止并说明缺失证据。
- Boundary Lens: 不自动运行破坏性测试；不伪造代码证据；不把 unknown 当 confirmed；需要用户确认后才执行外部扫描或写入项目资产。
- 关键追问: DFD 无法从代码完整推导时是阻塞还是标记 unknown；每个 STRIDE 威胁必须具备哪些代码证据才能从 hypothesis 升级为 finding；测试方法选择由规则、模型判断还是用户审批决定。
- 候选节点: scope_intake；code_evidence_scan；dfd_builder；stride_classifier；test_method_selector；evidence_verifier；report_writer。
- 负向/停止场景: 代码仓库不可读时停止；DFD 信任边界不明确时阻塞 confirmed finding；破坏性测试未审批时停止。

## Trigger Model
- 调用方式: 手动命令触发
- 触发细节: 用户通过 /develop 在安全测试目标仓库中发起 STRIDE workflow 设计。

## Inputs
- 必需输入: 用户需求文本；目标代码仓库路径；分析范围
- 可选输入: 架构文档；已有 DFD；允许执行的测试类型
- 所需外部上下文: 代码结构、入口点、外部接口、认证授权边界

## Outputs
- 主交付物: STRIDE 威胁报告；测试方法矩阵；证据索引
- 次级产物: DFD 草图；unknown 清单；验证摘要
- 输出格式: Markdown；JSON；YAML

## Quality Gates
- 阻塞条件: 代码不可读；DFD 核心对象缺失；破坏性测试未审批
- 必需验证: 每个 finding 关联 DFD、代码证据和测试方法；S5 验证证据文件存在
- 完成定义: DFD、威胁报告、测试矩阵和证据索引全部生成且可追溯

## Open Questions
- 阻塞未决问题: 无
- 可延后问题: 是否将 DFD 可视化为 Mermaid 或 Graphviz。
- 问题处理策略: 可视化格式在 S3 设计阶段决定，不阻塞逻辑建模。

## Assumptions and Boundaries
- 当前假设: 目标仓库可读且用户允许静态分析。
- 外部依赖: Claude Code runtime；可选安全分析 skill 或 CLI
- 关键边界场景: 仓库不可读时停止；证据不足时标记 unknown；测试工具缺失时输出 bootstrap 指引。
- 明确不做: 不自动执行破坏性测试；不联网攻击真实服务；不伪造证据。

## Target Workflow Graph Readback
- WorkflowProgram 自身是否仍按 `S0..S6` 开发主链执行: 是，WorkflowProgram 自身仍按 S1-S6 develop 主链执行。
- 目标工作流是否需要非 `S1..S6` 的业务节点: 需要，目标工作流使用安全测试业务节点。
- 目标 workflow_graph 节点: scope_intake；code_evidence_scan；dfd_builder；stride_classifier；test_method_selector；evidence_verifier；report_writer。
- 目标 workflow_graph 入口与转移: /stride-test -> scope_intake -> code_evidence_scan -> dfd_builder -> stride_classifier -> test_method_selector -> evidence_verifier -> report_writer -> done。
- 每个 graph 节点的输入、输出、gate、owner: scope_intake 输出范围；code_evidence_scan 输出代码证据；dfd_builder 输出 DFD；stride_classifier 输出威胁；test_method_selector 输出测试方法；evidence_verifier 输出 coverage；report_writer 输出报告。
- 每个 graph 节点的执行模型（skill / agent / script / team / loop）: scope_intake 使用 skill；code_evidence_scan 使用 agent；dfd_builder 使用 agent；stride_classifier 使用 security agent；test_method_selector 使用 skill；evidence_verifier 使用 script；report_writer 使用 skill。
- 哪些 node 需要独立 agent，原因是什么: code_evidence_scan、dfd_builder、stride_classifier 需要独立 agent，因为上下文重、专业判断强且失败归因需要分离。
- 哪些 node 不需要独立 agent，原因是什么: scope_intake、test_method_selector、evidence_verifier、report_writer 可由当前 skill 或脚本控制。
- 复杂 node-design 输出路径: outputs/stages/node-designs/dfd_builder.md；outputs/stages/node-designs/stride_classifier.md。
- 需要 `loop_policy` 的 graph 节点: dfd_builder；evidence_verifier。
- 每个 loop 节点的 `max_iterations`、反馈命令、停止条件、证据输出: dfd_builder max_iterations=3 直到 DFD coverage 足够；evidence_verifier max_iterations=3 直到 finding evidence coverage 通过。
- 目标输出是否已映射到 `registry` 或 `test_contract.artifacts`: 是，DFD、报告、测试矩阵和证据索引均映射到 deliverables。

## File Plan
- 需要创建的文件: .workflowprogram/design/workflow-spec.yaml；.workflowprogram/runtime/workflow-entry.py；.claude/commands/stride-test.md；.claude/skills/stride-test/SKILL.md。
- 需要修改的文件: .claude/settings.json。

## Readback Confirmation
- 回读摘要: 系统将创建一个 STRIDE 安全测试工作流，先从代码证据构建 DFD，再进行威胁分类和测试方法选择，缺证据时不输出 confirmed finding。
- 用户确认状态: 已确认
- 最近修正: DFD unknown 处理从“自动猜测”修正为“标记 unknown 或阻塞 confirmed finding”。
