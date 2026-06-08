---
name: workflowprogram-develop
description: Design or update Claude Code workflow assets for the current target project
version: 1.0.0
disable-model-invocation: true
---

面向 `TARGET_ROOT` 的工作流设计主入口。目标是在目标项目中设计或更新 `.claude/` 工作流资产，而不是修改插件源码仓。

普通用户请求应优先从 `/workflowprogram-cn:workflowprogram-orchestrate <需求>` 进入；本 skill 是 orchestrate 选择 `develop` intent 后的 leaf 入口，也可用于高级显式调试。

## Native Default Entry

D1 clarification semantics are owned by `workflowprogram-native-cn:requirement-clarification-lead`
and `${CLAUDE_PLUGIN_ROOT}/skills/workflow-spec-support/logic-lenses.md`.
This skill only relays JS-returned questions and reinvokes the product JS with
answers; it must not emulate that Agent through foreground prompt role-play.

默认路径是解析插件绝对路径后调用：

```text
Workflow({
  scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-develop.js",
  args: { ... }
})
```

### First Invocation Defaults

The user should not need to provide these fields manually. Before the first
`Workflow({ scriptPath, args })` call, the foreground assistant must derive a
structured nested `args` object from context:

- `request`: original user request text after removing the skill trigger.
- `targetRoot`: current working directory absolute path unless the user explicitly names another target.
- `runId`: create a stable new id such as `develop-YYYYMMDD-HHMMSS`, unless reinvoking an existing run.
- `runRoot`: `<targetRoot>/.workflowprogram/runs/<runId>`.
- `operation`: infer `migrate` for existing-workflow migration or refactor requests, `update` for updating an existing Native Workflow JS, otherwise `create`.
- `clarification`: pass a nested object. For `migrate`, it may start empty because `workflowprogram-develop.js` seeds migration lens defaults.
- `applyApproved`: default `false` unless the user explicitly approves managed apply.

Call the product JS on the first invocation with structured nested args:

```text
Workflow({
  scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-develop.js",
  args: {
    runId: "<RUN_ID>",
    request: "<original user request>",
    targetRoot: "<TARGET_ROOT>",
    runRoot: "<TARGET_ROOT>/.workflowprogram/runs/<RUN_ID>",
    operation: "create | update | migrate",
    clarification: { lenses: {}, openQuestions: [], confirmedByUser: false },
    migrationDecisions: {},
    applyApproved: false
  }
})
```

Do not call Workflow with only `scriptPath`, and do not ask the user for
`request`, `targetRoot`, `runRoot`, or `runId` when those values can be derived
from the current Claude Code session and request text.

前台模型负责先推导 `request`、`targetRoot`、`runRoot`、`runId`，只有不可推导时才向用户收集；随后收集澄清答案，转述 JS 返回的问题或确认请求，并按 `nextAction` 调用窄化 adapter 后重新调用同一 JS。候选 hash 和外部报告通过 `<PLUGIN_ROOT>/scripts/build-native-develop-evidence.py` 规范化。不得由 skill 或前台模型重新实现 JS 中的阶段顺序。

下面的 S1-S6 与 legacy runtime 说明仅作为已有目标的兼容参考；新建目标默认使用 Native JS 控制面。

## When To Use

- 为当前项目创建新的 Claude Code workflow
- 为现有项目补齐 `.claude/` 结构
- 重构已有 workflow 的技能、agents、rules 或 settings

## Core Rules

- 读取模板、规则和参考资产时，应从 `PLUGIN_ROOT` 读取。
- 不应直接把新文件静默写回 `TARGET_ROOT/.claude/`；应先生成候选产物，再通过 `${CLAUDE_PLUGIN_ROOT}/scripts/managed-assets.py` 决定是否应用。
- 若 `TARGET_ROOT` 已存在 `.claude/`，优先复用并增量修改。
- 必要时使用 `${CLAUDE_PLUGIN_ROOT}/skills/workflow-spec-support/spec-template.md` 作为规格模板来源。
- 不要把仓库维护命令包装进目标项目 workflow 设计。
- 若出现目标文件冲突，应把候选版本保留在 `RUN_ROOT/outputs/`，而不是覆盖用户资产。
- 对已应用文件，应维护 `TARGET_ROOT/.workflowprogram/managed-files.json`。
- 执行过程中必须由 runner / control-plane helper 在内部调用 `${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py` 写入进展与关键节点结果；不要把严格 CLI 参数组装交给模型。
- `workflow-spec.md` 草案在进入 YAML 设计前必须通过 `${CLAUDE_PLUGIN_ROOT}/scripts/validate-workflow-draft.py` 的确定性质量门槛，并产出 `clarification-record.json`、`open-questions.json`、`target-question-backlog.json`、`target-requirement-logic-map.json`、`assumption-log.md`、`design-readiness-report.json`、`clarification-challenge-report.json`、`clarification-handoff.json`、`clarification-evidence.json`。
- S1 必须通过多轮用户对话澄清“用户诉求、最终目的、成功标准”，并用七个 logic lenses（purpose、object_model、process_model、decision_model、evidence_model、acceptance_model、boundary_model）持续追问；若目的、对象、过程、决策、证据、验收或边界仍不足以影响 S2/S3 设计，不得提前结束需求阶段。
- S1 的问题必须是 design-consequential：不同答案应能改变目标节点、分支决策、证据要求、验收场景或停止边界；“还有什么边界场景/输入输出/约束”这类泛问题不能单独支撑 L/XL 复杂度进入设计。
- S1 必须把原始用户请求拆成 `REQ-*` 需求索引，并写入 `RUN_ROOT/outputs/stages/target-requirements.yaml`；每条需求必须保留来源、优先级、验收口径和边界。
- S1 必须把 `REQ-*` 映射到 `target-requirement-logic-map.json` 中的 process/evidence/acceptance refs；M+ 请求不得缺少这些链接。
- S2 必须把上下文研究结构化为 `RUN_ROOT/outputs/stages/target-context-findings.yaml`，并把可复用资产、能力候选、风险、约束候选回溯到 `REQ-*`。
- S3 必须先产出 `target-design-overview.md`、`target-design-detail.md`、`target-acceptance-tests.yaml`、`target-traceability-matrix.json` 和 `target-implementation-plan.md`，再把可执行语义投影成 `workflow-spec.yaml`。
- S3 完成后、S4 候选资产或 managed 写入前，必须生成 `outputs/stages/design-review/design-review-packet.json`，调用内部 `workflow-design-reviewer` 做隔离上下文审视，并产出 `issues.json`、`closure.json`、`gate-validation.json`；只有 `gate-validation.json.status=PASS` 才能进入实现。
- 若某个目标业务节点需要跨模块推理、专业工具、独立 agent/team、loop、逆向/安全等高风险领域能力，或会影响多个下游节点，必须按 `${CLAUDE_PLUGIN_ROOT}/skills/workflow-spec-support/target-node-design-template.md` 生成 `RUN_ROOT/outputs/stages/target-node-designs/<node-id>.md`；简单整理节点不得强制拆独立 agent。
- 每个 `design_refs.node_designs` 文件必须能通过 `${CLAUDE_PLUGIN_ROOT}/scripts/validate-target-node-design.py --spec <RUN_ROOT>/workflow-spec.yaml --node-design <path> --node-id <node-id>`，证明 node id、owner、template、gate、input_refs、output_refs、loop_policy、失败策略和验证证据与 `workflow_graph.nodes[*]` 一致。
- `workflow-spec.yaml` 是机器控制面投影，不是完整设计文档；完整设计推理留在 S3 设计源，YAML 只通过可选 `design_refs` 引用这些文件路径。
- `workflow-spec.yaml` 产出后必须调用 `${CLAUDE_PLUGIN_ROOT}/scripts/validate-workflow-spec.py` 进行结构校验。
- `workflow-spec.yaml` 必须包含 `intent_flows`，明确 `develop / audit / iterate / validate` 的逻辑阶段流。
- `workflow-spec.yaml` 必须包含 `runtime_contract`，且至少声明：`write_boundaries`、`required_evidence`、`failure_kinds`、`environment_skip`。
- `workflow-spec.yaml` 必须包含 `test_contract`，且至少声明：`entry`、`boundary`、`flow`、`artifacts`、`failure`。
- `workflow-spec.yaml` 必须包含 `generated_runtime_contract`，且 `mode` 当前固定为 `shared-control-plane-wrapper`。
- 若目标工作流需要请求特定业务节点图，则 `workflow-spec.yaml` 必须声明 `workflow_graph`；它描述目标工作流自身节点，不要求套用 WorkflowProgram 的 `S1..S6`。
- 新生成的目标工作流必须声明 `target_runtime_policy.mode=managed_runtime`，并将 `generated_runtime_contract.runtime_capabilities` 同步包含 `target_managed_runtime`；目标命令必须是 wrapper-only，只启动 `.workflowprogram/runtime/workflow-entry.py`，不得把完整 stage 执行逻辑写进 command prompt。
- 新生成的目标工作流必须声明 `target_executor_policy`；不得假设本机 `claude -p` 可作为节点 executor。ClaudeCode 当前会话、第三方 API 模型或人工协作场景默认使用 `current_agent` / `manual` provider，并要求每个 node 写入 `outputs/stages/executor-evidence/<node-id>.json`，记录输入、输出、operator、时间戳和 output sha256。
- 目标 runtime 的受控执行由 `target-workflow-runner.py` 消费 `workflow_graph.nodes[*]`，负责 owner 解析、input/output refs、retry/stop、immutable 路径和 artifact provenance；目标业务节点输出应写到 domain output 路径，不得在运行态生成或修改 `.claude/**`、`.workflowprogram/design/**`、`.workflowprogram/runtime/**` 或 `config/scripts/**`。
- 若 `target_executor_policy` 选中的 provider 不是自动可执行节点的 provider，`target-workflow-runner.py` 不得直接给出 `PASS`；只能在 evidence 完整时进入 `BLOCKED` 并交由 `target-runtime-finalizer.py` 复核后提升为 `PASS`。
- 新生成的目标工作流若产出最终报告、manifest、latest marker 或长期复用输出，必须声明 `target_publish_policy.enabled=true`，并将 `generated_runtime_contract.runtime_capabilities` 同步包含 `target_atomic_publish`；节点只能先写 `RUN_ROOT` 下的 run-scoped outputs，最终发布由 `target-runtime-finalizer.py` 统一校验 `target-state.json`、`node-results.json`、`artifact-provenance.json` 和 required reports 后原子写入 `publish_root`。
- Managed runtime prompt assets rule: every generated node owner prompt (agent/skill) that mentions `workflow_graph.nodes[*].output_refs` MUST state that those refs are written under the active run root / `WORKFLOWPROGRAM_OUTPUT_ROOT`, not directly under `TARGET_ROOT`; owner prompts MUST NOT reference or write finalizer-owned `target_publish_policy.manifest_path` or `target_publish_policy.latest_marker`.
- 业务节点、报告脚本、doctor 或 manifest 生成脚本不得自行声明最终 `PASS/COMPLETE`；只要 finalizer 的 required report、contract、provenance 或 latest marker 校验失败，目标运行最终状态必须为 `FAIL/implementation`，不得复用旧产物补齐。
- 对 `target_publish_policy.enabled=true` 的工作流，还必须通过 `validate-target-publish-state.py` 验证 final manifest/latest marker/run root/state/provenance 一致；任何手写 `COMPLETE`、旧 latest marker 或绕过 finalizer 的发布结果都不能作为可信结果。
- `target_publish_policy.required_reports` 不得包含 finalizer 自己生成的 `manifest_path` 或 `latest_marker`；required reports 只能是 finalizer 发布前当前 run root 中已经存在的 gate/doctor/contract 报告。
- `workflow_graph.nodes[*].input_refs/output_refs` 不得读取或写入 finalizer-owned `manifest_path` / `latest_marker`；这些文件只能由 finalizer 发布后写入并由 `validate-target-publish-state.py` 复核。
- node 是流程单位，agent 是执行角色；只有专业知识、上下文窗口、失败归因、并行审查或工具权限形成独立边界时，才为 node 指派独立 agent。
- 若某个目标业务节点需要持续执行直到 verifier/test 通过，应在该 `workflow_graph.nodes[*].loop_policy` 中声明 Ralph-style loop；适用场景包括逆向分析、迁移修复、报告收敛和 TDD 实现，不适用于宿主安装或人工审批。
- 若 `RUN_ROOT/outputs/stages/change-context.json.change_policy_required=true`，必须先读取既有设计与 managed 状态，生成 `existing-workflow-readback.json`、`change-policy.json` 和 `impact-analysis.json`，再生成候选资产；这些文件是本次修改的运行证据，不得写成 `workflow-spec.yaml` 顶层字段。
- change policy 的确定性写入门禁由 `workflow-entry.py` 在 managed apply 前执行；模型不得用口头说明或自行生成的“审批文件”替代 `--auto-approve` / `--approval-status approved` / 可信审批记录。
- 若 `loop_policy.goal_source=model_subgoal`，必须声明 `parent_goal_ref`；若启用 TDD，必须声明 test-first 证据要求，并同步扩展 `generated_runtime_contract.runtime_capabilities` 包含 `node_loop_execution`。
- 若 workflow 需要先发现候选专业能力，则 `workflow-spec.yaml` 还必须声明 `capability_discovery`，并同步扩展 `generated_runtime_contract.runtime_capabilities`。
- 若 workflow 依赖宿主专业能力或显式 team，则 `workflow-spec.yaml` 还必须声明 `host_capabilities`、`agent_team_contract`，并同步扩展 `generated_runtime_contract.runtime_capabilities`。
- 若 `host_capabilities.bootstrap.scope=project_local`，优先用声明式 `bootstrap.assets` 生成复用配置 / wrapper / marker 资产，而不是只留下占位输出。
- 若声明 `host_capabilities`，产品入口与目标侧 runtime 都必须在 probe/bootstrap 后生成 `environment-remediation-report.json` 与 `environment-remediation-guide.md`；若重复环境失败存在，则 S6 必须把修复建议提升到 `s6-lessons-delta.md`。
- develop 成功后，必须把 `workflow-spec.yaml`、`workflow-view.md`、`workflow-maintenance.md` 持久化到 `TARGET_ROOT/.workflowprogram/design/`。
- develop 成功后，还必须把目标侧 runtime 资产持久化到 `TARGET_ROOT/.workflowprogram/runtime/`。
- `workflow-maintenance.md` 仅用于维护与迭代指导，不得覆盖 `workflow-spec.yaml` 语义。
- `test_contract` 对执行字段必须使用 `runtime_contract.<field>` 固定引用语法，且不得复制 `runtime_contract` 同名字段。
- `test_contract.failure.implemented_now` 必须是 `runtime_contract.failure_kinds` 的子集，且不得反向改变 runner 的 verdict/failure_kind 语义。
- 生成链路完成后必须调用 `${CLAUDE_PLUGIN_ROOT}/scripts/workflow-runner.py` 进行程序化 stage 转移和状态落盘；runner 只负责控制面，不负责 S5 主判定。
- develop 主链的确定性脚本入口是 `${CLAUDE_PLUGIN_ROOT}/scripts/workflow-entry.py run`；它负责串起 spec 校验、视图生成、managed apply、runner 与 run-state 校验。
- S5 主判定必须由 `workflowprogram-validate` 承担，`runtime_smoke.py` 仅作为动态 harness 补证据。
- S5 必须检查 `REQ -> design node -> asset -> acceptance test -> evidence` 的需求血缘；缺设计节点、缺验收测试、缺证据映射、node-design 未投影到 YAML 或 node-design 内容未通过验证时，不得给出 clean PASS。
- `RUN_ROOT/state.json` 必须通过 `${CLAUDE_PLUGIN_ROOT}/scripts/validate-run-state.py`，确保 `kind/producer/status` 枚举合规。
- S5 必须检查 design-review gate 证据；缺 packet、缺 closure、存在 open blocking issue、stale fingerprint 或 managed apply 发生在 gate 未通过时，不得给出 clean PASS。

## Step 1: Resolve Target

1. 确认 `TARGET_ROOT`。
2. 检查 `TARGET_ROOT/.claude/` 是否已经存在。
3. 读取或生成 `RUN_ROOT/outputs/stages/route-intent.json` 与 `RUN_ROOT/outputs/stages/change-context.json`。
4. 若 `change_policy_required=true`，读取旧设计与 managed manifest，写入 `RUN_ROOT/outputs/stages/existing-workflow-readback.json`。
5. 识别用户需求中的触发方式、输入、输出、角色与质量门禁。
6. 写入进展事件：`S1 StageStarted`。

## Step 2: Produce Workflow Spec

1. 用统一规格模板整理需求。
2. 若本轮是修改既有工作流，先生成 `RUN_ROOT/outputs/stages/change-policy.json` 与 `RUN_ROOT/outputs/stages/impact-analysis.json`；`affected_artifacts` 描述语义改动，`allowed_derived_artifacts` 描述 view/lowlevel/runtime 等派生产物。
3. 每轮只提出当前最关键的 1-3 个未决问题，并根据用户回答继续追问，直到诉求、目的、成功标准和七个 logic lenses 清楚为止。
4. 提问顺序默认为 purpose -> object_model -> process_model -> decision_model -> evidence_model -> acceptance_model -> boundary_model；简单请求可压缩，但 M+ 请求必须留下完整 lens 状态。
5. 优先问会改变设计的问题，例如：“DFD 不完整时是标记 unknown、阻塞，还是要求用户补充？”、“每个威胁需要哪些代码证据和测试方法才能 PASS？”、“哪些目标节点需要独立 agent 或 loop？”。
6. 在 `workflow-spec.md` 中显式整理 `User Intent`、`Clarification Summary`、`Requirement Logic Interview`、`Open Questions`、`Assumptions and Boundaries`、`Target Workflow Graph Readback`、`File Plan`、`Readback Confirmation`。
7. 派生 `RUN_ROOT/outputs/stages/target-requirements.yaml`，把原始请求拆为 `REQ-*`，并记录 `source_ref`、`priority`、`acceptance_hint`、`boundaries`。
8. 调用 `${CLAUDE_PLUGIN_ROOT}/scripts/generate-clarification-package.py`，生成 S1 结构化澄清包、`target-question-backlog.json` 和 `target-requirement-logic-map.json`。
9. 调用 `${CLAUDE_PLUGIN_ROOT}/scripts/generate-clarification-review.py`，生成 challenge/handoff/evidence 三份审阅产物；handoff 必须携带 `logic_map_path`、`question_backlog_path`、S2 logic lens inputs、S3 node candidates 与 acceptance scenarios。
10. 约束：`requirement-clarification-lead` 是唯一与用户直接对话的角色；`scenario-extractor`、`assumption-auditor`、`constraint-reviewer` 只能在内部 challenge 中提出补问与 handoff 建议，不得直接触达用户。
11. 形成工作流规格、模式选择和文件清单，并让 `S2/S3` 显式消费 `clarification-handoff.json`、`target-requirements.yaml`、`target-question-backlog.json` 与 `target-requirement-logic-map.json`。
12. 写入进展事件：`S1 StageCheckpoint` 与 `S1 StageCompleted`。

## Step 3: Design Assets

先形成设计源和机器投影，再在 `RUN_ROOT/outputs/candidate/` 规划或生成候选资产：

- `outputs/stages/target-design-overview.md`
- `outputs/stages/target-design-detail.md`
- 条件性 `outputs/stages/target-node-designs/<node-id>.md`，复杂/loop/工具重节点必须按 target node design template 填写并通过验证
- `outputs/stages/target-acceptance-tests.yaml`
- `outputs/stages/target-traceability-matrix.json`
- `outputs/stages/target-implementation-plan.md`
- `workflow-spec.yaml`，其中可选 `design_refs` 只引用上述文件路径
- `outputs/stages/design-review/design-review-packet.json`
- `outputs/stages/design-review/issues.json`
- `outputs/stages/design-review/closure.json`
- `outputs/stages/design-review/gate-validation.json`

- `settings.json`
- `skills/`
- `agents/`
- `rules/`
- 必要时的 `commands/` 兼容层
- `.workflowprogram/design/{workflow-spec.yaml,workflow-view.md,workflow-maintenance.md}`
- `.workflowprogram/runtime/{workflow-entry.py,workflow-runner.py,validate-run-state.py,runtime-manifest.json}`

进入 S4 实现与写入链路时，使用以下流程：

1. 在真正生成或应用候选资产前，先调用 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/generate-design-review-packet.py --run-root <RUN_ROOT> --target-root <TARGET_ROOT> --request "<原始需求>"`。
2. 调用内部 `workflow-design-reviewer` 审视 packet；若发现 blocking issue，先回到 S3 修复设计源、traceability 或 `workflow-spec.yaml`，再重新生成 packet 与审视结果。
3. 写入 `outputs/stages/design-review/closure.json` 后，调用 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/validate-design-review-gate.py --run-root <RUN_ROOT>`；未 PASS 不得进入候选资产生成或 managed apply。
4. 调用 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflow-entry.py run --spec <RUN_ROOT>/workflow-spec.yaml --run-root <RUN_ROOT> --target-root <TARGET_ROOT> --entry-skill workflowprogram-develop --request "<原始需求>" --route-evidence <RUN_ROOT>/outputs/stages/route-intent.json --change-context <RUN_ROOT>/outputs/stages/change-context.json [--auto-approve|--approval-status approved]`
5. `workflow-entry.py` 必须按固定顺序调用：
   - `resolve-change-context.py`（复核目标状态与 stale context）
   - `validate-workflow-spec.py`
   - `generate-workflow-view.py`
   - `generate-workflow-maintenance.py`
   - `validate-change-policy.py`（仅当 `change_policy_required=true`，且必须发生在 managed apply 前）
   - `validate-design-review-gate.py`（必须发生在 candidate/runtime staging 与 managed apply 前）
   - `generate-target-runtime.py`
   - `managed-assets.py plan`
   - `managed-assets.py apply-staged`
   - `discover-host-capabilities.py`
   - `probe-host-capabilities.py`
   - `apply-host-bootstrap.py`（仅 `project_local + approval_required=false`）
   - `generate-environment-remediation.py`
   - `workflow-runner.py run`
   - `validate-run-state.py`
6. 若 `managed-assets.py apply-staged` 报冲突，停止在 S4，保留 candidate 与 conflict 副本，不静默覆盖目标项目
7. 交由 `workflowprogram-validate` 形成 S5 主判定，并在可用时运行 `runtime_smoke.py` 补充动态证据；S5 必须检查 traceability、node-design 内容与投影一致性、design-review gate 证据
8. 读取 `RUN_ROOT/outputs/stages/entry-orchestration-summary.json` 作为产品入口编排摘要
9. 写入进展事件：`S4 StageStarted`、`S4 StageCheckpoint`、`S4 StageCompleted`

## Step 4: Verify Readiness

1. 检查命名是否一致。
2. 检查新增资产是否可被后续 `workflowprogram-validate` 验证。
3. 检查 `managed-files.json` 与本次应用结果是否一致。
4. 检查 `s5-validation-summary.json`、`validation-runtime-report.md` 与 `transcript.md` 的边界是否清晰。
5. 输出建议的下一步动作。
6. 更新 `RUN_ROOT/outputs/progress/user-progress.md`，向用户展示当前进展和历史关键节点结果。

## Output

输出应包含：

- 目标项目路径
- 设计摘要
- 需求血缘摘要：`REQ-* -> design node -> asset -> acceptance test -> evidence`
- 计划新增或修改的 workflow 资产
- managed asset 计划或冲突摘要
- 当前阶段进展与关键节点历史结果摘要
- 建议执行的后续验证步骤
