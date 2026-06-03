---
description: Repository shipping compatibility command
argument-hint: [scope] [--auto-approve]
---

<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

按顺序交付当前变更：先审查，再校验，最后准备提交。

> Compatibility Note
>
> `/ship` 保留为当前仓库的交付兼容命令，用于审查、校验和提交准备。它不是 WorkflowProgram 面向 `TARGET_ROOT` 的主入口。
> 普通 workflow 请求统一从 `/workflowprogram-cn:workflowprogram-orchestrate <需求>` 进入。

## Usage

```text
/ship [<scope>] [--auto-approve]
```

**参数：**
- `<scope>`: 可选的变更范围（文件或目录）
- `--auto-approve`: 自动批准模式，跳过提交信息审批（用于 CI/CD）

**CI/CD 模式：**
设置环境变量 `CI=true` 或传入 `--auto-approve` 参数，提交门禁将自动放行。

**示例：**

```text
# 交互模式（默认）
/ship
/ship --all

# CI/CD 自动模式
/ship --auto-approve
CI=true /ship
```

## Stage 1: 预检查

**Goal**: 确认当前存在明确的交付范围。

1. 检查 git 仓库状态：
   ```bash
   git rev-parse --git-dir
   ```
   - 若返回非 0（非 git 仓库），输出：
     ```
     Error: Not a git repository.
     
     To fix this, choose one:
       1. Initialize new repo:  git init && git remote add origin <url>
       2. Clone existing repo:   git clone <url>
       3. Change to correct directory
     ```
     并停止。

2. 运行 `git status`，确认存在已暂存或未暂存变更。
3. 若提供了 `$ARGUMENTS`，据此缩小范围；否则默认覆盖当前全部变更。

**Verify**: 当前是 git 仓库，且至少存在一项需要交付的变更。

**On failure**：
- 非 git 仓库：输出上述指引并停止。
- 无变更：输出 `Nothing to ship.` 并停止。

## Stage 2: 代码审查 (Fan-out)

**Goal**: 收集当前 diff 的多维审查结果。

1. 通过 `git diff` 或 `git diff --cached` 获取差异。
2. 在单条 Task 消息中并行启动 4 个审查代理：
   - 安全审查
   - 性能审查
   - 风格审查
   - 逻辑审查
3. 所有子代理提示词必须完整内联，不能依赖外部 agent 文件。
4. 收集 JSON Lines 输出，并按 `critical -> warning -> info` 汇总。

**Verify**: 四条审查链路都返回了结构化结果或明确的“无问题”结论。

**On failure**：把审查失败记录到 `lessons.md` 并停止。

**Gate**：若出现任何 critical 级问题，必须先停下来让用户决定是修复还是强制继续。

## Stage 3: 运行校验

**Goal**: 确认仓库通过本次变更所需的分层门禁。

1. 默认运行 `python3 .claude/scripts/quality-gate.py commit`。
2. 如果变更涉及 runtime、runner、finalizer、schema、生成器、publish/package 或测试 harness，升级运行 `python3 .claude/scripts/quality-gate.py integration`。
3. 如果本次交付目标是发布 WorkflowProgram 插件版本，运行 `python3 .claude/scripts/quality-gate.py release`。
4. 若失败，分析失败原因并给出修复建议。
5. 在门禁未通过前不得继续准备提交。

**Verify**: 对应层级的 quality gate 成功退出。

**On failure**：展示失败原因并停止。

## Stage 4: 生成提交

**Goal**: 准备准确的提交信息并创建提交。

1. 如需暂存变更，先征求用户确认。
2. 分析当前变更范围并撰写 Conventional Commit 信息。
3. 将提交信息展示给用户审批。
4. 只有审批通过后才真正创建提交。

**自动批准模式**：若传入 `--auto-approve` 参数或环境变量 `CI=true` 存在，则跳过人工确认，使用生成的提交信息自动创建提交。

**Verify**: 用户已批准提交信息（或自动模式已启用），且 commit 成功。

**On failure**：在提交前停止，并说明阻塞点。

## Stage 5: 汇总

**Goal**: 输出简洁、可信的交付摘要。

输出：

- 按严重级别统计的审查摘要
- 校验状态
- 若已提交，则包含 commit hash 与 subject

**Verify**: 摘要内容与前面各阶段的实际结果一致。
