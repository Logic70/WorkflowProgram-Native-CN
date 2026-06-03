# Phase 5 实施计划

## 1. Phase 目标

Phase 5 只解决两个生命周期缺口：

1. **目标项目资产所有权与更新契约落地**
2. **安装产物可追溯性落地**

本阶段完成后，应达到以下状态：

1. `workflowprogram-develop` 不再把“直接写 `TARGET_ROOT/.claude/`”当作默认路径。
2. 仓库提供统一的 managed asset 工具，用于 plan / apply staged 候选资产。
3. `TARGET_ROOT/.workflowprogram/managed-files.json` 具备最小可用的 manifest 语义。
4. `dist/plugin/` 构建后会生成 `build-manifest.json`，记录版本、commit 和产物摘要。
5. runtime smoke 会把所使用的 build manifest 纳入 `RUN_ROOT` 证据。
6. 结构验证会检查 managed asset 工具和 build manifest 契约。

## 2. 本阶段不处理

- marketplace 正式发布流程定案
- 离线安装、团队分发策略
- 插件升级 / 回滚 / 卸载的最终用户脚本
- `RUN_ROOT` retention / cleanup 自动化
- 目标项目写入失败后的完整事务回滚

## 3. 影响范围

### 3.1 新增

- `.claude/scripts/managed-assets.py`
- `docs/phase-05-implementation-plan.md`

### 3.2 更新

- `.claude/skills/workflowprogram-develop/SKILL.md`
- `.claude/commands/develop.md`
- `tools/build_plugin.py`
- `tools/runtime_smoke.py`
- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`
- `README.md`
- `.claude-plugin/README.md`
- `validation-report.md`

## 4. 文件动作清单

| 文件/目录 | 动作 | 概述 |
|---|---|---|
| `.claude/scripts/managed-assets.py` | 新增 | 负责 plan/apply staged 候选资产，维护 managed-files.json，输出冲突证据 |
| `.claude/skills/workflowprogram-develop/SKILL.md` | 更新 | 把“先候选、后应用”写成主入口约束 |
| `.claude/commands/develop.md` | 更新 | 补 staged candidate + managed-assets 应用流程 |
| `tools/build_plugin.py` | 更新 | 复制完整脚本集，生成 `dist/plugin/build-manifest.json` |
| `tools/runtime_smoke.py` | 更新 | 将 build manifest 复制到 `RUN_ROOT/outputs/` |
| `.claude/scripts/validate-workflow.py` | 更新 | 校验 managed-assets 工具、plugin metadata 和 build manifest |
| `.claude/scripts/validate-workflow.ps1` | 更新 | 与 Python 版保持同一契约 |
| `README.md` | 更新 | 说明 managed asset 流程与 build manifest |
| `.claude-plugin/README.md` | 更新 | 说明安装产物中的 trace manifest |
| `validation-report.md` | 更新 | 记录 Phase 5 验证结果 |

## 5. 执行步骤

### Step 1: 定义候选资产写入路径

目标：统一要求先把候选文件写入 `RUN_ROOT/outputs/candidate/.claude/`。

### Step 2: 实现 managed asset 工具

目标：提供 `plan` 和 `apply-staged` 两个最小能力：

- 识别可安全创建 / 更新的 managed 文件
- 阻止覆盖 unmanaged 或 drifted 文件
- 将冲突候选保留在 `RUN_ROOT/outputs/conflicts/`
- 更新 `TARGET_ROOT/.workflowprogram/managed-files.json`

### Step 3: 实现产物 trace manifest

目标：让每次 `build_plugin.py` 都生成可追溯的 `dist/plugin/build-manifest.json`。

最低字段：

- `plugin_name`
- `plugin_version`
- `generated_at`
- `source_commit`
- `source_dirty`
- `files[]`（带 `path` 和 `sha256`）

### Step 4: 接入验证链

目标：让 source validator 和 runtime smoke 都感知新契约。

### Step 5: 回写文档和验证报告

目标：让 README、插件 README、主设计和 validation report 统一到 Phase 5 后的口径。

## 6. 风险点

### 风险 1：managed-assets 工具存在，但入口不强制使用

控制方式：

- 修改 `workflowprogram-develop`
- 修改 `/develop` 兼容命令

### 风险 2：trace manifest 存在，但没有进入运行证据

控制方式：

- `runtime_smoke.py` 把 `build-manifest.json` 复制到 `RUN_ROOT/outputs/`

### 风险 3：build 输出包含脚本，但生成头破坏可执行性

控制方式：

- `build_plugin.py` 对 markdown 与脚本采用不同 banner 规则

## 7. 验证方式

```bash
python3 tools/build_plugin.py
python3 .claude/scripts/validate-workflow.py
powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1
python3 tools/runtime_smoke.py --fixture empty-project --json
```

managed-assets 脚本级验证：

```bash
python3 .claude/scripts/managed-assets.py plan --target-root <tmp-target> --run-root <tmp-run> --source-root <tmp-run>/outputs/candidate/.claude --json
python3 .claude/scripts/managed-assets.py apply-staged --target-root <tmp-target> --run-root <tmp-run> --source-root <tmp-run>/outputs/candidate/.claude --json
```

## 8. 完成定义

满足以下条件即视为 Phase 5 完成：

1. managed asset 工具可生成 plan 和 apply 结果。
2. 冲突文件不会被静默覆盖。
3. `managed-files.json` 会记录已应用文件的 hash 和 producer version。
4. `build_plugin.py` 会生成 `dist/plugin/build-manifest.json`。
5. validator 会检查 managed asset 工具和 trace manifest。
6. runtime smoke 会把 build manifest 写入 `RUN_ROOT/outputs/`。
7. README 与插件 README 不再把目标项目写入描述成“直接覆盖”。
