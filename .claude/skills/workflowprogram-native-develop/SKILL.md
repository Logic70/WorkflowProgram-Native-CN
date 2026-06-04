---
name: workflowprogram-native-develop
description: Design or update a Claude Code Native Workflow JS control plane for the current target project
version: 1.1.0
---

面向 `TARGET_ROOT` 的 Claude Code Native Workflow JS authoring 入口。

普通自然语言请求由模型语义命中 `workflowprogram-orchestrate`。本 Skill 是插件产品 JS 的薄启动适配器：它解析插件绝对路径、转述用户问题、执行宿主侧窄化脚本并把证据传回同一个 Native Workflow JS。阶段顺序、gate 和状态机属于 `workflowprogram-develop.js`，不属于 Skill。

## When To Use

- 为新目标项目创建 `.claude/workflows/<name>.js`
- 更新已有 Native Workflow JS
- 为 Native Workflow JS 按需增加 reusable Skill、Agent、领域脚本或 authoring metadata

## Core Rules

- `.claude/workflows/<name>.js` 是目标工作流执行真源。
- 默认只生成一个 Native Workflow JS；Skill、Agent、脚本、`.workflowprogram/design/` 和可选 `workflow-spec.yaml` 必须由需求证明后显式声明。
- 所有产品 JS 通过绝对 `scriptPath` 启动。不要假设插件内 `workflows/*.js` 已注册为 saved workflow。
- 所有目标文件先写入 `RUN_ROOT/outputs/candidate/`；只有用户批准后才能通过 `managed-assets.py apply-staged` 写入 `TARGET_ROOT`。
- 生成、校验、smoke、apply 都必须绑定同一个 `candidateHash`。不得把旧证据复用于新候选。
- 交互式 smoke 未实际执行时，不得伪造 `PASS`。
- 已有旧 runtime 目标也默认使用 Native authoring；若 router 返回 `manual_migration_required=true`，必须在候选区完成样例验证后再由用户批准写入，且不得自动删除旧 runtime 文件。

## Step 1: Resolve Mode And Roots

1. 确认 `TARGET_ROOT`。
2. 为本次运行创建稳定 `RUN_ID` 和 `RUN_ROOT=<TARGET_ROOT>/.workflowprogram/runs/<RUN_ID>`。
3. 调用：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/route-native-control-plane.py \
  --target-root <TARGET_ROOT> \
  --out <RUN_ROOT>/outputs/stages/control-plane-route.json \
  --json
```

4. 若结果包含 `manual_migration_required=true`，继续 Native authoring，但在输出中明确这是旧 runtime 目标迁移，候选写入前必须有用户批准和样例验证证据。
5. 将 `${CLAUDE_PLUGIN_ROOT}` 解析为插件安装目录的绝对路径。

## Step 2: Launch Or Reinvoke Product JS

## Clarification Ownership

D1 clarification semantics are owned by `workflowprogram-native-cn:requirement-clarification-lead`
and `${CLAUDE_PLUGIN_ROOT}/skills/workflow-spec-support/logic-lenses.md`.
This skill only relays JS-returned questions to the user and reinvokes the same
`workflowprogram-develop.js` with accumulated answers. Do not replace the registered
Agent with foreground prompt role-play.

调用：

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
    applyApproved: false
  }
})
```

后续每次调用使用同一个 `RUN_ID`、`RUN_ROOT` 和绝对 `scriptPath`，并累积上一次返回的结构化 evidence。

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

M15 已将 product handoff 作为主路径；generator 仍是宿主侧 deterministic renderer，不拥有控制顺序：

1. 将产品 JS 返回的 `READY_FOR_GENERATION` handoff envelope 写入 `RUN_ROOT/outputs/stages/native-workflow-generation-handoff-input.json`（包含 `status`、`workflow`、`runId`、`targetRoot`、`runRoot`、`designEvidence`、`reviewEvidence`、`authoringSpec`、`generationRequest`）。

2. 将 handoff 中的 `authoringSpec` 原样序列化为 `RUN_ROOT/native-workflow-authoring.json`。不得根据 `designEvidence.lowLevelDesign`、聊天记录或模型自由判断重写 JS body；如果 `authoringSpec` 缺失或需要修改，必须重新调用产品 JS 的 Author 阶段，而不是前台手写。

3. 执行 staging，不传 `--apply`：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/generate-native-workflow.py \
  --spec <RUN_ROOT>/native-workflow-authoring.json \
  --generation-handoff <RUN_ROOT>/outputs/stages/native-workflow-generation-handoff-input.json \
  --target-root <TARGET_ROOT> \
  --run-root <RUN_ROOT> \
  --json
```

`--generation-handoff` 是 M15+M18 主路径。Generator 会验证 handoff status=`READY_FOR_GENERATION`、workflow、targetRoot/runRoot 匹配、generationRequest、designEvidence、reviewEvidence 和 authoringSpec，并验证磁盘 spec 与 handoff authoringSpec 等价。非法、stale 或被前台改写的 handoff 阻断 candidate 写入并落盘结构化验证报告。

Generator 将 handoff 验证结果写入 `RUN_ROOT/outputs/stages/native-workflow-generation-handoff.json`（schema `native-workflow-generation-handoff-validation`）。

4. 规范化 generation evidence：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/build-native-develop-evidence.py generation \
  --candidate-root <RUN_ROOT>/outputs/candidate \
  --report <RUN_ROOT>/outputs/stages/native-workflow-generation.json \
  --json
```

4. 把输出作为 `args.generationEvidence` 重新调用产品 JS。

## Step 5: Deterministic Validation

当前 generator 已生成 `native-workflow-validation.json`。规范化并重新调用：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/build-native-develop-evidence.py validation \
  --candidate-root <RUN_ROOT>/outputs/candidate \
  --report <RUN_ROOT>/outputs/stages/native-workflow-validation.json \
  --json
```

把输出作为 `args.validationEvidence`。

## Step 6: Interactive Smoke

通过宿主侧 Computer Use harness 或人工入口真实启动 Claude Code，验证 candidate 的 discovery、launch、Agent、schema、JS gate 和 blocker 路径。将 JSONL 或 transcript 路径规范化：

```text
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/build-native-develop-evidence.py smoke \
  --candidate-root <RUN_ROOT>/outputs/candidate \
  --status PASS \
  --evidence <JSONL-or-transcript-path> \
  --json
```

把输出作为 `args.smokeEvidence`。smoke 未执行或 evidence 路径不存在时必须保持阻断。

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
  --report <RUN_ROOT>/outputs/managed-change-result.json \
  --json
```

把输出作为 `args.applyEvidence`。有 drift 或冲突时停止，不覆盖目标文件。

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
- 交互式 smoke JSONL 或 transcript
- candidate tree
- 用户批准时的 managed apply 结果和 manifest
