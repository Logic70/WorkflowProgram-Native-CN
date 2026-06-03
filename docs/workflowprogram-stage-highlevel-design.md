# WorkflowProgram Stage High-Level 设计

## 1. 目的与范围

本文档定义 WorkflowProgram 在目标项目中的高层运行逻辑，覆盖：

- 用户界面使用流程（自然语言与 slash）
- 按 Stage 划分的运行逻辑
- 输入、最终输出与项目结构
- 质量要求

本文基于当前实现（`workflowprogram-orchestrate` 主入口、`workflowprogram-*` leaf skills、兼容 `/develop`、`managed-assets.py`、`RUN_ROOT` 证据模型）编写。
若与历史文档冲突，以本文和本次讨论形成的新方案为准。

## 2. 设计基线与冲突收敛

### 2.1 基线

- 入口能力由 `workflowprogram-*` skills 承载。
- 自然语言自动触发策略仅开放 `workflowprogram-orchestrate`，并通过 `route-intent.py` 提供确定性路由（strict 模式可硬阻断歧义）。
- 主产品入口的确定性脚本链为 `workflow-entry.py -> (validate spec/view/lowlevel/target-runtime, managed-assets, probe/apply bootstrap) -> workflow-runner.py -> validate-run-state.py`；叶子 skill 不应只靠提示词顺序隐式串联这些脚本。
- 生成后的目标工作流也必须交付自己的 `.workflowprogram/runtime/` 控制面包装层；当前固定模式为 `shared-control-plane-wrapper`，但目标业务图执行必须由 `target_runtime_policy.mode=managed_runtime` 下的 `target-workflow-runner.py` 消费 `workflow_graph.nodes`，不得只靠 command prompt 口头顺序。
- 目标业务图 executor 必须由 `target_executor_policy` 声明；不得硬编码或默认假设 `claude -p` 可用。ClaudeCode 当前会话、第三方 API 模型或人工协作只能走 `current_agent` / `manual` 证据模式，由 finalizer 复核后才能 PASS。
- 生成后的目标工作流若有最终报告、manifest、latest marker 或长期复用输出，还必须交付 `target_publish_policy` 和 `target-runtime-finalizer.py` 事务层；节点输出先进入 run-scoped workspace，最终 `PASS/COMPLETE` 只能由 finalizer 在校验当前 run 证据后原子发布。`target_publish_policy.required_reports` 与 `workflow_graph` 节点 refs 不得引用 finalizer 自己生成的 manifest/latest marker，`validate-target-publish-state.py` 负责验证最终目录没有被模型或业务脚本在 runtime 失败后手写伪造成 `COMPLETE`。
- 已实现能力：新生成的 managed runtime 目标工作流会维护目标项目 `CLAUDE.md` 中的 WorkflowProgram runtime guard block。该 block 只作为提示层防绕过约束，提醒模型服从 `run/status/resume/diagnose`、`current_agent/manual` evidence 和 finalizer-only publish；可信边界仍由 runner/finalizer/validator/doctor 执行。
- 目标项目写入采用 staged candidate + managed apply 流程。
- 运行证据统一写入 `TARGET_ROOT/.workflowprogram/runs/<run-id>/`。
- 若工作流启用 `capability_discovery`，则在 `host_capabilities` 最终定稿前，必须先生成候选能力推荐与结构化人工指引。
- 若工作流依赖宿主专业能力或显式 agent team，则必须分别通过 `host_capabilities` 与 `agent_team_contract` 在 `workflow-spec.yaml` 中声明。
- 生成后的目标工作流若需要自己的业务节点图，必须在 `workflow-spec.yaml.workflow_graph` 中声明；目标工作流不强制套用 WorkflowProgram 自身的 `S1..S6` 模板。
- 若目标工作流的某个业务节点需要 Ralph-style 持续执行直到验证通过，必须在该 `workflow_graph.nodes[*].loop_policy` 中声明；它是目标节点策略，不替换 WorkflowProgram 自身 `S1..S6` 主链。
- 目标工作流设计采用“target design source -> target runtime map -> target derived views -> runtime evidence”分层：`target-design-overview.md` / `target-design-detail.md` 解释为什么这样设计，`workflow-spec.yaml` 只承载脚本、validator、runner、judge 需要执行和验证的最小机器契约；legacy `s3-design-highlevel.md` / `s3-design-lowlevel.md` 仅作为迁移兼容别名。

### 2.2 冲突收敛决策

- 决策 D1：优先使用现有 Claude Code 能力边界，不引入脱离现状的独立工作流引擎。
- 决策 D2：`workflow-spec.yaml` 作为流程控制面（control plane）与机器语义真源；完整设计推理、取舍与复杂节点方案必须留在 S3 设计源文件中，不反向塞进 YAML。
- 决策 D3：`state` 分为 `values` 与 `artifacts` 两类；文件内容落盘，`state` 仅追踪文件引用与状态。
- 决策 D4：skill/agent 负责节点执行，跨节点轮转由 spec 约束，不由单一大提示词临场决定。
- 决策 D5：所有目标项目写入必须经过 managed asset 链路，禁止静默覆盖。
- 决策 D6：Runner 采用“程序控制面 + AI 节点执行”分层；程序负责状态转移与约束检查，AI 负责节点语义工作。
- 决策 D7：`workflow-spec.yaml` 同时承载 `runtime_contract` 与 `test_contract`；前者定义执行期硬约束，后者定义基础运行测试的判定语义。
- 决策 D8：`test_contract` 只能通过 `runtime_contract.<field>` 引用执行约束，禁止复制或削弱 runner 已声明的执行语义。
- 决策 D9：逻辑阶段模型与执行阶段列表分离。`S0..S6` 用于统一描述职责与证据归属，具体执行链可由 `workflow-spec.yaml.stages` 承载；其中 `workflowprogram-validate` 负责 S5 判定，`runtime_smoke.py` 负责补充运行态证据，`learn` 负责 S6 闭环。
- 决策 D10：`workflow-spec.yaml.intent_flows` 作为“意图到逻辑阶段流”的机器可读真源；`test_contract.flow` 默认表达 `develop` 主链，其他意图流由 `intent_flows` 解释。
- 决策 D11：`workflow-spec.yaml.workflow_graph` 作为目标工作流业务图的机器可读真源；`workflow-view.md` 与 `workflow-maintenance.md` 只能从 YAML 派生展示，不得反向定义新的执行语义。
- 决策 D12：managed apply 必须同时产出 `managed-rollback-manifest.json` 与 `managed-recover-instructions.md`，用于覆盖 created / updated / conflicted / user-modified 文件的恢复边界。
- 决策 D13：面向用户或跨阶段消费的 JSON 报告必须带 `schema_version`、`error_code`、`failure_kind` 与 `remediation` 字段，并对 token/password/key-like 内容做脱敏。
- 决策 D14：原始需求必须沿 `target-requirements.yaml -> target-context-findings.yaml -> target design source -> workflow-spec.yaml projection -> S4 assets -> S5 evidence -> S6 lessons` 保留需求血缘，禁止在阶段切换中丢失来源。
- 决策 D15：复杂目标业务节点不拆成新的 WorkflowProgram `S1..S6`，而是升级为 `target-node-designs/<node-id>.md` 单节点设计契约，并由 `workflow_graph.nodes[*]`、可选 `loop_policy`、可选 agent/team 契约承接；node-design 内容必须通过确定性校验。
- 决策 D16：node 是流程单位，agent 是执行角色；二者不强制一一对应，只有复杂认知边界、专业能力边界或独立上下文边界才需要独立 agent。
- 决策 D17：简单工作流不得被强行重型化；`target-node-designs/**`、agent team、loop policy、host bootstrap 都是按复杂度和需求触发的条件性设计，不是所有工作流的默认负担。
- 决策 D21：completed develop 必须把 target design source 归档到 `TARGET_ROOT/.workflowprogram/design/source/**`，使后续修改、审计、validate 与 publish 不依赖旧 `RUN_ROOT`。
- 决策 D18：修改已有目标工作流不新增 `workflowprogram-change` 入口，而是在 `workflowprogram-develop` 内启用 controlled evolution；`change-policy.json`、`impact-analysis.json`、`existing-workflow-readback.json` 是单次运行证据，不是 `workflow-spec.yaml` 顶层字段。
- 决策 D19：change policy 的提示词规则是“候选资产生成前先分析”，确定性硬门禁是 `workflow-entry.py` 在 managed apply 前复核 `route-intent.json`、`change-context.json`、policy、impact、审批与 stale context。
- 决策 D20：S3 完成后必须经过内部 `workflow-design-reviewer` 的隔离上下文审视，并由 `validate-design-review-gate.py` 形成确定性写入门禁；设计审视产物属于本轮 run evidence，不写入 `workflow-spec.yaml` 顶层。
- 决策 D22：WorkflowProgram 自身代码提交与插件发布采用分层质量门禁；`quality-gate.py commit` 只做快速提交检查，`quality-gate.py integration` 覆盖 runtime/schema/publish 类改动，`quality-gate.py release` 保留构建、版本一致性、完整仓库校验、插件 bootstrap 与 smoke matrix。

## 3. 项目结构（高层）

```text
workflowprogram-native-cn/
├── .claude/                 # 源码真源（skills/agents/rules/scripts/settings）
├── .claude-plugin/          # 插件元数据
├── tools/                   # 构建、验证、smoke
├── dist/plugin/             # 仓库内 canonical 运行时载荷目录
├── docs/                    # 设计文档
└── tests/                   # fixtures 与验证证据

TARGET_ROOT/
├── .claude/                 # 最终交付工作流资产
└── .workflowprogram/
    ├── managed-files.json   # managed 文件清单
    ├── design/              # 目标工作流机器契约与派生视图
    ├── runtime/             # 目标侧 shared-control-plane-wrapper
    └── runs/<run-id>/       # 本次运行证据
```

### 3.1 安装与分发模型（可执行）

`dist/plugin/` 不是“源码目录的一个副本”，而是“仓库内唯一 canonical marketplace 运行时载荷目录”。
最终用户的主安装路径是 marketplace；源码构建仍可用于本仓库开发和调试。

| 通道 | 载荷来源 | 安装步骤 | 当前状态 |
|---|---|---|---|
| Marketplace / `/plugin install` | 平台安装器 + 本仓库 `dist/plugin/` 载荷 | 添加 marketplace -> 安装 `workflowprogram-native-cn@logic70-plugins` -> `SessionStart` 自动准备 plugin-local Python runtime | 主路径 |
| Source Build | 本仓库 `dist/plugin/` | `python3 tools/build_plugin.py`，仅供仓库开发/调试 | 辅助路径 |

### 3.2 GitHub 安装步骤（用户视角）

1. 在 Claude Code 中添加本仓库发布的 marketplace。
2. 安装 `workflowprogram-native-cn@logic70-plugins`。
3. 首次 `SessionStart` 自动把 `PyYAML` 安装到 `${CLAUDE_PLUGIN_DATA}/python/site-packages`。
4. 插件内所有 Python 控制面脚本统一通过 `workflowprogram-python` 访问这层 plugin-local `site-packages`。
5. 在目标项目目录直接启动 `claude`。
6. 在会话中执行 `/workflowprogram-native-cn:workflowprogram-orchestrate ...`。高级显式 intent 可使用对应 `workflowprogram-*` leaf 入口。

## 4. 用户界面使用流程

### 4.1 入口方式

- 自然语言入口：`workflowprogram-orchestrate`
- 显式主入口（slash）：`/workflowprogram-native-cn:workflowprogram-orchestrate <需求>`
- 高级显式 leaf：`workflowprogram-develop`、`workflowprogram-audit`、`workflowprogram-iterate`、`workflowprogram-validate`

### 4.2 使用过程

1. 用户在目标项目目录发起请求（自然语言或 slash）。
2. `workflowprogram-orchestrate` 识别意图：`develop | audit | iterate | validate`。
3. 系统解析 `TARGET_ROOT`，加载 `PLUGIN_ROOT` 资产。
4. 按意图进入对应 Stage 流程。
5. 产出目标项目资产与运行证据。

### 4.2A 意图到 Stage 流程

- `develop`: `S0 -> S1 -> S2 -> S3 -> S4 -> S5 -> S6`
- `audit`: `S0 -> S5(审计模式) -> S6`
- `iterate`: `S0 -> S6(提案模式) -> S5(可选)`
- `validate`: `S0 -> S5 -> S6(可选)`

### 4.3 输入与最终输出

输入（最小）：

- 用户需求文本
- 目标项目路径（隐式当前目录或显式路径）
- 可选约束（质量门禁、触发方式、是否自动审批）

最终输出（交付层）：

- `TARGET_ROOT/.claude/` 资产（`settings.json`、`skills/`、`agents/`、`rules/`、可选 `commands/`）
- `TARGET_ROOT/.workflowprogram/design/` 机器契约与派生视图（`workflow-spec.yaml`、`workflow-view.md`、`workflow-maintenance.md`）
- `TARGET_ROOT/.workflowprogram/runtime/` 目标侧 deterministic runtime 资产（`workflow-entry.py`、`workflow-runner.py`、`validate-run-state.py`、`runtime-manifest.json`）
- `TARGET_ROOT/.workflowprogram/managed-files.json`
- `RUN_ROOT` 证据（`context.json`、`state.json`、`events.jsonl`、`transcript.md`、`validation-runtime-report.md`、`outputs/`）
- 进展可视化资产（`outputs/progress/current-progress.json`、`outputs/progress/milestones.jsonl`、`outputs/progress/user-progress.md`）

## 5. Stage 运行逻辑（High-Level）

### S0 路由阶段（Route）

- 目标：确定意图与目标项目上下文。
- 入口：`workflowprogram-orchestrate`
- 输出：路由结果与 hand-off 上下文。
- 规范要求：
  - `target_root` 必须解析为绝对路径。
  - `S0` 准出前 `target_root` 必须已存在；若路径不存在，系统必须先创建目录并记录该结果。
  - 路由证据必须记录 `intent`、`entry_skill`、`target_root` 与“目录原本已存在/本阶段创建”的事实。
  - 路由阶段必须写入 `RUN_ROOT/outputs/stages/route-intent.json`。
  - 若目标目录已有 `.workflowprogram/design/workflow-spec.yaml`、`.workflowprogram/managed-files.json` 或 `.claude/**` workflow 资产，必须写入 `RUN_ROOT/outputs/stages/change-context.json`，其中包含 `target_state`、`request_kind`、`change_policy_required` 与关键文件 fingerprints。

### S1 需求澄清阶段（Explore Requirement）

- 目标：通过持续多轮对话把自然语言需求收敛为无歧义规格，明确用户诉求、最终目的与成功标准。
- 输出：
  - `workflow-spec.md`（人类可读规格草案）
  - `outputs/stages/s1-requirements.yaml`（`REQ-*` 需求索引、来源、优先级、成功标准、边界）
  - `clarification-record.json`
  - `open-questions.json`
  - `question-backlog.json`
  - `requirement-logic-map.json`
  - `assumption-log.md`
  - `design-readiness-report.json`
  - `clarification-challenge-report.json`
  - `clarification-handoff.json`
  - `clarification-evidence.json`
- 适用范围：仅适用于 `develop` 主链；`audit / iterate / validate` 不进入 S1，除非后续设计显式扩展。
- 规范要求：
  - S1 不得只做单轮问答后立即结束；只要仍存在会影响设计的歧义，就必须继续向用户追问。
  - `requirement-clarification-lead` 是唯一直接与用户对话的角色；challenge roles 只能在内部审阅草案、提出补问建议与 handoff 建议，不得直接对用户发问。
  - 每轮只聚焦当前最高优先级的 1-3 个 design-consequential 问题，直到“用户诉求 / 最终目的 / 成功标准 / 触发方式 / 输入输出 / 质量门禁 / logic lenses”全部明确。
  - S1 必须按七个 logic lenses 组织需求逻辑：`purpose`、`object_model`、`process_model`、`decision_model`、`evidence_model`、`acceptance_model`、`boundary_model`。
  - 问题必须能改变目标 workflow 节点、分支决策、证据要求、验收场景或停止边界；L/XL 请求不得只靠“还有什么边界场景/输入输出/约束”这类泛问题进入设计。
  - `workflow-spec.md` 必须包含 `User Intent`、`Clarification Summary`、`Requirement Logic Interview`、`Open Questions`、`Assumptions and Boundaries`、`Readback Confirmation`。
  - S1 必须把澄清结果派生为结构化澄清包与 challenge/handoff/evidence 产物，供 `S2/S3` 直接消费，而不是只依赖 prose draft。
  - `clarification-handoff.json` 必须携带 `logic_map_path`、`question_backlog_path`、S2 logic lens inputs、S3 node candidates 与 acceptance scenarios。
  - S1 必须把原始请求拆成可追踪 `REQ-*`，每条需求都要保留 `source_ref`、优先级、验收口径和边界；阻塞未决问题不得伪装成已确认需求。

### S2 领域研究阶段（Explore Context）

- 目标：识别目标项目可复用资产、缺口和命名约定。
- 输出：
  - `outputs/stages/s2-context-report.md`
  - `outputs/stages/s2-context-findings.yaml`（可复用资产、能力缺口、风险、外部依赖、约束候选）
- 规范要求：
  - S2 研究必须显式消费 `REQ-*` 与 `clarification-handoff.json`，不能只对目标仓库做泛泛扫描。
  - 若发现某条需求依赖 skill / MCP / CLI / licensed tool，应先形成 `capability_candidate`，再由 S3 决定是否投影为 `capability_discovery` 或 `host_capabilities`。

### S3 结构设计阶段（Design）

- 目标：把 S1 需求与 S2 上下文转化为可执行工作流设计、机器契约和验收映射。
- 输出：
  - `outputs/stages/target-design-overview.md`（目标工作流整体设计源）
  - `outputs/stages/target-design-detail.md`（节点、字段、证据、失败路径、能力依赖的设计源）
  - 条件性 `outputs/stages/target-node-designs/<node-id>.md`（复杂节点子设计）
  - `outputs/stages/target-implementation-plan.md`
  - `outputs/stages/target-acceptance-tests.yaml`
  - `outputs/stages/target-traceability-matrix.json`
  - `outputs/stages/design-review/design-review-packet.json`
  - `outputs/stages/design-review/issues.json`
  - `outputs/stages/design-review/closure.json`
  - `outputs/stages/design-review/gate-validation.json`
  - `workflow-spec.yaml`（机器可读控制面）
  - 可选 `design_refs`（内嵌于 `workflow-spec.yaml`，只引用设计源、验收与 traceability 文件路径，不承载完整设计推理）
  - `runtime_contract`（内嵌于 `workflow-spec.yaml`，定义写入边界、证据集、失败枚举、环境 skip）
  - `test_contract`（内嵌于 `workflow-spec.yaml`，定义入口/边界/流程/产物/失败五类基础测试判定）
  - `generated_runtime_contract`（内嵌于 `workflow-spec.yaml`，定义目标侧 runtime 包装层的交付路径与 `runtime_capabilities`）
  - 可选 `workflow_graph`（目标工作流自己的业务节点、入口、转移、输出、gate 与 owner；不要求套用 `S1..S6`）
  - 可选 `capability_discovery`（能力发现与推荐契约）
  - 可选 `host_capabilities`（宿主专业能力契约）
  - 可选 `agent_team_contract`（显式 team 拓扑契约）
  - 其中 `test_contract.flow` 默认表达 `develop` 主链；非 `develop` 流转由 `intent_flows` 约束
  - `workflow-view.md`（只读视图）
  - `workflow-maintenance.md`（维护与迭代指导；不得覆盖 YAML 语义）
- 规范要求：
  - S3 必须先产出设计源，再投影 `workflow-spec.yaml`；不得跳过设计源直接写 YAML。
  - `target-design-overview.md` 回答目标工作流为什么存在、整体怎么组织、用户怎么使用、如何验证。
  - `target-design-detail.md` 回答每个目标节点的输入输出、owner、gate、能力依赖、证据、失败路径和对应 YAML 字段。
  - 复杂节点满足任一条件时必须产出 target node design：跨模块阅读、多步推理、生成中间模型、需要专业工具/agent、需要 verifier/test 循环、输出影响多个后续节点。
  - agent 设计必须基于复杂认知边界，而不是按 node 机械一一拆分；简单格式化、归档、命名、状态更新应优先由 skill 或 script 承接。
  - `traceability-matrix.json` 必须记录 `REQ -> design node -> asset -> acceptance test -> evidence` 的最小覆盖链。
  - `develop` 主链必须在 S3 完成后先生成 `design-review-packet.json`，再由内部 `workflow-design-reviewer` 审视目标一致性、复杂度、上下文传递、YAML 投影、change policy 影响与运行时兼容性。
  - `design-review/closure.json.status=PASS` 且 `gate-validation.json.status=PASS` 是进入 S4 的硬门禁；存在 open blocking issue、stale fingerprint 或缺 closure 时不得生成或应用候选资产。
  - design review 的 accepted risk 必须记录 residual risk；它可允许 S4 继续，但 S5 必须把 accepted risk 作为 INFO 证据保留。
  - `develop` 主链必须在 S3 完成后经过审批 gate 与 design-review gate，方可进入 S4。
  - 审批记录必须区分 `approved`（人工批准）与 `auto-approved`（CI 或参数自动放行）。
  - `generated_runtime_contract.mode` 当前固定为 `shared-control-plane-wrapper`；目标工作流必须交付 wrapper，不得只交付提示词与设计文档。
  - 当声明 `capability_discovery.enabled=true` 时，`generated_runtime_contract.runtime_capabilities` 必须包含 `capability_discovery`。
  - `capability_discovery` 可按领域画像展开基线能力包；当前至少支持 `reverse_engineering`，并允许通过 `profile_overrides` 显式移除、替换 profile 默认能力。
  - 当声明 `host_capabilities` 时，`generated_runtime_contract.runtime_capabilities` 必须包含 `host_capability_probe`。
  - 当声明 `agent_team_contract.enabled=true` 时，`generated_runtime_contract.runtime_capabilities` 必须包含 `team_orchestration`。
  - 当任一 `workflow_graph.nodes[*].loop_policy.enabled=true` 时，`generated_runtime_contract.runtime_capabilities` 必须包含 `node_loop_execution`。
  - 新生成的目标工作流必须声明 `target_runtime_policy.mode=managed_runtime`，且 `generated_runtime_contract.runtime_capabilities` 必须包含 `target_managed_runtime`。
  - 新生成的目标工作流必须声明 `target_executor_policy`；若 provider 不可自动执行节点，runner 不得直接 PASS，只能在结构化 executor evidence 完整时进入 `BLOCKED`，由 finalizer 校验后提升为 `PASS`。
  - 新生成的目标工作流若声明 `target_publish_policy.enabled=true`，则 `generated_runtime_contract.runtime_capabilities` 必须包含 `target_atomic_publish`，并由 `target-runtime-finalizer.py` 统一发布最终产物。
  - 领域画像可选地推荐默认 `agent_team_contract`，但推荐值必须保持可编辑，且不得覆盖用户显式选择。
  - `workflow-spec.md` 是用户回读确认材料；完整设计推理落在 S3 设计源；真正进入脚本、validator、runner、judge 的执行语义必须投影到 `workflow-spec.yaml`。
  - 若存在 `workflow_graph`，S3 readback 必须列出 graph summary、目标资产清单、启用/关闭能力与 managed apply policy。

### S4 资产生成与受控写入阶段（Generate + Managed Apply）

- 目标：先生成候选，再受控应用到目标项目。
- 输出：
  - `RUN_ROOT/outputs/candidate/.claude/*`
  - `RUN_ROOT/outputs/candidate/.workflowprogram/design/*`
  - `RUN_ROOT/outputs/candidate/.workflowprogram/runtime/*`
  - 条件性 `RUN_ROOT/outputs/stages/change-policy.json`
  - 条件性 `RUN_ROOT/outputs/stages/impact-analysis.json`
  - 条件性 `RUN_ROOT/outputs/stages/validate-change-policy.json`
  - `managed-change-plan/result/summary`
  - `managed-rollback-manifest.json`
  - `managed-recover-instructions.md`
  - `TARGET_ROOT/.workflowprogram/managed-files.json`
  - 应用后的 `TARGET_ROOT/.claude/*`（无冲突场景）
  - 应用后的 `TARGET_ROOT/.workflowprogram/design/{workflow-spec.yaml,workflow-view.md,workflow-maintenance.md}`（无冲突场景）
  - 应用后的 `TARGET_ROOT/.workflowprogram/runtime/{workflow-entry.py,workflow-runner.py,validate-run-state.py,runtime-manifest.json}`（无冲突场景）
- 规范要求：
  - 若 `change-context.json.change_policy_required=true`，S4 不得进入 managed apply，直到 `validate-change-policy.py` 返回 PASS。
  - S4 不得进入 candidate staging 或 managed apply，直到 `validate-design-review-gate.py` 返回 PASS；该 gate 必须发生在 `stage_persistent_design_assets()`、`stage_target_runtime_assets()` 与 `managed-assets.py` 之前。
  - `workflow-entry.py` 必须在写入前重新解析 target state；如果 design spec、lowlevel 或 managed manifest fingerprint 变化，则以 `change_context_stale` 阻断。
  - policy 中的 `affected_artifacts` 表示语义修改范围；`allowed_derived_artifacts` 表示由 entry 自动派生的 view/lowlevel/runtime 输出。
  - 目标侧 runtime 继续采用 `shared-control-plane-wrapper`，通过 wrapper 调共享控制面，不复制独立引擎。
  - 若声明 `capability_discovery`，产品入口与目标侧 runtime 入口都必须先生成 `host-capability-candidates.json` 与 `host-bootstrap-instructions.md`，再进入 host probe / runner。
  - 若能力发现启用领域画像，则 `host-capability-candidates.json` 必须保留画像来源、被排除能力、被替换能力，以及是否推荐默认 team 拓扑。
  - 若声明 `host_capabilities`，产品入口与目标侧 runtime 入口都必须在 runner 前执行宿主探测；只允许自动执行 `project_local + approval_required=false` 的 bootstrap，`host_global/manual_only` 只生成 plan 与人工处理指引。
  - managed plan/result/rollback 等用户可分享报告必须带公共 schema 字段并脱敏 secret-like 内容。

### S5 验证阶段（Validate）

- 目标：形成 workflow 级统一校验结论与运行证据。
- 目标补充：基础运行测试必须覆盖 `entry / boundary / flow / artifacts / failure` 五类契约；执行期语义以 `runtime_contract` 为准，判定语义以 `test_contract` 为准。
- 主承载：`workflowprogram-validate`
- 辅助证据：`runtime_smoke.py`
- 输出：`PASS | WARN | FAIL | ENVIRONMENT-SKIP` 结论与证据链，至少包含 `validation-runtime-report.md` 与 `outputs/stages/s5-validation-summary.json`。
- 证据归属：
  - `context.json`、`state.json`、`events.jsonl` 属于运行态/控制面证据，由 runner 负责保留。
  - `validation-runtime-report.md` 与 `outputs/stages/s5-validation-summary.json` 属于 S5 判定产物。
  - `transcript.md` 属于动态运行证据，由 `runtime_smoke.py` 或等效 harness 补充，供 S5 消费。
  - S5 必须校验设计源、`workflow-spec.yaml`、生成资产与运行证据之间的覆盖关系；若某个 `REQ-*` 没有设计节点、验收测试或证据映射，不得判为 clean PASS。
  - 若存在 `target-node-designs/<node-id>.md`，S5 必须确认对应 `workflow_graph.nodes[*].id` 存在，且该节点的关键输入、输出、gate、owner、能力、loop policy、失败策略与验证证据已投影到 YAML 或 traceability，并通过 `validate-target-node-design.py`。
  - 若声明 `capability_discovery`，S5 必须消费 `host-capability-candidates.json` 与 `host-bootstrap-instructions.md`，并验证候选与人工指引都已生成。
  - 若声明 `host_capabilities`，S5 必须消费 `host-capability-report.json`，并在 `validate/audit` 场景对当前宿主执行实时 probe。
  - 若声明 `host_capabilities`，`validate/audit/iterate` 还必须产出 `environment-remediation-report.json` 与 `environment-remediation-guide.md`，把未解决的 manual step / bootstrap / re-check 指引显式写给用户。
  - 若声明 `agent_team_contract.enabled=true`，S5 必须消费 `team-plan.json`、`team-results.json`、`team-join-summary.json` 与对应事件证据；确定性 provider 缺结构化 team evidence 时不得判为 clean PASS。
  - 若声明 `workflow_graph.nodes[*].loop_policy.enabled=true`，S5 必须消费 `outputs/stages/loops/<node_id>/loop-plan.json`、`iteration-summary.jsonl`、`final-verdict.json` 与 loop events；确定性 provider 缺结构化 loop evidence 时必须失败，`claude_cli` 缺证据只能 WARN。

### S6 闭环阶段（Lessons & Constraints）

- 目标：将失败经验、冲突与可复用约束沉淀。
- 输出：`lessons.md` 增量、约束候选、下一轮改进建议。
- 规范要求：
  - 若环境失败包含宿主能力证据，`iterate` 必须把重复失败提升为 remediation proposal，而不是只重复 failure code。
  - 若 `environment-remediation-report.json` 指出重复 blocker，`s6-lessons-delta.md` 必须至少包含一个 remediation / bootstrap / re-check 类候选项。

### 5A. Stage 可验证验收矩阵

| Stage | 可验证准出条件 | 最小证据 |
|---|---|---|
| S0 | `intent` 属于 4 个枚举，`target_root` 为绝对路径且目录已存在（不存在时已创建） | `RUN_ROOT/outputs/stages/s0-route.json` |
| S1 | `workflow-spec.md` 存在、不含 `TBD/待补`，包含 `User Intent`、`Clarification Summary`、`Requirement Logic Interview`、`Open Questions`、`Assumptions and Boundaries`、`Readback Confirmation`；`澄清轮次 >= 2`；`target-requirements.yaml` 至少包含一条 `REQ-*`；M+ 草案必须有完整七个 logic lenses、`target-question-backlog.json`、`target-requirement-logic-map.json` 且 `REQ-*` 链接到 process/evidence/acceptance；`design-readiness-report.json=READY`；`clarification-handoff.json.ready=true`；challenge roles 未直接面向用户 | `RUN_ROOT/workflow-spec.md`、`RUN_ROOT/outputs/stages/target-requirements.yaml`、`RUN_ROOT/outputs/stages/target-question-backlog.json`、`RUN_ROOT/outputs/stages/target-requirement-logic-map.json`、`RUN_ROOT/outputs/stages/clarification-record.json`、`RUN_ROOT/outputs/stages/open-questions.json`、`RUN_ROOT/outputs/stages/assumption-log.md`、`RUN_ROOT/outputs/stages/design-readiness-report.json`、`RUN_ROOT/outputs/stages/clarification-challenge-report.json`、`RUN_ROOT/outputs/stages/clarification-handoff.json`、`RUN_ROOT/outputs/stages/clarification-evidence.json` |
| S2 | 上下文报告包含“可复用资产/缺口/命名建议”三段，结构化 findings 能回溯到 `REQ-*` | `RUN_ROOT/outputs/stages/s2-context-report.md`、`RUN_ROOT/outputs/stages/target-context-findings.yaml` |
| S3 | `target-design-overview.md`、`target-design-detail.md`、`target-acceptance-tests.yaml`、`target-traceability-matrix.json` 存在且覆盖 `REQ-*`；复杂节点已有 target node design 或明确豁免；`workflow-spec.yaml` 可解析且关键键存在；`workflow-view.md` 与 `workflow-maintenance.md` 已生成，且 `workflow-maintenance.md` 可由 `workflow-spec.yaml` 确定性重算；审批状态已记录且未绕过 gate；design-review gate 已闭合且 fingerprints 未过期 | `RUN_ROOT/outputs/stages/target-design-overview.md`、`RUN_ROOT/outputs/stages/target-design-detail.md`、条件性 `RUN_ROOT/outputs/stages/target-node-designs/`、`RUN_ROOT/outputs/stages/target-implementation-plan.md`、`RUN_ROOT/outputs/stages/target-acceptance-tests.yaml`、`RUN_ROOT/outputs/stages/target-traceability-matrix.json`、`RUN_ROOT/outputs/stages/design-review/design-review-packet.json`、`RUN_ROOT/outputs/stages/design-review/issues.json`、`RUN_ROOT/outputs/stages/design-review/closure.json`、`RUN_ROOT/outputs/stages/design-review/gate-validation.json`、`RUN_ROOT/workflow-spec.yaml`、`RUN_ROOT/workflow-view.md`、`RUN_ROOT/workflow-maintenance.md`、`outputs/stages/s3-design-summary.json` |
| S4 | candidate 目录存在；managed plan/result 存在；`TARGET_ROOT/.workflowprogram/managed-files.json` 已写入且带 `updated_at`；目标侧设计包与 `.workflowprogram/runtime/` 已持久化；冲突不覆盖目标文件 | `RUN_ROOT/outputs/candidate/.claude/`、`RUN_ROOT/outputs/candidate/.workflowprogram/design/`、`RUN_ROOT/outputs/candidate/.workflowprogram/runtime/`、`managed-change-plan/result`、`TARGET_ROOT/.workflowprogram/managed-files.json` |
| S5 | 产生 workflow 级结论，且证据链文件齐全；若声明能力发现、宿主能力或 team 契约，则对应 discovery / probe / team evidence 已纳入判定 | `validation-runtime-report.md`、`outputs/stages/s5-validation-summary.json`、条件性 `outputs/stages/host-capability-candidates.json`、`outputs/stages/host-bootstrap-instructions.md`、`outputs/stages/host-capability-report.json`、`outputs/stages/team-plan.json`、`outputs/stages/team-results.json`、`outputs/stages/team-join-summary.json` |
| S6 | 输出 lessons 增量与约束候选，关联本次 `run-id` 与 `failure_kind`，且 `user-progress.md` 含“历史关键节点结果” | `RUN_ROOT/outputs/stages/s6-lessons-delta.md` |

### 5B. 基础运行测试契约

为避免把测试规则散落在自由文本中，`workflow-spec.yaml` 必须显式声明：

- `runtime_contract`
  - 执行期硬约束：写入边界、最小证据集、失败类别枚举、环境 skip 条件
- `test_contract`
  - 基础运行测试判定：`entry / boundary / flow / artifacts / failure`
- `generated_runtime_contract`
  - 目标工作流 deterministic runtime 的机器契约；当前模式固定为 `shared-control-plane-wrapper`
- 可选 `target_runtime_policy`
  - 目标工作流业务图的受控执行策略；新生成工作流默认 `mode=managed_runtime`，要求 command wrapper-only、node lifecycle 事件、owner 解析、output contract、immutable path 和 artifact provenance 由代码校验
- 可选 `target_executor_policy`
  - 目标业务节点 executor provider 契约；声明 `fixture_host` / `command_adapter` 自动执行，或 `current_agent` / `manual` 结构化证据执行，禁止依赖 `claude -p` 超时路径
- 可选 `capability_discovery`
  - 目标能力发现与推荐契约，用于在 `host_capabilities` 最终定稿前生成候选 `skill / MCP / CLI` 清单
- 可选 `host_capabilities`
  - 宿主专业能力声明、probe 方式与 bootstrap 范围；若 `bootstrap.scope=project_local`，还可声明要生成的复用配置 / wrapper / bootstrap 资产
- 可选 `agent_team_contract`
  - opt-in team 拓扑、fan-out 限额、join policy 与运行证据要求
- 可选 `design_refs`
  - 只引用 S1/S2/S3 设计源、验收测试和 traceability 文件，帮助 S5 做一致性检查；不得把设计推理全文复制进 YAML

统一原则：

- S3 设计源回答“为什么这样设计”，`workflow-spec.yaml` 回答“机器怎么执行和验证”，S5 证据回答“实际有没有做到”。
- `runtime_contract` 决定 runner 可以做什么、必须保留什么、如何降级。
- `test_contract` 决定基础测试应检查什么、哪些结果算通过或失败。
- `generated_runtime_contract` 决定目标工作流是否真正交付了自己的 wrapper + control-plane 接口，而不只是提示词资产。
- `capability_discovery` 只负责候选能力推荐与结构化人工指引，不直接修改 `TARGET_ROOT` 交付物。
- `host_capabilities` 只描述宿主依赖，不改变 `TARGET_ROOT` 交付语义；对应 readiness / bootstrap 证据必须落在 `RUN_ROOT`。唯一允许进入 `TARGET_ROOT` 的宿主 bootstrap 资产，必须严格限制在 `TARGET_ROOT/.workflowprogram/bootstrap/**`。
- 只要存在 `required && status != ready`，最终 summary 必须 `FAIL`，且 `failure_kind = environment`。
- `agent_team_contract` 只在显式声明时生效；普通 subagent 并不自动等于 team orchestration。
- `workflow_graph.nodes[*].loop_policy` 只适合验证驱动的迭代节点，例如逆向分析、迁移修复、报告修订、测试驱动实现；不适合一次性问答、不可自动验证的主观写作、宿主环境安装或人工审批动作。
- `loop_policy.goal_source` 可以来自用户，也可以来自模型分解的子目标；模型子目标必须通过 `parent_goal_ref` 回溯到用户目标或上游节点输出，TDD 型 loop 必须先有 failing verifier/test 再进入实现。
- `node-design` 只在复杂节点需要时生成；它必须按 target node design template 覆盖目的/边界、输入、输出、上下文读写、调用关系、失败策略、验证与观测，并被投影到 `workflow_graph`、能力契约、team 契约、loop 契约或 traceability，不能成为孤立说明文档。
- `workflowprogram-validate` 是 `test_contract` 的主消费方，`runtime_smoke.py` 是补充烟测与证据采集工具。
- `test_contract` 对执行字段只允许引用，不允许复制同名内容。
- `test_contract.failure.implemented_now` 仅表达“当前实现覆盖度”，不得反向改变 runner 的 `verdict` 或 `failure_kind` 语义。

## 5C. 产品入口编排

- `workflowprogram-orchestrate` 负责意图路由，不负责替代控制面脚本链。
- `workflowprogram-develop` 的确定性脚本入口是 `${CLAUDE_PLUGIN_ROOT}/scripts/workflow-entry.py run`。
- `workflow-entry.py` 必须按固定顺序执行：
  - `validate-workflow-spec.py`
  - `generate-workflow-view.py`
  - `generate-workflow-maintenance.py`
  - `validate-design-review-gate.py`（在 S4 写入链路前复核 S3 设计审视闭合状态）
  - `generate-target-runtime.py`
  - `managed-assets.py plan/apply-staged`
  - `discover-host-capabilities.py`
  - `probe-host-capabilities.py`
  - `apply-host-bootstrap.py`（只自动执行 `project_local + approval_required=false`，`host_global/manual_only` 只记录 skipped 和处理指引）
  - `generate-environment-remediation.py`
  - `workflow-runner.py run`
  - `validate-run-state.py`
- 编排结果必须落盘到 `RUN_ROOT/outputs/stages/entry-orchestration-summary.json`。
- 目标工作流自己的 deterministic runtime 入口是 `TARGET_ROOT/.workflowprogram/runtime/workflow-entry.py`，并沿用 shared-control-plane-wrapper：`discover(optional) -> probe/apply-bootstrap -> environment-remediation -> target-workflow-runner -> validate-target-runtime-state -> target-runtime-finalizer(optional) -> validate-target-publish-state(optional)`。

## 5D. 目标工作流发布环节

- `workflowprogram-publish` 是独立生命周期，不属于 `develop` 的 S1-S6 阶段。
- 发布前必须确认目标 workflow 已完整经过 `workflowprogram-develop`，并具备当前有效的 design-review、managed apply、runtime state/events 与 S5 `PASS` 证据。
- 发布流程不得直接修改目标 workflow 的语义设计；若发现不可发布的设计或实现缺口，必须停止并要求回到 `workflowprogram-develop` 的 change-policy 修改流。
- 发布入口为 `/workflowprogram-native-cn:workflowprogram-publish`，对应 skill 为 `workflowprogram-publish`。
- 发布证据固定写入 `RUN_ROOT/outputs/stages/publish/`，包括 `publish-eligibility.json`、`plugin-package-plan.json`、`plugin-validation-report.json`、`github-publish-result.json`、`install-instructions.md` 与 `publish-summary.json`。
- 目标插件 runtime 打包模式必须显式选择：`workflowprogram_dependency` 或 `vendored_runtime`。当前稳妥默认是 `workflowprogram_dependency`，安装说明必须提示消费者先安装 WorkflowProgram。
- 发布仓库模式支持 `export_repo` / `current_repo` / `existing_marketplace`。其中 `existing_marketplace` 复用已有 `.claude-plugin/marketplace.json`，把插件 payload 规划到 `plugins/<plugin-id>/`，并以 merge plan 追加或显式更新同名条目。
- `existing_marketplace` 不得静默覆盖同名 plugin，不得改写已存在条目的 source；更新必须显式授权且版本提升。
- GitHub 发布使用用户自己的 `gh` / `git` 认证状态；WorkflowProgram 不保存 token。缺认证、缺权限或缺审批时，发布以 `BLOCKED/environment` 或 `BLOCKED/design` 停止。

基础运行测试的统一场景骨架至少包含：

- 标准成功场景
- 非法入口场景
- 边界/冲突场景
- 流程阻断场景
- 环境不足场景

每个具体工作流可在 `test_contract` 中进一步裁剪判定目标，但不得绕开上述五类契约。

## 6. Quality 要求

### 6.1 一致性要求

- 所有 Stage 必须声明输入、输出、准出目标和失败反馈路径。
- `workflow-spec.yaml` 字段命名、枚举和状态机转移必须一致。
- `design_refs`、`traceability-matrix.json` 与 `workflow_graph` 必须保持一致，防止设计源、机器投影和 S5 证据相互漂移。
- 文档中的 `TARGET_ROOT / RUN_ROOT / PLUGIN_ROOT` 含义必须统一。

### 6.2 可靠性要求

- 目标项目资产写入必须先 candidate 后 apply。
- unmanaged 或 drifted 文件不得静默覆盖。
- 每次执行必须产生可追踪证据，且可定位失败阶段。
- 每个 Stage 必须输出进展事件并可回溯关键节点结果。

### 6.3 可维护性要求

- 叶子 skill 只负责节点执行，不承担全流程调度职责。
- 规则与校验脚本必须与真实注册状态同步。
- 设计变更必须同步更新 high-level 与 low-level 文档。
- 改设计理由或复杂节点推理时，先改 S3 设计源；改执行语义时，必须投影到 `workflow-spec.yaml` 并重生成派生视图。
- 统一 runner 负责状态转移与 enum 约束落盘，避免仅靠自然语言约定驱动流程。
- develop 主链必须通过 `workflow-entry.py` 串起 spec/view/managed-assets/runner/state 校验，而不是由 skill 自由决定脚本顺序。

### 6.4 可验证性要求

- 结构校验：`validate-workflow.py/.ps1`
- 运行烟测：`runtime_smoke.py`
- 变更证据：`managed-change-*`、`events.jsonl`、`state.json`
- spec 契约校验：`validate-workflow-spec.py` 同时校验 `runtime_contract` 与 `test_contract`
- 判定边界：runner 只执行 `runtime_contract`；`test_contract` 由 validator、验证技能或外部 harness 消费

## 7. 与现有实现的关系

- 本设计不推翻现有 `workflowprogram-*` skill 体系。
- 本设计把 `workflow-spec.yaml` 定位为机器控制面投影，而不是完整设计文档；设计解释由 S3 设计源承载，执行仍通过现有 skill/agent/script 完成。
- 本设计不引入强依赖的新外部运行时；先以当前能力闭环，再渐进增强自动化调度。
- 当前 runner 已以脚本化控制面落地（`workflow-runner.py` + `validate-workflow-spec.py` + `validate-run-state.py`），并与 `managed-assets.py`、`stage-progress.py`、`generate-workflow-view.py` 组成闭环。
- 当前 develop 产品入口已通过 `workflow-entry.py` 收口为确定性脚本编排。
- 当前 S5 验证链路由 `workflowprogram-validate`、`runtime_smoke.py` 和 `s5-validation-summary.json` 构成，不由 runner 单独承担。
