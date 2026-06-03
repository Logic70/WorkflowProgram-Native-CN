---
description: Repository hotfix compatibility command
argument-hint: [description]
---

<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

以最小但必要的安全门禁快速处理热修复。

这个流程会跳过风格、性能与文档审查，只保留安全检查和校验作为硬门禁。

> Compatibility Note
>
> `/hotfix` 保留为当前仓库的维护兼容命令，用于热修复和快速交付。它不是 WorkflowProgram 面向 `TARGET_ROOT` 的主入口。
> 普通 workflow 请求统一从 `/workflowprogram-cn:workflowprogram-orchestrate <需求>` 进入。

## Usage

```text
/hotfix [<description>]
```

默认目标：当前所有变更。

## Stage 1: 创建热修复分支

**Goal**: 确保修复工作不直接落在 `main` 上。

1. 运行 `git branch --show-current`。
2. 若已经位于 `hotfix/*` 分支，则直接继续。
3. 若当前在 `main`，则创建并切换到 `hotfix/<description>`。

**Verify**: 当前工作分支不是 `main`，并且符合热修复分支命名。

**On failure**：停止并请求用户确认热修复描述。

## Stage 2: 安全检查

**Goal**: 确认当前 diff 中没有 critical 安全问题。

1. 启动一个安全审查任务，并内联完整提示词。
2. 重点检查注入、权限绕过、凭据泄露和内存安全问题。

**Verify**: 安全任务返回结构化结果或明确的“无问题”结论。

**On failure**：把任务失败情况记录到 `lessons.md` 并停止。

**Gate**：若出现 critical 安全问题，必须先停下来并要求修复。

## Stage 3: 运行关联校验

**Goal**: 确认热修复不会破坏仓库既有校验。

1. 通过 `git diff` 识别受影响文件。
2. 如项目具备关联测试，则优先运行相关测试。
3. 若没有明确的关联测试，则运行 `python3 .claude/scripts/quality-gate.py commit`。
4. 若热修复触及 runtime、runner、finalizer、schema、生成器、publish/package 或测试 harness，则升级运行 `python3 .claude/scripts/quality-gate.py integration`。

**Verify**: 校验通过后才能继续准备提交。

**On failure**：展示失败信息并停止。

## Stage 4: 快速提交

**Goal**: 生成并创建最小必要提交。

1. 暂存本次修复相关变更。
2. 生成 `fix(scope): subject` 形式的提交信息。
3. 向用户展示提交信息并等待批准。
4. 批准后再执行提交。

**Verify**: 提交信息已获批准，且 commit 创建成功。

**On failure**：在提交前停止，并说明原因。

## Stage 5: 汇总

**Goal**: 向用户汇报热修复当前状态。

输出：

- 当前分支名
- 安全检查状态
- 校验状态
- commit hash 与 subject

**Verify**: 汇总内容与执行结果一致。

Target：`$ARGUMENTS`
