# Phase 1 Step 1 映射关系审计

## 1. 审计目的

本文档用于回答 `Phase 1 / Step 1` 的核心问题：

> 当前 `.claude/` 源资产，是如何映射到现有根级兼容插件目录的？

这份审计结论将直接作为后续 `tools/build_plugin.py` 的实现依据。

## 2. 审计范围

本次审计覆盖以下对象：

### 2.1 源码层

- `.claude/agents/`
- `.claude/commands/`
- `.claude/skills/`
- `.claude/rules/`
- `.claude/scripts/`
- `.claude/settings.json`
- `.claude/settings.local.json`

### 2.2 当前根级兼容层

- `agents/`
- `commands/`
- `skills/`
- `rules/`
- `scripts/`

### 2.3 插件清单层

- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `.claude-plugin/README.md`

## 3. 审计方法

本次审计通过以下方式完成：

1. 列出 `.claude/` 下的所有源文件
2. 列出根级兼容目录中的所有文件
3. 对代表性文件进行内容抽样
4. 结合 `tools/sync_plugin_assets.py` 的逻辑判断其映射规则

## 4. 现状汇总

### 4.1 源码层文件数量

- `.claude/agents/`: 8 个文件
- `.claude/commands/`: 6 个文件
- `.claude/skills/`: 10 个文件
- `.claude/rules/`: 1 个文件
- `.claude/scripts/`: 4 个文件

总计：29 个源文件（不含 `.claude/settings*.json`）

### 4.2 当前根级兼容层文件数量

- `agents/`: 8 个文件
- `commands/`: 6 个文件
- `skills/`: 16 个文件
- `rules/`: 1 个文件
- `scripts/`: 1 个文件

总计：32 个兼容层文件

### 4.3 关键结论

当前映射不是“全量复制”，而是三种模式混合：

1. **原样复制 + 头注释**
2. **转换生成**
3. **完全不进入根级兼容层**

也就是说，当前根级兼容层并不是 `.claude/` 的一份完整镜像。

## 5. 映射规则分类

### 5.1 原样复制 + 头注释

以下内容会被复制到根级兼容目录，并在文件顶部加上：

```text
<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->
```

#### A. Agents

源：`.claude/agents/*.md`

目标：`agents/*.md`

映射规则：

- 文件名不变
- 内容基本不变
- 仅额外加自动生成头注释

结论：

- 这是标准的“源码层 agent -> 兼容运行层 agent”复制模式
- 后续应迁移为：`.claude/agents/ -> dist/plugin/agents/`

#### B. Rules

源：`.claude/rules/constraints.md`

目标：`rules/constraints.md`

映射规则：

- 文件路径变化
- 内容不改，仅增加自动生成头注释

#### C. Skills（非 command wrapper）

源：`.claude/skills/*`

目标：`skills/*`

映射规则：

- 目录结构保持不变
- 每个文件原样复制
- 增加自动生成头注释

例如：

- `.claude/skills/commit/SKILL.md` -> `skills/commit/SKILL.md`
- `.claude/skills/develop/spec-template.md` -> `skills/develop/spec-template.md`
- `.claude/skills/develop/test-scenarios-template.md` -> `skills/develop/test-scenarios-template.md`
- `.claude/skills/develop/yaml-spec-template.md` -> `skills/develop/yaml-spec-template.md`

#### D. Scripts（仅部分）

源：`.claude/scripts/validate-workflow.ps1`

目标：`scripts/validate-workflow.ps1`

映射规则：

- 原样复制
- 增加自动生成头注释

注意：`.claude/scripts/` 并不是全量进入根级兼容层，只有这一项被复制。

### 5.2 转换生成

#### A. Commands -> 根级 commands

源：`.claude/commands/*.md`

目标：`commands/*.md`

映射规则：

- 增加自动生成头注释
- 在正文前自动插入 frontmatter：
  - `description`
  - `argument-hint`
- 对正文中的部分路径做替换：
  - `.claude/skills/develop/spec-template.md` -> `${CLAUDE_PLUGIN_ROOT}/skills/develop/spec-template.md`
  - `.claude/rules/constraints.md` -> `${CLAUDE_PLUGIN_ROOT}/rules/constraints.md`
  - `.claude/scripts/validate-workflow.ps1` -> `${CLAUDE_PLUGIN_ROOT}/scripts/validate-workflow.ps1`

这说明根级 `commands/*.md` 不是简单复制，而是“带插件路径适配的生成产物”。

#### B. Commands -> `skills/command-*` wrapper

源：`.claude/commands/*.md`

目标：`skills/command-*/SKILL.md`

映射规则：

- 每个 command 额外生成一个 skill wrapper
- 增加自动生成头注释
- 自动插入 frontmatter：
  - `name`
  - `description`
  - `version`
  - `argument-hint`
  - `disable-model-invocation: true`
- 主体内容直接复用 command 正文
- 仍保留同样的 `${CLAUDE_PLUGIN_ROOT}` 路径替换

这一层是当前仓库把“commands 兼容转换为 skills”的关键机制。

### 5.3 完全未进入根级兼容层

以下源资产当前不会出现在根级兼容目录中：

#### A. `.claude/settings.json`

- 没有根级对应文件
- 当前根级兼容运行层并不依赖 `settings.json` 驱动

#### B. `.claude/settings.local.json`

- 没有根级对应文件
- 这是本地配置，本来就不应进入安装产物

#### C. `.claude/scripts/state-bus.py`

- 当前未进入根级兼容层
- 属于被源码引用但未正式暴露的辅助脚本

#### D. `.claude/scripts/validate-workflow.py`

- 当前未进入根级兼容层
- 说明跨平台校验尚未进入插件运行层

#### E. `.claude/scripts/verify-plugin-load.sh`

- 当前未进入根级兼容层
- 说明插件发现验证脚本属于仓库内部验证工具，而不是插件运行资产

## 6. `.claude-plugin/` 的实际位置

`.claude-plugin/` 当前处于一个特殊状态：

- 它存在于仓库根目录
- 它不是由 `tools/sync_plugin_assets.py` 生成的
- 它也不属于根级兼容目录的一部分

也就是说，当前仓库实际上有三层：

1. 源码层：`.claude/`
2. 根级兼容层：`commands/skills/agents/rules/scripts`
3. 插件清单层：`.claude-plugin/`

这正是为什么 `Phase 1` 必须把安装产物统一收口到 `dist/plugin/`。

## 7. 当前映射矩阵

| 源类别 | 源位置 | 当前目标位置 | 处理方式 | 备注 |
|---|---|---|---|---|
| agents | `.claude/agents/*.md` | `agents/*.md` | 复制 + 头注释 | 后续应迁移到 `dist/plugin/agents/` |
| commands | `.claude/commands/*.md` | `commands/*.md` | 转换生成 | 加 frontmatter + 路径替换 |
| commands | `.claude/commands/*.md` | `skills/command-*/SKILL.md` | wrapper 生成 | 兼容层 |
| skills | `.claude/skills/*` | `skills/*` | 复制 + 头注释 | 目录结构保持 |
| rules | `.claude/rules/constraints.md` | `rules/constraints.md` | 复制 + 头注释 | 单文件 |
| scripts | `.claude/scripts/validate-workflow.ps1` | `scripts/validate-workflow.ps1` | 复制 + 头注释 | 仅此一项进入兼容层 |
| scripts | `.claude/scripts/state-bus.py` | 无 | 未映射 | 内部脚本 |
| scripts | `.claude/scripts/validate-workflow.py` | 无 | 未映射 | 内部脚本 |
| scripts | `.claude/scripts/verify-plugin-load.sh` | 无 | 未映射 | 内部脚本 |
| settings | `.claude/settings.json` | 无 | 未映射 | 当前运行层不靠 settings 驱动 |
| settings.local | `.claude/settings.local.json` | 无 | 未映射 | 本地配置 |
| plugin manifest | `.claude-plugin/*` | 无统一产物位置 | 独立保留 | 应并入 `dist/plugin/` |

## 8. 对 `build_plugin.py` 的直接要求

基于当前映射关系，`tools/build_plugin.py` 第一版至少要满足以下要求：

1. **保留现有有效映射语义**
   - agents 继续复制
   - commands 继续生成
   - command wrapper 继续生成
   - skills/rules 继续复制
   - 保留路径替换逻辑

2. **把当前分散层收口到 `dist/plugin/`**
   - `dist/plugin/agents/`
   - `dist/plugin/commands/`
   - `dist/plugin/skills/`
   - `dist/plugin/rules/`
   - `dist/plugin/scripts/`
   - `dist/plugin/.claude-plugin/`

3. **明确哪些脚本进入插件产物，哪些只留在仓库内部**
   - 当前最保守做法：先只迁移 `validate-workflow.ps1`
   - `state-bus.py`、`validate-workflow.py`、`verify-plugin-load.sh` 是否进入产物，需要后续明确

4. **保留 Agent 双层定义模型**
   - 源码层：`.claude/agents/`
   - 产物层：`dist/plugin/agents/`

## 9. 本步骤的结论

`Phase 1 / Step 1` 的结论是：

1. 当前根级兼容层不是 `.claude/` 的完整镜像，而是“复制 + 生成 + 遗漏”的混合结构。
2. `agents` 其实已经体现出“源码定义 -> 运行层暴露”的雏形，只是当前暴露位置还是根级 `agents/`，而不是 `dist/plugin/agents/`。
3. `commands` 当前承担了两层产物：
   - 根级 `commands/*.md`
   - `skills/command-*` wrapper
4. `.claude-plugin/` 当前游离于构建链之外，是后续必须收口到 `dist/plugin/` 的对象。
5. `build_plugin.py` 第一版应优先保持现有映射语义不变，只改变产物落点。

## 10. 下一步

本步骤完成后，下一步应进入：

- `Phase 1 / Step 2`：固定 `dist/plugin/` 的产物目录规范

在进入 Step 2 前，不应直接开始删除根级兼容目录，也不应提前改动 skills-first 入口层。
