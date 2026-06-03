# Phase 1 Step 4 过渡链保留与文档收口计划

## 1. 目标

本步骤只做两件事：

1. 保留旧同步链，明确其为迁移期过渡方案。
2. 更新文档定位，使仓库说明与 Phase 1 目标一致。

本步骤不处理：

- skills-first 入口切换
- 动态验证
- 删除根级兼容目录
- plugin 安装方式的最终定案

## 2. 影响范围

- `README.md`
- `CLAUDE.md`
- `.claude-plugin/README.md`
- `tools/sync_plugin_assets.py`

## 3. 文件动作

### 3.1 更新

- `README.md`
  - 说明 `.claude/` 是源码层
  - 说明 `dist/plugin/` 是安装产物
  - 明确根级兼容目录是迁移期资产
  - 补充插件运行时模型和双轨安装说明

- `CLAUDE.md`
  - 说明 `.claude/` 是唯一真源
  - 说明 `dist/plugin/` 是唯一安装产物
  - 明确根级兼容目录为过渡层
  - 将构建命令改为 `python3 tools/build_plugin.py`

- `.claude-plugin/README.md`
  - 本地开发验证切换到 `dist/plugin/`
  - 区分开发安装和正式安装
  - 不再把根级兼容目录当正式插件运行目录

- `tools/sync_plugin_assets.py`
  - 更新头部说明
  - 明确它是过渡脚本，不是未来正式构建入口

## 4. 执行顺序

1. 新建本计划文档
2. 更新 `README.md`
3. 更新 `CLAUDE.md`
4. 更新 `.claude-plugin/README.md`
5. 更新 `tools/sync_plugin_assets.py` 注释说明
6. 复查文档和脚本定位是否一致

## 5. 风险点

- 文档可能仍旧混用“源码层”“兼容层”“安装产物层”三个概念
- README 和 CLAUDE 的职责边界可能继续重叠
- 旧脚本若不明确降级，后续仍会被误认为正式构建入口

## 6. 验证方式

- `README.md` 明确写出 `.claude/`、`dist/plugin/`、根级兼容目录的关系
- `CLAUDE.md` 的 Build 命令更新为 `python3 tools/build_plugin.py`
- `.claude-plugin/README.md` 的示例命令改为面向 `dist/plugin/`
- `tools/sync_plugin_assets.py` 顶部说明明确标记为 transitional
