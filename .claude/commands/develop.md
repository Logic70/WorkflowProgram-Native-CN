根据用户需求设计一个新工作流。这个命令生成的是工作流文件，
例如 commands、skills、agents、rules 与 settings 更新，而不是应用代码。

> Compatibility Note
>
> `/develop` 作为历史兼容入口保留。普通用户应优先使用
> `/workflowprogram-cn:workflowprogram-orchestrate <需求>`，再由 orchestrate 路由到
> `workflowprogram-develop`。
> 下方 Stage 内容是兼容参考；受控执行必须进入 `${CLAUDE_PLUGIN_ROOT}/scripts/workflow-entry.py run`。

## Usage

```text
/develop <requirement> [--auto-approve]
```

**参数：**
- `<requirement>`: 工作流需求描述（自然语言）
- `--auto-approve`: 自动批准模式，跳过人工确认门禁（用于 CI/CD）

**CI/CD 模式：**
设置环境变量 `CI=true` 或传入 `--auto-approve` 参数，所有设计门禁将自动放行。

**示例：**

```text
# 交互模式（默认）
/develop 设计一个用于审计 Markdown 链接有效性的工作流

# CI/CD 自动模式
/develop "设计一个用于审计 Markdown 链接有效性的工作流" --auto-approve
CI=true /develop "设计一个用于审计 Markdown 链接有效性的工作流"
```

整个过程遵循 TDD 风格循环：定义目标 -> 执行 -> 验证 -> 失败则记录到
`lessons.md` -> 修复 -> 重试。

## Stage 进展播报契约

每个 Stage 的进展事件都必须由 `workflow-runner.py` 或等价的 control-plane helper
在内部调用 `${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py` 发射，不要求模型手工拼接
`stage-progress.py update ...` CLI。

维护以下进展资产：

- `RUN_ROOT/outputs/progress/current-progress.json`
- `RUN_ROOT/outputs/progress/milestones.jsonl`
- `RUN_ROOT/outputs/progress/user-progress.md`

每个 Stage 至少记录三个事件：

- `StageStarted`
- `StageCheckpoint`
- `StageCompleted`

并向用户同步：

- 当前 Stage / Node
- 当前完成度（percent）
- 最近关键节点结果（milestones）
- 下一步动作

## Stage 1: 理解需求 (Explore)

**Goal**: 通过多轮用户对话生成一个没有歧义的 `workflow-spec.md`，并同步产出后续阶段可读的结构化澄清包。

**Progress hooks**：
- Stage 开始：`S1 StageStarted`
- 规格草案写入后：`S1 StageCheckpoint`
- Stage 完成：`S1 StageCompleted`

1. 将 `$ARGUMENTS` 解析为初始工作流需求。
2. 识别当前仍会影响设计的歧义点，围绕以下维度分轮向用户追问：
   - 用户真正想解决的问题和最终目的是什么？
   - 需要自动化的流程是什么？（触发 -> 步骤 -> 输出）
   - 输入和输出分别是什么？
   - 有哪些质量门禁、停止条件或成功标准？
   - 涉及多少种角色或专家维度？
   - 应由手动命令触发，还是由 hook 自动触发？
3. 每轮只提 1-3 个最高优先级问题；若用户回答后仍存在设计歧义，则继续下一轮，不得只做单轮问答后直接结束。
4. 当“用户诉求 / 最终目的 / 成功标准 / 触发方式 / 输入输出 / 质量门禁”都已明确后，使用 `.claude/skills/workflow-spec-support/spec-template.md` 生成 `workflow-spec.md`。
5. 运行 `generate-clarification-package.py`，从 `workflow-spec.md` 派生：
   - `outputs/stages/clarification-record.json`
   - `outputs/stages/open-questions.json`
   - `outputs/stages/assumption-log.md`
   - `outputs/stages/design-readiness-report.json`
6. 运行 `generate-clarification-review.py`，由内部 challenge roles 生成：
   - `outputs/stages/clarification-challenge-report.json`
   - `outputs/stages/clarification-handoff.json`
   - `outputs/stages/clarification-evidence.json`
   - 约束：`requirement-clarification-lead` 是唯一直接与用户对话的角色；`scenario-extractor`、`assumption-auditor`、`constraint-reviewer` 只允许在内部审阅并向 lead 提出补问/补证建议。
7. **Verify**: 规格中的每个字段都有明确值，包含 `User Intent`、`Clarification Summary`、`Open Questions`、`Assumptions and Boundaries`、`Target Workflow Graph Readback`、`File Plan`、`Readback Confirmation`，`澄清轮次 >= 2`，`design-readiness-report.json` 判定为 `READY`，且 `clarification-handoff.json.ready=true`，可直接供 `S2/S3` 消费。

**On failure**：把歧义点和所需补充信息记录到 `lessons.md`。

## Stage 2: 领域研究 (Explore)

**Goal**: 生成覆盖规格范围的领域上下文报告。

**Progress hooks**：
- Stage 开始：`S2 StageStarted`
- 上下文报告写入后：`S2 StageCheckpoint`
- Stage 完成：`S2 StageCompleted`

1. 启动只读 Explore 子代理，分析：
   - 现有 `.claude/` 资产：agents、skills、commands、settings、rules
   - `CLAUDE.md` 中的项目约定、校验方式和命名规则
   - 与目标工作流领域相关的项目结构
2. 输出结构化报告，列出可复用资产、缺口和命名建议。
3. **Verify**: 报告覆盖 `workflow-spec.md`、`clarification-record.json` 与 `clarification-handoff.json.s2_inputs` 中提到的所有领域范围。

**On failure**：把遗漏的上下文记录到 `lessons.md`。

## Stage 3: 模式选择与工作流设计 (Specialized Agent)

**Goal**: 生成包含模式组合、Agent 编制和文件清单的设计文档。

**Progress hooks**：
- Stage 开始：`S3 StageStarted`
- YAML/View 生成后：`S3 StageCheckpoint`
- design-review gate 通过后：`S3 StageCompleted`

设计前先阅读 `.claude/rules/constraints.md`。

### 工作流抽取决策框架

在真正生成文件前，先判断这个工作流是否应被抽取成独立仓库。

**ALWAYS extract when：**

- 该工作流强依赖某种语言、框架或工具链
- 其他团队或项目也可能独立复用它
- 它需要独立演进和发布节奏
- 它与当前仓库技术栈明显不同

**NEVER extract when：**

- 它只服务于本仓库
- 它高度依赖当前仓库约定或本地配置
- 它还在高频变化期
- 它本质上是通用能力，应留在当前仓库

**If extracting：**

1. 先在当前仓库中生成草稿
2. 向用户展示设计
3. 批准后复制到 `../{name}-workflow/`
4. 再清理当前仓库中的临时副本

随后，基于六种原子模式分析需求：

- Sequential
- Fan-out/Fan-in
- Explore
- Event-Driven
- Test-Driven
- Specialized Agent

设计文档至少包括：

- ASCII 流程图
- Agent 清单：名称、职责、关注点、输出格式、约束
- Skill 清单：触发方式与职责
- Hook 清单：只有确实需要 hooks 时才添加
- 文件清单：要创建或修改的每个文件
- 每一阶段的 TDD 目标和验证条件
- S3 设计审视计划：审视 lens、阻塞问题闭合方式、accepted risk 记录方式

**三层设计输出（Design Package）**：

设计阶段产出三份互补的设计文档：

1. **`workflow-spec.yaml`** —— 机器可读的编排配置（源文件）
   - 包含：阶段定义、Agent 引用、转移条件、资源限额、运行契约（`runtime_contract`）、基础运行测试判定契约（`test_contract`）
   - 同时必须包含 `generated_runtime_contract`；若工作流需要先搜索候选能力，则声明 `capability_discovery`；若工作流依赖宿主能力或显式 team，则还必须声明 `host_capabilities`、`agent_team_contract`
   - 若目标工作流需要请求特定业务节点图，则必须声明 `workflow_graph`；该图不强制套用 WorkflowProgram 自身 `S1..S6`
   - 必须同时声明 `intent_flows`，明确 `develop / audit / iterate / validate` 的逻辑阶段流
   - `runtime_contract` 必须显式定义：
     - `write_boundaries`（允许写入边界）
     - `required_evidence`（最小运行证据集）
     - `failure_kinds`（失败类别枚举）
     - `environment_skip`（环境 skip 条件）
   - `test_contract` 必须显式定义：
     - `entry`（主入口、入口类型、必需参数、缺参与非法入口 verdict）
     - `boundary`（写入边界引用、managed 覆盖/冲突/外部写入策略）
     - `flow`（required/skippable stages、失败回流、终止条件）
     - `artifacts`（关键交付物、关键证据引用、可缺失非关键输出）
     - `failure`（失败枚举引用、环境 skip 引用、`implemented_now` 覆盖度声明）
   - `intent_flows` 必须显式定义：
     - `develop.required_stage_slots = [S1,S2,S3,S4,S5,S6]`
     - `audit.required_stage_slots = [S5,S6]`
     - `iterate.required_stage_slots = [S6]`
     - `validate.required_stage_slots = [S5]`
   - 约束：`test_contract` 对执行字段必须使用 `runtime_contract.<field>` 固定引用语法，且不得复制或削弱 runner 语义
   - 约束：`generated_runtime_contract.mode` 当前固定为 `shared-control-plane-wrapper`，`runtime_capabilities` 必须至少包含 `state_transitions` 与 `run_state_validation`
   - 约束：若启用 `capability_discovery`，则 `runtime_capabilities` 还必须包含 `capability_discovery`
   - 约束：若声明 `host_capabilities.bootstrap.scope=project_local`，则可选的 `bootstrap.assets` 只能写入 `.workflowprogram/bootstrap/**`，用于生成复用配置或 wrapper 资产
   - 约束：若声明 `host_capabilities`，产品入口与目标侧 runtime 都必须在 probe/bootstrap 后生成 `environment-remediation-report.json` 与 `environment-remediation-guide.md`；若重复环境失败存在，则 S6 必须把修复建议提升到 `s6-lessons-delta.md`
   - 格式：结构化 YAML，支持 `max_retries`、`max_parallel` 等约束
   - 用途：Code Agent 执行时解析，强制执行状态转移
   - 可编辑：✅ 人工可编辑，AI 可生成

2. **`workflow-view.md`** —— 人类可读的只读视图（生成文件）
   - 包含：ASCII 流程图、设计决策说明、Agent 职责描述
   - 格式：自然语言 Markdown
   - 用途：人工审查、快速浏览、设计讨论
   - 可编辑：❌ 禁止直接编辑，从 YAML 单向生成

3. **`workflow-maintenance.md`** —— 维护与迭代指导（生成文件）
   - 包含：真源层级、阶段契约、证据归属、持久化设计资产规则、维护方法
   - 格式：自然语言 Markdown
   - 用途：后续 audit / iterate / 人工维护时快速理解当前工作流
   - 可编辑：❌ 禁止直接编辑；它只能解释 YAML，不能覆盖 YAML 语义

**单向瀑布生成原则**：
```
workflow-design.md（设计决策，人工审查）
         ↓
   提取转换
         ↓
workflow-spec.yaml（机器编排，单点真实）
         ├───────────────┐
         ↓               ↓
workflow-view.md     workflow-maintenance.md
（只读视图）           （维护指导）
```

**编辑规则**：
- 如需修改设计 → 编辑 `workflow-spec.yaml`
- 重新生成视图 → 运行 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/generate-workflow-view.py --spec <RUN_ROOT>/workflow-spec.yaml --out <RUN_ROOT>/workflow-view.md`
- 重新生成维护指导 → 运行 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/generate-workflow-maintenance.py --spec <RUN_ROOT>/workflow-spec.yaml --out <RUN_ROOT>/workflow-maintenance.md`

### S3 Design Review Gate

在进入 S4 候选资产生成或 managed apply 前，必须先完成设计审视闭环：

1. 调用 `${CLAUDE_PLUGIN_ROOT}/scripts/generate-design-review-packet.py --run-root <RUN_ROOT> --target-root <TARGET_ROOT> --request "$ARGUMENTS"`。
2. 调用内部 `workflow-design-reviewer`，按 goal fidelity、requirement coverage、flow closure、spec projection、evidence quality、change impact、runtime compatibility、complexity control、context propagation 审视。
3. 每轮写入 `outputs/stages/design-review/round-<n>.json`，汇总 `issues.json` 与 `report.md`。
4. 若存在 blocking issue，回到 S3 修改设计源、traceability 或 `workflow-spec.yaml`，重新生成 packet 并复审。
5. 写入 `outputs/stages/design-review/closure.json` 后，调用 `${CLAUDE_PLUGIN_ROOT}/scripts/validate-design-review-gate.py --run-root <RUN_ROOT>`。
6. 只有 `gate-validation.json.status=PASS` 才能进入 S4；accepted risk 必须记录 residual risk，允许继续但由 S5 作为 INFO 证据保留。
- 结构校验规格 → 运行 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/validate-workflow-spec.py --spec <RUN_ROOT>/workflow-spec.yaml`
- 需要先推荐宿主能力时 → 运行 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/discover-host-capabilities.py --spec <RUN_ROOT>/workflow-spec.yaml --target-root <TARGET_ROOT> --run-root <RUN_ROOT> --request "<原始需求>"`
- 禁止直接编辑 `workflow-view.md` 与 `workflow-maintenance.md`（会被覆盖）
- develop 成功后，`workflow-spec.yaml`、`workflow-view.md`、`workflow-maintenance.md` 必须持久化到 `TARGET_ROOT/.workflowprogram/design/`
- develop 成功后，还必须把目标侧 runtime 资产持久化到 `TARGET_ROOT/.workflowprogram/runtime/`

**On failure**：把设计失误写入 `lessons.md`。

**Gate**：将设计展示给用户，得到批准后再进入生成阶段。

**自动批准模式**：若传入 `--auto-approve` 参数或环境变量 `CI=true` 存在，则跳过人工确认，打印确认信息后自动继续。

## Stage 4: 从 YAML 生成工作流文件 (Sequential + 即时校验)

**Goal**: 从 `workflow-spec.yaml` 生成所有工作流文件。

**Progress hooks**：
- Stage 开始：`S4 StageStarted`
- candidate 与 managed plan 完成后：`S4 StageCheckpoint`
- apply 成功或冲突归档后：`S4 StageCompleted`

**复杂度级别**: 从 YAML 读取 `complexity` 字段，用于 Stage 5 Turn Count 配置

**写入约束**：

- 不要直接把新文件静默覆盖到 `TARGET_ROOT/.claude/`。
- 先把候选文件写入 `RUN_ROOT/outputs/candidate/.claude/`。
- 候选产物生成完成后，调用 `${CLAUDE_PLUGIN_ROOT}/scripts/managed-assets.py`：
  - `plan --target-root <TARGET_ROOT> --run-root <RUN_ROOT> --source-root <RUN_ROOT>/outputs/candidate/.claude`
  - 若无冲突，再执行 `apply-staged`
- 若返回冲突，必须把候选版本保留在 `RUN_ROOT/outputs/` 并向用户报告，不能静默覆盖用户资产。
- 确定性产品入口脚本为 `${CLAUDE_PLUGIN_ROOT}/scripts/workflow-entry.py run`；不要把 `managed-assets.py`、`workflow-runner.py`、`validate-run-state.py` 作为松散顺序提示留给模型自由发挥。

**生成流程**：

1. 解析 `workflow-spec.yaml`
   - 读取 `meta` 段：target_platform, version
   - 读取 `stages` 段：阶段定义、Agent 引用、约束

2. 按 YAML 定义生成文件（每个文件生成后立即校验，最多3次）：

生成顺序（每个文件生成后立即校验，最多3次，失败则人工介入）：

1. `.claude/agents/*.md`
   - 从 YAML `agent_refs` 提取 Agent 定义
   - 生成后调用 `validate-file` skill 检查
   - 失败则修复，最多3次，仍失败则停止并人工介入

2. `.claude/skills/*/SKILL.md`
   - 从 YAML `skills` 段生成技能定义
   - 生成后调用 `validate-file` skill 检查
   - 失败则修复，最多3次，仍失败则停止并人工介入

3. `.claude/commands/*.md`
   - 从 YAML `stages` 生成命令 Stage 结构
   - 生成后调用 `validate-file` skill 检查
   - 失败则修复，最多3次，仍失败则停止并人工介入

4. `.claude/settings.json`
   - 从 YAML 生成命令和技能注册
   - 生成后调用 `validate-settings` skill 检查
   - 失败则修复，最多3次，仍失败则停止并人工介入

5. `.claude/rules/constraints.md`（如需要，从 YAML `constraints` 提取）
6. 生成 `workflow-view.md`（从 YAML 单向渲染，只读）
7. 生成 `workflow-maintenance.md`（从 YAML 单向渲染，只作维护指导）
8. 生成目标侧 deterministic runtime 资产：`.workflowprogram/runtime/{workflow-entry.py,workflow-runner.py,validate-run-state.py,runtime-manifest.json}`
9. 更新 `CLAUDE.md`（如需要）
10. 候选资产生成或应用前，必须已有 `outputs/stages/design-review/{design-review-packet.json,issues.json,closure.json,gate-validation.json}`，且 gate status 为 `PASS`。
11. 候选资产生成完成后，必须调用确定性脚本入口：
   - `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflow-entry.py run --spec <RUN_ROOT>/workflow-spec.yaml --run-root <RUN_ROOT> --target-root <TARGET_ROOT> --entry-skill workflowprogram-develop --request "$ARGUMENTS" [--auto-approve|--approval-status approved]`
   - 该脚本负责按固定顺序执行 `validate-workflow-spec.py -> generate-workflow-view.py -> generate-workflow-maintenance.py -> validate-design-review-gate.py -> generate-target-runtime.py -> managed-assets.py -> discover-host-capabilities.py -> probe-host-capabilities.py -> apply-host-bootstrap.py -> generate-environment-remediation.py -> workflow-runner.py -> validate-run-state.py`
   - 它会把 `RUN_ROOT/workflow-spec.yaml`、`RUN_ROOT/workflow-view.md`、`RUN_ROOT/workflow-maintenance.md` 复制到 `RUN_ROOT/outputs/candidate/.workflowprogram/design/`，并把目标侧 runtime 资产写入 `RUN_ROOT/outputs/candidate/.workflowprogram/runtime/`，再与 `.claude/*` 一起走 managed apply
   - 若 `managed-assets.py` 发现冲突，脚本必须停在 S4，并输出 `RUN_ROOT/outputs/stages/entry-orchestration-summary.json`
12. 交由 `workflowprogram-validate` 形成 S5 主判定与运行态证据：
   - `workflowprogram-validate` 是 S5 主 judge，负责消费 `test_contract`
   - `runtime_smoke.py` 作为动态 harness，在 Claude 可用时补充 `validation-runtime-report.md`
   - `RUN_ROOT/outputs/stages/s5-validation-summary.json` 由验证链路汇总写入，不由 runner 独占

**Verify**: 设计文档中的每个文件都存在且通过 `validate-file` 检查。

**On failure**：单文件3次尝试失败后，停止并人工介入。

## Stage 5: 运行时验证 (Runtime Validation)

**Goal**: 以 `test_contract` 为判定来源，验证工作流运行态是否符合设计。

**Progress hooks**：
- Stage 开始：`S5 StageStarted`
- 关键验证节点后：`S5 StageCheckpoint`
- 结论写入后：`S5 StageCompleted`

**Step 1: 读取判定契约**

1. 读取 `workflow-spec.yaml.runtime_contract` 与 `workflow-spec.yaml.test_contract`。
2. 以 `workflowprogram-validate` 作为 S5 主 judge，按 `entry / boundary / flow / artifacts / failure` 五类契约生成检查项。
3. 将 `runtime_smoke.py` 视为动态 harness，仅在 Claude 可用时补充真实执行证据。

**Step 2: 产出判定结果**

1. 生成 `RUN_ROOT/outputs/stages/s5-validation-summary.json`。
2. 生成或更新 `validation-runtime-report.md`。
3. 如可执行真实 smoke，则补充 `transcript.md` 与额外运行证据。

**反馈路径**：
- **PASS** → 进入 Stage 6
- **WARN** → 进入 Stage 6，但记录告警和约束候选
- **FAIL (设计缺陷)** → 回到 Stage 3
- **FAIL (实现缺陷)** → 回到 Stage 4
- **ENVIRONMENT-SKIP** → 记录环境原因并进入 Stage 6

**最大循环**：10轮或问题收敛为0

**Verify**: `validation-runtime-report.md`、`s5-validation-summary.json` 和 `transcript.md` 的职责边界清晰，且检查项可追溯到 `test_contract`。

**On failure**：记录问题到 `lessons.md`，按缺陷类型反馈到 Stage 3 或 4，重新验证。

## Stage 6: 约束演进与流程闭环

**Goal**: 从本次设计会话中提炼可复用规则，完成流程闭环。

**前提**: Stage 5 已完成，且结果可用于闭环（PASS / WARN / ENVIRONMENT-SKIP）

**Progress hooks**：
- Stage 开始：`S6 StageStarted`
- lessons 增量生成后：`S6 StageCheckpoint`
- 闭环总结后：`S6 StageCompleted`

1. 回顾本次 `/develop` 会话写入 `lessons.md` 的内容（只读取本次会话新增的记录）。
2. 判断问题是否会重复出现。
3. 对可复用问题提炼 `ALWAYS` 或 `NEVER` 规则，写入 `.claude/rules/constraints.md`。
4. 为规则标注来源命令和日期。
5. 当工作流文件成为正式交付物后，删除临时 `workflow-spec.md`，但保留 `clarification-record.json`、`open-questions.json`、`assumption-log.md`、`design-readiness-report.json`、`clarification-challenge-report.json`、`clarification-handoff.json`、`clarification-evidence.json` 作为 S1 结构化证据。

**关于 Lessons 机制**:

- `lessons.md` 是**追加式日志**，用于记录失败经验和待提取的约束
- 每次新会话**不加载** `lessons.md` 的完整历史（避免上下文膨胀）
- 只读取本次会话新增的记录，或最新3条记录
- 长期约束沉淀到 `constraints.md`，新会话自动加载
- 使用 `/iterate-workflow` 定期将 `lessons.md` 中的约束批量提取到 `constraints.md`

**流程闭环说明**:

```
Stage 5 (运行时验证)
       │
       ├── PASS ──→ Stage 6 ──→ 完成
       │
       ├── FAIL (设计缺陷) ──→ Stage 3 (重新设计，需用户批准)
       │
       └── FAIL (实现缺陷) ──→ Stage 4 (重新生成)
              │
              └── 修复后 ──→ Stage 5 (重新验证)

最大循环: 10轮或问题收敛为0
```

**Verify**: 可复用经验已经沉淀为规则，临时草稿已清理。

**On failure**：保留临时文件并向用户解释原因。

## Final Output

输出以下内容：

- 工作流名称与触发命令
- 创建或修改的文件
- 使用的模式组合
- 新增的约束
- 下一步建议

Target：`$ARGUMENTS`
