# Phase 1 Step 3 `tools/build_plugin.py` 实现计划

## 1. 目标

本步骤的目标是：

> 实现 `tools/build_plugin.py`，把当前分散的插件构建输出统一收口到 `dist/plugin/`。

这一步只迁移**产物目录**，不改变以下内容：

- 不切换到 skills-first 注册模型
- 不删除根级兼容目录
- 不改写 `.claude/commands/*.md` 的语义
- 不改写 `.claude/skills/*` 的能力内容
- 不引入动态测试

## 2. 输入与输出

### 2.1 输入

`tools/build_plugin.py` 的输入来源固定为：

- `.claude/agents/`
- `.claude/commands/`
- `.claude/skills/`
- `.claude/rules/constraints.md`
- `.claude/scripts/validate-workflow.ps1`
- `.claude-plugin/`

### 2.2 输出

输出目录固定为：

```text
dist/plugin/
├── .claude-plugin/
├── agents/
├── commands/
├── skills/
├── rules/
└── scripts/
```

## 3. 构建策略

### 3.1 总体策略

第一版 `build_plugin.py` 必须遵循：

- **保留现有兼容层语义**
- **只改变产物落点，不改变运行语义**
- **尽量复用 `sync_plugin_assets.py` 的已验证逻辑**

也就是说，第一版不是重设计构建器，而是把：

```text
.claude/ -> root/
```

改成：

```text
.claude/ + .claude-plugin/ -> dist/plugin/
```

### 3.2 目录重建策略

脚本执行时应：

1. 删除旧的 `dist/plugin/`（若存在）
2. 重新创建：
   - `dist/plugin/.claude-plugin/`
   - `dist/plugin/agents/`
   - `dist/plugin/commands/`
   - `dist/plugin/skills/`
   - `dist/plugin/rules/`
   - `dist/plugin/scripts/`

注意：

- 本步骤不动根级 `commands/skills/agents/rules/scripts`
- 只负责生成新的 `dist/plugin/`

## 4. 文件生成规则

### 4.1 自动生成头注释

所有从源码层生成到 `dist/plugin/` 的文件，都继续保留当前头注释：

```text
<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->
```

原因：

- 避免误编辑产物
- 和现有兼容层保持一致

### 4.2 Agents

来源：`.claude/agents/*.md`

目标：`dist/plugin/agents/*.md`

规则：

- 文件名不变
- 内容保持不变
- 增加自动生成头注释

### 4.3 Rules

来源：`.claude/rules/constraints.md`

目标：`dist/plugin/rules/constraints.md`

规则：

- 原样复制
- 增加自动生成头注释

### 4.4 Skills

来源：`.claude/skills/*`

目标：`dist/plugin/skills/*`

规则：

- 保持目录结构
- 原样复制每个文件
- 增加自动生成头注释

### 4.5 Commands

来源：`.claude/commands/*.md`

目标：`dist/plugin/commands/*.md`

规则：

- 增加自动生成头注释
- 增加 frontmatter：
  - `description`
  - `argument-hint`
- 应用路径替换：
  - `.claude/skills/develop/spec-template.md` -> `${CLAUDE_PLUGIN_ROOT}/skills/develop/spec-template.md`
  - `.claude/rules/constraints.md` -> `${CLAUDE_PLUGIN_ROOT}/rules/constraints.md`
  - `.claude/scripts/validate-workflow.ps1` -> `${CLAUDE_PLUGIN_ROOT}/scripts/validate-workflow.ps1`

### 4.6 Command Wrapper Skills

来源：`.claude/commands/*.md`

目标：`dist/plugin/skills/command-*/SKILL.md`

规则：

- 每个 command 生成一个 wrapper skill
- 增加自动生成头注释
- 增加 frontmatter：
  - `name`
  - `description`
  - `version`
  - `argument-hint`
  - `disable-model-invocation: true`
- 主体内容复用 command 正文
- 应用同样的路径替换

### 4.7 Scripts

来源：`.claude/scripts/validate-workflow.ps1`

目标：`dist/plugin/scripts/validate-workflow.ps1`

规则：

- 原样复制
- 增加自动生成头注释

当前明确不进入 `dist/plugin/scripts/` 的文件：

- `state-bus.py`
- `validate-workflow.py`
- `verify-plugin-load.sh`

### 4.8 Plugin Manifest

来源：`.claude-plugin/*`

目标：`dist/plugin/.claude-plugin/*`

规则：

- 直接复制
- 不加自动生成头注释

原因：

- 这些文件本身就是插件清单，不是从 `.claude/` 派生出来的

## 5. 代码结构建议

`tools/build_plugin.py` 建议最少拆成这些函数：

- `copy_with_header(src, dst)`
- `copy_tree_with_header(src_dir, dst_dir)`
- `render_command(src, dst, desc, hint)`
- `render_command_wrapper(src, dst, name, desc, hint)`
- `copy_plugin_manifest(src_dir, dst_dir)`
- `prepare_output_dirs(root)`

同时保留这些常量：

- `COMMAND_DESCRIPTIONS`
- `REPLACEMENTS`
- `HEADER`

## 6. 与旧脚本的关系

### 6.1 `sync_plugin_assets.py` 的处置方式

本步骤不删除旧脚本。

建议处理方式：

- 先保留 `tools/sync_plugin_assets.py`
- 新增 `tools/build_plugin.py`
- 后续在 Phase 1 收尾或 Phase 4 中再决定是否删除旧脚本

### 6.2 为什么不直接重命名旧脚本

因为当前目标不是“原地替换”，而是：

- 保留现有可运行路径
- 新增正式安装产物路径
- 在迁移期间允许两套输出并存

## 7. 风险点

### 风险 1：路径替换遗漏

如果 `REPLACEMENTS` 没有完整迁移到 `build_plugin.py`，则生成产物中的路径会断链。

控制方式：

- 第一版直接复用旧脚本中的替换表
- 不在本步骤引入新的路径语义

### 风险 2：plugin manifest 复制后路径假设失效

如果 `.claude-plugin/` 被复制到 `dist/plugin/.claude-plugin/` 后，外部安装逻辑对相对路径有额外要求，可能需要二次调整。

控制方式：

- 第一版先原样复制
- 在后续安装验证中再校正

### 风险 3：生成结果和旧兼容层不一致

如果 `dist/plugin/` 产物和现有根级兼容层差异过大，后续会难以判断是构建器错误还是架构差异。

控制方式：

- 第一版以“语义等价”为目标
- 对比关键产物目录的数量和关键文件内容

## 8. 验证方式

本步骤完成后应做以下验证：

### 8.1 目录验证

- `dist/plugin/` 成功生成
- 六类目录均存在：
  - `.claude-plugin/`
  - `agents/`
  - `commands/`
  - `skills/`
  - `rules/`
  - `scripts/`

### 8.2 文件数量验证

应满足大致一致关系：

- `dist/plugin/agents/` = 8 个文件
- `dist/plugin/commands/` = 6 个文件
- `dist/plugin/skills/` >= 16 个文件
- `dist/plugin/rules/` = 1 个文件
- `dist/plugin/scripts/` = 1 个文件
- `dist/plugin/.claude-plugin/` = 3 个文件

### 8.3 内容验证

抽样检查至少包括：

- `dist/plugin/agents/workflow-designer.md`
- `dist/plugin/commands/develop.md`
- `dist/plugin/skills/command-develop/SKILL.md`
- `dist/plugin/rules/constraints.md`
- `dist/plugin/scripts/validate-workflow.ps1`
- `dist/plugin/.claude-plugin/plugin.json`

其中要确认：

- 自动生成头注释是否存在
- 路径替换是否生效
- wrapper frontmatter 是否存在
- plugin manifest 是否被正确复制

### 8.4 回归验证

- 根级兼容目录仍保持不变
- 旧构建链仍可保留
- 新增构建链不破坏当前仓库已有结构

## 9. 本步骤完成定义

只有以下条件全部满足，才能认为 `Phase 1 / Step 3` 完成：

1. `tools/build_plugin.py` 已创建
2. `dist/plugin/` 能成功生成
3. 产物结构符合 Step 2 定义
4. 关键产物内容与旧兼容层语义一致
5. 旧兼容层仍然保留且未被破坏

## 10. 下一步

本步骤完成后，下一步应进入：

- `Phase 1 / Step 4`：保留旧同步链并更新文档定位

在进入 Step 4 前，不应提前删除旧兼容目录，也不应在本步骤里同时引入 skills-first 重构。
