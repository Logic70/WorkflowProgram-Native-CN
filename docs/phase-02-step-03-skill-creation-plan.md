# Phase 2 Step 3 新增 Skills 落地计划

## 1. 目标

本步骤只落地一件事：创建新的 `workflowprogram-*` 主入口 skills，并让源码层能够引用它们。

本步骤不处理：

- 旧 commands 的兼容降级文案
- README / CLAUDE / 插件说明更新
- 校验脚本更新
- 动态验证

## 2. 影响范围

- `.claude/skills/workflowprogram-orchestrate/SKILL.md`
- `.claude/skills/workflowprogram-develop/SKILL.md`
- `.claude/skills/workflowprogram-audit/SKILL.md`
- `.claude/skills/workflowprogram-iterate/SKILL.md`
- `.claude/skills/workflowprogram-validate/SKILL.md`
- `.claude/settings.json`

## 3. 文件动作

### 3.1 新建

- `workflowprogram-orchestrate`
- `workflowprogram-develop`
- `workflowprogram-audit`
- `workflowprogram-iterate`
- `workflowprogram-validate`

### 3.2 更新

- `.claude/settings.json`
  - 先只新增 skill 注册
  - 暂不调整旧 commands 说明

## 4. 落地要求

每个新 skill 必须：

1. 具备完整 frontmatter
2. 明确自己是面向 `TARGET_ROOT` 的主入口
3. 显式说明 `PLUGIN_ROOT` 只读、`TARGET_ROOT` 可写
4. 明确调用哪些底层 skills 或支持资产
5. 不直接把仓库维护命令包装成主能力

## 5. 执行顺序

1. 创建 5 个 skill 目录
2. 写入 5 个 `SKILL.md`
3. 更新 `.claude/settings.json`
4. 运行源码层校验
5. 复跑 `tools/build_plugin.py`

## 6. 风险点

- 新 skill 文案仍带旧 command 语气，导致双主入口
- `workflowprogram-validate` 与 `preflight` 文案重叠
- settings 注册遗漏或路径错误

## 7. 验证方式

- `python3 .claude/scripts/validate-workflow.py`
- `python3 tools/build_plugin.py`
- `dist/plugin/skills/` 中出现 5 个新 skill 目录
