---
name: doc
description: 为变更后的代码或工作流资产生成或更新文档
version: 1.0.0
disable-model-invocation: true
---

<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->


为 `$ARGUMENTS` 指定的目标生成或更新文档；若未指定，则默认处理当前变更。

## Step 1: 识别范围

如果 `$ARGUMENTS` 指向某个文件或模块，则以它为准。
否则运行 `git diff --name-only` 找出当前变更文件。

## Step 2: 分析文档需求

对每个变更文件检查：

- [ ] 公共函数或类是否需要文档说明
- [ ] 现有说明是否已过时
- [ ] 复杂逻辑是否需要解释原因的注释
- [ ] README 是否需要补充新的公共能力或使用方式
- [ ] 若存在 CHANGELOG，是否需要更新

## Step 3: 生成文档内容

对于缺失文档：

- 按项目约定补充 docstring 或说明文字
- 说明参数、返回值、异常或使用方式

对于 README：

- 更新功能说明
- 同步示例命令或路径

对于 CHANGELOG：

- 在 `Unreleased` 下补充本次用户可见变更

## Step 4: 应用变更

先向用户展示拟议修改，再在获得确认后落盘。

输出：按文件组织的文档更新摘要。
