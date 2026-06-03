# Session State Bus

`state-bus.py` 是一个开发态辅助工具，用于在长流程中保存阶段状态、创建检查点，并在指定 `RUN_ROOT` 时把关键状态变化追加到 `events.jsonl`。它不是 `Phase 3` 的主 runtime harness；主动态验证入口仍是 `tools/runtime_smoke.py`。

## 定位

- 主用途：手工调试、长流程状态持久化、阶段间数据传递
- 非主用途：替代 runtime smoke 或替代 Claude CLI 运行
- 对齐原则：优先写入 `TARGET_ROOT/.workflowprogram/runs/<run-id>/`

## 路径模型

优先级如下：

1. `--session <path>`
2. 环境变量 `WORKFLOWPROGRAM_SESSION_FILE`
3. `--run-root <path>`
4. 环境变量 `WORKFLOWPROGRAM_RUN_ROOT`
5. 默认路径 `.workflowprogram/session-state.json`

当提供 `--run-root` 或 `WORKFLOWPROGRAM_RUN_ROOT` 时：

- 会话文件写入：`<RUN_ROOT>/state-bus/session-state.json`
- 事件日志追加到：`<RUN_ROOT>/events.jsonl`

## 常用命令

### 初始化 RUN_ROOT 对齐的会话

```bash
python3 .claude/scripts/state-bus.py init   --run-root "$TARGET_ROOT/.workflowprogram/runs/<run-id>"   --command "/workflowprogram-develop minimal-workflow"   --max-turns 100
```

### Stage 执行流程

```bash
python3 .claude/scripts/state-bus.py transition   --run-root "$TARGET_ROOT/.workflowprogram/runs/<run-id>"   --stage explore

python3 .claude/scripts/state-bus.py write   --run-root "$TARGET_ROOT/.workflowprogram/runs/<run-id>"   --stage explore   --key requirements   --value "为当前项目设计最小 workflow"

python3 .claude/scripts/state-bus.py checkpoint   --run-root "$TARGET_ROOT/.workflowprogram/runs/<run-id>"   --stage explore
```

### 查看状态

```bash
python3 .claude/scripts/state-bus.py status --run-root "$TARGET_ROOT/.workflowprogram/runs/<run-id>"
python3 .claude/scripts/state-bus.py history --run-root "$TARGET_ROOT/.workflowprogram/runs/<run-id>"
python3 .claude/scripts/state-bus.py checkpoints --run-root "$TARGET_ROOT/.workflowprogram/runs/<run-id>"
```

## 数据结构

### session-state.json

```json
{
  "meta": {
    "session_id": "uuid",
    "command": "/workflowprogram-develop minimal-workflow",
    "status": "running",
    "created_at": "2026-04-03T12:00:00Z"
  },
  "state": {
    "current_stage": "design",
    "stage_history": ["explore"],
    "turn_count": 2,
    "max_turns": 100,
    "run_root": "/abs/path/to/TARGET_ROOT/.workflowprogram/runs/<run-id>"
  },
  "data_bus": {
    "explore": {
      "requirements": "为当前项目设计最小 workflow"
    }
  },
  "checkpoints": [],
  "debug": {
    "performance": {
      "tokens_input": 0,
      "tokens_output": 0,
      "api_calls": 0
    }
  }
}
```

### events.jsonl

当提供 `RUN_ROOT` 时，以下动作会向 `events.jsonl` 追加事件：

- `init`
- `write`
- `transition`
- `checkpoint`
- `restore`

事件示例：

```json
{"ts":"2026-04-03T12:00:03Z","type":"StateBusTransition","stage":"design","source":"state-bus","status":"ok","message":"Transitioned from explore to design"}
```

## 与 Phase 3 的关系

- `tools/runtime_smoke.py` 负责创建 `RUN_ROOT`、调用 Claude CLI、写运行报告
- `state-bus.py` 负责可选的阶段状态持久化和检查点
- 两者共享 `RUN_ROOT` 和 `events.jsonl` 的基本约定，但 `runtime_smoke.py` 仍是主验证入口
