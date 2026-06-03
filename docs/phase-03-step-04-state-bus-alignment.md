# Phase 3 Step 4 State Bus 对齐说明

## 目标

把 `state-bus.py` 从“默认写入源码仓 `.claude/`”调整为“优先对齐 `RUN_ROOT`”，同时明确它在 Phase 3 中只是辅助状态工具，不是主 runtime harness。

## 改动内容

### 1. 默认路径调整

旧默认路径：

- `.claude/session-state.json`

新默认路径：

- `.workflowprogram/session-state.json`

优先级：

1. `--session`
2. `WORKFLOWPROGRAM_SESSION_FILE`
3. `--run-root`
4. `WORKFLOWPROGRAM_RUN_ROOT`
5. `.workflowprogram/session-state.json`

### 2. RUN_ROOT 对齐

当提供 `--run-root` 或 `WORKFLOWPROGRAM_RUN_ROOT` 时：

- 会话状态写入 `<RUN_ROOT>/state-bus/session-state.json`
- 事件追加到 `<RUN_ROOT>/events.jsonl`

### 3. 事件补充

`state-bus.py` 现在会在以下动作追加结构化事件：

- `StateBusInit`
- `StateBusWrite`
- `StateBusTransition`
- `StateBusCheckpoint`
- `StateBusRestore`

### 4. 角色边界

保留结论：

- `tools/runtime_smoke.py` 仍然是 Phase 3 的主动态验证入口
- `state-bus.py` 是开发态辅助工具
- 不要求每个 workflow 运行都必须显式调用 `state-bus.py`

## 验证方式

```bash
python3 -m py_compile .claude/scripts/state-bus.py
python3 .claude/scripts/state-bus.py init --run-root /tmp/workflowprogram-run --command "/workflowprogram-develop demo"
python3 .claude/scripts/state-bus.py transition --run-root /tmp/workflowprogram-run --stage explore
```

验收标准：

- `/tmp/workflowprogram-run/state-bus/session-state.json` 生成成功
- `/tmp/workflowprogram-run/events.jsonl` 生成成功
- `status` 能显示 session file 和 event file
