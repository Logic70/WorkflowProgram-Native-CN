# WorkflowProgram Native CN

[中文](README.md) | [English](README.en.md)

面向 Claude Code 工作区的**元工作流引擎**。它不提供业务代码，而是帮你把 workflow 做成可交付、可验证、可迭代的产品。

## 它解决什么问题

大多数 Claude Code workflow 最初都是"一个 SKILL.md + 几个 agent + 手工改 settings.json"。这样做能跑，但很快会遇到：

- 文档和实际行为脱节，没有统一真源
- 步骤顺序靠模型记忆，容易跳步漏步
- 目标项目被直接覆盖，冲突无法恢复
- 失败后无法分层定位，也没有结构化证据
- 经验留在聊天记录里，下次还是从零开始

WorkflowProgram 用四层设计系统性地回应这些问题：**真源** / **控制面** / **验证层** / **闭环层**。

## 安装

**前置要求**：宿主机存在 `Python 3.10+` 的 `python3`。

主安装路径是 Claude Code marketplace：

```bash
claude plugin marketplace add Logic70/WorkflowProgram-Native-CN
claude plugin install workflowprogram-native-cn@logic70-plugins
```

如果你已经在 Claude Code 交互界面里，也可以执行：

```text
/plugin marketplace add Logic70/WorkflowProgram-Native-CN
/plugin install workflowprogram-native-cn@logic70-plugins
/reload-plugins
```

安装完成后：

1. 重新启动 `claude`，或在会话内执行 `/reload-plugins`
2. 首次启动会在 `${CLAUDE_PLUGIN_DATA}/python/site-packages` 自动准备插件私有 Python 依赖
3. 如需最小化排障，执行 `workflowprogram-doctor`
4. 如需清理插件 Python 缓存、测试产物或目标工作流旧 run，执行 `workflowprogram-clean`；默认只 dry-run，删除必须加 `--apply`

排障：

- 如果出现 `Unknown skill: workflowprogram-orchestrate`，通常是当前 Claude 会话还没重新加载插件。执行 `/reload-plugins` 或重启 `claude`，然后用 `/workflowprogram-native-cn:workflowprogram-orchestrate ...` 入口，不要让模型手写 `Skill(workflowprogram-orchestrate)`。
- 如果出现 `bin/workflowprogram-python: Permission denied`，说明安装缓存里的 launcher 没有执行权限。更新到最新 marketplace 载荷后重新安装；临时修复可执行 `chmod +x ~/.claude/plugins/cache/logic70-plugins/workflowprogram-native-cn/0.1.11/bin/workflowprogram-*`。

开发和调试仍可使用源码构建 `dist/plugin/`，但那不再是面向最终用户的主安装模型。

## 使用

在你的目标项目目录中启动 Claude Code：

```bash
cd your-project
claude
```

然后直接用自然语言描述你的需求。模型会根据语义命中 `workflowprogram-orchestrate`：

```text
"为当前项目设计一个 code review workflow"
```

显式 slash command 只用于调试路由或自动命中失败时兜底：

```text
/workflowprogram-native-cn:workflowprogram-orchestrate 为当前项目设计一个 code review workflow
```

其他自然语言示例：

```text
"审计当前项目的 workflow 结构"
"验证当前项目的 workflow 资产"
"把这个已经完成的 workflow 发布成 Claude Code 插件"
```

`workflowprogram-orchestrate` 会自动路由到正确的入口技能。以下叶子入口主要用于高级显式 intent 或调试，普通使用优先走 orchestrate：

| 入口 | 用途 |
|------|------|
| `workflowprogram-develop` | 从需求到交付的完整设计流程 |
| `workflowprogram-audit` | 审计已有 workflow 的结构和模式 |
| `workflowprogram-validate` | 对 workflow 资产做一次验证判定 |
| `workflowprogram-iterate` | 从 lessons 中提炼改进建议 |
| `workflowprogram-publish` | 将完整 develop 过的目标 workflow 发布为 marketplace plugin |

## 核心概念

### 三根目录

| 目录 | 角色 | 说明 |
|------|------|------|
| `PLUGIN_ROOT` | 能力来源 | WorkflowProgram 的 skills、脚本、模板（`dist/plugin/`）。只读。 |
| `TARGET_ROOT` | 交付目标 | 用户的项目根目录。最终的 `.claude/` 资产写在这里。只通过 managed apply 写入。 |
| `RUN_ROOT` | 运行证据 | 单次运行的隔离空间（`TARGET_ROOT/.workflowprogram/runs/<run-id>/`）。 |

### 阶段模型 S0..S6

| 阶段 | 职责 |
|------|------|
| S0 | 路由：识别用户意图，准备目标环境 |
| S1 | 需求澄清：多轮对话确保规格无歧义 |
| S2 | 上下文研究：分析目标项目现有结构 |
| S3 | 设计、审视与审批：生成 `workflow-spec.yaml`，通过内部 `workflow-design-reviewer` 和 gate 后才进入下一步 |
| S4 | 受控写入：候选资产生成 &rarr; managed apply &rarr; runner 执行 |
| S5 | 验证判定：S5 judge 消费 test_contract 给出 verdict |
| S6 | 经验回流：提炼 lessons 和约束候选 |

所有入口都会先经过 `S0` 路由；`workflow-spec.yaml.intent_flows` 继续定义 `S1-S6` 的逻辑阶段需求。当前默认模板中：`develop` 走 `S1-S6`，`audit` 走 `S5-S6`，`validate` 走 `S5`（可选 `S6`），`iterate` 走 `S6`（可选 `S5`）。

### S1 需求逻辑访谈

`develop` 的 S1 不再只是泛泛澄清输入输出，而是按七个 logic lenses 追问需求逻辑：

- `purpose`：为什么要做，成功信号是什么
- `object_model`：读取、转换、分类、产出的对象是什么
- `process_model`：目标工作流需要哪些业务步骤或节点
- `decision_model`：哪些分支、策略、阈值或人工确认会改变执行
- `evidence_model`：什么证据能证明中间产物和最终结论可信
- `acceptance_model`：哪些正向、负向、歧义场景能验收
- `boundary_model`：何时停止、降级、延后或明确不做

S1 会生成 `question-backlog.json` 和 `requirement-logic-map.json`。前者记录每个追问为什么会影响设计，后者把 `REQ-*` 链接到 process/evidence/acceptance 等逻辑元素。对 `L/XL` 复杂度请求，只问“还有哪些边界场景”这类泛问题会被 `validate-workflow-draft.py` 拦截，不能进入设计阶段。

### S3 设计审视 Gate

`develop` 在 S3 设计源和 `workflow-spec.yaml` 完成后，会生成 `design-review-packet.json` 并交给内部 `workflow-design-reviewer` 从新上下文审视目标一致性、需求覆盖、流程闭合、YAML 投影、证据质量、修改影响和运行时兼容性。只有 `closure.json` 与 `gate-validation.json` 都通过，S4 才能继续受控写入；未闭合 blocker 会以 `design_review_unresolved` 阻断。

### AI 和 Python 的分工

- **AI**：理解需求、补充设计、在每个节点内生成候选资产。
- **Python**：`workflow-entry.py` 串联固定脚本链，负责 spec/view/lowlevel/runtime 渲染、受控写入、能力探测与环境修复；`workflow-runner.py` 控制 WorkflowProgram 自身 S0-S6 状态转移；`target-workflow-runner.py` 控制生成目标工作流的 `workflow_graph.nodes`；`workflow-s5-judge.py` 给出判定。

编排顺序由程序决定，不由模型"记住"。

### Native Workflow JS authoring（交互式迁移路径）

仓库已提供一条与旧 Python runtime 并存的 Native authoring 路径。新建目标默认由插件产品级 `workflowprogram-develop.js` 控制 Clarify、Confirm、Design、Review、Generate、Validate、Smoke、Apply 和 Deliver；旧 Python runtime 仍保留用于 legacy 目标兼容。

`workflowprogram-orchestrate` 在 `develop` intent 下会继续调用 `route-native-control-plane.py`：所有目标默认路由到 `workflowprogram-native-develop`；已存在 `.workflowprogram/runtime/` 或旧设计 spec 的目标会返回 `manual_migration_required=true`，但不再自动转回旧主链，也不会自动重写旧 runtime 文件。

Native develop 不会根据首轮模糊需求直接生成。Skill 解析插件绝对路径后调用 `Workflow({ scriptPath, args })` 启动 `workflowprogram-develop.js`。JS 在信息不足时返回 `NEEDS_USER_INPUT`，等待确认时返回 `READY_FOR_CONFIRMATION`，需要宿主侧动作时返回 `READY_FOR_GENERATION / READY_FOR_VALIDATION / READY_FOR_SMOKE / READY_FOR_APPLY`。前台只负责转述、执行窄化脚本并携带证据重新调用。

authoring spec 使用 JSON：

```json
{
  "name": "example-workflow",
  "description": "Describe what the workflow does.",
  "phases": [{ "title": "Probe", "detail": "Return PASS." }],
  "body": "phase('Probe')\n\nreturn { status: 'PASS' }\n",
  "supporting_assets": []
}
```

默认只生成 candidate 和静态校验报告：

```bash
python .claude/scripts/generate-native-workflow.py \
  --spec <authoring-spec.json> \
  --readiness <confirmed-readiness.json> \
  --target-root <target-root> \
  --run-root <run-root> \
  --json
```

M9 过渡期仍复用该 JSON renderer，但 JSON authoring spec 不是控制面真源。candidate 生成后，使用 `build-native-develop-evidence.py` 对 candidate tree 求稳定 hash，并规范化 generation、validation、smoke 和 apply evidence。用户批准后由 `managed-assets.py apply-staged` 负责受控写入、冲突保护、回滚清单和恢复说明。独立校验已有 JS 时执行：

```bash
python .claude/scripts/validate-native-workflow-js.py --script <workflow.js> --json
```

`supporting_assets` 只在单文件 JS 不足时显式增加，可生成 reusable skill、Agent、领域脚本、thin compatibility command 或可选 authoring metadata。每个可选资产必须提供 `reason`，并受目标路径白名单约束。

插件产品 develop 控制面通过以下形式启动：

```text
Workflow({
  scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/workflowprogram-develop.js",
  args: {
    runId: "<RUN_ID>",
    request: "<user requirement>",
    targetRoot: "<TARGET_ROOT>",
    runRoot: "<RUN_ROOT>",
    operation: "create",
    clarification: {
      lenses: {},
      openQuestions: [],
      confirmedByUser: false
    },
    applyApproved: false
  }
})
```

实际调用时必须把 `${CLAUDE_PLUGIN_ROOT}` 解析为绝对路径；Workflow 工具不会展开 shell 环境变量字面量。

当前已验证交互式 Claude Code CLI 中的自定义 JS 执行。可用以下命令从真实会话 JSONL 生成能力判读：

```bash
python .claude/scripts/probe-native-workflow-capability.py \
  --jsonl <session.jsonl> \
  --workflow <workflow-name> \
  --json
```

M11 第一版还提供宿主侧交互式 smoke packet 和 JSONL 判读器：

```bash
python .claude/scripts/build-native-interactive-smoke.py packet \
  --workflow <workflow-name> \
  --script-path <absolute-workflow-js-path> \
  --expected-status PASS \
  --evidence-profile full \
  --json

python .claude/scripts/build-native-interactive-smoke.py evaluate \
  --jsonl <session.jsonl> \
  --journal-jsonl <optional-journal.jsonl> \
  --workflow <workflow-name> \
  --expected-status PASS \
  --evidence-profile full \
  --json
```

`packet` 会生成包含 `ultrawork` 触发词的人工执行提示，但不会自行启动 Claude Code。`evaluate` 只读取真实 JSONL。当前支持 manual WSL login-shell execution + deterministic JSONL evaluation；Computer Use 终端驱动仍 deferred，等待允许的非终端集成。

M12 增加 Native workflow manifest 和发布资格聚合器：

```bash
python .claude/scripts/build-native-workflow-manifest.py \
  --run-id <run-id> \
  --candidate-root <candidate-root> \
  --workflow-name <workflow-name> \
  --workflow-script <candidate-workflow-js> \
  --design-review-report <report.json> \
  --static-validation-report <report.json> \
  --interactive-smoke-report <report.json> \
  --drift-report <report.json> \
  --out <native-workflow-manifest.json> \
  --json

python .claude/scripts/validate-publish-qualification.py \
  --manifest <native-workflow-manifest.json> \
  --candidate-root <candidate-root> \
  --target-root <target-root> \
  --json
```

manifest 将 Design Review、Static Validation、Interactive Smoke、Asset Scope、Drift Check 和 Manifest 六个 gate 绑定到同一 `candidateHash`。`managed-assets.py apply-staged` 对相同候选重放执行真正 no-op，不重复写目标文件或 managed manifest；目标 drift 返回冲突。外部 GitHub apply 继续复用 `github-publish-target-plugin.py`，没有第二套 runner。

非交互式执行、自动化发布和旧目标工作流批量改写仍不支持。

`workflowprogram-native-authoring.js`、readiness packet 和 JSON authoring spec 仍作为 M7 renderer 兼容桥保留。M9 已将 develop 的阶段顺序和 gate 移入 `workflowprogram-develop.js`；目标稳态仍不默认生成 JSON authoring spec 或 `workflow-spec.yaml` 作为第二份语义真源。

M8 已验证插件内 JS 可通过绝对 `scriptPath` 启动，但不会自动注册为可按名称调用的 saved workflow。M9 已实现 develop 控制面，并通过真实交互式 CLI 验证空参数调用进入 `BLOCKED_INPUT`，不再返回 M8 的 `NOT_IMPLEMENTED`。M10A 已完成 validate 与 audit 的自动化实现；M10B 已完成 iterate Native Lessons Loop；M10C 已完成 publish 的资格、打包、验证、本地交付和显式外部 apply 控制面。M11 v1 已增加可重放 smoke packet、完整 PASS 与 early-blocker JSONL 判读。M12 已完成 Native manifest、发布资格聚合、managed apply no-op 和 drift 阻断。五个产品 JS 均已移除 `NOT_IMPLEMENTED` 分发骨架。证据见 `tests/manual-fixtures/native-workflow-product-registration/README.md`、`tests/manual-fixtures/native-workflow-develop-reentrant/README.md` 和 `tests/manual-fixtures/native-workflow-interactive-smoke/README.md`。

M13 已完成按任务类型选择模型的核心实现：Agent 声明逻辑 `taskType`，`resolve-task-model-policy.py` 将 taskType 解析为模型别名并输出 `task-model-resolution.json` 至 `RUN_ROOT/outputs/stages/`；`withTaskModel(taskType, options)` JS 助手在对应 product workflow 中消费解析结果，将具体模型传给 Native `agent(..., { model })`；未配置或不可用时继承默认模型。首版默认将澄清、仓库探索、普通生成和低风险静态复核映射到 `deepseek-v4-flash[1M]`，将架构设计、复杂生成、风险审查和发布资格复核映射到 `deepseek-v4-pro[1M]`。该能力已纳入基础 Native 迁移。

M14 已完成 legacy 下线资格评估：`assess-native-legacy-retirement.py` 提供确定性、事实驱动的只读评估器，对 14 项 legacy 资产/资产组按 retain / replace / narrow / remove 给出处置结论与分组 removalPlan。评估器定义 5 条阻断规则；M15 已将 develop JS 的 `READY_FOR_GENERATION` handoff 接入 renderer 主路径，`generate-native-workflow.py` 使用 `--generation-handoff` 校验并持久化 handoff report，旧 `--readiness` 仅保留为兼容入口，不再出现在活跃 leaf skill 中。M16 已关闭 rollback/deprecation anchor 与 legacy routing blocker。当前仓库稳定返回 `BLOCKED_RETIREMENT`，仅剩 product smoke 未声明完成。评估器不执行任何删除操作；实际下线待阻断条件关闭后推进。

### Legacy 目标侧 runtime 与扩展能力

以下内容描述兼容保留的 legacy `workflowprogram-develop` 主链。新建 Native 目标默认不生成 `.workflowprogram/runtime/`。

- develop 成功后，除了 `.claude/` 资产，还会持久化 `TARGET_ROOT/.workflowprogram/design/{workflow-spec.yaml,workflow-view.md,workflow-maintenance.md}`，并把目标工作流设计源归档到 `TARGET_ROOT/.workflowprogram/design/source/**`。
- 目标工作流设计源使用 `target-design-overview.md`、`target-design-detail.md`、`target-acceptance-tests.yaml`、`target-traceability-matrix.json`；`workflow-view.md` / `workflow-maintenance.md` 是从 YAML 派生的视图，不是新的设计真源。
- 复杂、loop、工具重、逆向/安全或影响多个下游节点的目标业务节点，还必须生成 `target-node-designs/<node-id>.md`。它是单节点可执行设计契约，需和 `workflow_graph.nodes[*]` 的 owner、template、gate、input/output、loop policy 保持一致，并由 `validate-target-node-design.py` 和 S5 校验。
- 目标项目还会获得自己的 deterministic runtime 包装层：`TARGET_ROOT/.workflowprogram/runtime/{workflow-entry.py,workflow-runner.py,validate-run-state.py,runtime-manifest.json}`。
- 新生成的目标工作流默认使用 `target_runtime_policy.mode=managed_runtime`：对外 command 只应作为 wrapper 启动 `.workflowprogram/runtime/workflow-entry.py`，实际业务节点由 `target-workflow-runner.py` 按 `workflow_graph` 执行，并留下 `target-state.json`、`target-events.jsonl`、`node-results.json` 与 `artifact-provenance.json`。绕过 runtime 或缺少 provenance 不能获得 clean PASS。
- 目标 runtime 不再假设本机 `claude -p` 可作为节点 executor。`target_executor_policy` 声明允许的 provider；`fixture_host` / `command_adapter` 可自动执行，`current_agent` / `manual` 只能提交 `outputs/stages/executor-evidence/<node-id>.json` 证据，finalizer 复核通过后才会把状态提升为 `PASS`。executor 不可用或证据缺失时必须 `FAIL` 且不 publish。
- 对会生成最终报告或长期复用输出的目标 workflow，默认启用 `target_publish_policy.enabled=true`：节点输出先进入本轮 `RUN_ROOT`，`target-runtime-finalizer.py` 校验 state、node results、artifact provenance 和 required reports 后，才把当前 run 的产物原子发布到 `publish_root` 并写 latest marker / manifest。业务节点或报告脚本不能自行声明最终 `PASS/COMPLETE`。
- managed runtime 目标 workflow 会在目标项目 `CLAUDE.md` 写入 WorkflowProgram runtime guard block，提示模型只能通过 `run/status/resume/diagnose` 服从 runtime 派单；该 block 不替代代码门禁，但缺失或冲突会被 generated-runtime / publish eligibility 校验阻断。
- `validate-target-publish-state.py` 会复核最终 manifest/latest marker/run root 是否同属当前 run，且 manifest 必须带有 `producer=target-runtime-finalizer.py` 和 finalizer seal；如果出现 `target-state=FAIL` 但 final manifest 被手写成 `COMPLETE`，验证必须失败。
- `target_publish_policy.required_reports` 只能列出 finalizer 发布前已经存在于当前 `RUN_ROOT` 的 gate 报告；不得把 finalizer 自己写入的 `manifest_path` 或 `latest_marker` 放入 required reports，避免形成“先要求 COMPLETE manifest，后由 finalizer 生成 manifest”的循环依赖。
- `workflow_graph.nodes[*].input_refs/output_refs` 也不得引用 `manifest_path` 或 `latest_marker`；业务节点不能在 finalizer 运行前读取或写入最终发布状态文件。
- 若 workflow 声明 `capability_discovery`，入口会先生成候选 `skill / MCP / CLI` 推荐与人工指引，再进入后续探测。
- 若 workflow 声明 `host_capabilities`，入口与 S5 会消费 `host-capability-report.json`、`environment-remediation-report.json`、`environment-remediation-guide.md`。
- 若 workflow 声明 `agent_team_contract`，S5 还会校验 `team-plan.json`、`team-results.json`、`team-join-summary.json` 等 Team 证据。
- 完整通过 `workflowprogram-develop` 的目标 workflow 可以进入独立发布环节：`/workflowprogram-native-cn:workflowprogram-publish` 会先检查 develop/S5/design-review/managed/target design source 证据，再把目标 workflow 打包成 Claude Code marketplace plugin，并通过用户自己的 GitHub 账户生成发布计划或执行发布。

### 发布前准备

在调用 `/workflowprogram-native-cn:workflowprogram-publish` 前，用户需要先完成：

1. 目标 workflow 已完整跑完 `workflowprogram-develop`，且最近一次发布资格所依赖的 S5/design-review/managed 证据仍有效。
2. 已决定目标插件的 `plugin-id`、显示名和版本号。
3. 已准备一个用于发布该目标 workflow 的 GitHub 仓库；当前流程不会自动创建新仓库。
4. 本机已安装并登录 `gh`，且对目标仓库有 push 权限。
5. 如果要真实推送，而不是 `--dry-run`，还要准备该 GitHub 仓库的本地 checkout 路径，供 `--repo-path` 使用。
6. 若要复用已有 marketplace，而不是生成独立 marketplace，则该 checkout 中还必须已有 `.claude-plugin/marketplace.json`，并选择 `--repo-mode existing_marketplace`。

最小调用示例：

```text
/workflowprogram-native-cn:workflowprogram-publish <target-root> --plugin-id <id> --repo <owner/repo-or-url>
```

复用已有 marketplace 的示例：

```text
/workflowprogram-native-cn:workflowprogram-publish <target-root> --plugin-id <id> --repo <owner/repo-or-url> --repo-mode existing_marketplace --repo-path <marketplace-checkout>
```

该模式会把插件 payload 规划到 `plugins/<plugin-id>/`，并合并已有 marketplace manifest；同名插件更新还需要显式选择更新入口，且版本必须提升。

需要真实 GitHub 写入时，发布流会要求显式审批；缺少仓库、权限、登录或本地 checkout 时，会返回 `BLOCKED` 并给出修复指引，而不是半自动“猜着发”。

### 受控写入

AI 不直接写目标项目。而是：

1. 候选资产写到 `RUN_ROOT/outputs/candidate/`
2. `managed-assets.py plan` 生成变更计划
3. `managed-assets.py apply-staged` 执行受控写入
4. 冲突时保留副本，不静默覆盖

如果目标项目已经有 WorkflowProgram 生成过的 workflow，后续“修改/拆分/替换/重新设计”不会直接 patch，也不会默认全量重做。`workflowprogram-develop` 会先生成：

- `outputs/stages/route-intent.json`
- `outputs/stages/change-context.json`
- `outputs/stages/existing-workflow-readback.json`
- `outputs/stages/change-policy.json`
- `outputs/stages/impact-analysis.json`

`workflow-entry.py` 会在 managed apply 前复核这些证据、审批状态和目标文件 fingerprints。缺少 change policy、审批缺失或目标状态已变化时，会先以 `BLOCKED/design` 停止，不会写入目标项目。

### 三层验证

| 层 | 职责 | 关键文件 |
|----|------|---------|
| Runner | 控制面硬约束（边界、证据、值域） | `state.json`, `events.jsonl` |
| S5 Judge | workflow 级 verdict（消费 test_contract） | `s5-validation-summary.json`, `validation-runtime-report.md` |
| Runtime Smoke | 动态端到端 harness | `tools/runtime_smoke.py` |

### 代码与发布门禁

WorkflowProgram 自身维护使用三层质量门禁，避免日常提交被完整发布验证拖慢，同时保证发布前的插件载荷可信：

| 门禁 | 命令 | 使用场景 |
|------|------|----------|
| Commit Gate | `python3 .claude/scripts/quality-gate.py commit` | 普通提交前的快速检查：diff、核心 JSON 元数据、最小 spec 和模板 schema |
| Integration Gate | `python3 .claude/scripts/quality-gate.py integration` | 改到 runtime、runner、finalizer、schema、生成器、publish/package 或测试 harness 时 |
| Release Gate | `python3 .claude/scripts/quality-gate.py release` | 发布 WorkflowProgram 插件版本前，包含构建、版本一致性、完整仓库校验、插件 bootstrap 和 smoke matrix |

原则是精简提交门禁，不精简发布门禁。发布插件前必须验证 `dist/plugin/` 产物，而不是只验证源码。

### 经验闭环

- `lessons.md`：追加式日志，记录失败经验和待提炼约束
- `constraints.md`：长期 ALWAYS/NEVER 规则，新会话只加载这个文件
- `s6-lessons-delta.md`：单次运行增量，由 `validate-lessons-delta.py` 校验

## 项目结构

```
workflowprogram-native-cn/
├── CLAUDE.md                    # 项目协作说明
├── README.md
├── lessons.md                   # 经验日志
├── .claude/
│   ├── settings.json            # 命令与技能注册表
│   ├── commands/                # 6 个源码命令入口
│   ├── skills/                  # 12 个技能（含 5 个主产品技能）
│   ├── agents/                  # 8 个专家 agent 定义
│   ├── rules/constraints.md     # 长期约束规则
│   └── scripts/                 # 确定性脚本链、校验器与共享库
├── .claude-plugin/              # 插件元数据与 plugin root 真源
├── dist/plugin/                 # 构建产物（canonical marketplace payload）
├── docs/                        # 设计文档、教程、实现计划
├── tests/                       # fixtures、expectations、transcripts
└── tools/                       # 构建、烟雾测试、mock host
```

## 开发与验证

```bash
# 快速提交门禁
python .claude/scripts/quality-gate.py commit

# runtime / schema / generator / publish 相关改动的集成门禁
python .claude/scripts/quality-gate.py integration

# 发布 WorkflowProgram 插件版本前的发布门禁
python .claude/scripts/quality-gate.py release

# 仓库结构校验
python .claude/scripts/validate-workflow.py

# spec / lowlevel / generated runtime 校验
python .claude/scripts/validate-workflow-spec.py --spec <workflow-spec.yaml>
python .claude/scripts/validate-workflow-maintenance.py --spec <workflow-spec.yaml> --maintenance <workflow-maintenance.md>
python .claude/scripts/validate-generated-runtime.py --spec <workflow-spec.yaml> --runtime-root <target-runtime-root>

# 烟雾测试（单场景）
python tools/runtime_smoke.py --fixture empty-project --runtime-provider fixture_host

# 烟雾测试（完整矩阵，含 capability / host / team 场景）
python tools/runtime_smoke_matrix.py

# 清理维护命令回归
python tools/test_clean_workflowprogram.py

# 重新构建插件
python tools/build_plugin.py
```

## 教程

- [HTML 版教程](docs/workflowprogram-101-html/index.html) -- 可视化、循序渐进
- [HTML Tutorial (English)](docs/workflowprogram-101-html/index.en.html)
- [单页版 Markdown](docs/workflowprogram-101.md) -- 快速扫一遍全貌
- [Single-page Markdown (English)](docs/workflowprogram-101.en.md)
- [章节版 Markdown](docs/workflowprogram-101/index.md) -- 逐章深入
- [Chapter Guide (English)](docs/workflowprogram-101-en/index.md)

## 许可

MIT
