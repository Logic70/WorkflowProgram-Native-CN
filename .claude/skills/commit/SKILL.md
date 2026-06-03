---
name: commit
description: 为当前变更生成结构化的 Conventional Commit 提交信息
version: 1.0.0
disable-model-invocation: true
---

分析当前变更并生成一条结构清晰的 Conventional Commit 提交信息。

## Step 1: 获取变更

运行 `git diff --cached --stat` 查看已暂存变更。
如果没有已暂存内容，则运行 `git diff --stat` 查看未暂存变更，并询问用户是否要全部暂存。

## Step 2: 分析变更

阅读完整 diff，理解：

- 改了什么
- 为什么改
- 影响范围在哪个模块或工作流资产

## Step 3: 生成提交信息

格式：

```text
type(scope): subject

Body: 解释为什么改，而不是重复描述改了什么。
```

常见类型：

- `feat`
- `fix`
- `refactor`
- `docs`
- `test`
- `chore`
- `perf`
- `style`
- `ci`
- `build`

## Step 4: 运行提交门禁

在提交前运行：

```bash
python3 .claude/scripts/quality-gate.py commit
```

该门禁只做快速提交质量检查：`git diff --check`、核心 JSON 元数据解析、最小 spec fixture 和 YAML 模板 schema 校验。不要在普通提交前默认运行完整 smoke matrix；如果改动触及 runtime、runner、finalizer、schema、生成器或 publish 逻辑，再升级运行 `python3 .claude/scripts/quality-gate.py integration`。

## Step 5: 确认并提交

1. 展示生成的提交信息
2. 等待用户确认或修改
3. 使用确认后的内容执行 `git commit`

Target：`$ARGUMENTS`
