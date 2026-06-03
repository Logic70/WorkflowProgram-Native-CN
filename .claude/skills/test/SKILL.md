---
name: test
description: Run validation or tests for current changes
version: 1.0.0
disable-model-invocation: true
---

运行与当前变更相关的测试或验证命令，并在失败时分析原因。

默认使用分层门禁，不再把每次日常提交都升级成完整发布验证：

- `commit`：快速提交门禁，适合小改动提交前运行。
- `integration`：涉及 runtime、runner、finalizer、schema、生成器、publish 逻辑时运行。
- `release`：发布插件版本前运行，包含构建、版本一致性、完整仓库校验、插件 bootstrap 与 smoke matrix。

## Step 1: 识别变更文件

运行 `git diff --name-only $ARGUMENTS` 列出变更文件。
如果 `$ARGUMENTS` 为空，则默认使用未暂存变更。

## Step 2: 查找关联测试

针对每个变更文件查找可能的测试文件：

- 同目录下的 `test_<name>.*`
- 同目录下的 `<name>.test.*`
- 同目录下的 `<name>_test.*`
- `tests/` 或 `__tests__/` 中的对应文件

## Step 3: 运行测试或验证

- 如果存在明确关联测试，则优先运行关联测试
- 如果找不到，则默认运行 `python3 .claude/scripts/quality-gate.py commit`
- 如果改动涉及 `.claude/scripts/`、`tools/runtime_smoke*.py`、`tools/mock_runtime_host.py`、`validate-workflow-spec.py`、`generate-target-runtime.py`、`target-*runtime*.py`、`workflow-publish-entry.py` 或 publish/package 脚本，则运行 `python3 .claude/scripts/quality-gate.py integration`
- 如果本次目标是发布 WorkflowProgram 插件版本，则运行 `python3 .claude/scripts/quality-gate.py release`
- 允许透传额外参数

## Step 4: 分析结果

如果全部通过：

- 报告通过情况与测试数量

如果有失败：

- 展示失败输出
- 分析根因
- 给出可执行修复建议
