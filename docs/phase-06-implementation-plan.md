# Phase 6 实施计划

## 1. Phase 目标

Phase 6 聚焦两项能力工程化：

1. **Stage 执行封装落地**
   - 将 Stage 执行过程明确映射到 `skill_node/agent_node/script_node/gate_node`。
   - 让 lowlevel 设计可以直接指导最终 workflow 生成。

2. **运行时进展与关键节点结果可见化**
   - 在运行过程中持续向用户提供当前进展与历史关键节点结果。
   - 除 `state/events` 外，新增用户可读与机读进展资产。

## 2. 完成定义

满足以下条件视为完成：

1. 仓库新增统一进展脚本：`.claude/scripts/stage-progress.py`。
2. `develop` 与 `workflowprogram-develop` 明确要求每个 Stage 调用进展脚本。
3. lowlevel 文档明确 Stage 封装矩阵与进展播报契约。
4. `validate-workflow.py/.ps1` 把 `stage-progress.py` 纳入必检项。
5. 构建产物 `dist/plugin/` 包含 `scripts/stage-progress.py`。

## 3. 影响范围

### 3.1 新增

- `.claude/scripts/stage-progress.py`
- `docs/phase-06-implementation-plan.md`

### 3.2 更新

- `.claude/commands/develop.md`
- `.claude/skills/workflowprogram-develop/SKILL.md`
- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`
- `docs/workflowprogram-stage-lowlevel-design.md`

## 4. 执行步骤

### Step 1: 定义进展资产契约

定义以下资产：

- `RUN_ROOT/outputs/progress/current-progress.json`
- `RUN_ROOT/outputs/progress/milestones.jsonl`
- `RUN_ROOT/outputs/progress/user-progress.md`

### Step 2: 实现进展脚本

实现 `stage-progress.py update`，支持：

- 写入当前阶段进展
- 追加里程碑事件
- 生成用户可读进展摘要

### Step 3: 接入 Stage 主链

在 `develop` 与 `workflowprogram-develop` 中明确：

- Stage 开始时记录 `StageStarted`
- 关键节点后记录 `StageCheckpoint`
- Stage 完成时记录 `StageCompleted`

### Step 4: 同步校验链

更新 Python/PowerShell 校验脚本：

- 源码层检查 `stage-progress.py`
- 构建层检查 `dist/plugin/scripts/stage-progress.py`
- build-manifest 必须包含 `scripts/stage-progress.py`

### Step 5: 验证

执行：

```bash
python3 .claude/scripts/stage-progress.py update --run-root /tmp/wf-run --stage S0 --node route_intent --event StageStarted --status running --percent 5 --result "intent routing started"
python3 tools/build_plugin.py
python3 .claude/scripts/validate-workflow.py
powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1
```

## 5. 风险与控制

### 风险 1：仅文档接入，未形成可执行约束

控制：验证脚本必须检查 `stage-progress.py` 与 dist 产物。

### 风险 2：进展播报与真实 Stage 状态不一致

控制：进展脚本写入必须包含 `stage/node/status/result`，并由 Stage 执行流程显式调用。

### 风险 3：进展信息过长影响可读性

控制：`user-progress.md` 仅保留当前状态 + 最近 3 个关键节点。

