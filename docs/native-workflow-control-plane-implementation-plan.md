# Native Workflow JS Control Plane Implementation Plan

## 1. 目的

本文将 [Native Workflow JS HLD](native-workflow-control-plane-highlevel-design.md) 和 [Native Workflow JS LLD](native-workflow-control-plane-lowlevel-design.md) 转换为增量迁移任务。

P1-P7 已完成 Native 原型切片，不替换旧 Python runtime 主链。P8 已完成插件产品 JS 分发与绝对 `scriptPath` 启动契约验证。P9 之后迁移 WorkflowProgram 自身业务控制流，完成验证后再下线旧 runtime。

## 2. 实施顺序

### P1. 轻量静态校验器

新增：

- `.claude/scripts/validate-native-workflow-js.py`
- `tests/native-workflow-fixtures/*.js`
- `tests/unit/test_native_workflow_js.py`

验收：

- 合法 fixture PASS。
- meta、phase、禁用 API、schema、parallel write 和 return envelope 非法 fixture 被对应规则阻断。

### P2. 最小 Native JS 生成器

新增：

- `.claude/scripts/generate-native-workflow.py`

验收：

- 从 JSON authoring spec 生成 candidate JS。
- 默认只生成 `.claude/workflows/<name>.js`。
- 静态校验失败时不 apply。

### P3. Controlled Update 集成

复用：

- `.claude/scripts/managed-assets.py`

验收：

- `--apply` 创建新目标 JS。
- 已存在 unmanaged 文件产生冲突且不覆盖。
- managed manifest、rollback manifest 和 recovery instructions 保持现有行为。

### P4. Dist 与仓库校验

更新：

- `.claude/scripts/validate-workflow.py`
- `tools/build_plugin.py` 生成的 `dist/plugin/scripts/*`

验收：

- repository validator 要求源码和 dist 均包含新增脚本。
- dist 内容由现有 builder 生成，禁止手工编辑。

### P5. 文档与证据

更新：

- `docs/workflowprogram-design-status.md`
- Native HLD、LLD、Migration Plan 和本文交叉引用。

保留：

- `tests/manual-fixtures/native-workflow-smoke/`
- JSONL 证据路径。

## 3. 回滚

- 新增脚本不接入旧 `workflow-entry.py`，回滚时删除 Native 新增脚本、fixture、测试和 supporting docs 即可。
- 目标项目写入仍由 `managed-assets.py` 防护。
- 旧 runtime 生成路径不变。

## 4. 后续阶段

### P8. 五个插件产品 Workflow JS 分发骨架

新增：

- `.claude/workflows/workflowprogram-develop.js`
- `.claude/workflows/workflowprogram-audit.js`
- `.claude/workflows/workflowprogram-iterate.js`
- `.claude/workflows/workflowprogram-validate.js`
- `.claude/workflows/workflowprogram-publish.js`

验收：

- 五个文件符合 pure-literal `meta` 契约。
- 五个文件只返回统一 `NOT_IMPLEMENTED` envelope、`plugin-script-path` 启动模式、后续迁移里程碑和 legacy delegation 提示，不包含真实 Agent 调度或业务控制流。
- source、`dist/plugin/` 和 build manifest 均包含五个入口。
- 真实 Claude Code CLI 可通过插件绝对路径执行 `Workflow({ scriptPath, args })`。
- 同一 CLI 中 `Workflow({ name, args })` 查找产品名称失败，证明插件产品入口不得依赖 saved workflow registry 自动注册。

### P9. 已完成早期 blocker smoke、待 P11 完整交互式覆盖：Develop 可重入控制面

实现：

- Clarify、Confirm、Design、Review、Generate、Validate、Smoke、Apply、Deliver。
- 稳定状态 `NEEDS_USER_INPUT`、`READY_FOR_CONFIRMATION`、`PASS` 和 `BLOCKED_*`。
- 前台模型只负责转述、收集答案和重新调用。
- High-Level、Low-Level 设计经过审视后直接指导 JS 生成；JSON authoring spec 仅作为过渡桥。
- 外部副作用以 `READY_FOR_GENERATION / READY_FOR_VALIDATION / READY_FOR_SMOKE / READY_FOR_APPLY` handoff 衔接前台；每次回传 evidence 必须绑定同一 candidate hash。
- `build-native-develop-evidence.py` 只负责 candidate tree hash 和 evidence 规范化，不拥有控制顺序。

验收：

- 缺 lens 返回问题。
- 补充答案后返回确认摘要。
- 用户确认后进入设计。
- review blocker、静态失败、smoke 失败和 drift 冲突均阻断后续阶段。
- stale evidence 因 candidate hash 不匹配而被阻断。

### P10A. 自动化已完成、待 P11 完整交互式覆盖：Validate 与 Audit Native 化

实现：

- 优先将 validate 与 audit 迁移到 Native JS，形成 develop 的质量关卡。
- 将静态校验、代码审计、文件检查、checksum 和 drift 收窄为确定性脚本。
- 复杂共享编排使用嵌套 workflow；Skill 只承载复用知识或脚本调用规范。

验收：

- validate 与 audit 均有正常路径和 blocker 路径 smoke。
- 脚本没有重新实现通用 Workflow runner。

实现结果：

- `workflowprogram-validate.js` 使用 candidate-bound `staticEvidence` 和 `externalEvidence` handoff。
- `workflowprogram-audit.js` 使用 candidate-bound discovery、只读 Inspect / Audit Agent 和 deterministic verify handoff。
- Node mock runtime 覆盖正常路径、blocker、stale hash、畸形注入 evidence 和稳定 envelope。

### P10B. 自动化已完成、待 P11 完整交互式覆盖：Iterate 与 Native Lessons Loop

实现：

- 将 iterate 迁移到 Native JS。
- 串联 findings、lessons delta、delta 校验、lessons append 和 constraints approval。
- 保留并收窄 `validate-lessons-delta.py`；长期约束更新仍需审视和用户批准。

验收：

- iterate 正常路径、无新经验路径、非法 delta 和未批准约束提升路径均有测试。
- lessons append 与 constraints 更新具备受控写入证据。

实现结果：

- `workflowprogram-iterate.js` 串联 Readback、findings、lessons delta、确定性校验、lessons append、constraints proposal、独立审视、显式批准和 apply。
- `build-native-iterate-evidence.py` 复用 `validate-lessons-delta.py`，只负责宿主侧 readback、staging、幂等 append/apply 和 drift 检查。
- Node mock runtime 与 adapter 单测覆盖无新增经验、非法 delta、未批准约束、hash 漂移、幂等重试和同 runId 内容冲突。

### P10C. 自动化已完成、待 P11 完整交互式覆盖：Publish Native 化

实现：

- 将 publish 迁移到 Native JS。
- 将 manifest 和发布资格收窄为确定性脚本。
- publish 默认交付本地包、资格 manifest 和计划；外部 GitHub push 或 marketplace 更新通过单独 capability probe、用户显式批准和可幂等 adapter 执行。

验收：

- publish 具备本地交付正常路径和 blocker 路径 smoke。
- 未批准外部写入时，publish 不得执行 push，但本地交付仍应 PASS。

实现结果：

- `workflowprogram-publish.js` 串联资格、打包、验证、existing marketplace merge、本地交付和显式外部 apply。
- `build-native-publish-evidence.py` 绑定 target/package hash，并独立生成本地安装说明，不调用 legacy 总控 runner。
- `github-publish-target-plugin.py` 增加 run-scoped 幂等 receipt；dry-run 不得作为真实 apply evidence。

### P11. Computer Use 交互式 Smoke

M11 第一版已完成宿主侧 `build-native-interactive-smoke.py`（`packet` + `evaluate` 子命令）。Computer Use 终端驱动仍 deferred。

已完成（M11 v1）：

- `packet` 子命令：根据 workflow、scriptPath、args、expected-status 生成稳定 JSON execution packet。
- `evaluate` 子命令：从真实或 fixture JSONL 做确定性判读，输出 evidence booleans、runIds、matching lines 和 blockingIssues。
- 证据分类：skill_listing、workflow_invoked、async_launched、agent_started、schema_result、completed_pass、completed_blocked、environment_disabled。
- 退出码：PASS(0)、INCONCLUSIVE(1)、UNAVAILABLE(2)。
- 单元测试覆盖 packet、完整 PASS、early blocker、缺 Agent/schema、disabled context、真实 journal 格式、journal 辅助证据和错误输入。
- 使用历史真实 JSONL 回归：完整 Agent PASS 和 Agent 前 `BLOCKED_INPUT` 均返回 `PASS` 判读。
- 手动 fixture README 明确人工执行步骤、Windows JSONL 路径、支持矩阵和 Computer Use 限制。
- 更新 validate-workflow.py / .ps1、README、HLD、LLD、迁移计划和设计状态索引。

待后续：

- 在出现允许的非终端集成后，增加 Computer Use adapter 驱动真实 Claude Code 会话。
- 自动验证 Plugin Skill listing、`scriptPath` launch、Agent、schema、正常 PASS 和 blocker 路径。
- 自动记录 transcript、run ID、JSONL 和结果摘要。
- 自动化失败时回退人工复核。

验收：

- 明确 Windows / WSL / 终端支持矩阵。
- 自动化失败时可回退人工复核。

### P12. 已完成：发布资格与副作用幂等

实现：

- `validate-publish-qualification.py`
- `build-native-workflow-manifest.py`
- 可选 `apply-external-publish.py`
- apply / publish 使用 `runId`、`candidateHash`、checksum、manifest 和 drift 检查。

验收：

- 同一 candidate hash 重放不会重复写入。
- drift 时返回 `BLOCKED_CONFLICT`。
- 缺少 Design Review、Static Validation、Interactive Smoke、Asset Scope、Drift Check 或 Manifest 任一 gate 时返回 `BLOCKED_PUBLISH`。

实施结果：

- `managed-assets.py apply-staged` 对相同候选返回 `noop`，不重复写目标文件或 managed manifest。
- `build-native-workflow-manifest.py` 生成六 gate `native-workflow-manifest`，绑定资产全集 checksum 与 `candidateHash`。
- `validate-publish-qualification.py` 独立校验 manifest、gate、资产全集、安全相对路径、candidate hash 和目标 drift。
- external apply 复用 M10C `github-publish-target-plugin.py`，不增加第二套 runner。

### P13. 已完成：按任务类型选择模型

实现：

- Agent 声明逻辑 `taskType`，`resolve-task-model-policy.py` host-side resolver 读取可选 `task-model-policy.json`，将 taskType 解析为模型别名，输出 `task-model-resolution.json` 至 `RUN_ROOT/outputs/stages/`。
- 支持 `--task-type` 可重复筛选、`--available-model` 可重复（CLI 优先于 `AVAILABLE_MODELS` env）、`--out` 精确路径、`--policy` 可选 policy 文件。
- product workflow JS 使用 `withTaskModel(taskType, options)` 助手：映射不存在、为空或为 `inherit` 时不传 `model`，具体别名才成为 `options.model`。
- 嵌套 workflow 继续透传 `args.taskModels`。
- 缺失、别名不可用或宿主不支持时 fallback 到 `inherit`，记录 `MODEL_ALIAS_UNAVAILABLE`、`TASK_TYPE_UNMAPPED`、`POLICY_FILE_UNAVAILABLE` 或 `POLICY_FILE_INVALID` evidence。
- 首版默认映射：
  - `clarification`、`repository-exploration`、`generation`、`static-review` -> `deepseek-v4-flash[1M]`
  - `architecture`、`complex-generation`、`risk-review`、`publish-verification` -> `deepseek-v4-pro[1M]`

验收：

- 31 项单元测试覆盖默认映射、policy 覆盖、不可用 alias 回退、自定义 alias 接受/拒绝、缺失/无效 policy 文件、未知 taskType、--task-type 过滤、--available-model CLI 优先于 env、--out 精确路径、缺少输出目的地、JS model 属性在 inherit/absent 时省略、product workflow 透传（develop/audit/iterate/native-authoring）、迭代全路径四种 agent 类型传播。
- 供应商与具体版本不散落硬编码在 workflow JS。

### P14. Legacy 下线评估（已完成评估，实际删除 deferred）

实现：

- `assess-native-legacy-retirement.py`：确定性、事实驱动的只读评估器。
- 14 项 legacy 资产/资产组 disposition（retain / replace / narrow / remove），含路径、原因和 removeWhen 前提。
- 5 项内容驱动 blocker，从文件存在性、内容扫描和可选证据 JSON 推导。
- 结构化 `removalPlan` 按 disposition 分组，支持机器消费。
- 18 项单元测试，含稳定规则注册表、READY_FOR_RETIREMENT closure fixture、目录型资产探测和异常证据回归。
- Schema 名称：`native-legacy-retirement-assessment`。

暂不实现：

- 逐项删除旧 runner、默认 `workflow-spec.yaml` 和目标 `.workflowprogram/runtime/` deferred 至阻断条件关闭。
- 保留经过评估仍有价值的确定性脚本、静态 validator、设计证据和兼容入口。

验收：

- 每项旧能力都有 retain / replace / narrow / remove 结论。
- 回滚到最后一个已验证版本仍可执行。
- 文档状态索引切换到 Native JS 真源。

### P15. Product handoff renderer 收窄（已完成）

实现：

- `workflowprogram-develop.js` 的 `READY_FOR_GENERATION` handoff 增加顶层 `targetRoot`、`runRoot`，并在 `generationRequest` 中绑定 target/run 路径与只写 `RUN_ROOT` 的生成规则。
- `generate-native-workflow.py` 增加 `--generation-handoff` 主路径；与旧 `--readiness` 使用 argparse 必选互斥门禁。
- `validate_handoff()` 校验 status、workflow、字符串 runId、targetRoot/runRoot、generationRequest、designEvidence 和 reviewEvidence；验证报告落盘为 `native-workflow-generation-handoff.json`。
- 非法或 stale handoff 在 candidate 写入前失败，不创建 target root。
- `workflowprogram-native-develop/SKILL.md` Step 4 只描述 product handoff 主路径；M7 compatibility assets 保留在脚本、测试和历史文档中，不作为 active leaf skill 主路径。
- `assess-native-legacy-retirement.py` 仅在 active skill/command 引用 `workflowprogram-native-authoring.js`、`validate-native-authoring-readiness.py` 或 `--readiness` 时触发 `transitional-renderer-bridge-active`。

验收：

- generator/handoff/develop JS 聚焦回归通过。
- 当前仓库 legacy retirement assessment 在 M16 后剩余 1 条活跃 blocker：完整产品交互式 smoke 未声明完成。
- HLD、LLD、迁移计划、状态索引和 README 均登记 `--generation-handoff` 主路径。

## 5. 本轮实施状态

已完成：

- P1：轻量静态校验器与合法/非法 fixture。
- P2：单文件 Native Workflow JS 生成器。
- P3：通过 `managed-assets.py` 完成 create、managed update、unmanaged conflict 和静态失败不写入。
- P4：源码、`dist/plugin/`、仓库 validator 和 capability matrix 同步。
- P5：HLD、LLD、迁移计划、README、manual smoke fixture 和 JSONL 证据索引。
- M4：可选 supporting assets 白名单、显式原因和 optional asset matrix。
- M5：pipeline、parallel、schema、gate 样例迁移资产与静态再生成验证。
- M6：`route-native-control-plane.py` 与 `workflowprogram-native-develop`，初始实现新建默认 Native、已有 legacy 保留旧模式；M16 已收窄为所有目标默认 Native，旧 runtime 标记只报告人工迁移注意事项。
- M1 补强：`probe-native-workflow-capability.py` 可从真实 JSONL 判读交互式能力状态。
- M7：`validate-native-authoring-readiness.py` 将前台澄清、用户确认、七个 logic lenses 和 `TARGET_ROOT` 绑定关系变成 generator 前置硬门禁。
- M7：`workflowprogram-native-authoring.js` 通过原生 Workflow 后台执行只读 `Explore -> Design -> Review -> Handoff`，使确认后的 authoring 阶段进入 `/workflows`。
- M7：`tools/build_plugin.py` 分发插件自身 `workflows/` 目录；`validate-workflow.py` 校验 source、dist 和 manifest 映射。
- P8：五个插件产品级 Native Workflow JS 分发骨架、统一 `NOT_IMPLEMENTED` 与 `plugin-script-path` envelope、单元测试、dist 构建、仓库级必需资产校验和真实 CLI 路径启动 smoke。
- P9 自动化部分：`workflowprogram-develop.js` 可重入状态机、`build-native-develop-evidence.py`、Skill 启动适配器、Node mock runtime fixture 和 candidate hash 回归。
- P10A 自动化部分：`workflowprogram-validate.js` 与 `workflowprogram-audit.js`、candidate-bound handoff、只读结构化 Agent 和稳定 envelope 回归。
- P10B 自动化部分：`workflowprogram-iterate.js`、`build-native-iterate-evidence.py`、Native Lessons Loop、幂等写入和 drift 回归。
- P10C 自动化部分：`workflowprogram-publish.js`、`build-native-publish-evidence.py`、local-only 默认交付、existing marketplace gate 和 GitHub 幂等 receipt。

本轮完成的是交互式 Native authoring 最小迁移切片。旧 Python runtime 主链仍保留，后续阶段需按样例工作流逐个迁移，不能把本轮结果解释为旧 runtime 已下线。

交互式 authoring 迁移已具备可用入口；旧 runtime 保留是兼容策略，不再是新建目标的默认选择。批量改写旧目标、非交互执行和自动化发布仍不属于当前支持范围。

普通用户不需要显式输入 orchestrate slash command。模型应根据自然语言和 Plugin Skill listing 语义选择 WorkflowProgram 入口；Skill 解析插件绝对路径后调用 `Workflow({ scriptPath, args })`。slash command 只用于调试和兜底。

M9 已将澄清、确认、设计审视和宿主侧 handoff 控制决策移入 `workflowprogram-develop.js`。JS 通过 `NEEDS_USER_INPUT`、`READY_FOR_CONFIRMATION` 和 `READY_FOR_*` 返回状态与前台对话衔接；前台模型只转述、执行窄化 adapter 并重新调用。M7 元工作流和 JSON renderer 保留为过渡桥。

P10A 已将 validate 与 audit 的质量关卡迁入 Native JS。P10B 已将 iterate 的 Lessons Loop 迁入 Native JS；短期 lessons 追加与长期 constraints 提升由窄化 adapter 执行，长期约束仍需独立审视和用户显式批准。

P10C 已将 publish 顺序迁入 Native JS；默认只交付本地包，existing marketplace merge 和 GitHub apply 保持独立 gate，外部写入需显式批准并由幂等 receipt 保护。

P13 已完成按任务类型选择模型的核心实现（见上文实施结果）。M14 legacy 下线评估已完成：`assess-native-legacy-retirement.py` 提供事实驱动的只读评估，14 项 legacy 资产/资产组 disposition 以及分组 removalPlan。M15 已完成 product handoff renderer 收窄：`--generation-handoff` 成为 active develop leaf 主路径，`--readiness` 仅保留为兼容回退。M16 已关闭 rollback/deprecation anchor 和 legacy routing blocker，当前仓库活跃 legacy retirement blocker 收敛为 1 条。实际 legacy 删除 deferred 至完整产品交互式 smoke 关闭。

## Closure Review

| 轮次 | 发现 | 关闭方式 |
|---|---|---|
| Round 1 | readiness 基础字段类型、可选资产描述和 legacy 文档标题需要收紧 | 增加严格类型校验，修正文档边界 |
| Round 2 | 元工作流输入需要显式 readiness 状态；`scriptPath` 不能依赖未展开的 `${CLAUDE_PLUGIN_ROOT}` 字面量 | 增加 `readinessStatus=PASS`，要求先解析插件绝对路径 |
| Round 3 | Native leaf 设置 `disable-model-invocation` 会削弱 orchestrate handoff | 移除 Native leaf 的禁用标记，仍由 leaf 内部门禁约束行为 |
| Round 4 | readiness packet 可能被跨目标目录复用；Windows validator 子进程编码依赖 locale | 将 packet 绑定到 `TARGET_ROOT`，固定 validator 子进程 UTF-8 协议 |
| Round 5 | 新鲜复核无新增 actionable issue | 保留交互式 `/workflows` smoke 作为环境相关人工验收 |
| Round 6 | M7 原型与目标稳态混淆；registry 字段证据过度推断；apply 未批准分支不准确；`taskType` 被误写为当前必填；Computer Use 边界不清 | 重写 HLD/LLD，区分三接口平面、原型和稳态；修正状态机；将 model policy 和 Computer Use 明确为宿主侧扩展 |
| Round 7 | audit、iterate、validate、publish 缺少逐阶段 LLD；外部发布写入与默认本地 publish 混合；未来 resolver 和 adapter 缺少明确文件契约 | 补齐阶段表、错误分类、`apply-external-publish.py` 和 `resolve-task-model-policy.py`，要求嵌套 workflow 透传 `args.taskModels` |
| Round 8 | repository validator 仍要求 M1-M7 原型兼容标记 | 增加明确标注为 transitional 的兼容说明，不改变稳态设计 |
| Round 9 | 新鲜复核无新增 actionable issue；仓库校验、链接和空白检查通过 | 关闭本次设计修订 |
| Round 10 | M8 注册骨架与 M9-M10C 业务迁移边界不够严格；M10 内部优先级未拆分；Native Lessons Loop 缺少完整阶段 | 将 M8 限定为 `NOT_IMPLEMENTED` 注册契约；拆分 M10A / M10B / M10C；补齐 findings、lessons delta、constraints approval |
| Round 11 | release 级仓库校验只检查文件存在；P13 / P14 与 M13 / M14 顺序不一致；HLD / LLD 未登记过渡态 `NOT_IMPLEMENTED` | 仓库 validator 主动执行 Native JS 静态校验；对齐编号；登记仅供 M8 使用的过渡状态 |
| Round 12 | 新鲜复核无新增 actionable issue；单元测试、integration gate、仓库校验、链接和空白检查通过 | 当时关闭 M8 自动化实现，并保留真实 CLI listing / name-launch 手工 smoke；该假设随后被 Round 13 的真实证据修正 |
| Round 13 | 真实 CLI 证明插件产品 JS 可按绝对 `scriptPath` 启动，但不会自动进入 saved workflow registry | 将 M8 改为插件产品 JS 分发与路径启动契约；Skill 负责语义发现和绝对路径解析 |
| Round 14 | 插件产品嵌套调用仍可能误用按名称 lookup；Computer Use smoke 口径仍引用 name launch | 要求嵌套产品 workflow 使用传入或解析后的绝对脚本引用；将 smoke 口径改为 Skill listing 与 `scriptPath` launch |
| Round 15 | fixture 容易被理解为真实 CLI 回包已包含后加的 `launchMode` 字段 | 明确区分真实 smoke 证明的路径启动能力与静态测试保证的新 envelope |
| Round 16 | 新鲜复核无新增 actionable issue | 关闭 M8 路径启动边界修订 |
| Round 17 | M9 的外部 evidence 若只检查 `PASS`，可能把旧 validation 或 smoke 结果复用于新 candidate | 增加 candidate tree hash；generation、validation、smoke 和 apply evidence 必须绑定同一 hash |
| Round 18 | 让模型手工拼 candidate hash 会削弱确定性；Skill 仍把控制顺序描述为 M7 前台桥 | 增加 `build-native-develop-evidence.py`，把 Skill 收窄为 scriptPath 启动和宿主侧 evidence adapter |
| Round 19 | evidence 数组仍接受空字符串；显式 smoke `FAIL` 且 transcript 存在时缺少 blocker；leaf Skill 漏写 M7 readiness 与 `supporting_assets` 兼容约束 | 收紧 JS gate，补 smoke fallback blocker，并恢复 renderer 兼容说明 |
| Round 20 | 初次 PTY 启动绕过 login shell，未注入原生 `Workflow` 工具；源码读取中的 `BLOCKED_INPUT` 曾造成假阳性 | 改为解析 JSONL 工具调用；使用继承 shell feature flags 的 PTY 启动；新增 M9 blocker smoke fixture |
| Round 21 | 新鲜复核无新增 actionable issue | 关闭 M9 自动化实现，保留完整交互式生命周期 smoke 给 M11 harness 持续覆盖 |
| Round 22 | model policy 的新映射只登记了 `complex-generation`，与已有通用 `generation` task type 漂移 | 同时保留 `generation -> flash` 和 `complex-generation -> pro`，由任务复杂度决定升级 |
| Round 23 | fallback 只描述为 `inherit`，缺少可审计的解析产物和失败原因 | 增加 `task-model-resolution.json` 契约、`MODEL_ALIAS_UNAVAILABLE` evidence，并禁止 JS 静默切换 |
| Round 24 | 新鲜复核无新增 actionable issue；具体 alias 未进入当前产品 JS | 关闭 P13 设计收敛，保留后续独立实现和 smoke |
| Round 25 | M10A 初版 injected inspect/audit evidence 仅检查 `status`，且 BLOCKED evidence 可能返回空 blocker | 增加结构化 JS gate、fallback blocker 和回归测试 |
| Round 26 | 新 validate/audit READY/PASS envelope 未统一包含 `blockingIssues`；validate phase 文案把宿主侧存在性验证误写成 JS 自身检查；状态枚举缺少新 handoff | 增加默认 `blockingIssues`、修正文案并补齐 LLD enum |
| Round 27 | M8 手工 fixture 与实施计划摘要仍可能被误读为当前骨架状态 | 将 fixture 标记为历史快照，并同步 M10A 当前实现状态 |
| Round 28 | 新鲜复核无新增 actionable issue；iterate 与 publish 仍是唯一 `NOT_IMPLEMENTED` 产品骨架 | 关闭 M10A 自动化实现，保留真实 Agent 交互 smoke 给 M11 |
| Round 29 | M10B 初版 readback 未强制非空 hash；Agent schema 缺少 hash；append/apply 将写入后 hash 与写入前 baseline 混用；iterate 测试 helper 覆盖 develop helper；adapter 未复用旧 delta validator | 拆分 baseline/post-write hash，补齐 Agent schema 与 gate，修复 helper 命名，并复用 `validate-lessons-delta.py` |
| Round 30 | `validate-delta --run-root` 仍可省略而绕开旧 validator；幂等判断晚于 drift 判断；append 未绑定已验证 `deltaHash`；readback 接受缺失 lessons | 将参数改为必填，优先识别内容绑定 marker，再检查 drift；append 强制 delta hash；缺失或空 lessons 阻断 |
| Round 31 | leaf skill 仍描述旧前台流程；仓库 validator 未要求新 adapter；README、状态索引和 LLD enum 尚未登记 M10B | 四个已迁移 leaf 增加 Native 默认入口，登记 adapter、状态、next action 和当前实施状态 |
| Round 32 | Windows PowerShell validator 基线已存在重复 hash key 与中文编码解析问题；本轮 PS1 diff 仅新增两条 adapter 资产登记 | 保留 Python release validator 作为当前有效仓库门禁，将 PS1 修复登记为独立跨平台维护债务 |
| Round 33 | 新鲜复核无新增 M10B actionable issue；publish 是唯一 `NOT_IMPLEMENTED` 产品骨架 | 关闭 M10B 自动化实现，保留真实 Agent 交互 smoke 给 M11 |
| Round 34 | M10C 初版 PASS evidence 未要求空 blocker；target hash 包含可变 runs；local delivery 没有真实产物生成动作 | 收紧 JS gate，拆分 target/package hash，并新增本地安装说明生成器 |
| Round 35 | GitHub adapter 在同一成功 run 重试时仍可能再次执行 copy、commit、tag 和 push | 增加 package hash 与 run-scoped PASS receipt 短路 |
| Round 36 | receipt 短路晚于 auth/repo-path 检查；dry-run PASS 仍可能被当作真实 external apply | 在显式批准后优先复用真实 receipt；normalizer 拒绝 dry-run PASS |
| Round 37 | publish leaf、仓库 validator、README、状态索引和 LLD enum 尚未登记 M10C | 同步 Native 默认入口、adapter 必需资产和当前实施状态 |
| Round 38 | 新鲜复核无新增 M10C actionable issue；五个产品 JS 均已移除 M8 骨架 | 关闭 M10C 自动化实现，进入 M11 完整交互式 smoke |
| Round 39 | M11 v1 smoke harness 实现 `packet`/`evaluate`；Computer Use 终端驱动仍 deferred | 关闭 M11 v1，保留 Computer Use adapter 为后续扩展 |
| Round 40 | 初版把所有 blocker 都要求 Agent/schema，且假定 journal 为 `subagent_start/subagent_output` | 增加 `full` / `early-blocker` profile，支持真实 journal `started/result` |
| Round 41 | 真实 session 的 `async_launched` 位于嵌套 `toolUseResult`；文本回退污染 run ID | 改为递归结构解析，并将 run ID 限制为 `[A-Za-z0-9_-]+`；两份历史真实 JSONL 回归通过 |
| Round 42 | M12 初版 no-op 仍重写 managed manifest；资格校验允许遗漏资产和不安全路径 | 纯 no-op 不保存 manifest；资格校验增加资产全集、安全路径、重复路径和 target root 检查 |
| Round 43 | builder 在计算 `all_pass` 后才追加 workflow script 不在 managed assets 的 blocker | 将检查前移到 `assetScope` gate，并新增回归测试 |
| Round 44 | M13 初版 resolver 缺少 `--task-type`、`--available-model`、`--out`；code-review | 新增 --task-type 可重复筛选、--available-model 可重复（CLI 优先于 env）、--out 精确路径；custom alias 默认接受（仅显式可用列表缺失时拒绝）；缺失/无效 policy 文件记录 POLICY_FILE_UNAVAILABLE / POLICY_FILE_INVALID；未知 taskType 记录 TASK_TYPE_UNMAPPED；JS 改为 withTaskModel 助手，inherit/absent 时不传 model；transitional authoring 添加 task type 传播 |
| Round 45 | resolver 在缺少 `--run-root` 和 `--out` 时仍返回成功；JS helper 未规范化空白 alias；测试没有区分缺失 `model` 属性与值为 `undefined` | 强制要求输出目的地；对 alias 执行 trim；mock harness 记录 `model` 属性是否真实存在并增加回归 |
| Round 46 | `diff_added_line_check` 直接包含冲突标记字面量，导致新增自检代码扫描自身 diff 时误报 | 运行时构造冲突标记，并增加真实冲突标记拒绝回归 |
| Round 47 | M14 初版命名 `assess-legacy-retirement.py` 与 schema `workflowprogram-legacy-retirement-assessment` 偏离约定；评估器硬编码 `True`/`False` 无法收敛；空目录总是 blocked 而非提供 closure fixture | 重命名为 `assess-native-legacy-retirement.py` + schema `native-legacy-retirement-assessment`；改为内容驱动的事实检测；增加 READY_FOR_RETIREMENT closure fixture（含闭合的证据 JSON） |
| Round 48 | 新鲜复核无新增 actionable issue | 关闭 M14 评价实施阶段；实际删除 deferred |
| Round 49 | M14 closure review 发现目录型 runtime 误用 `is_file()`、smoke 覆盖只检查字段存在、异常 evidence 形状可能崩溃、bridge 文件存在被误判为活跃引用、文档中规则数与活跃 blocker 数混淆 | 目录资产改用 `exists()`；覆盖值必须显式为 `true`；异常证据保持可见 blocker；bridge 仅按主路径引用阻断；文档明确 5 条规则、当前 4 条活跃 |
| Round 50 | M14 修复后新鲜复核无新增 actionable issue | 关闭 M14 资格评估实施；实际 legacy 删除保持 deferred |
| Round 51 | M15 初版使用 `--handoff`，未形成严格二选一 CLI；handoff 字段校验和 report 不完整；assessor 容易被弱 marker 绕过 | 改为 `--generation-handoff` 与 `--readiness` 必选互斥；增加结构化 handoff report；按 active skill/command 中的 M7 兼容资产引用判断 bridge blocker |
| Round 52 | 复核发现 runId/rule 会被字符串化、错误信息缺少 f-string、非法 handoff 会先创建 target root、文档仍有旧 M14/M15 状态 | runId 和 generationRequest.rule 必须原生字符串；修复错误信息；非法 handoff 在 candidate 写入前失败且不创建 target root；同步 README、HLD、LLD、迁移计划和状态索引 |
| Round 53 | 新鲜复核无新增 M15 actionable issue；聚焦回归、全量单元、integration gate、仓库 validator、Markdown 链接和 diff 检查通过 | 关闭 M15 product handoff renderer 收窄；legacy 实际删除仍 deferred 至剩余 3 条 blocker 关闭 |
| Round 54 | 剩余 blocker 中 rollback anchor 和 legacy routing 可由确定性资产关闭；product smoke 仍必须来自真实交互 JSONL，不能伪造 | 新增 `legacy-retirement-anchor.json`；router 收窄为始终 Native 并报告 `manual_migration_required`；测试和文档改为仅剩 product smoke blocker |
| Round 55 | product smoke 缺少从 evaluator reports 到 assessor evidence 的确定性聚合步骤，手工编辑 flags 容易绕过真实 JSONL 证据 | 新增 `build-native-product-smoke-evidence.py` 和 product smoke manual fixture；聚合器只接受 evaluator PASS reports，覆盖不完整时保持 `declaredComplete=false` |
| Round 56 | develop smoke report 没有绑定实际 candidate `scriptPath`，evaluator 也缺少稳定落盘输出 | evaluator 增加 `--script-path`、`--candidate-root`、`--out`，develop evidence 校验 `scriptHash`、`candidateHash`、scenario 和 report hash |
| Round 57 | generation/validation 仍可接受浅 PASS JSON；apply adapter 与真实 `managed-change-result` 形状不一致 | 只接受真实 report schema；以实际 managed-assets 输出和持久化 manifest 回归 apply evidence |
| Round 58 | product smoke 聚合器只看 schema/status，浅 evaluator PASS 仍可关闭 legacy blocker | 聚合器重新校验 return code、blockers、路径、run ID、profile 和对应证据 |
| Round 59 | 独立 Claude Code 审查发现静态 validator 漏掉部分宿主工具、裸引用和动态执行；product smoke 未校验 workflow 与 scriptPath 文件名 | 扩展高置信度静态规则并要求产品 workflow 名与脚本文件名一致 |
| Round 60 | 新鲜复核发现 apply manifest 可以位于旁路路径，目标文件内容和目标根未绑定；schema/profile 版本边界不明确 | apply evidence 显式接收并回传 `targetRoot`，绑定持久化 managed result、目标 manifest 和目标文件 hash；报告校验 schema version 与 evidence profile |
| Round 61 | 独立 Claude Code 复核发现 JS gate 未拒绝同一 smoke report 同时声明 PASS 与 BLOCKED completion | 增加 completion 互斥 gate 和回归测试；保留 aggregate camelCase schema、tagged-template 拒绝与 persisted report 精确相等的既有契约 |
| Round 62 | 新鲜 Codex 复核发现 generation/validation 可指向同一 candidate tree 内的不同 JS，`early-blocker` 可被用于 PASS，间接 `eval` / `Function` 引用可绕过静态规则 | generation/validation 共同回传并比较 `workflowScriptPath`；限制 `early-blocker` 仅用于 BLOCKED；拒绝动态执行 API 的裸引用并补充回归测试 |
| Round 63 | 独立 Claude Code 复核未发现关键 false PASS，但发现注释中的 `eval` / `Function` 名称会触发静态校验 false positive，且 phase alignment 的路径语义需要说明 | forbidden API 检查先剥离注释并补充回归测试；LLD 明确 `PHASE_ALIGNMENT` 只校验声明与调用名称集合；保留已决定的 aggregate camelCase 和 skill listing 兼容 fallback |
| Round 64 | 独立 Claude Code 窄审再次提出已决策的 aggregate camelCase 和 legacy BLOCKED 问题，同时指出 `skill_listing` content 子串匹配与 body 注释中的 `phase()` 可能污染证据/phase alignment | 接受 exact-token skill listing 与 body 注释剥离两个局部增强并补回归；拒绝 product aggregate 重命名、伪造 product smoke、放宽 meta pure-literal 注释等超出或违背当前契约的建议 |
| Round 65 | 新鲜收口复核未发现新的 P20 actionable issue；聚焦测试、integration gate、仓库 validator、主 Workflow static validator 和 diff check 均通过 | 关闭 WPN 机制修复阶段；legacy retirement 仍按设计保持 `BLOCKED_RETIREMENT`，唯一活跃阻断是真实 product smoke 未完成 |

P8 已完成：真实 Claude Code CLI 中绝对 `scriptPath` 启动成功，按产品名称 lookup 失败并被记录为部署边界。P9-M10C 已完成五个产品 Native JS 的自动化实现；M11 第一版交互式 smoke harness（`build-native-interactive-smoke.py`）已完成 `packet` 与 `evaluate` 子命令，支持人工执行 packet 生成与确定性 JSONL 判读；M12 已完成 Native manifest、发布资格聚合、managed apply no-op 和 drift 阻断。P13（即 M13）已完成：按任务类型选择模型的核心实现，`resolve-task-model-policy.py` 将逻辑 taskType 解析为模型别名并输出 resolution；product workflow JS 通过 `withTaskModel(taskType, options)` 消费映射结果；31 项单元测试覆盖。M14 已完成只读 legacy 下线资格评估，实际删除仍 deferred。M15 已完成 product handoff renderer 收窄，active develop leaf 不再依赖 M7 readiness/authoring 兼容桥。M16 已关闭 rollback/deprecation anchor 与 legacy routing blocker，当前 active blocker 仅剩完整产品交互式 smoke。Computer Use 终端驱动仍处于 deferred 状态，当前仅支持 manual WSL login-shell execution + deterministic JSONL evaluation。不得将宿主侧 renderer 兼容桥解释为第二套 runtime。

验证环境边界：

- Windows 原生可执行静态校验、生成器单测、仓库 validator 和 integration gate。
- `dist/plugin/bin/workflowprogram-*` 当前是 Unix launcher，完整 plugin bootstrap 与 runtime smoke matrix 应在 WSL/Linux 运行。
- Windows 原生直接运行 release 级 smoke matrix 还会受到长 fixture 路径限制；这属于现有分发与测试 harness 的跨平台边界，不属于本轮 Native authoring 迁移范围。

### P20. FreeSTRIDE 迁移回归修复

问题来源：

- FreeSTRIDE 候选 JS 直接调用了 Native Workflow runtime 未提供的 `Bash()`，但旧 validator 仍返回 PASS。
- 原始 JSONL、占位 evidence 和字符串 manifest 可以绕过 develop 控制面的 smoke/apply gate。
- authoring spec 将迁移资产内容与资产处置决策混在 `supporting_assets` 中，无法表达 retain/remove/defer 等无内容变更决策。

实施：

- 收紧 `validate-native-workflow-js.py`：拒绝未支持的宿主工具直接调用或裸引用，拒绝动态代码执行，保守检测关键未声明标识符，不要求所有返回 envelope 包含 `runId`。
- 收紧 `build-native-interactive-smoke.py`、`build-native-develop-evidence.py` 与 `workflowprogram-develop.js`：generation/validation 只接受当前 schema 版本的真实报告，并共同指向同一个 `.claude/workflows/*.js` 主脚本；smoke 只接受绑定 candidate `scriptPath`、`scriptHash`、`candidateHash`、scenario 和有效 evidence profile 的完整 evaluator 报告，且 `early-blocker` 只能证明预期 BLOCKED；apply 显式绑定 `targetRoot`，只接受覆盖 candidate、匹配持久化 managed result、目标 manifest 与目标文件 hash 的结构化证据。
- 收紧 `generate-native-workflow.py`：将 `asset_disposition` 与 `supporting_assets` 分离，并限制 `task_model_policy` 形状。
- 更新 leaf skill、HLD、LLD、迁移计划、fixtures 和单元测试，再用真实 FreeSTRIDE 迁移验证门禁。

验收：

- 无效 `Bash()`、宿主工具裸引用、动态代码执行、未声明关键标识符、原始 JSONL、占位证据、字符串 apply manifest、旁路 manifest、目标文件 drift、未覆盖 candidate 的 manifest、缺失迁移 disposition 和未知模型策略字段均失败。
- 有效最小 JS 不需要 `runId` 仍可通过；retain-only 迁移不需要伪造 supporting asset。
- FreeSTRIDE 仅在真实 candidate `scriptPath` smoke、evaluator 报告和 managed apply 证据闭合后切换入口。

### P21. FreeSTRIDE Foreground-Bypass Regression Repairs

Scope:

- Do not modify FreeSTRIDE assets directly. Use the FreeSTRIDE migration JSONL and
  final candidate only as regression evidence for WPN.
- Repair WPN so a blocked product JS result cannot be bypassed by the foreground
  assistant manually writing target files or committing changes.

Design changes:

- D1 clarification receives settled WPN platform decisions and must not ask the
  user to re-decide them.
- D1 open question normalization drops resolved/answered objects and never
  stringifies object questions as `[object Object]`.
- D4 design review gate treats non-empty `requiredRevisions` as blocking even
  when `status=PASS`.
- D4 review-fix re-entry has a first-class `reviewFixes` correction field,
  accepts `designReviewRebuttal` as a compatibility alias, reuses supplied
  `explorations`, and tells the foreground which stale evidence fields to omit.
- Product JS uses built-in default task model mappings when no `taskModels` map
  is supplied; explicit maps still own their provided task types.
- Intent routing gives workflow create/update/migrate requests priority over
  domain words such as "security audit".
- Foreground guard state plus `PreToolUse` hook blocks direct writes to managed
  target assets and blocks commits until `PASS` + `managed-apply` + manifest.
- Foreground guard shell checks block embedded writer APIs when they target
  managed paths, including Python `open(..., 'w')` / `Path.write_text`, Node
  `fs.writeFile*`, PowerShell content writers, and shell `tee`/`touch`/`mkdir`;
  read-only probes and active run-root candidate writes remain allowed.

Implementation tasks:

- Update `workflowprogram-develop.js`, `workflowprogram-audit.js`,
  `workflowprogram-iterate.js`, and `workflowprogram-native-authoring.js` task
  model fallback behavior.
- Update `workflowprogram-develop.js` review-block return payloads with
  `reinvokeArgsPolicy`, normalize review correction aliases, and add regression
  tests for exploration reuse on review-fix re-entry.
- Add `workflowprogram-foreground-guard.py`, register it in plugin hooks, and
  include it in repository/dist validation.
- Add embedded-writer regression coverage for Bash/PowerShell/Shell commands
  that target `.claude/**` or `.workflowprogram/managed-files.json`.
- Generate target-runtime wrappers with a cross-platform plugin Python launcher:
  keep `bin/workflowprogram-python` on POSIX, use `sys.executable` plus
  plugin-local bootstrap and `PYTHONPATH` setup on Windows, and cover this with
  an invocation test for generated `workflow-entry.py`.
- Update `workflowprogram-native-develop` skill and WorkflowProgram LLD skill
  references with guard and clarification rules.
- Add regression tests for route intent, clarification open questions, review
  revisions, default models, and foreground guard.

Acceptance:

- Focused unit tests pass for Native workflow JS, task model policy, route
  intent, and foreground guard.
- `validate-workflow.py` passes after `dist/plugin` is rebuilt.
- Independent deepseek-v4-flash and deepseek-v4-pro review passes do not report
  unresolved critical blockers.
