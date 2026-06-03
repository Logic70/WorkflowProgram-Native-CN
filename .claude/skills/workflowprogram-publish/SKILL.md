---
name: workflowprogram-publish
description: Publish a completed WorkflowProgram-generated target workflow as a Claude Code marketplace plugin
version: 1.0.0
disable-model-invocation: true
---

把已经完整经过 `workflowprogram-develop` 的目标工作流发布成 Claude Code marketplace plugin。

这是独立环节：它只做发布资格检查、插件打包、包校验、GitHub 发布计划/执行和安装说明生成。若发现目标工作流本身需要修改，停止并要求用户回到 `workflowprogram-develop`，不得在 publish 流程里直接改设计、skill、command、agent 或 runtime 语义。

## Native Default Entry

默认解析插件绝对路径后调用：

```text
Workflow({
  scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-publish.js",
  args: { ... }
})
```

Native JS 拥有 Qualify、Package、Verify、Local Deliver 和 Optional External Apply 顺序。前台模型只按 `nextAction` 调用既有发布脚本和 `<PLUGIN_ROOT>/scripts/build-native-publish-evidence.py` 归一化 evidence，再重新调用同一 JS。默认只交付本地包；GitHub push 或 marketplace checkout 写入必须设置 `externalApplyApproved=true` 并通过显式审批 adapter。不得把 legacy `workflow-publish-entry.py` 作为第二套默认 runner。

## When To Use

- 用户说“把这个 workflow 发布成插件”
- 用户想让其他人通过 Claude Code `/plugin marketplace add` 和 `/plugin install` 安装目标工作流
- 目标项目已经存在 `TARGET_ROOT/.workflowprogram/design/`、`TARGET_ROOT/.workflowprogram/runtime/` 与 managed evidence

## Core Rules

- 只发布完整通过 `workflowprogram-develop` 的目标工作流。
- 默认要求最新 develop 的 S5 verdict 为 `PASS`；`WARN` 必须显式接受后才能继续。
- 发布依赖用户自己的 GitHub 账户；只调用本地 `gh` / `git`，不得存储 token。
- 先把插件 payload 写到 `RUN_ROOT/outputs/stages/publish/package-root/`，校验通过后才允许写入发布仓库。
- 默认使用 `export_repo`，避免把应用源码仓误当成插件 marketplace 仓库。
- 若用户要把 workflow 加入已有 marketplace，使用 `existing_marketplace`；该模式必须读取已有 `.claude-plugin/marketplace.json`，并把插件 payload 放入 `plugins/<plugin-id>/`。
- 已有 marketplace 中同名插件不得静默覆盖；只有用户显式选择更新且版本提升时才可继续。
- 运行态打包模式必须明确：
  - `workflowprogram_dependency`：消费者需要先安装 WorkflowProgram 插件。
  - `vendored_runtime`：发布包携带经过校验的最小 runtime。
- 若包校验发现目标 workflow 需要语义调整，停止并让用户运行 `workflowprogram-develop` 的 change-policy 修改流。

## Step 1: Confirm Publish Context

确认以下信息：

- `TARGET_ROOT`
- 插件 ID，例如 `stride-security-workflow`
- 插件显示名
- GitHub 仓库，例如 `owner/stride-security-workflow`
- 版本号，例如 `0.1.0`
- 仓库模式：默认 `export_repo`
- 若复用已有 marketplace，还需确认 checkout 路径、manifest 名称，以及是否允许更新同名 plugin
- runtime 模式：默认 `workflowprogram_dependency`

缺少 GitHub 登录或仓库权限时，不要尝试绕过；输出 remediation，让用户先完成 `gh auth login` 或仓库授权。

## Step 2: Run Deterministic Publish Entry

调用：

```bash
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflow-publish-entry.py run \
  --target-root <TARGET_ROOT> \
  --run-root <RUN_ROOT> \
  --plugin-id <plugin-id> \
  --plugin-name "<display-name>" \
  --version <version> \
  --repository <github-repo-or-url> \
  --repo-mode export_repo \
  --runtime-mode workflowprogram_dependency \
  --json
```

如果只是预演，不执行 GitHub push：

```bash
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflow-publish-entry.py run \
  --target-root <TARGET_ROOT> \
  --run-root <RUN_ROOT> \
  --plugin-id <plugin-id> \
  --version <version> \
  --repository <github-repo-or-url> \
  --dry-run \
  --skip-claude-validate \
  --json
```

执行真实 GitHub 写入必须显式审批：

```bash
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflow-publish-entry.py run \
  --target-root <TARGET_ROOT> \
  --run-root <RUN_ROOT> \
  --plugin-id <plugin-id> \
  --version <version> \
  --repository <github-repo-or-url> \
  --repo-path <local-publish-checkout> \
  --execute-github \
  --approve-github \
  --json
```

若要加入已有 marketplace：

```bash
workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/workflow-publish-entry.py run \
  --target-root <TARGET_ROOT> \
  --run-root <RUN_ROOT> \
  --plugin-id <plugin-id> \
  --version <version> \
  --repository <github-repo-or-url> \
  --repo-mode existing_marketplace \
  --repo-path <existing-marketplace-checkout> \
  --marketplace-name <existing-marketplace-name> \
  --dry-run \
  --json
```

## Step 3: Inspect Evidence

发布证据固定在：

- `RUN_ROOT/outputs/stages/publish/publish-eligibility.json`
- `RUN_ROOT/outputs/stages/publish/plugin-package-plan.json`
- `RUN_ROOT/outputs/stages/publish/plugin-manifest-preview.json`
- `RUN_ROOT/outputs/stages/publish/plugin-validation-report.json`
- `RUN_ROOT/outputs/stages/publish/marketplace-resolution.json`
- `RUN_ROOT/outputs/stages/publish/marketplace-merge-plan.json`
- `RUN_ROOT/outputs/stages/publish/marketplace-manifest-preview.json`
- `RUN_ROOT/outputs/stages/publish/marketplace-validation-report.json`
- `RUN_ROOT/outputs/stages/publish/github-publish-plan.json`
- `RUN_ROOT/outputs/stages/publish/github-publish-result.json`
- `RUN_ROOT/outputs/stages/publish/install-instructions.md`
- `RUN_ROOT/outputs/stages/publish/publish-summary.json`

## Output

输出应包含：

- 发布状态：`PASS`、`BLOCKED` 或 `FAIL`
- 插件 ID、版本、GitHub 仓库
- runtime 打包模式
- 包校验结论
- GitHub 发布结论或阻塞原因
- 安装命令位置：`install-instructions.md`
