# Native Workflow JS Control Plane Migration Plan

## 1. 目的与边界

本文承接 [Native Workflow JS Control Plane High-Level 设计](native-workflow-control-plane-highlevel-design.md) 的实施顺序、兼容过渡、风险和回滚策略。

High-Level 文档描述迁移完成后的稳态架构。本文只描述如何从当前 Python runtime 控制面和已完成 Native 原型演进到产品级 Native Workflow JS 控制面。

当前只实施交互式 Claude Code CLI。非交互式 `--print`、后台自动化和外部服务调用在完成单独 capability probe 前保持不支持。

## 2. 当前基线

### M0. 已完成：最小能力探针

已创建只读 fixture：

- [workflowprogram-native-smoke.js](../tests/manual-fixtures/native-workflow-smoke/target-root/.claude/workflows/workflowprogram-native-smoke.js)
- [Native Workflow Smoke Fixture Evidence](../tests/manual-fixtures/native-workflow-smoke/README.md)

已观察结果：

- 交互式 Claude Code CLI 可按路径调用用户自行编写的 `Workflow({ scriptPath })`。
- 结构化 Agent、schema 和 JS gate 可以运行。
- fixture 返回 `PASS`，Run ID 为 `wf_c719aa99-826`。
- 初始 `skill_listing` 已包含 `workflowprogram-native-smoke`；不同 Claude Code 入口和版本仍需持续执行 discovery smoke。
- 其他自动化上下文曾返回 `Workflow exists but is not enabled in this context.`，因此支持矩阵必须按入口单独探测。

## 3. 分阶段实施

### M1. 已完成：文档真源与能力探针

目标：

- 保持现有 Stage High-Level 和 Low-Level 文档为旧 runtime 真源。
- 将 Native HLD 与本文登记为 supporting docs。
- 固化交互式 smoke fixture 和证据路径。
- 增加 capability probe，区分环境未启用与 JS 本身失败。

准出条件：

- 文档状态索引可区分旧 runtime 真源、Native 稳态设计和迁移计划。
- fixture 可在目标交互式 CLI 环境重复执行。
- capability probe 失败时返回明确环境结论。

### M2. 已完成：轻量静态校验器

目标：

- 实现 `validate-native-workflow-js`。
- 增加合法和非法 fixture。
- 检查 meta literal、必要字段、phase 对齐、禁用 API、schema、并行写入提示和 return envelope。

准出条件：

- 合法最小 fixture 校验通过。
- 每类非法 fixture 都被对应规则阻断。
- 校验器不尝试完整解释业务语义。

### M3. 已完成：最小 Native JS 生成器

目标：

- 生成单文件 `.claude/workflows/<name>.js`。
- 支持 `phase()`、`agent()`、schema、`parallel()`、`pipeline()` 和 JS gate。
- 默认不生成 `.workflowprogram/runtime/`、`workflow-spec.yaml`、skill 或 Agent 文件。
- 对已有文件执行 drift 检测，禁止静默覆盖。

准出条件：

- 生成后的最小 workflow 通过静态校验和最低 smoke。
- 默认部署树只包含 `.claude/workflows/<name>.js`。
- 更新 drifted 文件时生成冲突报告。

### M4. 已完成：可选 Supporting Assets

目标：

- 按需生成 reusable skill。
- 按需生成 reusable Agent。
- 按需生成确定性领域脚本。
- 按需生成 `.workflowprogram/design/`、`.workflowprogram/runs/` 和 `managed-files.json`。
- 仅在复杂生成器确有稳定 IR 需求时支持可选 `workflow-spec.yaml`。

准出条件：

- 每类 supporting asset 都有显式生成条件。
- 关闭可选能力时，目标 workflow 仍可独立运行。
- IR 存在时，JS 仍是最终执行真源，并有 drift 检测。

### M5. 已完成自动化、待交互式 smoke：旧资产样例迁移

目标：

- 选择一个现有 WorkflowProgram 目标工作流作为样例。
- 对比旧 Python runtime 与 Native JS 的功能和证据。
- 逐项判断 runner、guard、validator、finalizer、resume/cache 和 evidence ledger 是否删除、替换、收窄或保留。

准出条件：

- 样例 workflow 在 Native JS 下通过正常路径 smoke。
- 高风险行为具备 blocked-path 和 external-fact smoke。
- 旧 runtime 资产删除不影响已声明能力。

### M6. 已完成交互式 authoring 路由：发布与兼容过渡

目标：

- 更新插件打包、安装说明和发布验证。
- 已发布旧 workflow 保持兼容，不自动重写。
- 新生成 workflow 默认选择 Native JS 模式。
- 需要旧 slash command 时生成 thin compatibility skill。

准出条件：

- 发布包只携带目标 workflow 实际需要的 assets。
- 安装后的交互式 CLI smoke 通过。
- 旧模式和 Native 模式可以被明确识别和审计。

### M7. 已完成自动化、待交互式 smoke：前台澄清与 Native authoring 元工作流

目标：

- 普通用户只描述自然语言需求，由模型语义命中 `workflowprogram-orchestrate`；slash command 降级为调试和兜底入口。
- Native develop 在前台执行多轮澄清、用户回读确认和 readiness gate。
- readiness PASS 后，通过 `Workflow({ scriptPath, args })` 启动插件自身的 `workflowprogram-native-authoring.js`。
- 后台只读执行 `Explore -> Design -> Review -> Handoff`，让 authoring 进度进入 `/workflows`。
- 元工作流返回 handoff 后，由前台生成 authoring spec，再调用 generator 生成 candidate。

准出条件：

- readiness validator 对未确认、缺 lens、仍有开放问题和绑定到其他 `TARGET_ROOT` 的 packet 返回 `BLOCKED`。
- generator 强制要求 `--readiness`，不得绕过确认门禁生成 candidate。
- `tools/build_plugin.py` 将插件自身 `.claude/workflows/` 映射到 `dist/plugin/workflows/`。
- 元工作流通过静态校验；交互式 Claude Code 中能够通过 `/workflows` 观察执行。

M7 是验证方向的过渡切片，不是最终稳态。它仍把澄清、JSON authoring spec 生成和 managed apply 留在前台桥中。稳态要求 WorkflowProgram 自身的产品阶段由 Native Workflow JS 主导，并通过可重入返回值与前台对话衔接。

### M8. 已完成：插件产品 Native Workflow JS 分发与路径启动契约

目标：

- 新增 `workflowprogram-develop.js`、`workflowprogram-audit.js`、`workflowprogram-iterate.js`、`workflowprogram-validate.js` 和 `workflowprogram-publish.js`。
- 使用 pure-literal `meta` 保持脚本合法，但插件产品入口不依赖 saved workflow registry 自动注册。
- Skill 解析插件绝对路径后，正式调用使用 `Workflow({ scriptPath, args })`。
- 每个入口只返回统一的 `NOT_IMPLEMENTED` envelope、`plugin-script-path` 启动模式、后续迁移里程碑和 legacy delegation 提示；M8 不迁移真实业务控制流。
- 将用户交互与授权面、Plugin Skill 发现与启动面、Workflow 工具面明确分离。
- 明确 Agent、Skill、确定性脚本和嵌套 workflow 的边界。

准出条件：

- 五个产品 workflow JS 通过静态校验。
- 源码、`dist/plugin/` 和 build manifest 均包含五个入口。
- 真实 Claude Code CLI 能通过绝对 `scriptPath` 启动插件内产品骨架。
- 同一 CLI 中按产品名称查找失败被记录为部署边界；插件产品入口不得依赖 `Workflow({ name, args })`。

当前状态：

- 自动化部分已完成：五个分发骨架、静态校验、单元测试、dist 构建和仓库校验均通过。
- 环境相关部分已完成：真实 CLI 中 `scriptPath` 启动返回结构化 `NOT_IMPLEMENTED`；按名称查找失败，验证了插件分发边界。
- 未迁移能力继续由已有 Skill / legacy 路径承载；分发骨架不会静默伪装为已实现。

### M9. 已完成早期 blocker smoke、待 M11 完整交互式覆盖：可重入 Develop 控制面

目标：

- 将 Clarify、Confirm、Design、Review、Author、Generate、Validate、Smoke、Apply、Deliver 写入 `workflowprogram-develop.js`。
- Clarify 信息不足时返回 `NEEDS_USER_INPUT`；等待确认时返回 `READY_FOR_CONFIRMATION`。
- 前台模型只负责转述问题、收集答案和重新调用，不拥有 gate 逻辑。
- 设计文档经过审视后直接指导 JS 生成；JSON authoring spec 降级为过渡桥，不作为默认语义真源。
- D5-D9 不直接读写文件系统或控制桌面；D5 Author 在 JS 内产出 locked `authoringSpec`，D6-D9 返回 `READY_FOR_GENERATION / READY_FOR_VALIDATION / READY_FOR_SMOKE / READY_FOR_APPLY`，由前台执行窄化脚本并携带 candidate-bound evidence 重新调用。
- 增加 `build-native-develop-evidence.py`，对 candidate tree 求稳定 hash，并规范化 generation、validation、smoke 和 apply evidence。

准出条件：

- 缺失 lens、补充答案、等待确认、确认后继续四类路径均有 fixture。
- 设计审视 blocker 未关闭时不得进入 Generate。
- 默认目标部署树不包含 JSON spec、`workflow-spec.yaml` 或旧 runtime。
- stale validation、smoke 或 apply evidence 因 candidate hash 不匹配而被阻断。

当前状态：

- 自动化部分已完成：develop JS 状态机、Node mock runtime fixture、candidate hash adapter、Skill 启动适配器和仓库校验已实现。
- 环境相关部分：缺输入早期分支的真实 Claude Code `scriptPath` smoke 已完成；包含 Agent 的完整 Design -> Review 和宿主侧 handoff 闭环仍需在 M11 Computer Use harness 中持续覆盖。

### M9C. 已完成：Existing Workflow Migration 收敛规则

目标：

- 修正 `operation=migrate`、`request_kind=redesign_existing`、`target_state=existing_managed_workflow` 场景下的探索收敛。
- 将目标 Native JS 不存在、旧 spec 过时、旧 runtime 归档、managed-files 更新、重复遗留资产和缺少 Native JS reference 归类为 `migrationTasks`，而不是 `BLOCKED_DESIGN`。
- 只有目标不可读、没有行为真源、未决用户决策改变拓扑、写入边界不明确或必需资产无替代来源时，才进入 `trueBlockers`。
- 为 HLD/LLD 提供实现级 positive/negative examples，避免模型只记住一句规则。

准出条件：

- `workflowprogram-develop.js` 的探索 schema 包含 `migrationTasks`、`trueBlockers`、`userDecisions`、`sourceOfTruth` 和 `assetDispositionHints`。
- migrate 模式下仅 `trueBlockers` 或未被 `migrationDecisions` / `assetDispositionHints` 覆盖的未决 `userDecisions` 阻断 Design；migrationTasks 和已决资产处置确认项会被传入 Design/Author。
- 单元测试覆盖 missing target workflow、stale legacy assets、已决资产处置确认项等 expected migration work 不阻断，以及 true blocker 仍阻断。
- `workflowprogram-highlevel-design` 与 `workflowprogram-lowlevel-design` 都能索引实现级正反例。

### M10A. 自动化已完成、待 M11 完整交互式覆盖：Validate 与 Audit Native 化

目标：

- 优先迁移 validate 与 audit 到 Native JS，形成 develop 主链所需的质量关卡。
- 将代码审计、文件检查、checksum 和 drift 校验保留为窄化确定性脚本。
- 删除通用 Python runner 责任，不用脚本重新实现 Native runtime。

准出条件：

- validate 与 audit 的正常路径和 blocker 路径均有静态与交互式 smoke。
- Skill 仅承载复用知识或脚本调用规范，不隐藏控制顺序。
- 复杂复用控制流通过嵌套 `workflow(nameOrRef, args)` 实现；插件产品 JS 之间使用传入或解析后的绝对脚本引用，不假设名称已注册。

当前状态：

- `workflowprogram-validate.js` 已实现 Discover、Static Validate、External Verify 和 Report，可重入消费 candidate-bound 宿主证据。
- `workflowprogram-audit.js` 已实现 Discover、Inspect、Audit、Verify 和 Report；Inspect 与风险审查使用只读结构化 Agent，外部事实验证保持宿主侧 handoff。
- 静态 validator 和 Node mock runtime 已覆盖正常路径、blocker、stale hash、畸形注入证据和稳定 envelope。真实 Agent 交互式 smoke 仍由 M11 harness 覆盖。

### M10B. 自动化已完成、待 M11 完整交互式覆盖：Iterate 与 Native Lessons Loop

目标：

- 迁移 iterate 到 Native JS。
- 衔接 findings、lessons delta、delta 校验、lessons append 和 constraints approval。
- 约束提升必须经过审视和用户批准；不得自动把候选规则写入长期 `constraints.md`。

准出条件：

- iterate 正常路径、无新经验路径、非法 delta 和未批准约束提升路径均有测试。
- `validate-lessons-delta.py` 收窄保留为确定性校验脚本。
- lessons 追加与 constraints 更新具备受控写入证据。

当前状态：

- `workflowprogram-iterate.js` 已实现 Readback、Collect Findings、Build Lessons Delta、Validate Delta、Append Lessons、Propose Constraints、Review、Apply Approved Constraints 和 Deliver。
- `build-native-iterate-evidence.py` 复用 `validate-lessons-delta.py`，并通过 `runId + baselineHash + deltaHash/proposalHash` 保证写入幂等与 drift 阻断。
- Node mock runtime 与 adapter 单测覆盖正常路径、无新增经验、非法 delta、未批准约束、幂等重试和冲突路径。真实 Agent 交互式 smoke 仍由 M11 harness 覆盖。

### M10C. 自动化已完成、待 M11 完整交互式覆盖：Publish Native 化

目标：

- 迁移 publish 到 Native JS。
- 将 manifest 和发布资格保留为窄化确定性脚本。
- publish 默认只生成本地包、资格 manifest 和交付计划；外部 GitHub push 或 marketplace 更新通过单独 capability probe、用户显式批准和可幂等 adapter 执行。

准出条件：

- publish 的本地交付正常路径和 blocker 路径均有静态与交互式 smoke。
- 未批准外部写入时，publish 仍可正常交付本地包和计划。

当前状态：

- `workflowprogram-publish.js` 已实现 Qualify、Package、Verify、Local Deliver 和 Optional External Apply。
- 默认路径只生成本地包和安装说明；existing marketplace merge 与 GitHub apply 分别有独立 gate。
- `build-native-publish-evidence.py` 绑定 target/package hash；GitHub adapter 使用 run-scoped receipt 阻止同一成功发布重复执行。完整真实交互 smoke 仍由 M11 harness 覆盖。

### M11. 第一版已完成、Computer Use Adapter 待后续：交互式 Smoke 与发布资格

M11 v1 已完成：

- `build-native-interactive-smoke.py`：`packet`（生成执行说明）和 `evaluate`（确定性 JSONL 判读）。
- 证据分类：skill_listing、workflow_invoked、async_launched、agent_started、schema_result、completed_pass、completed_blocked、environment_disabled。
- 单元测试覆盖完整 PASS、early blocker、缺 Agent/schema、disabled context、真实 journal 格式和辅助证据。
- 已用历史真实会话 JSONL 回归：完整 Agent PASS 和 Agent 前 `BLOCKED_INPUT` 均可判读。
- 手动 fixture README 明确人工执行步骤和支持矩阵。

待后续 Computer Use adapter：

- 在出现允许的非终端集成后，由 Computer Use adapter 执行 discovery、launch、Agent、schema、PASS 和 blocker-path smoke。
- 发布前验证 Design Review、Static Validation、Interactive Smoke、Asset Scope、Drift Check 和 Manifest。
- 记录 workflow name、JS path、checksum、验证结果、smoke evidence 和 run ID。

准出条件：

- 支持矩阵明确 Windows、WSL 和终端组合。
- 发布缺少任一 gate 时返回 `BLOCKED_PUBLISH`。
- Computer Use 自动化失败时保留人工复核入口和 transcript。

### M12. 已完成：副作用幂等保护

目标：

- 为 apply、publish 和外部副作用增加 `runId`、`candidateHash`、apply manifest 和 drift 检查。
- 原生 resume 只承担运行恢复，不被误认为业务幂等保证。

准出条件：

- 相同 candidate hash 重放不会重复写入。
- 目标文件变化后重放返回 `BLOCKED_CONFLICT`。
- publish manifest 能关联设计审视、静态校验和 smoke evidence。

已实现：

- `managed-assets.py apply-staged` 对相同候选返回 `noop`，不更新目标文件 mtime，也不重写 managed manifest。
- `build-native-workflow-manifest.py` 生成包含六个 gate、资产全集和 checksum 的 Native manifest。
- `validate-publish-qualification.py` 独立重算 candidate hash、拒绝遗漏资产和路径穿越，并区分 `BLOCKED_PUBLISH` 与 `BLOCKED_CONFLICT`。
- 外部 apply 继续复用 M10C `github-publish-target-plugin.py` 的 run-scoped receipt。

### M13. 已完成：按任务类型选择模型

实现：

- `resolve-task-model-policy.py` host-side resolver：支持 `--task-type`（可重复，筛选请求的 task type；未指定时解析全部 8 个标准类型）、`--available-model`（可重复，CLI 值优先于 `AVAILABLE_MODELS` 环境变量）、`--out`（精确输出路径，至少与 `--run-root` 之一）、`--policy`（可选 policy 文件，缺失或无效 JSON 时以 `POLICY_FILE_UNAVAILABLE` / `POLICY_FILE_INVALID` fallback）、`--json`（stdout 输出）。
- 默认映射：`clarification`、`repository-exploration`、`generation`、`static-review` -> `deepseek-v4-flash[1M]`；`architecture`、`complex-generation`、`risk-review`、`publish-verification` -> `deepseek-v4-pro[1M]`。
- 未知任务类型（不在默认映射且不在 policy 中）解析为 `inherit`，记录 `TASK_TYPE_UNMAPPED` evidence。
- 自定义 policy alias 仅在没有显式可用模型列表时被接受；存在显式可用列表且不包含该 alias 时记录 `MODEL_ALIAS_UNAVAILABLE` evidence。
- product workflow JS 使用 `withTaskModel(taskType, options)` 助手：映射不存在、为空或为 `inherit` 时不传 `model`（默认继承），具体别名才成为 `options.model`。供应商与版本不散落硬编码在 workflow JS 中。
- `workflowprogram-native-authoring.js` 过渡资产也添加了 `withTaskModel` 消费（explore -> repository-exploration、design -> architecture、review -> risk-review）。
- 输出 `task-model-resolution.json` 至 `RUN_ROOT/outputs/stages/`（或 `--out` 指定路径）。嵌套 workflow 通过透传 `args.taskModels` 保持相同解析结果。

准出条件：

- 31 项单元测试覆盖默认映射、policy 覆盖、不可用 alias 回退、自定义 alias 接受/拒绝、缺失/无效 policy 文件（POLICY_FILE_UNAVAILABLE / POLICY_FILE_INVALID）、未知 taskType（TASK_TYPE_UNMAPPED）、--task-type 过滤、--available-model CLI 优先于 env、--out 精确路径、缺少输出目的地、JS model 属性在 inherit/absent 时省略、product workflow 透传（develop/audit/iterate/native-authoring）、迭代全路径四种 agent 类型传播。

### M17. 本次实施：目标 workflow 生成路径的模型控制面

范围：

- 在 `generate-native-workflow.py` 的 authoring spec 契约中新增可选 `task_model_policy.agent_task_models`。
- renderer 只负责把逻辑 task type 映射和 `withTaskModel` helper 写入目标 JS，不在生成阶段解析具体模型别名。
- 目标 workflow 运行时继续消费 `args.taskModels`；缺失、空值和 `inherit` 均省略 `model` 属性，保持默认继承。
- 生成器必须保持 `meta` pure-literal 开头，模型 helper 只能出现在 `meta` 后。

准出条件：

- generator 单测覆盖显式映射、`inherit`、缺失映射、生成 JS 执行时的 `model` 透传。
- Native static validation、仓库 `validate-workflow.py` 和 `claude plugin validate dist/plugin` 通过。

### M18. 本次实施：Authoring 责任收口与模块级验证

问题来源：

- FreeSTRIDE 迁移显示 active develop leaf 在 `READY_FOR_GENERATION` 后仍由前台模型自由创建 `native-workflow-authoring.json`，没有专用 authoring agent 或 handoff/spec 绑定。
- 旧 validator 只做轻量正则检查，未执行 ESM module parse，导致 body 包含第二个 `export const meta`、非 async 函数内 `await` 等不可加载 JS 被误判为 PASS。
- 测试 fixture 覆盖了最小 happy path，但没有覆盖“复杂迁移时把完整 JS 文件塞进 body”的负例。

范围：

- 在 `workflowprogram-develop.js` 中新增 Author 阶段，使用 `workflowprogram-develop:author` Agent 产出 `authoringSpec`；该 Agent 使用 `complex-generation` task type。
- `READY_FOR_GENERATION` handoff 必须携带 `authoringSpec`；前台 Skill 只将该对象原样落盘，不再根据 LLD 自由合成 JS。
- `generate-native-workflow.py` 验证 handoff 包含 authoring spec，并验证磁盘 spec 与 handoff spec 等价；不一致时在创建 candidate 前失败。
- `generate-native-workflow.py` 在 spec 层拒绝 body 中的 `export const meta`、`import`、`module.exports`、`require()` 等完整文件或模块边界。
- `validate-native-workflow-js.py` 增加 ESM module parse、唯一 meta export、pipeline/parallel 基础形态检查；module parse 失败作为硬错误阻断 smoke。
- 增加 FreeSTRIDE 暴露问题的精简负例测试：完整 JS body、重复 meta、非 async await、handoff 缺少 authoringSpec、handoff/spec mismatch。

准出条件：

- develop JS 单测覆盖 Author agent label、model 传递和 `READY_FOR_GENERATION.authoringSpec`。
- generator/validator 单测覆盖上述负例并保持有效最小样例 PASS。
- `validate-workflow.py`、`pytest` 目标集、plugin validation 和 dist build 均通过。

### M19. 已实施：需求澄清语义资产收口

问题来源：

- 复盘 FreeSTRIDE 重构会话发现，模型可以在内联 JS 或前台 `Agent` prompt 中写“你是 workflow-designer / requirement-clarification-lead”，但这不等价于调用已注册的 WPN agent。
- 七个 logic lenses 的含义目前分散在 `workflowprogram-develop` skill、`workflow-spec-support/spec-template.md`、`clarification_utils.py` 和 validator 中。模型能看到“必须使用 lens”，但不一定在 D1 澄清阶段完整掌握每个 lens 的含义、好问题/坏问题和停止条件。
- `workflowprogram-develop.js` 当前只根据缺失 lens 返回通用问题；稳态应由专用澄清 agent 生成 design-consequential 问题，JS 只负责 gate 和可重入状态。

范围：

- 新增 `.claude/agents/requirement-clarification-lead.md`，集中定义七个 logic lenses、追问顺序、输出 schema、停止条件和 forbidden generic questions。
- 新增或抽取 `.claude/skills/workflow-spec-support/logic-lenses.md`，作为人类可读的共享 lens 定义；`scripts/lib/clarification_utils.py::LOGIC_LENSES` 继续作为机器可读定义。
- 在 `workflowprogram-develop.js` D1 阶段通过 `agentType: 'workflowprogram-native-cn:requirement-clarification-lead'` 调用专用 agent，禁止仅靠 prompt 角色扮演。
- 补充 lens key 映射规则：产品 JS 运行态使用 camelCase，旧 S1/readiness 兼容资产可保留 snake_case；handoff/validator 必须拒绝无法映射的第三套字段。
- 更新 static validation 或 smoke evaluator，检查 D1 子代理 JSONL 中的 `attributionAgent`，并覆盖“prompt-only role emulation”负例。
- 更新 `workflowprogram-develop` / `workflowprogram-native-develop` skill 文本，使其只描述薄入口职责，不复制完整 lens 方法论。

准出条件：

- D1 re-entrant clarification fixture 证明缺 lens 时调用注册的 `requirement-clarification-lead` agent，并返回带 lens coverage 的结构化问题。
- JSONL evidence 中能看到 `attributionAgent=workflowprogram-native-cn:requirement-clarification-lead` 或等价插件 agent 归因。
- validator 覆盖：缺 lens、open question 未闭合、无 REQ 映射、process/evidence/acceptance 链接缺失、prompt-only role emulation。
- `logic-lenses.md` 与 `clarification_utils.py::LOGIC_LENSES` 的 title/task/question 映射有 drift 检查。
- `validate-workflow.py`、目标单测和插件校验通过。

实施落点：

- `.claude/agents/requirement-clarification-lead.md` 成为 D1 澄清复用 Agent。
- `.claude/skills/workflow-spec-support/logic-lenses.md` 成为人类可读共享 lens 定义。
- `workflowprogram-develop.js` 在缺失 lens 或存在 open question 时调用 `workflowprogram-native-cn:requirement-clarification-lead`，并保留 JS re-entry gate。
- `validate-native-authoring-readiness.py` 接受 camelCase runtime key 与 snake_case legacy key，并拒绝无法映射的第三套 lens key。
- `build-native-interactive-smoke.py evaluate` 支持 `--required-agent-attribution`，用于检查真实 JSONL 中的注册 Agent 归因。

### M20. 本次实施：大工作流 Authoring 模板化

问题来源：

- FreeSTRIDE 迁移会话中的 `wf_19ff0fb6-295` 证明，12-phase 级别目标 workflow 若要求 Author agent 在 `StructuredOutput` 中返回完整 JS body，容易触发 `max_tokens` 截断，随后出现空 `{}` 结构化输出和 schema 缺字段错误。
- 该问题不属于 FreeSTRIDE 目标设计问题，而是 WPN Author / Generate 边界过度依赖模型一次性生成大段 JS 源码。

范围：

- `workflowprogram-develop.js` 的 Author prompt 明确两种互斥输出形态：小 workflow 使用 `authoringSpec.body`；大 workflow 使用 `authoringSpec.template="sequential-agent-workflow-v1"` 与 `authoringSpec.phase_contracts`。
- `hasAuthoringSpec` gate 接受 `body` 或 `template + phase_contracts`，并继续拒绝缺少 authoring body source 的 spec。
- `generate-native-workflow.py` 验证 `body` 与 `template` 不得同时存在或同时缺失，拒绝未知 template、空 contracts、重复 phase/label、缺少 phase/label/prompt/schema 的 contract。
- `generate-native-workflow.py` 对 `sequential-agent-workflow-v1` 做 deterministic render：每个 contract 生成一个 `phase()` 和一个 `agent()`，可选 `blockWhen` 生成提前返回 gate；render 后继续沿用既有静态校验、handoff/spec 等价校验和 task model 注入。
- 增加 FreeSTRIDE 规模的 12-phase 回归测试，证明大 workflow 可通过 `phase_contracts` 生成候选 JS，而不需要 Author agent 输出完整 body。

准出条件：

- `tests/unit/test_native_workflow_js.py` 覆盖 body 模式兼容、template 模式生成、缺 body/template、body+template 同时存在、未知 template、空 contracts、缺必填字段、重复 phase、由 contracts 派生 phases、12-phase FreeSTRIDE 规模、handoff 集成和 task model 注入。
- `validate-workflow.py`、目标单测、dist build、版本一致性和插件更新通过。
- 重新触发 FreeSTRIDE 迁移时，Author 阶段不得再因超大 `authoringSpec.body` 截断而失败；如后续失败，应分类为新的 WPN gate/foreground/interoperability 问题。

### M14. 已完成：Legacy 下线评估

当前状态：

- `assess-native-legacy-retirement.py` 已实现：对 14 项 legacy 资产/资产组逐项评估，按 retain / replace / narrow / remove 给出结构化处置结论和分组 removalPlan。
- 评估器是确定性、事实驱动的只读检查器：从文件存在性和内容推导 blocker 状态，不硬编码 `True`/`False`。
- CLI：支持 `--repo-root`、`--evidence-root`、`--out`、`--json`。
- JSON schema 名称：`native-legacy-retirement-assessment`。
- 评估器定义 5 条阻断规则（通过文件内容和可选证据 JSON 驱动）；M16 后当前仓库稳定返回 `BLOCKED_RETIREMENT`，仅剩 1 条处于活跃状态：
  1. **required-assessment-assets-missing** — 评估器自身资产缺失时阻断。
  2. **transitional-renderer-bridge-active** — `workflowprogram-native-authoring.js`、readiness validator 或 `--readiness` 仍被 active skill/command 主路径引用时阻断；M15 已关闭当前仓库中的该 blocker，仅保留兼容文件不会触发。
  3. **full-product-interactive-smoke-not-declared-complete** — `.workflowprogram/evidence/native-product-interactive-smoke.json` 未声明完整覆盖。
  4. **legacy-compatibility-routing-active** — `route-native-control-plane.py` 中仍存在兼容路由逻辑；M16 已关闭当前仓库中的该 blocker。
  5. **rollback-deprecation-anchor-missing** — `.workflowprogram/evidence/legacy-retirement-anchor.json` 未包含 known-good-ref 和弃用通知；M16 已创建 anchor 并关闭当前仓库中的该 blocker。
- 20 项单元测试覆盖 BLOCKED_RETIREMENT、缺失资产触发 blocker、稳定规则注册表、disposition 结构与枚举、目录型资产探测、removalPlan 分组、报告落盘、只读保证、异常证据、narrow renderer 引用豁免、active 兼容引用阻断和 READY_FOR_RETIREMENT closure fixture。
- 评估器不执行任何删除操作。
- 名称和 schema 遵循 `assess-native-legacy-retirement.py` / `native-legacy-retirement-assessment` 命名约定。

目标：

- 在产品 workflow JS、交互式 smoke、发布资格和副作用保护全部稳定后，逐步删除旧 Python runner、默认 `workflow-spec.yaml` 和目标 `.workflowprogram/runtime/`。
- 保留确有价值的静态脚本、设计证据和兼容入口。

### M15. 已完成：Product handoff renderer 收窄

当前状态：

- `workflowprogram-develop.js` 的 `READY_FOR_GENERATION` 响应已携带顶层 `targetRoot`、`runRoot`，并在 `generationRequest` 中重复绑定 target/run 路径和只写 `RUN_ROOT` 的生成规则。
- `generate-native-workflow.py` 增加 `--generation-handoff` 主路径，与旧 `--readiness` 构成 argparse 必选互斥门禁。`--readiness` 仅作为 M7 兼容回退保留。
- generator 会验证 handoff 的 `status=READY_FOR_GENERATION`、`workflow=workflowprogram-develop`、字符串 `runId`、top-level 与 `generationRequest` 中的 `targetRoot/runRoot` 精确匹配、非空 `generationRequest.rule`、PASS 的 `designEvidence` 和 PASS 且无 blocker 的 `reviewEvidence`。
- handoff 验证结果落盘至 `RUN_ROOT/outputs/stages/native-workflow-generation-handoff.json`，schema 为 `native-workflow-generation-handoff-validation`。非法 handoff 在 candidate 写入前失败，且不会创建 target root。
- `workflowprogram-native-develop/SKILL.md` Step 4 已切换为 product handoff 主路径，不再把 `workflowprogram-native-authoring.js`、`validate-native-authoring-readiness.py` 或 `--readiness` 作为 active leaf 路径。
- `assess-native-legacy-retirement.py` 的 bridge blocker 仅扫描 active skill/command 中的 M7 兼容资产引用；`generate-native-workflow.py` 与 `--generation-handoff` 不构成 blocker 引用。

准出条件：

- generator/handoff/develop JS 聚焦回归通过。
- legacy retirement assessor 当前仓库活跃 blocker 从 4 条收敛为 3 条；M16 进一步关闭 legacy routing 与 rollback/deprecation anchor，仅剩完整产品交互式 smoke 未声明完成。
- 兼容资产仍可分发和测试，但不得重新成为 active leaf skill 的主路径。

准出条件：

- 每项旧能力都有 retain / replace / narrow / remove 结论和验证证据。
- 旧目标迁移失败时仍可按版本回滚。
- 文档状态索引切换到 Native JS 真源。

## 4. 旧能力迁移清单

| 旧能力 | 当前职责 | 迁移动作 | 验证 |
|---|---|---|---|
| intent 路由 | 将自然语言映射到 develop / audit / iterate / validate / publish | 由模型结合 Plugin Skill listing 语义选择；Skill 解析绝对脚本路径并启动产品 JS，不自建 runtime router | 路由 smoke |
| Python runtime runner | 执行目标阶段顺序与状态转移 | 普通目标 workflow 删除，由 JS 控制流替代 | JS gate smoke |
| validator | 校验结构和领域事实 | 拆为轻量静态校验与按需领域脚本 | 非法 fixture、领域测试 |
| `workflow-spec.yaml` | 承载 legacy 机器执行语义 | Native 默认删除；仅有明确机器审计需求时可选保留为 IR | 默认部署树检查、IR drift 测试 |
| target runtime guard | 提示目标项目不要绕开 runtime | 默认删除；高风险场景按需保留提示层 guard | guard 场景测试 |
| smoke test | 验证运行链路 | 保留为宿主侧 Native 交互式 smoke 契约；M11 v1 使用人工 packet + JSONL evaluator，Computer Use adapter 待允许的非终端集成 | discovery、launch、agent、schema、gate、blocked path |
| resume/cache | 自有恢复和复用 | 使用原生恢复；apply、publish 和外部副作用增加窄化幂等保护 | resume、idempotency、conflict smoke |
| evidence ledger | 长期证据留存 | 默认使用原生 journal；合规场景按需落盘 | evidence 场景测试 |
| managed assets | 受控写入和 drift 检测 | 保留在 authoring 阶段 | 冲突 fixture |
| 首轮需求澄清 | 防止模型基于模糊请求直接设计 | 移入可重入 `workflowprogram-develop.js`；M19 收口为专用 `requirement-clarification-lead` Agent + shared lens definition + validator | `NEEDS_USER_INPUT`、`READY_FOR_CONFIRMATION`、Agent attribution、lens drift fixture |
| WorkflowProgram authoring 后台可见性 | 让用户通过 `/workflows` 观察设计过程 | 五个产品入口均迁移为 Native Workflow JS | 静态校验、Skill listing、`scriptPath` launch、Computer Use `/workflows` smoke |
| finalizer | 原子发布报告和 marker | 默认删除；有原子发布需求时按领域增加 | 发布测试 |
| reusable skill | 入口或复用规范 | 仅在路由、复用或兼容时生成 | 安装后调用测试 |
| reusable Agent | 复用角色 | 仅在跨 workflow、独立权限或独立调用时生成 | 引用检查 |
| 任务类型模型选择 | 根据任务难度、风险和成本选择模型 | M13 已完成：可选 `resolve-task-model-policy.py` + `withTaskModel` JS helper；默认继承现有模型 | policy、fallback 测试 |

## 5. 测试计划

### 5.1 最低测试集

| 测试 | 阶段 | 目的 |
|---|---|---|
| capability probe | M1 | 区分环境未启用和脚本错误 |
| discovery smoke | M1-M3 | 验证 project/user saved JS 进入 listing |
| launch smoke | M1-M3 | 验证 `Workflow({ scriptPath })` 可启动 |
| validator fixture suite | M2 | 验证静态规则 |
| agent/schema/gate smoke | M3 | 验证最小原生控制面 |
| drift conflict fixture | M3 | 验证不静默覆盖 |
| optional asset matrix | M4 | 验证可选资产不成为默认依赖 |
| readiness fixture suite | M7 | 验证未确认需求无法进入生成 |
| Native authoring meta-workflow static validation | M7 | 验证插件自身 JS 元工作流结构 |
| plugin product workflow scriptPath launch | M8 | 验证五个产品 JS 被插件分发，并可通过绝对 `scriptPath` 启动 |
| plugin product workflow negative name lookup | M8 | 记录插件产品 JS 不自动进入 saved workflow registry 的当前边界 |
| re-entrant clarification fixture | M9 | 验证澄清和确认均由 JS 状态返回控制 |
| clarification semantic ownership fixture | M19 | 验证 D1 使用注册澄清 agent，lens 定义无漂移，prompt-only role emulation 被拒绝 |
| candidate-bound develop evidence | M9 | 验证 generation、validation、smoke 和 apply evidence 绑定同一 candidate hash |
| Interactive smoke harness | M11 | 人工 packet + JSONL evaluator 验证真实 CLI Skill listing、`scriptPath` launch、Agent、schema、PASS 和 blocker 路径；Computer Use adapter 后续增加 |
| apply idempotency and conflict | M12 | 验证副作用重放安全 |
| model policy selection and fallback | M13 | 验证任务类型模型选择扩展 |

### 5.2 高风险追加测试

| 测试 | 适用场景 |
|---|---|
| blocked-path smoke | 有失败 gate |
| parallel smoke | 有并行 Agent |
| pipeline smoke | 有逐项处理 |
| external-fact smoke | 调用 CLI 或领域脚本 |
| resume smoke | 有写入、发布或外部副作用 |
| publish smoke | 发布插件或共享产物 |

## 6. 回滚策略

- 迁移期间保留现有 Python runtime 生成路径。
- Native JS 生成器通过显式模式开关启用，不直接覆盖旧模式。
- 每个样例 workflow 独立迁移；失败时回退到旧生成路径。
- 已发布旧 workflow 不自动重写。
- 删除旧 runtime 资产必须晚于对应 Native smoke 和兼容验证通过。

## 7. 风险登记

| 风险 | 缓解 |
|---|---|
| 把 schema 当成事实证明 | 强制区分 L1 Schema、L2 JS Gate 和 L3 External Fact |
| 依赖 skill 自动命中 | 必需 skill 在 Agent prompt 中显式点名；固定命令直接写入 prompt |
| 并行 Agent 写冲突 | 并行默认只用于研究和评审；共享写入串行执行 |
| 删除 runtime 后丢失治理能力 | 每项旧能力逐项迁移和验证，不整体假设可删除 |
| 设计过程文件污染部署产物 | `.workflowprogram/` 作为可选 authoring metadata，不默认发布 |
| 过早引入 YAML 双真源 | JS 始终是执行真源；IR 按需增加并检测 drift |
| 误以为原生 resume 自动满足业务恢复 | 有副作用场景增加 resume smoke |
| 不同 Claude Code 入口能力不一致 | 每个支持入口单独执行 capability probe |
| 语义触发失败导致用户误以为必须记忆 slash command | 保留 slash command 作为兜底，但文档默认展示自然语言入口 |
| 后台 Workflow 在需求未收敛时提前执行 | Native develop JS 先返回 `NEEDS_USER_INPUT` / `READY_FOR_CONFIRMATION`，生成阶段再由 generator `--generation-handoff` 校验 `READY_FOR_GENERATION` handoff；`--readiness` 仅保留为 M7 兼容回退 |
| 需求澄清角色被 prompt-only 伪调用 | M19 抽取 `requirement-clarification-lead` 注册 Agent 和 shared lens definition；smoke/evaluator 检查 JSONL `attributionAgent`，validator 检查 lens drift 和缺失映射 |
| 迁移已有工作流时反复要求用户重申可推导事实 | `operation=migrate` 在 D1 前用迁移默认 lens 补齐缺失澄清：subprocess 合约从现有资产探索，旧 runtime 默认 retained/deferred 为非活动资产，平台策略不再作为用户问题 |
| 前台模型把结构化 args 写成字符串或 dotted key | Leaf Skill 增加 canonical invocation 正例和反例：必须使用绝对 `scriptPath` 与结构化 `args` 对象；真实用户只表达迁移目标，控制参数由入口适配层派生 |
| 前台模型只用 `scriptPath` 启动产品 JS 并把 `request/targetRoot/runRoot/runId` 转问用户 | 主入口 Skill 明确首轮默认推导规则并用单测覆盖；只有不可推导的目标、边界或外部决策才允许提问 |
| 探索 Agent 把已决迁移事项重复标记为 userDecision | Explore prompt 明确 `migrationDecisions` 是 settled input；JS gate 还会把已被 `migrationDecisions` 或 `assetDispositionHints` 覆盖的 `userDecisions` 归为非阻塞确认项；无真实 blocker 时必须返回 `trueBlockers: []` |
| 前台模型自由写 JS authoring spec | M18 后由 `workflowprogram-develop:author` 专用 Agent 产出 `authoringSpec`，前台只保存完整 Workflow result 并运行 `workflowprogram-continue.py`；runner 原样落盘 handoff/spec，generator 校验 handoff/spec 等价 |
| 正则静态 validator 漏掉 JS module 语法错误 | M18 后静态 validation 包含 ESM module parse、唯一 meta export 和基础 pipeline/parallel 形态负例 |
| 把 M7 原型或 M8 分发骨架误认为最终控制面 | 文档明确 M7 是过渡切片；M8 只分发五个入口并验证路径启动；M9-M10C 才迁移 WorkflowProgram 自身业务控制流 |
| 原生 resume 导致副作用重复执行 | 为 apply、publish 和外部调用增加 candidate hash、manifest 和 drift 检查 |
| 模型选择策略散落在 Agent prompt 和 JS 中 | M13 已实现：使用逻辑 task type 和集中 model policy；默认继承模型 |
| Explore 把内部设计工作误报为用户决策 | `operation=migrate` gate 将 phase/gate/schema/Python Bash strategy/smoke fixture/managed-files count 等问题归一化为 Design work item；只有外部用户必须决策且无法由真源或默认策略收敛的问题才阻塞 |
| `removeDotAgentsDir` 被误解为删除 `.claude/agents/` | 该决策只适用于根目录 `.agents/` / `.agentos/`；develop JS 对 `.claude/agents/` 和 `.claude/skills/` 整目录 remove 增加确定性阻断，除非显式允许 removeClaude registry |
| Design Agent 产出超长 HLD/LLD 后无法返回结构化结果 | Design prompt 与 schema 增加输出限幅；大工作流使用 phase contracts、生成约束和 traceability 引用，不复制完整 prompt、源文件或完整 JS body |

## 8. 发布前完成定义

- Native HLD 和迁移计划已登记在文档状态索引。
- M1-M3 最低测试集通过。
- M8-M13 产品级 Native JS、可重入澄清、交互式 smoke harness、发布资格、副作用保护和任务类型模型选择通过。
- 至少一个旧目标 workflow 完成样例迁移。
- 默认交付物不包含 `.workflowprogram/runtime/`。
- skill、Agent、领域脚本和 metadata 均为按需资产。
- 旧模式仍可显式选择和回滚。
- 非交互式入口在未完成 probe 前保持不支持。

## 9. 当前实施结论

- 已新增 `probe-native-workflow-capability.py`，从真实 JSONL 判读 `PASS | UNAVAILABLE | INCONCLUSIVE`。
- 已新增并收窄 `route-native-control-plane.py`：所有目标默认 Native，已有旧 runtime 标记只返回 `manual_migration_required=true`，不再自动转回旧主链，也不会自动重写旧目标文件。
- 已新增 `workflowprogram-native-develop` leaf skill。
- `generate-native-workflow.py` 支持按需 supporting assets；关闭可选资产时仍只生成单 JS。
- 已新增 [Native Workflow Sample Migration](../tests/manual-fixtures/native-workflow-sample-migration/README.md)，自动化覆盖 pipeline、parallel、schema 和 JS gate。
- 已新增 `validate-native-authoring-readiness.py`；未确认、缺 lens、存在开放问题或 packet 绑定到其他 `TARGET_ROOT` 时不得生成 candidate。
- 已新增插件自身的 `workflowprogram-native-authoring.js`；确认后可通过原生 Workflow 后台执行只读 Explore、Design、Review、Handoff。
- 已更新构建器，将 `.claude/workflows/` 同步分发到 `dist/plugin/workflows/`。
- 已新增五个插件产品级 Native Workflow JS 分发入口；M8 初始骨架统一返回 `NOT_IMPLEMENTED` 和 `plugin-script-path`。
- 已将 `workflowprogram-develop.js` 从 M8 分发骨架升级为 M9 可重入 Native develop 控制面。
- 已将 `workflowprogram-validate.js` 和 `workflowprogram-audit.js` 从 M8 分发骨架升级为 M10A Native 控制面。
- 已将 `workflowprogram-iterate.js` 从 M8 分发骨架升级为 M10B Native Lessons Loop，并新增 `build-native-iterate-evidence.py` 窄化 adapter；publish 仍保持 `NOT_IMPLEMENTED`。
- 已将 `workflowprogram-publish.js` 从 M8 分发骨架升级为 M10C Native publish 控制面，并新增 `build-native-publish-evidence.py` target/package hash normalizer 与 GitHub run-scoped 幂等 receipt。
- 已新增 [Native Develop Re-entrant Blocker Smoke](../tests/manual-fixtures/native-workflow-develop-reentrant/README.md)：真实交互式 CLI 通过绝对 `scriptPath` 启动 develop JS，并返回 `BLOCKED_INPUT`，证明 M9 已替换 M8 `NOT_IMPLEMENTED` 骨架。完整生命周期仍由 M11 Computer Use harness 覆盖。
- 已新增 `resolve-task-model-policy.py` host-side taskType 解析器，支持 `--task-type` 可重复筛选、`--available-model` 可重复（CLI 优先于 env）、`--out` 精确路径，输出 `task-model-resolution.json`。M13 已完成。
- 已将 `workflowprogram-develop.js`、`workflowprogram-audit.js`、`workflowprogram-iterate.js` 和 `workflowprogram-native-authoring.js` 的 `model: taskModel(...)` 改为 `withTaskModel(taskType, options)` 助手，inherit/absent 时不传 model。
- 已新增 `build-native-develop-evidence.py`，只负责 candidate tree hash 和宿主侧 evidence 规范化，不重新实现 runtime runner。
- 样例的实际交互式执行仍需在启用了 Native Workflow 的 Claude Code 会话中手工 smoke；非交互上下文不能替代该验收。
- M7 证明交互式 Native authoring 的最小方向可行；M9-M10C 已迁移五个 WorkflowProgram 产品控制面。完整真实交互 smoke 和 legacy 下线评估仍属于后续阶段。
- M8 已完成：真实 CLI 通过绝对 `scriptPath` 成功启动插件产品骨架；同一会话中的 name lookup 失败证明插件目录不会自动注册为 saved workflow。
- M11 v1（packet + evaluate）、M12 副作用幂等和 M13 按任务类型选择模型已完成；M16 新增 product smoke evidence 聚合器，只接受 evaluator 报告并在覆盖不完整时保持 `declaredComplete=false`。完整 Computer Use 终端驱动仍等待允许的非终端集成；legacy 实际删除仍等待 product smoke 关闭。

## 10. FreeSTRIDE 迁移反馈后的门禁

FreeSTRIDE 首次 Native 迁移暴露出静态校验、smoke 证据和 apply 证据之间可以出现伪闭环。后续迁移必须满足以下顺序，任何一步失败都不得切换入口或下线旧 runtime：

1. 静态 validator 拒绝未支持的宿主工具直接调用或裸引用、动态代码执行和关键未声明标识符；generation/validation evidence 仅接受对应真实 schema 报告，并必须指向同一个 `.claude/workflows/*.js` 主脚本；不得通过新增非原生返回字段、手工 PASS JSON 或同一候选树中的不同脚本拼接代替语义校验。
2. smoke 仅接受 `build-native-interactive-smoke.py evaluate` 生成的报告，并要求报告证明 Workflow launch、异步运行、Agent 启动、schema 结果和预期完成状态，同时绑定当前 candidate `scriptPath`、`scriptHash`、`candidateHash` 和非空 scenario；`early-blocker` profile 只能用于预期 `BLOCKED` 的场景。
3. controlled apply 必须显式绑定 `targetRoot`，仅接受由持久化 `RUN_ROOT/outputs/managed-change-result.json` 和目标 managed manifest 构建的结构化 `applyManifest`，且必须覆盖全部 candidate 文件并校验目标文件当前 hash。
4. update/migrate authoring 必须提供独立 `asset_disposition`；`supporting_assets` 只在确实需要生成、更新或归档内容时提供。
5. `task_model_policy` 只承载 `agent_task_models` 映射；未知字段在生成前失败。
6. 入口切换、旧 runtime 归档和 managed-files 更新均晚于真实 smoke 与 apply 证据闭合。
