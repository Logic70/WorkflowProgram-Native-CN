# WorkflowProgram 文档状态索引

## 当前生效设计真源

以下文档构成当前运行与验证口径的真源：

- [workflowprogram-stage-highlevel-design.md](D:/Code/WorkflowProgram-CN/docs/workflowprogram-stage-highlevel-design.md)
- [workflowprogram-stage-lowlevel-design.md](D:/Code/WorkflowProgram-CN/docs/workflowprogram-stage-lowlevel-design.md)
- [workflowprogram-stage-consistency-check.md](D:/Code/WorkflowProgram-CN/docs/workflowprogram-stage-consistency-check.md)

## Supporting Doc

以下文档为当前真源提供补充定义，但不单独决定阶段职责：

- [native-workflow-control-plane-highlevel-design.md](D:/Code/WorkflowProgram-CN/docs/native-workflow-control-plane-highlevel-design.md)
- [native-workflow-control-plane-lowlevel-design.md](D:/Code/WorkflowProgram-CN/docs/native-workflow-control-plane-lowlevel-design.md)
- [native-workflow-control-plane-migration-plan.md](D:/Code/WorkflowProgram-CN/docs/native-workflow-control-plane-migration-plan.md)
- [native-workflow-control-plane-implementation-plan.md](D:/Code/WorkflowProgram-CN/docs/native-workflow-control-plane-implementation-plan.md)
- [phase-03-step-02-runtime-evidence-spec.md](D:/Code/WorkflowProgram-CN/docs/phase-03-step-02-runtime-evidence-spec.md)
- [workflowprogram-target-claude-guard-design.md](D:/Code/WorkflowProgram-CN/docs/workflowprogram-target-claude-guard-design.md)
- [workflowprogram-capability-matrix.json](D:/Code/WorkflowProgram-CN/docs/workflowprogram-capability-matrix.json)
- [workflowprogram-101-html/index.html](D:/Code/WorkflowProgram-CN/docs/workflowprogram-101-html/index.html)
- [workflowprogram-101.md](D:/Code/WorkflowProgram-CN/docs/workflowprogram-101.md)
- [workflowprogram-101/index.md](D:/Code/WorkflowProgram-CN/docs/workflowprogram-101/index.md)

## Native Workflow JS 目标稳态

以下结论用于后续 Native 迁移，不改变当前 legacy runtime 的生效状态：

- WorkflowProgram 自身的 `develop / audit / iterate / validate / publish` 最终都应迁移为 Native Workflow JS，而不只是生成目标项目的 JS。
- 用户自然语言、Plugin Skill 发现与路径启动、Workflow 工具调用属于三个不同平面。插件产品 JS 使用绝对 `scriptPath`；project/user saved workflow 可在 runtime 可发现时按名称调用。普通用户不需要知道脚本路径。
- Native `develop` 的澄清和确认由 JS 返回 `NEEDS_USER_INPUT`、`READY_FOR_CONFIRMATION` 控制；前台模型只负责转述问题、收集答案和重新调用。
- Native JS 是最终执行真源。High-Level / Low-Level 设计文档是规范性审视依据；`workflow-spec.yaml` 和 JSON authoring spec 不再是 Native 默认语义真源。
- Skill 用于复用知识、工具调用规范或确定性脚本入口；复杂复用控制流使用嵌套 workflow；工作流专属 Agent 默认内联。
- 原生 resume 不自动保证 apply、publish 和外部副作用幂等。副作用阶段必须增加 `runId`、`candidateHash`、manifest 和 drift 检查。
- 交互式 smoke 仍是发布资格的一部分。M11 v1 已完成宿主侧 `build-native-interactive-smoke.py`（packet + evaluate）；Computer Use 终端驱动仍 deferred，当前支持 manual WSL execution + deterministic JSONL evaluation。
- Native iterate 迁移必须包含 findings 收集、lessons delta 校验、短期 lessons 追加和长期 constraints 审批提升；不能只迁移入口。
- 针对不同任务类型选择不同模型登记为后续版本能力：Agent 声明逻辑 `taskType`，host-side model policy resolver 在调用前写入 `args.taskModels`，JS 再传给 Native `agent(..., { model })`；默认 fallback 为继承模型。

M8 已验证五个插件产品 JS 的分发与绝对 `scriptPath` 启动边界。M9 已将 Native develop 状态机移入 `workflowprogram-develop.js`。M10A 已将 validate 与 audit 质量关卡移入产品 JS。M10B 已将 iterate Lessons Loop 移入 `workflowprogram-iterate.js`，并通过 `build-native-iterate-evidence.py` 保留窄化确定性校验与幂等写入。M10C 已将 publish 的资格、打包、验证、本地交付和显式外部 apply 移入 `workflowprogram-publish.js`，通过 `build-native-publish-evidence.py` 绑定 target/package hash，并为 GitHub adapter 增加 run-scoped 幂等 receipt。五个产品 JS 均已移除 M8 骨架。M11 v1 已完成宿主侧交互式 smoke harness（`build-native-interactive-smoke.py`: packet + evaluate；Computer Use 终端驱动 deferred）；真实完整产品交互式证据仍需按 fixture 逐条采集。M12 已完成 `build-native-workflow-manifest.py`、`validate-publish-qualification.py`、managed apply no-op 和 drift 阻断，外部 apply 继续复用 M10C GitHub adapter。`workflowprogram-native-authoring.js`、JSON renderer 和 readiness packet 仍是过渡兼容资产。M14 已完成 legacy 下线资格评估，实际删除仍等待阻断条件关闭。M15 已完成 transition renderer bridge 窄化：`generate-native-workflow.py` 增加 `--generation-handoff` 主路径（绑定 develop JS 的 `READY_FOR_GENERATION` handoff：workflow、runId、targetRoot、runRoot、generationRequest、designEvidence、reviewEvidence），`--readiness` 保留为 M7 兼容回退；`workflowprogram-native-develop/SKILL.md` Step 4 已切换为主路径描述。

M13 已完成按任务类型选择模型的核心实现：`resolve-task-model-policy.py` 支持 `--task-type` 可重复筛选、`--available-model` 可重复（CLI 优先于 `AVAILABLE_MODELS` env）、`--out` 精确路径、`--policy`（缺失或无效时记录 `POLICY_FILE_UNAVAILABLE` / `POLICY_FILE_INVALID` fallback）。8 个标准 taskType 映射到 `deepseek-v4-flash[1M]` 或 `deepseek-v4-pro[1M]`；未知 taskType 记录 `TASK_TYPE_UNMAPPED`；自定义 alias 仅在没有显式可用模型列表时被接受。`workflowprogram-develop.js`、`workflowprogram-audit.js`、`workflowprogram-iterate.js` 及过渡 `workflowprogram-native-authoring.js` 均使用 `withTaskModel(taskType, options)` 助手消费解析结果；映射不存在、为空或为 `inherit` 时不传 model（默认继承），具体别名才成为 `options.model`。模型供应商与具体版本不散落硬编码在 workflow JS 中。31 项单元测试覆盖。嵌套 workflow 可通过透传 `args.taskModels` 保持相同解析结果。

M14 legacy 下线评估已完成：`assess-native-legacy-retirement.py` 对 14 项旧 legacy 资产/资产组按 retain / replace / narrow / remove 给出结构化处置结论与分组 removalPlan。评估器是确定性、事实驱动的只读检查器；M16 已关闭 legacy 兼容路由和 rollback/deprecation anchor blocker。当前仓库稳定返回 `BLOCKED_RETIREMENT`，仅受完整产品交互式 smoke 未声明完成影响。`transitional-renderer-bridge-active` 已在 M15 窄化后关闭（leaf skill 不再引用 M7 兼容资产作为主路径）。评估器不执行任何删除操作。实际下线待阻断条件关闭后推进。

M15 product-handoff narrowing 已完成：
- `generate-native-workflow.py` CLI 使用 `--generation-handoff` 互斥参数取代旧 `--handoff`；`--readiness` 保留为 M7 兼容回退。
- 增加 comprehensive product handoff 验证：`validate_handoff()` 结构化校验 status、workflow、runId、targetRoot/runRoot、generationRequest、designEvidence（含 summary、HLD、LLD、traceability 数组）和 reviewEvidence（含 summary、blockingIssues 数组），验证结果落盘 `RUN_ROOT/outputs/stages/native-workflow-generation-handoff.json`（schema `native-workflow-generation-handoff-validation`）。
- `workflowprogram-develop.js` 的 `READY_FOR_GENERATION` 响应增加顶层 `targetRoot` 和 `runRoot`。
- `workflowprogram-native-develop/SKILL.md` Step 4 全面切换为 product-handoff 主路径，移除 M7 兼容回退段落，不再提及 `--readiness`、`validate-native-authoring-readiness.py` 或 `workflowprogram-native-authoring.js`。
- `assess-native-legacy-retirement.py` 的 `transitional-renderer-bridge-active` 检测改为只扫描 active skill/command 中 `workflowprogram-native-authoring.js`、`validate-native-authoring-readiness.py` 或 `--readiness` 的引用；`generate-native-workflow.py` 和 `--generation-handoff` 不被视为 blocker 引用。
- 兼容资产（`workflowprogram-native-authoring.js`、`validate-native-authoring-readiness.py`、`--readiness`）继续在脚本、测试和历史文档中留存，不作为 active leaf skill 主路径。
- generator/handoff/develop JS 与 legacy retirement 评估器聚焦回归共 172 项单元测试通过。
- Computer Use 终端驱动仍 deferred。

M16 已关闭两个可确定性关闭的 legacy retirement blocker：`.workflowprogram/evidence/legacy-retirement-anchor.json` 提供 rollback/deprecation anchor；`route-native-control-plane.py` 不再把旧 runtime 标记自动路由回旧主链，而是返回 Native 路由和 `manual_migration_required`。新增 `build-native-product-smoke-evidence.py` 聚合真实 evaluator 报告；当前仍不会伪造完整 product smoke，因此唯一活跃 blocker 是完整产品交互式 smoke 未声明完成。

## 历史追溯文档

以下文档保留为设计演进记录，不再充当当前运行时真源：

- [workflowprogram-skills-first-redesign.md](D:/Code/WorkflowProgram-CN/docs/workflowprogram-skills-first-redesign.md)
- [phase-02-step-01-entry-boundary-audit.md](D:/Code/WorkflowProgram-CN/docs/phase-02-step-01-entry-boundary-audit.md)
- [phase-03-step-01-runtime-validation-audit.md](D:/Code/WorkflowProgram-CN/docs/phase-03-step-01-runtime-validation-audit.md)
- [phase-04-implementation-plan.md](D:/Code/WorkflowProgram-CN/docs/phase-04-implementation-plan.md)

## 已关闭决策

- `workflow-spec.yaml.intent_flows` 是 `develop / audit / iterate / validate` 的机器可读真源。
- `workflow-spec.yaml` 是机器语义真源与运行态地图，不是完整设计文档；完整设计推理由 S3 设计源承载。
- `state.json` 与 `events.jsonl` 属于运行时控制面证据，由 runner 产出，S5 只消费。
- `target_root` 在 `S0` 准出前必须存在；若不存在，由执行链创建并记录。
- `S1` 仅属于 `develop` 主链。
- `S3` 必须经过审批 gate，且必须区分 `approved` 与 `auto-approved`。
- 阶段模型固定为显式 `stage_slot: S1..S6`，不再允许按顺序隐式推导。
- `stage_slot: S1..S6` 只约束 WorkflowProgram 自身控制面；生成后的目标工作流可通过 `workflow_graph` 声明自己的业务节点图。
- 产品主入口的确定性脚本链为 `workflow-entry.py -> managed-assets.py -> workflow-runner.py -> validate-run-state.py`。
- 目标工作流 runtime 的交付模式固定为 `generated_runtime_contract.mode = shared-control-plane-wrapper`。
- 新生成的 managed runtime 目标工作流必须通过 `target_claude_guard` 维护目标项目 `CLAUDE.md` 中的 WorkflowProgram runtime guard block；该 block 是提示层防绕过约束，硬门禁仍由 runner/finalizer/validator/doctor 执行。
- S1/S2/S3 的需求转化链为 `target-requirements.yaml -> target-context-findings.yaml -> target-design-overview.md / target-design-detail.md -> workflow-spec.yaml -> target-traceability-matrix.json`。
- `workflow-spec.md` 是用户回读，`workflow-view.md` 与 `workflow-maintenance.md` 是从 YAML 派生的报告，`target-design-detail.md` 才是目标工作流低层设计源。
- 复杂目标业务节点应升级为 `outputs/stages/target-node-designs/<node-id>.md`，而不是拆成新的 WorkflowProgram `S1..S6`；node 与 agent 不要求一一对应，且 node-design 必须通过内容校验证明与 `workflow_graph.nodes[*]` 的 owner、template、gate、input/output、loop policy 一致。
- completed develop 需要把 target design source 归档到 `TARGET_ROOT/.workflowprogram/design/source/**`，供后续修改、审计、validate 与 publish 使用。
- managed apply 必须保留 `managed-rollback-manifest.json` 与 `managed-recover-instructions.md`，并在共享报告中包含 schema/remediation 字段。
- 宿主专业能力必须通过 `host_capabilities` 声明，readiness / bootstrap 证据只写入 `RUN_ROOT`。
- `project_local` bootstrap 只允许写入 `TARGET_ROOT/.workflowprogram/bootstrap/**`，且应优先通过声明式 `bootstrap.assets` 生成可复用配置 / wrapper / marker 资产，并同步落 target bootstrap manifest。
- 交互式 Native authoring 所有目标默认使用 `.claude/workflows/*.js`；已有 `.workflowprogram/runtime/` 或旧设计 spec 的目标由 `route-native-control-plane.py` 返回 `manual_migration_required=true`，不再自动转回旧主链，也不自动重写旧 runtime 文件。
- Native supporting assets 按需生成；skill、Agent、领域脚本、compatibility command 和 authoring metadata 不是单文件 JS 的默认依赖。
- 普通用户通过自然语言语义命中 `workflowprogram-orchestrate`；显式 slash command 只作为调试、路由复核和自动命中失败时的兜底入口。
- Native develop 已由可重入 `workflowprogram-develop.js` 返回状态控制澄清、确认、设计审视和宿主侧 evidence handoff。未确认、缺 lens、仍有开放问题或 evidence hash 不匹配时不得推进。
- `workflowprogram-native-authoring.js`、readiness validator 和 JSON renderer 继续作为 M7 兼容桥；目标文件写入仍由前台 generator 和 managed apply 窄化脚本负责，但阶段顺序属于产品 JS。
- 若工作流启用 `capability_discovery`，则必须在 `RUN_ROOT` 生成 `host-capability-candidates.json` 与 `host-bootstrap-instructions.md`，用于在 `host_capabilities` 最终定稿前给出候选能力和精确人工指引。
- 显式 team orchestration 必须通过 `agent_team_contract` 声明；普通 subagent 不自动等于 team flow。
- Ralph-style 持续执行只能作为 `workflow_graph.nodes[*].loop_policy` 的目标节点策略；它不替换 WorkflowProgram 自身 `S1..S6`，且成功必须由 verifier/test 证据证明。
