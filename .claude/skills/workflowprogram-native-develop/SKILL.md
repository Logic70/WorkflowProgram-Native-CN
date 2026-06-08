---
name: workflowprogram-native-develop
description: Use for WPN / WorkflowProgram Native requests that create, update, migrate, or refactor a Claude Code Native Workflow JS control plane; must launch product Workflow({scriptPath,args}) before any foreground Agent or direct write.
version: 1.1.0
---

面向 `TARGET_ROOT` 的 Claude Code Native Workflow JS authoring 入口。

普通自然语言请求由模型语义命中 `workflowprogram-orchestrate`。本 Skill 是插件产品 JS 的薄启动适配器：它解析插件绝对路径、转述用户问题、执行宿主侧窄化脚本并把证据传回同一个 Native Workflow JS。阶段顺序、gate 和状态机属于 `workflowprogram-develop.js`，不属于 Skill。

## When To Use

- 为新目标项目创建 `.claude/workflows/<name>.js`
- 更新已有 Native Workflow JS
- 为 Native Workflow JS 按需增加 reusable Skill、Agent、领域脚本或 authoring metadata

## Core Rules

- If the user request says WPN, WorkflowProgram Native, native workflow
  migration, migrate an existing workflow, or refactor workflow assets, this
  skill is a control-plane launcher. The first substantive action must be the
  product `Workflow({ scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-develop.js", args })`
  invocation after deriving roots and operation. Do not start with a generic
  Agent exploration pass that can complete the migration in the foreground.
- Foreground Agent/Read/Bash may gather only the minimum context needed to
  derive `targetRoot`, `runId`, `runRoot`, and `operation`. They must not write
  `.claude/**`, `.workflowprogram/design/**`, `.workflowprogram/runtime/**`,
  `.workflowprogram/runs/**`, or `.workflowprogram/managed-files.json`.

- `.claude/workflows/<name>.js` 是目标工作流执行真源。
- 默认只生成一个 Native Workflow JS；Skill、Agent、脚本、`.workflowprogram/design/` 和可选 `workflow-spec.yaml` 必须由需求证明后显式声明。
- 所有产品 JS 通过绝对 `scriptPath` 启动。不要假设插件内 `workflows/*.js` 已注册为 saved workflow。
- 所有目标文件先写入 `RUN_ROOT/outputs/candidate/`；只有用户批准后才能通过 `managed-assets.py apply-staged` 写入 `TARGET_ROOT`。
- 生成、校验、smoke、apply 都必须绑定同一个 `candidateHash`。不得把旧证据复用于新候选。
- 交互式 smoke 未实际执行时，不得伪造 `PASS`。
- 已有旧 runtime 目标也默认使用 Native authoring；若 router 返回 `manual_migration_required=true`，必须在候选区完成样例验证后再由用户批准写入，且不得自动删除旧 runtime 文件。

## Step 1: Derive Invocation Inputs Without Side Effects

1. Confirm `TARGET_ROOT` from the current working directory or the user's
   explicit target path.
2. Derive a stable `RUN_ID`, `RUN_ROOT=<TARGET_ROOT>/.workflowprogram/runs/<RUN_ID>`,
   and `operation=create|update|migrate` from read-only context only.
3. Resolve `${CLAUDE_PLUGIN_ROOT}` to the plugin installation directory and build
   the absolute product script path:
   `<PLUGIN_ROOT>/workflows/workflowprogram-develop.js`.
4. Do not create `RUN_ROOT`, run `route-native-control-plane.py`, write route
   output, or create candidate/stage files before the product Workflow is
   invoked. Route discovery, run-root creation, candidate staging, and manifest
   writes are product Workflow ownership.
5. If the current Claude Code session does not expose the `Workflow` tool, report
   `BLOCKED_WORKFLOW_TOOL_UNAVAILABLE` with the session JSONL path and do not
   fall back to foreground `Agent`, `Bash`, `PowerShell`, `Write`, or direct
   Python runner execution.

## Step 2: Launch Or Reinvoke Product JS

## Clarification Ownership

D1 clarification semantics are owned by `workflowprogram-native-cn:requirement-clarification-lead`
and `${CLAUDE_PLUGIN_ROOT}/skills/workflow-spec-support/logic-lenses.md`.
This skill only relays JS-returned questions to the user and reinvokes the same
`workflowprogram-develop.js` with accumulated answers. Do not replace the registered
Agent with foreground prompt role-play.

### Canonical Invocation

Always invoke the product JS through its absolute `scriptPath` and a structured
`args` object. The user should not need to provide these fields manually; the
foreground assistant derives `RUN_ID`, `RUN_ROOT`, `TARGET_ROOT`, operation, and
settled migration decisions before launching the product JS.

Use this shape:

```text
Workflow({
  scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-develop.js",
  args: {
    runId: "<RUN_ID>",
    request: "<用户原始需求>",
    targetRoot: "<TARGET_ROOT>",
    runRoot: "<RUN_ROOT>",
    operation: "create | update | migrate",
    clarification: {
      lenses: {
        purpose: "",
        objectModel: "",
        processModel: "",
        decisionModel: "",
        evidenceModel: "",
        acceptanceModel: "",
        boundaryModel: ""
      },
      openQuestions: [],
      confirmedByUser: false
    },
    migrationDecisions: {
      keepVerifyValidationPocSeparate: true,
      flatOutputDir: "outputs/stride-audit",
      pythonViaSubprocess: true,
      promptsInline: true,
      reusableAsRegistered: true,
      managedApplyAllowed: false
    },
    applyApproved: false
  }
})
```

Do **not** use a string args payload or dotted keys as the primary path:

```text
Workflow({
  name: "workflowprogram-native-cn:workflowprogram-develop",
  args: "operation=migrate clarification.confirmedByUser=true decisions.flatOutputDir=outputs/stride-audit"
})
```

That anti-pattern creates top-level keys such as `"clarification.confirmedByUser"`.
The product JS expects `args.clarification.confirmedByUser`, so dotted keys can
cause the workflow to loop at `READY_FOR_CONFIRMATION`.

For existing-workflow migration, resolved `migrationDecisions` are settled input,
not new user questions. Exploration Agents must not return a resolved decision
again in `userDecisions`. For example, when `flatOutputDir` is already
`"outputs/stride-audit"`, a question about whether to keep flat outputs is not a
blocker. If there is no real blocker, return `trueBlockers: []`; do not write
placeholder text such as `"No true blockers identified"` in `trueBlockers`.
Asset-disposition confirmations covered by `assetDispositionHints` or
`migrationDecisions` are design context, not foreground questions.

后续每次调用使用同一个 `RUN_ID`、`RUN_ROOT` 和绝对 `scriptPath`，并累积上一次返回的结构化 evidence。

## Foreground Guard Protocol

After every `Workflow({ scriptPath, args })` return, persist the exact returned
envelope before taking any next action. When Claude Code reports a completed
background Workflow with `<output-file>...</output-file>`, pass that task output
file directly to the guard. Do not create `RUN_ROOT`, do not use `Write`, and do
not handwrite `latest-workflow-result.json` first; the guard creates the stage
file and session state itself.

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflowprogram-foreground-guard.py record \
  --target-root <TARGET_ROOT> \
  --run-root <RUN_ROOT> \
  --workflow-task-output <WORKFLOW_TASK_OUTPUT_FILE> \
  --json
```

If a task output file is not available, pass the returned JSON with
`--workflow-result-json '<JSON>'` or through stdin. Never recover from a missing
result file by manually creating directories or writing the result with the
`Write` tool.

If the result is `NEEDS_USER_INPUT`, `READY_FOR_CONFIRMATION`, or any
`BLOCKED_*` state, the foreground assistant may only relay questions/blockers or
collect user confirmation. It must not edit `.claude/**`, `.workflowprogram/design/**`,
`.workflowprogram/runtime/**`, or commit changes to the target project.
It must also not edit Claude Code's transient workflow cache files under
`<CLAUDE_PROJECT>/workflows/scripts/workflowprogram-develop-*.js` to bypass a
product JS gate. Those files are runtime cache/resume artifacts, not the source
of truth for WPN fixes.

If the result is `READY_FOR_GENERATION`, `READY_FOR_VALIDATION`, `READY_FOR_SMOKE`,
or `READY_FOR_APPLY`, the foreground assistant must execute only the controlled
script named by `nextAction` and feed the resulting evidence back into the same
product JS. Do not repair, rewrite, or complete target files in the foreground.

Before committing a target workflow update, run:

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflowprogram-foreground-guard.py assert-commit \
  --target-root <TARGET_ROOT> \
  --json
```

The commit gate passes only after the product JS returns `PASS` with
`deliveryMode=managed-apply` and a structured `applyManifest`.

## Step 3: Relay Re-entrant States

| JS 状态 | 前台动作 |
|---|---|
| `NEEDS_USER_INPUT` | 将 `questions` 转述给用户；把回答写回 `clarification.lenses` 或 `openQuestions` 后重新调用 |
| `READY_FOR_CONFIRMATION` | 向用户回读 `requirementSummary`；只有用户明确确认后才设置 `confirmedByUser=true` |
| `BLOCKED_DESIGN` / `BLOCKED_DESIGN_REVIEW` | 转述 blocker，补充输入或修订设计后重新调用 |
| `READY_FOR_GENERATION` | 执行 Step 4 |
| `READY_FOR_VALIDATION` | 执行 Step 5 |
| `READY_FOR_SMOKE` | 执行 Step 6 |
| `READY_FOR_APPLY` | 只有用户批准写入后执行 Step 7 |
| `BLOCKED_*` | 报告 blocker，不绕过 gate |
| `PASS` | 交付 candidate-only 或 managed-apply 结果 |

## Step 4: Controlled Generation

M15 已将 product handoff 作为主路径；M18 收紧为确定性 continuation runner。**Foreground 不得手写 handoff input JSON、authoring spec JSON 或 JS body。** 前台必须通过 `workflowprogram-continue.py` 确定性脚本驱动整个 generation pipeline：

### Foreground Bypass Hardening Rule

**NEVER handwrite handoff files in the foreground.** 直接在前台手工创建 `native-workflow-generation-handoff-input.json`、`native-workflow-authoring.json` 或任何 candidate 文件是禁止的。`workflowprogram-foreground-guard.py` 在 `READY_FOR_GENERATION` 状态下只允许运行 `workflowprogram-continue.py`；任何前台 Write/Edit/Bash/PowerShell/Shell 写入 managed target 路径都会被阻断。

### 4a. Record the Workflow Result

先将产品 JS 返回的 envelope 落盘为 latest-workflow-result.json：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflowprogram-foreground-guard.py record \
  --target-root <TARGET_ROOT> \
  --run-root <RUN_ROOT> \
  --workflow-task-output <WORKFLOW_TASK_OUTPUT_FILE> \
  --json
```

Guard 的 `record` 子命令现在会 unwrap `{result: {...}}` envelopes——当 Workflow 工具将 JS 结果包装在 `result` 键中时，guard 提取内部对象再持久化状态。
It also writes `<RUN_ROOT>/outputs/stages/latest-workflow-result.json`, so the
foreground assistant must not create that file manually.

### 4b. Run Deterministic Continuation

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflowprogram-continue.py \
  --workflow-result <RUN_ROOT>/outputs/stages/latest-workflow-result.json \
  --target-root <TARGET_ROOT> \
  --run-root <RUN_ROOT> \
  --json
```

`workflowprogram-continue.py` 执行以下确定性步骤：

1. **Unwrap result envelope** — 如果输入包含 `{result: {...}}` 包装，提取内部 workflow 对象。
2. **Validate handoff** — 确认 status=`READY_FOR_GENERATION`、workflow=`workflowprogram-develop`、runId 非空、authoringSpec 和 generationRequest 存在。
3. **Write handoff input JSON** — 将完整 handoff envelope（status、workflow、runId、targetRoot、runRoot、designEvidence、reviewEvidence、authoringSpec、generationRequest）写入 `RUN_ROOT/outputs/stages/native-workflow-generation-handoff-input.json`。
4. **Write authoring spec JSON** — 将 `authoringSpec` 原样序列化为 `RUN_ROOT/native-workflow-authoring.json`。
5. **Invoke generator** — 调用 `generate-native-workflow.py --generation-handoff` 进行 handoff 验证和 candidate staging（不传 `--apply`）。
6. **Persist handoff validation report** — generator 必须写入 `RUN_ROOT/outputs/stages/native-workflow-generation-handoff.json`，记录 handoff status、workflow、target/run root、generationRequest、designEvidence、reviewEvidence、authoringSpec 与磁盘 spec 等价性校验。
7. **Build generation evidence** — 调用 `build-native-develop-evidence.py generation` 规范化 generation 报告。
8. **Emit continuation report** — 输出结构化 JSON，包含 generationEvidence、所有文件路径和下一步 re-invoke 指令。

如果任何步骤失败，脚本返回 FAIL 报告并列出 blocking issues。

### 4c. Reinvoke Product JS

把 continuation 报告中的 `generationEvidence` 作为 `args.generationEvidence` 重新调用产品 JS。输出中的 `workflowScriptPath` 必须是当前 candidate 的 `.claude/workflows/<WORKFLOW_NAME>.js` 绝对路径。非 PASS、candidate 为空、主 Workflow JS 不在标准路径或 evidence 文件不存在时必须保持阻断。

### Authoring Spec Integrity

关于 authoring spec 的完整性规则不变：

- `supporting_assets` 只描述需要生成、更新或归档的资产内容。
- `asset_disposition` 独立描述 update/migrate 时每个现有或目标资产的 `retain | generate | update | archive | remove | defer | not-applicable` 决策。
- `task_model_policy` 只接受 `agent_task_models` 映射；不要在 authoring spec 中散落模型别名字段。

如果 `authoringSpec` 缺失或需要修改，必须重新调用产品 JS 的 Author 阶段，而不是前台手写。

## Step 5: Deterministic Validation

当前 generator 已生成 `native-workflow-validation.json`。规范化并重新调用：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/build-native-develop-evidence.py validation \
  --candidate-root <RUN_ROOT>/outputs/candidate \
  --report <RUN_ROOT>/outputs/stages/native-workflow-validation.json \
  --json
```

把输出作为 `args.validationEvidence`。`validationEvidence.workflowScriptPath` 必须与 `generationEvidence.workflowScriptPath` 完全一致，避免生成报告与验证报告指向同一 candidate tree 中的不同脚本。非 PASS 或主脚本不一致时保持 `BLOCKED_VALIDATION`。

## Step 6: Interactive Smoke

通过宿主侧 Computer Use harness 或人工入口真实启动 Claude Code，验证 candidate 的 discovery、launch、Agent、schema、JS gate 和 blocker 路径。先使用 `build-native-interactive-smoke.py evaluate` 将真实 JSONL 判读为 evaluator 报告；不得把原始 JSONL、transcript 或手工状态字符串直接当作 smoke evidence。

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/build-native-interactive-smoke.py evaluate \
  --workflow <WORKFLOW_NAME> \
  --script-path <CANDIDATE_WORKFLOW_ABSOLUTE_PATH> \
  --candidate-root <RUN_ROOT>/outputs/candidate \
  --expected-status <EXPECTED_STATUS> \
  --scenario-id <SCENARIO> \
  --jsonl <REAL_SESSION_JSONL> \
  --out <RUN_ROOT>/outputs/stages/native-workflow-interactive-smoke-<SCENARIO>.json
```

只有 evaluator 报告证明 `workflow_invoked`、`async_launched`、`agent_started`、`schema_result` 和预期完成状态后，才能规范化 smoke evidence：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/build-native-develop-evidence.py smoke \
  --candidate-root <RUN_ROOT>/outputs/candidate \
  --status PASS \
  --evidence <RUN_ROOT>/outputs/stages/native-workflow-interactive-smoke-<SCENARIO>.json \
  --json
```

把输出作为 `args.smokeEvidence`。输出必须包含非空 `smokeReports`，并绑定 evaluator 报告路径、hash、candidate `scriptPath`、`scriptHash`、`candidateHash`、scenario、run IDs 和证据 profile。smoke 未执行、链路证据不完整、启动路径不是当前 candidate 或 evaluator 报告路径不存在时必须保持阻断。

## Step 7: Controlled Apply

用户明确批准后，设置 `applyApproved=true`。产品 JS 返回 `READY_FOR_APPLY` 后执行：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/managed-assets.py apply-staged \
  --target-root <TARGET_ROOT> \
  --source-root <RUN_ROOT>/outputs/candidate \
  --run-root <RUN_ROOT> \
  --json
```

规范化结果：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/build-native-develop-evidence.py apply \
  --candidate-root <RUN_ROOT>/outputs/candidate \
  --target-root <TARGET_ROOT> \
  --report <RUN_ROOT>/outputs/managed-change-result.json \
  --json
```

把输出作为 `args.applyEvidence`。`applyEvidence.targetRoot` 必须匹配本次目标；`applyManifest` 必须是结构化对象，包含真实 managed manifest 路径、持久化 managed-change report 路径以及覆盖全部 candidate 文件的 `path`、`action`、`sha256` 条目。不得传入路径字符串或手工占位值。有 drift、冲突、目标不匹配、未覆盖资产或 hash 不一致时停止，不覆盖目标文件。

## Transitional Assets

- `workflowprogram-develop.js` 已在 M9 成为 Native develop 控制面真源。
- M15 已将 `--generation-handoff` 设为主路径；M7 兼容路径保留在脚本和测试中，不作为本 leaf skill 的主路径。
- 后续收敛 renderer 时可以删除兼容桥，但不得把控制顺序移回 Skill 或 Python runner。

## Output

输出应包含：

- `control-plane-route.json`
- 产品 JS 的最终结构化 envelope
- `native-workflow-generation.json`
- `native-workflow-validation.json`
- 交互式 smoke 原始 JSONL 与 evaluator 报告
- candidate tree
- 用户批准时的 managed apply 结果和结构化 manifest evidence
