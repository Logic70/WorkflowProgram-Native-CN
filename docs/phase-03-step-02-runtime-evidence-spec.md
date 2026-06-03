# Phase 3 Step 2 RUN_ROOT 运行时证据模型规范

## 1. 目的

本规范定义 Phase 3 动态验证的最小运行时证据模型，作为后续 `tools/runtime_smoke.py`、`state-bus.py` 重构和动态报告写入的共同契约。

## 2. 运行目录模型

每次动态验证都必须在 `TARGET_ROOT` 下创建独立运行目录：

```text
TARGET_ROOT/.workflowprogram/runs/<run-id>/
```

其中：

- `TARGET_ROOT`
  - 被测目标项目目录
- `.workflowprogram/`
  - 插件运行痕迹目录
- `runs/<run-id>/`
  - 单次运行的隔离证据目录

## 3. RUN_ROOT 最小目录结构

```text
TARGET_ROOT/.workflowprogram/runs/<run-id>/
├── context.json
├── state.json
├── events.jsonl
├── transcript.md
├── validation-runtime-report.md
└── outputs/
```

可选扩展：

```text
├── stderr.log
├── stdout.log
├── plugin-build-manifest.json
├── environment.json
└── checkpoints/
```

## 4. 必需文件定义

### 4.1 `context.json`

用途：记录本次运行的输入上下文。

最低字段：

```json
{
  "run_id": "20260403T120000Z-empty-project",
  "started_at": "2026-04-03T12:00:00Z",
  "plugin_root": "/abs/path/to/dist/plugin",
  "target_root": "/abs/path/to/tests/fixtures/empty-project",
  "fixture": "empty-project",
  "entry_skill": "workflowprogram-develop",
  "request": "为当前项目设计 Claude Code workflow",
  "claude_bin": "claude",
  "mode": "runtime-smoke"
}
```

### 4.2 `state.json`

用途：记录运行态状态机和总体结论。

最低字段：

```json
{
  "run_id": "20260403T120000Z-empty-project",
  "status": "running",
  "stage": "invoke",
  "result": null,
  "subagent_evidence": false,
  "events_written": 0,
  "started_at": "2026-04-03T12:00:00Z",
  "updated_at": "2026-04-03T12:00:05Z"
}
```

### 4.3 `events.jsonl`

用途：记录结构化事件流。

要求：

- 每行一个 JSON 对象
- 允许追加写入
- 必须按时间顺序写入

### 4.4 `transcript.md`

用途：记录人类可读的运行摘要和关键原始输出。

要求：

- 包含运行基本信息
- 包含 CLI 调用命令
- 包含关键 stdout/stderr 摘要
- 包含最终结论

### 4.5 `validation-runtime-report.md`

用途：记录本次动态验证的正式判定。

最低内容：

- 目标 fixture
- 入口 skill
- 结果状态
- 失败分类
- 证据位置
- 建议下一步

### 4.6 `outputs/`

用途：保存运行产生的中间或最终输出副本。

要求：

- 若目标 workflow 生成了 `.claude/` 资产，可在此目录保存摘要或 diff
- 若本次运行依赖 `dist/plugin/build-manifest.json`，应复制一份到 `outputs/plugin-build-manifest.json`
- 若本次运行执行了 managed asset 应用，可在此目录保存 `managed-change-plan.json`、`managed-change-result.json` 和冲突副本
- 不要求复制整个目标项目

## 5. 事件模型

### 5.1 必需事件字段

每个事件至少包含：

```json
{
  "ts": "2026-04-03T12:00:03Z",
  "type": "TaskCreated",
  "stage": "invoke",
  "source": "runtime_smoke",
  "status": "ok",
  "message": "created workflowprogram-develop task"
}
```

字段说明：

- `ts`
  - ISO 8601 时间戳
- `type`
  - 事件类型
- `stage`
  - 当前运行阶段
- `source`
  - 事件来源，如 `runtime_smoke`、`claude-cli`、`state-bus`
- `status`
  - `ok` / `warn` / `error`
- `message`
  - 人类可读说明

### 5.2 推荐事件类型

Phase 3 最低支持：

- `RunStarted`
- `RunFinished`
- `TaskCreated`
- `TaskCompleted`
- `SubagentStart`
- `SubagentStop`
- `PreToolUse`
- `PostToolUse`
- `OutputWritten`
- `RuntimeError`
- `EnvironmentSkip`

### 5.3 subagent 证据标准

Phase 3 不要求完整还原所有 subagent 细节，但至少要满足以下之一：

1. 在 `events.jsonl` 中出现 `SubagentStart` / `SubagentStop`
2. 在 transcript 中出现可判定的 subagent 调用痕迹
3. 在 Claude JSON 输出中存在明确 task/subagent 事件，被 harness 提取后写入 `events.jsonl`

判定字段：

- `state.json.subagent_evidence = true`

## 6. 运行结果状态模型

### 6.1 总体结果枚举

`validation-runtime-report.md` 和 `state.json.result` 统一使用：

- `PASS`
- `FAIL`
- `ENVIRONMENT-SKIP`

### 6.2 失败分类

若结果为 `FAIL`，还应细分：

- `STRUCTURE_FAILURE`
- `RUNTIME_FAILURE`
- `OUTPUT_FAILURE`
- `EVIDENCE_FAILURE`

若结果为 `ENVIRONMENT-SKIP`，还应细分：

- `CLAUDE_NOT_LOGGED_IN`
- `CLAUDE_NOT_FOUND`
- `UNSUPPORTED_CLI_VERSION`
- `UNKNOWN_ENVIRONMENT`

## 7. 最小通过条件

一次动态验证可判定为 `PASS` 的最低条件：

1. `RUN_ROOT` 已创建
2. `context.json`、`state.json`、`events.jsonl`、`transcript.md`、`validation-runtime-report.md` 已生成
3. 被测入口 skill 完成实际调用
4. `TARGET_ROOT` 中产生了预期级别的变化或明确的无变更解释
5. 至少有一个可判定的运行证据来源

## 8. 最小环境跳过条件

若出现以下情况，可判定为 `ENVIRONMENT-SKIP`：

- Claude CLI 不存在
- Claude CLI 未登录
- 当前环境不支持运行所需模式

要求：

- 仍要创建 `RUN_ROOT`
- 仍要写入 `validation-runtime-report.md`
- `events.jsonl` 中必须有 `EnvironmentSkip`

## 9. 对 `state-bus.py` 的约束

若继续保留 `state-bus.py`，则后续必须满足：

- 默认 session 路径可指向 `RUN_ROOT/state.json`
- 支持更新时间戳和阶段状态
- 不再假设运行目录位于插件源码仓内部 `.claude/`

## 10. 结论

Phase 3 的 smoke harness 只要严格遵守本规范，就可以做到：

- 对目标项目真实运行
- 对环境失败做明确隔离
- 对 subagent 参与给出最低可判定证据
- 为后续扩展到更复杂 fixture 留出空间
