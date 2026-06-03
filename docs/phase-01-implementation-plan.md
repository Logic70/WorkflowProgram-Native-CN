# Phase 1 实施计划

## 1. Phase 目标

Phase 1 只解决一个问题：**收口源码层和安装产物层的边界**。

本阶段不处理：

- skills-first 入口重构
- 动态验证落地
- 旧兼容目录删除
- agent teams 增强模式

本阶段完成后，应达到以下状态：

1. `.claude/` 被明确固定为唯一源码真源。
2. `dist/plugin/` 被明确固定为唯一安装产物目录。
3. Agent 采用双层模型：源码定义在 `.claude/agents/`，运行时暴露在 `dist/plugin/agents/`。
4. 根级 `commands/skills/agents/rules/scripts` 被明确降级为迁移期兼容资产。
5. 仓库文档不再把根级兼容目录表述为长期维护目标。

## 2. 当前现状

当前实际状态如下：

- 源码层在 `.claude/`
- 插件清单在 `.claude-plugin/`
- 构建脚本是 `tools/sync_plugin_assets.py`
- 当前构建输出是根级目录：
  - `commands/`
  - `skills/`
  - `agents/`
  - `rules/`
  - `scripts/`

这套结构的问题是：

- 构建产物和源码在仓库顶层并列出现
- 开发者容易误编辑生成产物
- 文档会持续把“兼容层”误写成“正式层”
- 后续无法顺畅切换到真正的安装产物目录 `dist/plugin/`

## 3. 影响范围

本阶段会影响以下范围：

### 3.1 直接影响

- `tools/sync_plugin_assets.py`
- `.claude-plugin/README.md`
- `README.md`
- `CLAUDE.md`

### 3.2 间接影响

- `.claude-plugin/plugin.json`
- `.claude/agents/`
- 根级 `commands/`
- 根级 `skills/`
- 根级 `agents/`
- 根级 `rules/`
- 根级 `scripts/`

### 3.3 本阶段明确不动的范围

- `.claude/skills/` 具体能力内容
- `.claude/commands/` 具体语义
- `.claude/agents/` 提示词内容
- `tests/` 动态测试体系
- `validation-report.md` 的结构改版

## 4. 文件动作清单

### 4.1 新建

- `tools/build_plugin.py`
  - 用途：从 `.claude/` 构建 `dist/plugin/`

- `dist/plugin/.gitkeep`
  - 用途：显式标记产物目录

- `dist/plugin/agents/.gitkeep`
  - 用途：显式标记插件运行时 agent 暴露目录

### 4.2 更新

- `README.md`
  - 更新点：说明源码层与安装产物层的区别

- `CLAUDE.md`
  - 更新点：明确 `.claude/` 是真源，`dist/plugin/` 是产物

- `.claude-plugin/README.md`
  - 更新点：改为使用 `dist/plugin/` 进行本地安装/验证

### 4.3 替换

- `tools/sync_plugin_assets.py`
  - 处理方式：保留文件名还是替换为 `tools/build_plugin.py`，本阶段需要先确认
  - 建议：**新建 `tools/build_plugin.py`，暂时保留 `tools/sync_plugin_assets.py`，并将后者降级为过渡脚本**

### 4.4 暂不删除

以下对象本阶段不删除：

- `commands/`
- `skills/`
- `agents/`
- `rules/`
- `scripts/`

原因：

- 这些目录当前仍被现有插件封装方式使用
- 在 `dist/plugin/` 构建链稳定之前删除会直接破坏现有能力

## 5. 执行步骤

### Step 1: 审计现有映射关系

目标：确认 `.claude/` 与根级兼容目录的一一映射是否完整。

执行内容：

- 列出 `.claude/` 下所有会进入插件产物的文件
- 列出当前根级生成目录中的对应文件
- 单独确认 `.claude/agents/` 到插件运行时 `dist/plugin/agents/` 的映射规则
- 标记哪些资产是原样复制，哪些资产带路径替换，哪些资产带 wrapper 生成

产出：

- 一份映射表，作为 `build_plugin.py` 的实现依据

### Step 2: 设计 `dist/plugin/` 产物布局

目标：固定新的安装产物目录结构。

建议布局：

```text
dist/plugin/
├── commands/
├── skills/
├── agents/
├── rules/
├── scripts/
└── .claude-plugin/
```

需要明确：

- 是否保留 `commands/` 作为迁移期兼容层
- 是否继续生成 `skills/command-*`
- `.claude-plugin/plugin.json` 是否复制到产物中
- `.claude/agents/` 是否完整生成到 `dist/plugin/agents/`
- 运行时相对路径替换逻辑是否仍然使用 `${CLAUDE_PLUGIN_ROOT}`

产出：

- 固定的产物目录规范

### Step 3: 实现新的构建脚本

目标：创建 `tools/build_plugin.py`。

最低能力要求：

- 输入：`.claude/` + `.claude-plugin/`
- 输出：`dist/plugin/`
- 清理旧的 `dist/plugin/`
- 复制或生成：
  - `commands/`
  - `skills/`
  - `agents/`
  - `rules/`
  - `scripts/`
  - `.claude-plugin/`
- 明确将 `.claude/agents/` 构建为 `dist/plugin/agents/`
- 保留生成头注释
- 保留必要的路径替换逻辑

注意：

- 第一版可以先与 `sync_plugin_assets.py` 保持等价逻辑
- 目标是先转移产物目录，不是立即消灭兼容结构

### Step 4: 保留旧同步链作为过渡

目标：避免 Phase 1 期间破坏现有可用性。

处理方式：

- `tools/sync_plugin_assets.py` 先保留
- 文档中把它标记为过渡方案
- 所有新说明统一改为优先使用 `tools/build_plugin.py`

### Step 5: 更新文档

目标：让仓库的正式描述和 Phase 1 目标一致。

更新要点：

- `README.md`
  - 声明 `.claude/` 是源码层
  - 声明 `dist/plugin/` 是安装产物
  - 补充插件运行时模型
  - 明确根级同步目录是迁移期资产

- `CLAUDE.md`
  - 声明后续开发只应修改 `.claude/`
  - 不把根级目录描述为正式真源

- `.claude-plugin/README.md`
  - 本地验证示例改为基于 `dist/plugin/`
  - 安装说明区分开发安装和正式安装

## 6. 风险点

### 风险 1：构建脚本和 plugin manifest 不一致

风险描述：

- `dist/plugin/` 里的布局如果和 `.claude-plugin/plugin.json` 假设不一致，会导致安装失败或行为异常。

控制方式：

- 在写 `build_plugin.py` 前先固定产物目录规范
- 不在 Phase 1 同时重构 skills-first 入口

### 风险 2：根级兼容目录仍被脚本或文档隐式依赖

风险描述：

- 即使 `dist/plugin/` 建好了，当前某些脚本或使用说明可能仍默认依赖根级目录。

控制方式：

- 本阶段不删根级目录
- 先审计引用，再在后续 Phase 清理

### 风险 3：路径替换逻辑不完整

风险描述：

- 当前 `sync_plugin_assets.py` 会替换 `.claude/...` 为 `${CLAUDE_PLUGIN_ROOT}/...`
- 若新构建脚本漏掉这些替换，运行时会直接断链

控制方式：

- 先复用当前替换表
- Phase 1 只做产物目录迁移，不改引用语义

### 风险 4：开发者误以为根级兼容目录仍是主编辑入口

风险描述：

- 即使技术上切换完成，文档不收口也会造成长期误用

控制方式：

- Phase 1 的文档更新是强制项，不可省略

## 7. 验证方式

本阶段完成后，至少要通过以下检查：

### 7.1 构建验证

- `tools/build_plugin.py` 能成功执行
- `dist/plugin/` 能被完整生成
- 产物目录结构符合预期

### 7.2 一致性验证

- `dist/plugin/` 中的关键资产和 `.claude/` 真源一致
- 关键路径替换仍然有效
- 生成头注释仍然存在

### 7.3 文档验证

- `README.md` 不再把根级兼容目录描述为长期维护目标
- `CLAUDE.md` 明确 `.claude/` 是真源
- `.claude-plugin/README.md` 的本地安装说明切换到 `dist/plugin/`

### 7.4 回归安全验证

- 现有根级兼容目录暂时仍能工作
- 当前插件打包方式在迁移期不被破坏

### 7.5 Agent 暴露验证

- `.claude/agents/` 中的关键 agent 能正确生成到 `dist/plugin/agents/`
- 运行时说明不再把源码层 agent 误写成安装态目录

## 8. 执行边界

本阶段明确不做以下动作：

- 不删除根级兼容目录
- 不重写 `.claude/skills/*` 具体实现
- 不切换到 skills-first 注册
- 不实现运行时 smoke test
- 不引入 fixtures
- 不接入 agent teams

这些动作属于后续 Phase。

## 9. Phase 1 完成定义

只有以下条件全部满足，才能认为 Phase 1 完成：

1. `tools/build_plugin.py` 已落地
2. `dist/plugin/` 已能从 `.claude/` 构建生成
3. 文档已经统一把 `.claude/` 定义为真源
4. 文档已经统一把 `dist/plugin/` 定义为安装产物
5. 根级兼容目录仍保留，但被明确标记为迁移期资产
