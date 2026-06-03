# Phase 4 实施计划

> Historical Note
>
> 本文档保留为 Phase 4 的迁移计划记录，不再作为当前结构真源。
> 当前真源和已关闭决策见 [workflowprogram-design-status.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-design-status.md)。

## 1. Phase 目标

Phase 4 只解决一个问题：**结束迁移期兼容层，把仓库收口为 `.claude/` 源码层 + `dist/plugin/` 安装产物的双层结构。**

本阶段完成后，应达到以下状态：

1. 根级 `commands/`、`skills/`、`agents/`、`rules/`、`scripts/` 兼容目录被移除。
2. `tools/sync_plugin_assets.py` 被移除，不再保留双构建链。
3. `README.md`、`CLAUDE.md`、`.claude-plugin/README.md` 只描述 `.claude/` 和 `dist/plugin/`。
4. 主验证脚本会检查旧兼容层和旧同步脚本已经不存在。
5. `dist/plugin/` 仍可由 `tools/build_plugin.py` 重新生成。

## 2. 本阶段不处理

- `dist/plugin/commands/` 的移除
- `.claude/commands/` 的移除
- agent teams 增强模式落地
- Claude CLI 登录状态问题

## 3. 影响范围

### 3.1 删除

- `commands/`
- `skills/`
- `agents/`
- `rules/`
- `scripts/`
- `tools/sync_plugin_assets.py`

### 3.2 更新

- `README.md`
- `CLAUDE.md`
- `.claude-plugin/README.md`
- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`
- `validation-report.md`

### 3.3 归档

- `review_report.md`
- `实施方案V3.md`
- `实施计划-Plugin架构迁移.md`

## 4. 文件动作清单

| 文件/目录 | 动作 | 概述 |
|---|---|---|
| `commands/` | 删除 | 移除根级迁移期命令兼容层 |
| `skills/` | 删除 | 移除根级迁移期技能兼容层 |
| `agents/` | 删除 | 移除根级迁移期 agent 兼容层 |
| `rules/` | 删除 | 移除根级迁移期规则兼容层 |
| `scripts/` | 删除 | 移除根级迁移期脚本兼容层 |
| `tools/sync_plugin_assets.py` | 删除 | 移除旧同步构建脚本，仅保留 `build_plugin.py` |
| `README.md` | 更新 | 删除根级兼容层描述与旧同步命令 |
| `CLAUDE.md` | 更新 | 删除根级兼容层描述，强调源码层与安装产物层 |
| `.claude-plugin/README.md` | 更新 | 删除迁移期兼容层描述，保留 `dist/plugin/` 开发验证说明 |
| `.claude/scripts/validate-workflow.py` | 更新 | 新增“旧兼容层不存在”和“旧同步脚本不存在”检查 |
| `.claude/scripts/validate-workflow.ps1` | 更新 | 与 Python 版保持一致 |
| `review_report.md` | 归档 | 移入 `docs/archive/`，避免继续充当活文档 |
| `实施方案V3.md` | 归档 | 移入 `docs/archive/` |
| `实施计划-Plugin架构迁移.md` | 归档 | 移入 `docs/archive/` |

## 5. 执行步骤

### Step 1: 审计仍在引用旧兼容层的活文档

目标：只更新活文档，不重写历史 phase 文档。

### Step 2: 更新主文档和验证器

目标：让仓库的正式说明与验证规则先切换到最终结构。

### Step 3: 删除根级兼容层和旧同步脚本

目标：移除重复资产和多余构建链。

### Step 4: 归档历史方案文档

目标：把旧迁移方案移出根目录，避免继续误导。

### Step 5: 重新构建并验证

目标：确认 `build_plugin.py`、结构校验和 runtime smoke 仍可工作。

## 6. 风险点

### 风险 1：删除兼容层后文档或脚本仍引用旧路径

控制方式：

- 先更新验证器，再删除目录
- 删除后做全局 `rg` 检查

### 风险 2：历史设计文档仍大量引用旧模型

控制方式：

- 活文档更新
- 历史方案移动到 `docs/archive/`

### 风险 3：`dist/plugin/` 构建链被误伤

控制方式：

- 保持 `tools/build_plugin.py` 不变
- 删除后立即重建 `dist/plugin/`

## 7. 验证方式

```bash
python3 tools/build_plugin.py
python3 .claude/scripts/validate-workflow.py
powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1
python3 tools/runtime_smoke.py --fixture empty-project --json
```

补充检查：

```bash
rg -n "tools/sync_plugin_assets|根级兼容层|commands/.*迁移期|skills/.*迁移期|agents/.*迁移期|rules/.*迁移期|scripts/.*迁移期" README.md CLAUDE.md .claude-plugin/README.md
```

## 8. 完成定义

满足以下条件即视为 Phase 4 完成：

1. 根级兼容目录已删除。
2. `tools/sync_plugin_assets.py` 已删除。
3. 主文档不再把根级兼容层当作正式结构。
4. 验证器会阻止旧兼容层回流。
5. `tools/build_plugin.py`、Python 校验、PowerShell 校验、runtime smoke 全部通过或正确返回 `ENVIRONMENT-SKIP`。
