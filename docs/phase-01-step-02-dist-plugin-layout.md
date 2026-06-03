# Phase 1 Step 2 `dist/plugin/` 产物目录规范

## 1. 目标

本文档用于固定 `Phase 1 / Step 2` 的结论：

> `dist/plugin/` 作为唯一安装产物目录，最终应包含哪些内容、哪些是兼容层、哪些暂时不进入产物。

这份规范会直接指导后续 `tools/build_plugin.py` 的实现。

## 2. 设计原则

`dist/plugin/` 的设计遵循以下原则：

1. **能运行的资产才进产物**
   - 进入 `dist/plugin/` 的内容必须是插件运行时会消费或直接依赖的内容。

2. **源码层和产物层严格分离**
   - `.claude/` 是源码真源
   - `dist/plugin/` 是运行产物

3. **先兼容，后收敛**
   - 第一版 `dist/plugin/` 保持与当前兼容层语义一致
   - 不在 Phase 1 直接消灭 `commands/` 或 `skills/command-*`

4. **插件清单必须并入产物**
   - `.claude-plugin/` 不能继续游离于构建链之外

## 3. `dist/plugin/` 第一版目录规范

第一版目标结构如下：

```text
dist/plugin/
├── .claude-plugin/
│   ├── plugin.json
│   ├── marketplace.json
│   └── README.md
├── agents/
├── commands/
├── skills/
├── rules/
└── scripts/
```

说明：

- 这是 **Phase 1 的兼容产物布局**
- 它的目标是先承接现有根级兼容层
- 不是最终最精简的稳态目录

## 4. 各目录的纳入规则

### 4.1 `.claude-plugin/`

状态：**必须进入产物**

纳入内容：

- `plugin.json`
- `marketplace.json`
- `README.md`

原因：

- 当前 `.claude-plugin/` 独立存在于仓库根目录
- 若继续不进入构建链，`dist/plugin/` 就不是真正完整安装产物

结论：

- `dist/plugin/.claude-plugin/` 是必需目录

### 4.2 `agents/`

状态：**必须进入产物**

来源：`.claude/agents/*.md`

纳入规则：

- 第一版全部复制到 `dist/plugin/agents/`
- 保留自动生成头注释
- 不改变内容语义

原因：

- 当前 agent 已经有明确的“源码定义 -> 运行层暴露”映射关系
- 只是当前暴露位置错误地停留在根级 `agents/`

结论：

- `dist/plugin/agents/` 是运行时 agent 暴露目录

### 4.3 `commands/`

状态：**Phase 1 保留，视为兼容层**

来源：`.claude/commands/*.md`

纳入规则：

- 继续生成到 `dist/plugin/commands/`
- 保留 frontmatter 注入逻辑
- 保留 `${CLAUDE_PLUGIN_ROOT}` 路径替换逻辑

原因：

- 当前仓库仍以 command 语义组织大部分工作流设计
- Phase 1 不负责 skills-first 重构
- 提前移除会增加迁移风险

结论：

- `dist/plugin/commands/` 在 Phase 1 中保留
- 但必须明确标记为迁移期兼容层

### 4.4 `skills/`

状态：**必须进入产物**

来源：

- `.claude/skills/*`
- `.claude/commands/*.md` 生成出的 `skills/command-*`

纳入规则：

- 现有 skills 全部复制到 `dist/plugin/skills/`
- 现有 command wrapper 继续生成到 `dist/plugin/skills/command-*`

原因：

- 当前兼容层仍依赖 `skills/command-*`
- 真正的 skills-first 重构在 Phase 2 处理

结论：

- `dist/plugin/skills/` 是第一版最核心的暴露目录
- 其中同时包含：
  - 原生 skills
  - command wrapper skills

### 4.5 `rules/`

状态：**必须进入产物**

来源：`.claude/rules/constraints.md`

纳入规则：

- 复制到 `dist/plugin/rules/constraints.md`
- 保留自动生成头注释

原因：

- 现有 command/skill 文本里直接引用 rules
- 不进产物会导致运行期断链

### 4.6 `scripts/`

状态：**第一版仅最小纳入**

来源：`.claude/scripts/*`

第一版只纳入：

- `validate-workflow.ps1`

第一版暂不纳入：

- `state-bus.py`
- `validate-workflow.py`
- `verify-plugin-load.sh`

原因：

- 当前兼容层中只有 `validate-workflow.ps1` 实际进入运行层
- 其余脚本还没有明确的插件运行时职责
- Phase 1 不扩大运行面，只保持现有有效行为

结论：

- `dist/plugin/scripts/` 第一版保守处理
- 后续再决定哪些脚本进入正式运行产物

## 5. 第一版明确不进入产物的内容

以下内容在 Phase 1 第一版中明确不进入 `dist/plugin/`：

### 5.1 `.claude/settings.json`

原因：

- 当前兼容层并不依赖它驱动运行
- 未来是否需要进入插件产物，取决于 Phase 2 的 skills-first 注册策略

### 5.2 `.claude/settings.local.json`

原因：

- 本地配置，不应进入安装产物

### 5.3 仓库根文档

暂不进入插件产物：

- `README.md`
- `CLAUDE.md`
- `lessons.md`
- `validation-report.md`

原因：

- 这些文件属于源码仓与开发过程文档
- 不是插件安装运行所必需的资产

## 6. 第一版兼容策略

`dist/plugin/` 第一版必须保留以下兼容行为：

1. 保留 `commands/`
2. 保留 `skills/command-*`
3. 保留 `${CLAUDE_PLUGIN_ROOT}` 路径替换
4. 保留自动生成头注释

这样做的目的不是长期维持兼容层，而是：

- 先把产物落点从根级迁到 `dist/plugin/`
- 再在后续 Phase 中逐步消除兼容层

## 7. 和现有根级兼容层的关系

Phase 1 中，`dist/plugin/` 与现有根级兼容层的关系应定义为：

- 根级 `commands/skills/agents/rules/scripts`：旧兼容层
- `dist/plugin/`：新的正式安装产物层

Phase 1 结束时，这两层会暂时并存。

但文档中应明确：

- 根级兼容层只是过渡资产
- `dist/plugin/` 才是后续唯一安装产物

## 8. 对 `build_plugin.py` 的直接要求

基于本规范，`build_plugin.py` 第一版至少要完成：

1. 清理并重建 `dist/plugin/`
2. 复制 `.claude-plugin/` 到 `dist/plugin/.claude-plugin/`
3. 复制 `.claude/agents/` 到 `dist/plugin/agents/`
4. 生成 `.claude/commands/` 到 `dist/plugin/commands/`
5. 复制 `.claude/skills/` 到 `dist/plugin/skills/`
6. 生成 `skills/command-*` 到 `dist/plugin/skills/`
7. 复制 `.claude/rules/constraints.md` 到 `dist/plugin/rules/constraints.md`
8. 复制 `.claude/scripts/validate-workflow.ps1` 到 `dist/plugin/scripts/validate-workflow.ps1`
9. 保留路径替换规则
10. 保留自动生成头注释

## 9. 本步骤结论

`Phase 1 / Step 2` 的结论是：

1. `dist/plugin/` 第一版应当承接当前根级兼容层的语义，而不是立即变成最终极简结构。
2. `dist/plugin/.claude-plugin/` 和 `dist/plugin/agents/` 是 Phase 1 中必须明确的新正式目录。
3. `commands/` 在 Phase 1 中仍保留，但仅作为迁移期兼容层。
4. `scripts/` 第一版只纳入最小有效集合，即 `validate-workflow.ps1`。
5. `settings.json` 和开发仓根文档暂不进入插件安装产物。

## 10. 下一步

本步骤完成后，下一步应进入：

- `Phase 1 / Step 3`：实现 `tools/build_plugin.py`

在进入 Step 3 前，不应提前删除旧兼容目录，也不应提前切换到 skills-first 注册模型。
