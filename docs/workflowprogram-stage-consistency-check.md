# WorkflowProgram Stage 设计一致性校验报告

## 1. 校验目的

本报告用于验证以下文档的前后文逻辑一致性：

- [workflowprogram-stage-highlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-highlevel-design.md)
- [workflowprogram-stage-lowlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-lowlevel-design.md)

并与当前实现基线对齐（`workflowprogram-*` skills、`/develop`、`managed-assets.py`、`RUN_ROOT` 证据模型）。

## 2. 校验结果总览

| 校验项 | 结果 | 说明 |
|---|---|---|
| Stage 命名与顺序一致性 | PASS | 两份文档均采用 `S0..S6` |
| 路径模型一致性 | PASS | `PLUGIN_ROOT/TARGET_ROOT/RUN_ROOT` 定义一致 |
| 安装与分发契约一致性 | PASS | `dist/plugin` 被定义为 canonical 载荷目录，支持 Source Build 与 GitHub Release 两种通道 |
| 入口契约一致性 | PASS | 自然语言由 `workflowprogram-orchestrate` 承接，并通过 `route-intent.py` 提供确定性路由 |
| 输出结论枚举一致性 | PASS | `PASS/WARN/FAIL/ENVIRONMENT-SKIP` 已统一 |
| state 字段约束完整性 | PASS | Lowlevel 定义了固定字段与枚举 |
| artifact 字段约束完整性 | PASS | `kind/root/producer/status` 已由 `validate-run-state.py` 强制校验 |
| spec 运行契约完整性 | PASS | `runtime_contract` 已覆盖写入边界、最小证据集、失败枚举、环境 skip 条件 |
| spec 测试契约完整性 | PASS | `test_contract` 已覆盖入口、边界、流程、产物、失败五类判定，并与 `runtime_contract` 通过固定引用语法对接 |
| 设计源与机器投影分层 | PASS | `target-design-overview.md` / `target-design-detail.md` 承载 target design source，`workflow-spec.yaml` 只承载机器语义和 `design_refs` |
| 需求血缘传递 | PASS | 原始请求通过 `target-requirements.yaml -> target-requirement-logic-map.json -> target-context-findings.yaml -> target-traceability-matrix.json` 映射到设计节点、资产、验收和证据 |
| 复杂节点分层 | PASS | 复杂业务环节通过 `target-node-designs/<node-id>.md` 与 `workflow_graph.nodes[*]` 对接，不拆成新的 WorkflowProgram `S1..S6` |
| 视图渲染链路一致性 | PASS | 设计与实现均明确 `tools/generate-view.py` 负责 `workflow-view.md` 渲染 |
| Stage 间 I/O 依赖闭合 | PASS | `S1->S2->S3->S4->S5->S6` 无未定义依赖 |
| Stage 准出可验证性 | PASS | 每个 Stage 已补充证据路径和可验证检查条目 |
| 进展与关键节点可视化契约 | PASS | 增加 `current-progress/milestones/user-progress` 三类进展资产 |
| 与现有实现贴合度 | PASS | 未引入强依赖的新外部运行时 |
| 设计与实现差距可见性 | PASS | 已提供 `validate-workflow-spec.py` + `workflow-runner.py` + `validate-run-state.py` 脚本化闭环 |

## 3. Stage 依赖链检查

### 3.1 主链（develop）

- `S0` 输出 `intent/target_root`，可驱动 `S1`。
- `S1` 输出 `workflow-spec.md`，可驱动 `S2`。
- `S1` 同时输出 `s1-requirements.yaml`，把原始请求转为 `REQ-*`。
- `S1` 同时输出 `question-backlog.json` 与 `requirement-logic-map.json`，把澄清问题、七个 logic lenses 和 `REQ-* -> process/evidence/acceptance` 链接传给 `S2/S3`。
- `S2` 输出上下文结论与 `s2-context-findings.yaml`，作为 `S3` 设计输入。
- `S3` 输出设计源、验收测试、traceability 与 `workflow-spec.yaml` 机器投影，可驱动 `S4`。
- `S4` 输出 candidate 与 managed 结果，可驱动 `S5`。
- `S5` 输出验证结论，可驱动 `S6` 闭环。

### 3.2 其他意图链

- `audit`: `S0 -> S5(审计模式) -> S6`
- `validate`: `S0 -> S5 -> S6(可选)`
- `iterate`: `S0 -> S6(提案模式) -> S5(可选)`

结论：意图链无循环死锁，且准出目标可判定。

## 4. state/artifact 冲突检查

### 4.1 已消解冲突

- 冲突 C1：验证结论枚举在高低层文档不一致。  
  处理：Lowlevel 已统一为 `PASS/WARN/FAIL/ENVIRONMENT-SKIP`。

- 冲突 C2：`producer` 无约束可能导致命名漂移。  
  处理：Lowlevel 规定 `producer` 必须为 `S0..S6`。

- 冲突 C3：state 直接承载文件内容风险高。  
  处理：Highlevel/Lowlevel 统一为“state 追踪引用，文件内容落盘”。

- 冲突 C4：`dist/plugin` 被表述为“唯一安装路径”，与 GitHub 包分发场景冲突。  
  处理：改为“仓库内 canonical 载荷目录”；安装可通过任意同构目录并用 `--plugin-dir` 加载。

- 冲突 C5：Stage 目标与输出缺少可判定标准。  
  处理：Highlevel 增加 Stage 验收矩阵，Lowlevel 为每个 Stage 增加证据路径与可验证检查。

### 4.2 本轮新增工程化实现

- 已实现 R1：`validate-workflow-spec.py` 对 `workflow-spec.yaml` 做脚本化字段与转移校验。
- 已实现 R2：`validate-run-state.py` 对 `kind/root/producer/status` 枚举进行强制验证。
- 已实现 R3：`workflow-runner.py` 提供程序化 Stage 转移、状态落盘与证据输出。
- 已实现 R4：`route-intent.py` 提供确定性路由，strict 模式下可对歧义请求执行硬阻断。
- 已实现 R5：`runtime_contract` 已程序化生效，`workflow-runner.py` 强制执行写入边界、最小证据集校验、失败类别枚举约束与环境 skip。
- 已实现 R6：S1 logic interview 已程序化生效，`generate-clarification-package.py` 生成 `question-backlog.json` / `requirement-logic-map.json`，`validate-workflow-draft.py` 拒绝泛问题、缺 lens 或缺 `REQ-*` 逻辑链接的设计草案。
- 已实现 R6：`test_contract` 已由 `validate-workflow-spec.py` 做字段级、引用一致性与覆盖度校验；`generate-view.py` 负责渲染但不改变 runner 语义。

### 4.3 本轮 5 轮设计审计结论

| 轮次 | 新识别问题 | 修正结论 |
|---|---|---|
| Round 1 | `workflow-spec.yaml` 被描述为“设计单点真实源”，容易把运行态地图膨胀成完整设计文档 | 改为“设计源 + 机器投影”分层，`workflow-spec.yaml` 只保留机器语义 |
| Round 2 | 原始需求在 S1/S2/S3/S5 之间缺少可追踪转化链 | 增加 `s1-requirements.yaml`、`s2-context-findings.yaml`、`traceability-matrix.json` 的需求血缘口径 |
| Round 3 | STRIDE / DFD 这类复杂环节如果只写整体 LowLevel，会导致上下文丢失或设计过载 | 增加条件性 `node-designs/<node-id>.md`，复杂节点独立设计但不改变 S1-S6 主链 |
| Round 4 | “每个 node 是否一个 agent”会导致过度拆分和调度噪声 | 明确 node 是流程单位、agent 是执行角色，只有复杂认知/专业能力/上下文边界才独立 agent |
| Round 5 | 新增设计源可能让流程变重并与历史派生 `workflow-maintenance.md` 混淆 | 设计源只在 S3/RUN_ROOT 形成审计证据，`workflow-maintenance.md` 继续是 YAML 派生维护视图，简单工作流不强制 node-design/team/loop |

## 5. 结论

当前文档级设计与实现已形成“规范 -> 脚本校验 -> 程序执行 -> 证据回写”的闭环。
当前无显式冲突：S3 设计源负责设计解释，`workflow-spec.yaml` 负责机器投影，`runtime_contract` 负责执行约束，`test_contract` 负责基础运行测试判定，二者通过固定引用语法衔接而不重复定义。
后续重点从“补缺”转为“稳定性与覆盖度提升”（如增加更多真实场景 smoke 和冲突恢复策略）。
